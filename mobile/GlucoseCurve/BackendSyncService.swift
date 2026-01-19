//
//  BackendSyncService.swift
//  GlucoseCurve
//
//  Created by Surya Gobi on 12/25/25.
//

import Foundation

struct SyncPayload: Codable {
    let device: String
    let notes: String?

    let egv_readings: [EGVDTO]
    let workouts: [WorkoutDTO]
    let weight_readings: [WeightDTO]

    let meal_events: [MealEventDTO]
    let medication_events: [MedicationEventDTO]
}

// You likely already have these DTOs for meal/med:
struct MealEventDTO: Codable { /* your existing */ }
struct MedicationEventDTO: Codable { /* your existing */ }

final class BackendSyncService {
    let baseURL: URL

    init(baseURL: URL) {
        self.baseURL = baseURL
    }

    func sync(payload: SyncPayload) async throws -> Data {
        var req = URLRequest(url: baseURL.appendingPathComponent("/api/sync/"))
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")

        let body = try JSONEncoder().encode(payload)
        req.httpBody = body

        let (data, resp) = try await URLSession.shared.data(for: req)
        guard let http = resp as? HTTPURLResponse, (200...299).contains(http.statusCode) else {
            let text = String(data: data, encoding: .utf8) ?? ""
            throw NSError(domain: "BackendSync", code: 1, userInfo: [NSLocalizedDescriptionKey: "Sync failed: \(text)"])
        }
        return data
    }
}
