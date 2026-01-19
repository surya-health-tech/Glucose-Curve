import Foundation
import HealthKit
import Combine

@MainActor
final class HealthKitSyncManager: ObservableObject {
    private let store = HKHealthStore()

    /// Used to fetch deltas from HealthKit
    private let lastSyncKey = "last_healthkit_sync_at"

    /// ISO8601 formatter used for backend timestamps
    private let iso: ISO8601DateFormatter = {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return f
    }()

    // MARK: - Public API

    func getLastSyncDate() -> Date {
        if let t = UserDefaults.standard.object(forKey: lastSyncKey) as? Date {
            return t
        }
        // If never synced, pull last 7 days
        return Calendar.current.date(byAdding: .day, value: -7, to: Date()) ?? Date(timeIntervalSince1970: 0)
    }

    func markSuccessfulSyncNow() {
        UserDefaults.standard.set(Date(), forKey: lastSyncKey)
    }

    func requestAuthorizationIfNeeded() async throws {
        guard HKHealthStore.isHealthDataAvailable() else { return }

        let readTypes: Set<HKObjectType> = [
            HKObjectType.quantityType(forIdentifier: .bloodGlucose)!,
            HKObjectType.quantityType(forIdentifier: .bodyMass)!,
            HKObjectType.workoutType(),
            HKObjectType.quantityType(forIdentifier: .heartRate)!,
            HKObjectType.quantityType(forIdentifier: .activeEnergyBurned)!,
            HKObjectType.quantityType(forIdentifier: .distanceWalkingRunning)!,
            HKObjectType.quantityType(forIdentifier: .distanceCycling)!,
            HKObjectType.categoryType(forIdentifier: .sleepAnalysis)!,
            HKObjectType.quantityType(forIdentifier: .heartRateVariabilitySDNN)!
        ]

        try await store.requestAuthorization(toShare: [], read: readTypes)
    }

    func fetchHealthKitDeltaPayload() async throws -> (
        egvs: [[String: Any]],
        workouts: [[String: Any]],
        weights: [[String: Any]],
        sleep: [[String: Any]],
        metrics: [[String: Any]]
    ) {
        let since = getLastSyncDate()

        // Run all fetches in parallel
        async let egvs = fetchEGVs(since: since)
        async let wts  = fetchWeights(since: since)
        async let wos  = fetchWorkouts(since: since, limit: 200)
        async let sleep = fetchSleep(since: since)
        async let metrics = fetchHRV(since: since)

        return try await (egvs, wos, wts, sleep, metrics)
    }
    
    
    // MARK: - Sleep Fetching
    private func fetchSleep(since: Date) async throws -> [[String: Any]] {
        let type = HKObjectType.categoryType(forIdentifier: .sleepAnalysis)!
        let predicate = HKQuery.predicateForSamples(withStart: since, end: Date(), options: .strictStartDate)
        
        // Pass 'nil' for sort and a number for limit to fix the error
        //let samples = try await sampleQuery(type: type, predicate: predicate, sort: nil, limit: 1000)
        
        print("Executing Sleep Query since \(since)...")
            let samples = try await sampleQuery(type: type, predicate: predicate, sort: nil, limit: 1000)
            print("Found \(samples.count) sleep samples.") // Check if this prints
        
        return samples.compactMap { s -> [String: Any]? in
            guard let sample = s as? HKCategorySample else { return nil }
            
            let stage: String
            switch sample.value {
            case HKCategoryValueSleepAnalysis.asleepDeep.rawValue: stage = "deep"
            case HKCategoryValueSleepAnalysis.asleepREM.rawValue:  stage = "rem"
            case HKCategoryValueSleepAnalysis.asleepCore.rawValue: stage = "core"
            default: stage = "asleep"
            }
            
            return [
                "start_at": iso.string(from: sample.startDate),
                "end_at": iso.string(from: sample.endDate),
                "stage": stage,
                "source": "healthkit",
                "source_id": sample.uuid.uuidString
            ]
        }
    }

    // MARK: - Health Metrics (HRV) Fetching
    private func fetchHRV(since: Date) async throws -> [[String: Any]] {
        let type = HKQuantityType.quantityType(forIdentifier: .heartRateVariabilitySDNN)!
        let predicate = HKQuery.predicateForSamples(withStart: since, end: Date(), options: .strictStartDate)
        
        print("Executing Health Metrics Query since \(since)...")
        
        // Pass 'nil' for sort and a number for limit to fix the error
        let samples = try await sampleQuery(type: type, predicate: predicate, sort: nil, limit: 1000)
        
        print("Found \(samples.count) Health Metrics.") // Check if this prints
        
        return samples.compactMap { s -> [String: Any]? in
            guard let sample = s as? HKQuantitySample else { return nil }
            
            let value = sample.quantity.doubleValue(for: .secondUnit(with: .milli))
            
            return [
                "measured_at": iso.string(from: sample.startDate),
                "metric_type": "HRV",
                "value": value,
                "unit": "ms",
                "source": "healthkit",
                "source_id": sample.uuid.uuidString
            ]
        }
    }

    // MARK: - EGV (blood glucose)

    private func fetchEGVs(since: Date) async throws -> [[String: Any]] {
        let type = HKQuantityType.quantityType(forIdentifier: .bloodGlucose)!
        let pred = HKQuery.predicateForSamples(withStart: since, end: Date(), options: .strictStartDate)
        let sort = NSSortDescriptor(key: HKSampleSortIdentifierStartDate, ascending: true)

        let samples: [HKQuantitySample] = try await sampleQuery(type: type, predicate: pred, sort: [sort], limit: HKObjectQueryNoLimit)

        let mgdlUnit = HKUnit(from: "mg/dL")
        let mmolUnit = HKUnit(from: "mmol/L")

        return samples.map { s in
            // Some sources store mg/dL, others mmol/L → try both safely
            let mgdl: Double
            do {
                mgdl = s.quantity.doubleValue(for: mgdlUnit)
            } catch {
                let mmol = s.quantity.doubleValue(for: mmolUnit)
                mgdl = mmol * 18.0
            }

            return [
                "measured_at": iso.string(from: s.startDate),
                "glucose_mgdl": String(format: "%.2f", mgdl),
                "source": "healthkit",
                "source_id": s.uuid.uuidString
            ]
        }
    }

    // MARK: - Weight

    private func fetchWeights(since: Date) async throws -> [[String: Any]] {
        let type = HKQuantityType.quantityType(forIdentifier: .bodyMass)!
        let pred = HKQuery.predicateForSamples(withStart: since, end: Date(), options: .strictStartDate)
        let sort = NSSortDescriptor(key: HKSampleSortIdentifierStartDate, ascending: true)

        let samples: [HKQuantitySample] = try await sampleQuery(type: type, predicate: pred, sort: [sort], limit: HKObjectQueryNoLimit)

        let kg = HKUnit.gramUnit(with: .kilo)

        return samples.map { s in
            let val = s.quantity.doubleValue(for: kg)
            return [
                "measured_at": iso.string(from: s.startDate),
                "weight_kg": String(format: "%.3f", val),
                "source": "healthkit",
                "source_id": s.uuid.uuidString
            ]
        }
    }

    // MARK: - Workouts (summary + avg HR + active kcal + distance)

    private func fetchWorkouts(since: Date, limit: Int) async throws -> [[String: Any]] {
        let type = HKObjectType.workoutType()
        let pred = HKQuery.predicateForSamples(withStart: since, end: Date(), options: .strictStartDate)
        let sort = NSSortDescriptor(key: HKSampleSortIdentifierStartDate, ascending: false)

        let workouts: [HKWorkout] = try await workoutQuery(predicate: pred, sort: [sort], limit: limit)

        var out: [[String: Any]] = []
        out.reserveCapacity(workouts.count)

        for w in workouts {
            async let avgHR = averageHeartRate(start: w.startDate, end: w.endDate)
            async let kcal  = activeEnergyKcal(start: w.startDate, end: w.endDate)
            async let miles = distanceMiles(workout: w)

            let activity = mapWorkoutType(w.workoutActivityType)

            out.append([
                "start_at": iso.string(from: w.startDate),
                "end_at": iso.string(from: w.endDate),
                "activity_type": activity,
                "duration_min": String(format: "%.2f", w.duration / 60.0),
                "distance_miles": (try await miles).map { String(format: "%.3f", $0) } as Any,
                "avg_hr_bpm": (try await avgHR).map { String(format: "%.2f", $0) } as Any,
                "active_energy_kcal": (try await kcal).map { String(format: "%.2f", $0) } as Any,
                "source": "healthkit",
                "source_id": w.uuid.uuidString
            ])
        }

        return out
    }

    private func averageHeartRate(start: Date, end: Date) async throws -> Double? {
        let type = HKQuantityType.quantityType(forIdentifier: .heartRate)!
        let pred = HKQuery.predicateForSamples(withStart: start, end: end, options: .strictStartDate)

        return try await statisticsQuery(
            type: type,
            predicate: pred,
            options: .discreteAverage,
            unit: HKUnit(from: "count/min")
        )
    }

    private func activeEnergyKcal(start: Date, end: Date) async throws -> Double? {
        let type = HKQuantityType.quantityType(forIdentifier: .activeEnergyBurned)!
        let pred = HKQuery.predicateForSamples(withStart: start, end: end, options: .strictStartDate)

        return try await statisticsQuery(
            type: type,
            predicate: pred,
            options: .cumulativeSum,
            unit: .kilocalorie()
        )
    }

    private func distanceMiles(workout: HKWorkout) async throws -> Double? {
        // If the workout provides totalDistance, use it.
        if let td = workout.totalDistance {
            return td.doubleValue(for: .mile())
        }

        // Fallback: derive by activity type via statistics.
        let qType: HKQuantityType? = {
            switch workout.workoutActivityType {
            case .running, .walking, .hiking:
                return HKQuantityType.quantityType(forIdentifier: .distanceWalkingRunning)
            case .cycling:
                return HKQuantityType.quantityType(forIdentifier: .distanceCycling)
            default:
                return nil
            }
        }()

        guard let qt = qType else { return nil }

        let pred = HKQuery.predicateForSamples(withStart: workout.startDate, end: workout.endDate, options: .strictStartDate)
        return try await statisticsQuery(type: qt, predicate: pred, options: .cumulativeSum, unit: .mile())
    }

    private func mapWorkoutType(_ t: HKWorkoutActivityType) -> String {
        switch t {
        case .running: return "running"
        case .walking: return "walking"
        case .hiking: return "hiking"
        case .cycling: return "cycling"
        case .traditionalStrengthTraining: return "strength"
        case .highIntensityIntervalTraining: return "hiit"
        case .swimming: return "swimming"
        default: return "other"
        }
    }

    // MARK: - Async HealthKit helpers

    private func sampleQuery<T: HKSample>(
        type: HKSampleType,
        predicate: NSPredicate?,
        sort: [NSSortDescriptor]?,
        limit: Int
    ) async throws -> [T] {
        try await withCheckedThrowingContinuation { cont in
            let q = HKSampleQuery(sampleType: type, predicate: predicate, limit: limit, sortDescriptors: sort) { _, samples, error in
                if let error = error {
                    cont.resume(throwing: error)
                    return
                }
                // Always resume, even if samples is nil
                cont.resume(returning: (samples as? [T]) ?? [])
            }
            store.execute(q)
        }
    }

    private func workoutQuery(predicate: NSPredicate?, sort: [NSSortDescriptor]?, limit: Int) async throws -> [HKWorkout] {
        let type = HKObjectType.workoutType()
        return try await sampleQuery(type: type, predicate: predicate, sort: sort, limit: limit)
    }

    private func statisticsQuery(
        type: HKQuantityType,
        predicate: NSPredicate?,
        options: HKStatisticsOptions,
        unit: HKUnit
    ) async throws -> Double? {
        try await withCheckedThrowingContinuation { cont in
            let q = HKStatisticsQuery(quantityType: type, quantitySamplePredicate: predicate, options: options) { _, stats, error in
                if let error = error { cont.resume(throwing: error); return }

                switch options {
                case .cumulativeSum:
                    let v = stats?.sumQuantity()?.doubleValue(for: unit)
                    cont.resume(returning: v)
                case .discreteAverage:
                    let v = stats?.averageQuantity()?.doubleValue(for: unit)
                    cont.resume(returning: v)
                default:
                    cont.resume(returning: nil)
                }
            }
            store.execute(q)
        }
    }
}
