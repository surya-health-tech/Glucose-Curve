//
//  HealthKitSyncService.swift
//  GlucoseCurve
//
//  Created by Surya Gobi on 12/25/25.
//

import Foundation
import HealthKit

struct EGVDTO: Codable {
    let measured_at: String
    let glucose_mgdl: Double
    let source: String
    let source_id: String
}

struct WeightDTO: Codable {
    let measured_at: String
    let weight_kg: Double
    let source: String
    let source_id: String
    let notes: String?
}

struct WorkoutDTO: Codable {
    let start_at: String
    let end_at: String
    let activity_type: String
    let duration_min: Double
    let distance_miles: Double?
    let avg_hr_bpm: Double?
    let active_energy_kcal: Double?
    let source: String
    let source_id: String
}

@MainActor
final class HealthKitSyncService {
    private let healthStore = HKHealthStore()
    private let iso = ISO8601DateFormatter()

    // Types
    private var glucoseType: HKQuantityType { HKQuantityType(.bloodGlucose) }
    private var bodyMassType: HKQuantityType { HKQuantityType(.bodyMass) }
    private var workoutType: HKWorkoutType { .workoutType() }
    private var heartRateType: HKQuantityType { HKQuantityType(.heartRate) }
    private var activeEnergyType: HKQuantityType { HKQuantityType(.activeEnergyBurned) }

    // Distance types (we’ll query by workout type)
    private var distWalkRunType: HKQuantityType { HKQuantityType(.distanceWalkingRunning) }
    private var distCyclingType: HKQuantityType { HKQuantityType(.distanceCycling) }
    private var distSwimType: HKQuantityType { HKQuantityType(.distanceSwimming) }

    // Call once (you likely already do this elsewhere)
    func requestAuthorization() async throws {
        guard HKHealthStore.isHealthDataAvailable() else { return }
        let readTypes: Set<HKObjectType> = [
            glucoseType, bodyMassType, workoutType, heartRateType, activeEnergyType,
            distWalkRunType, distCyclingType, distSwimType
        ]
        try await healthStore.requestAuthorization(toShare: [], read: readTypes)
    }

    // MARK: - Public: fetch all since date
    func fetchSince(_ since: Date) async throws -> (egvs: [EGVDTO], weights: [WeightDTO], workouts: [WorkoutDTO]) {
        async let egvs = fetchEGVsSince(since)
        async let weights = fetchWeightsSince(since)
        async let workouts = fetchWorkoutsSince(since)
        return try await (egvs, weights, workouts)
    }

    // MARK: - EGV
    private func fetchEGVsSince(_ since: Date) async throws -> [EGVDTO] {
        let predicate = HKQuery.predicateForSamples(withStart: since, end: Date(), options: .strictStartDate)
        let sort = [NSSortDescriptor(key: HKSampleSortIdentifierStartDate, ascending: true)]

        let samples: [HKQuantitySample] = try await sampleQuery(quantityType: glucoseType, predicate: predicate, sort: sort)

        let mgdlUnit = HKUnit(from: "mg/dL")
        let mmolUnit = HKUnit(from: "mmol/L")

        return samples.compactMap { s in
            let sourceID = s.uuid.uuidString

            // Normalize to mg/dL safely
            let mgdl: Double
            do {
                mgdl = s.quantity.doubleValue(for: mgdlUnit)
            } catch {
                let mmol = s.quantity.doubleValue(for: mmolUnit)
                mgdl = mmol * 18.0
            }

            return EGVDTO(
                measured_at: iso.string(from: s.startDate),
                glucose_mgdl: mgdl,
                source: "healthkit",
                source_id: sourceID
            )
        }
    }

    // MARK: - Weight
    private func fetchWeightsSince(_ since: Date) async throws -> [WeightDTO] {
        let predicate = HKQuery.predicateForSamples(withStart: since, end: Date(), options: .strictStartDate)
        let sort = [NSSortDescriptor(key: HKSampleSortIdentifierStartDate, ascending: true)]

        let samples: [HKQuantitySample] = try await sampleQuery(quantityType: bodyMassType, predicate: predicate, sort: sort)
        let kgUnit = HKUnit.gramUnit(with: .kilo)

        return samples.map { s in
            WeightDTO(
                measured_at: iso.string(from: s.startDate),
                weight_kg: s.quantity.doubleValue(for: kgUnit),
                source: "healthkit",
                source_id: s.uuid.uuidString,
                notes: nil
            )
        }
    }

    // MARK: - Workouts
    private func fetchWorkoutsSince(_ since: Date) async throws -> [WorkoutDTO] {
        let predicate = HKQuery.predicateForSamples(withStart: since, end: Date(), options: .strictStartDate)
        let sort = [NSSortDescriptor(key: HKSampleSortIdentifierStartDate, ascending: false)]

        let workouts: [HKWorkout] = try await workoutQuery(predicate: predicate, sort: sort)

        // enrich each workout with avg HR + active energy + distance
        var out: [WorkoutDTO] = []
        out.reserveCapacity(workouts.count)

        for w in workouts {
            async let avgHR = fetchAverageHeartRate(start: w.startDate, end: w.endDate)
            async let kcal = fetchActiveEnergy(start: w.startDate, end: w.endDate)
            async let miles = fetchDistanceMiles(for: w)

            out.append(
                WorkoutDTO(
                    start_at: iso.string(from: w.startDate),
                    end_at: iso.string(from: w.endDate),
                    activity_type: w.workoutActivityType.backendName,
                    duration_min: w.duration / 60.0,
                    distance_miles: try await miles,
                    avg_hr_bpm: try await avgHR,
                    active_energy_kcal: try await kcal,
                    source: "healthkit",
                    source_id: w.uuid.uuidString
                )
            )
        }
        return out
    }

    // Avg HR
    private func fetchAverageHeartRate(start: Date, end: Date) async throws -> Double? {
        let predicate = HKQuery.predicateForSamples(withStart: start, end: end, options: .strictStartDate)

        return try await withCheckedThrowingContinuation { (cont: CheckedContinuation<Double?, Error>) in
            let q = HKStatisticsQuery(
                quantityType: heartRateType,
                quantitySamplePredicate: predicate,
                options: .discreteAverage
            ) { _, result, error in
                if let error = error { cont.resume(throwing: error); return }
                let bpm = result?.averageQuantity()?.doubleValue(for: HKUnit(from: "count/min"))
                cont.resume(returning: bpm)
            }
            healthStore.execute(q)
        }
    }

    // Active energy
    private func fetchActiveEnergy(start: Date, end: Date) async throws -> Double? {
        let predicate = HKQuery.predicateForSamples(withStart: start, end: end, options: .strictStartDate)

        return try await withCheckedThrowingContinuation { (cont: CheckedContinuation<Double?, Error>) in
            let q = HKStatisticsQuery(
                quantityType: activeEnergyType,
                quantitySamplePredicate: predicate,
                options: .cumulativeSum
            ) { _, result, error in
                if let error = error { cont.resume(throwing: error); return }
                let kcal = result?.sumQuantity()?.doubleValue(for: .kilocalorie())
                cont.resume(returning: kcal)
            }
            healthStore.execute(q)
        }
    }

    // Distance miles (best-effort by type)
    private func fetchDistanceMiles(for workout: HKWorkout) async throws -> Double? {
        let start = workout.startDate
        let end = workout.endDate

        let type: HKQuantityType = {
            switch workout.workoutActivityType {
            case .running, .walking, .hiking:
                return distWalkRunType
            case .cycling:
                return distCyclingType
            case .swimming:
                return distSwimType
            default:
                return distWalkRunType
            }
        }()

        let predicate = HKQuery.predicateForSamples(withStart: start, end: end, options: .strictStartDate)

        let meters: Double? = try await withCheckedThrowingContinuation { (cont: CheckedContinuation<Double?, Error>) in
            let q = HKStatisticsQuery(
                quantityType: type,
                quantitySamplePredicate: predicate,
                options: .cumulativeSum
            ) { _, result, error in
                if let error = error { cont.resume(throwing: error); return }
                let m = result?.sumQuantity()?.doubleValue(for: .meter())
                cont.resume(returning: m)
            }
            healthStore.execute(q)
        }

        guard let meters else { return nil }
        return meters / 1609.344
    }

    // MARK: - Query helpers
    private func sampleQuery(
        quantityType: HKQuantityType,
        predicate: NSPredicate?,
        sort: [NSSortDescriptor]
    ) async throws -> [HKQuantitySample] {
        try await withCheckedThrowingContinuation { (cont: CheckedContinuation<[HKQuantitySample], Error>) in
            let q = HKSampleQuery(
                sampleType: quantityType,
                predicate: predicate,
                limit: HKObjectQueryNoLimit,
                sortDescriptors: sort
            ) { _, samples, error in
                if let error = error { cont.resume(throwing: error); return }
                cont.resume(returning: samples as? [HKQuantitySample] ?? [])
            }
            healthStore.execute(q)
        }
    }

    private func workoutQuery(predicate: NSPredicate?, sort: [NSSortDescriptor]) async throws -> [HKWorkout] {
        try await withCheckedThrowingContinuation { (cont: CheckedContinuation<[HKWorkout], Error>) in
            let q = HKSampleQuery(
                sampleType: workoutType,
                predicate: predicate,
                limit: HKObjectQueryNoLimit,
                sortDescriptors: sort
            ) { _, samples, error in
                if let error = error { cont.resume(throwing: error); return }
                cont.resume(returning: samples as? [HKWorkout] ?? [])
            }
            healthStore.execute(q)
        }
    }
}

// Workout type mapping to your backend strings
private extension HKWorkoutActivityType {
    var backendName: String {
        switch self {
        case .running: return "running"
        case .walking: return "walking"
        case .hiking: return "hiking"
        case .traditionalStrengthTraining: return "strength"
        case .highIntensityIntervalTraining: return "hiit"
        case .cycling: return "cycling"
        case .swimming: return "swimming"
        default: return "other"
        }
    }
}
