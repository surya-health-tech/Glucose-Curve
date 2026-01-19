import Foundation

// Keep your APIError enum as is
enum APIError: Error {
    case badURL
    case badResponse(Int)
    case invalidJSON
    case decodingError
}

final class APIClient {
    static let shared = APIClient()
    var baseURL: String = "http://192.168.1.18:8000"

    private init() {}

    // MARK: - GET Meal Templates
    func getMealTemplates() async throws -> [MealTemplate] {
        guard let url = URL(string: "\(baseURL)/api/meal-templates/") else { throw APIError.badURL }
        let (data, _) = try await URLSession.shared.data(for: URLRequest(url: url))
        
        // Uses MealTemplateResponse from Models.swift
        let decoded = try JSONDecoder().decode(MealTemplateResponse.self, from: data)
        return decoded.meal_templates
    }

    // MARK: - GET Medication Options
    // This is the function AddMedication.swift is looking for
    func getMedicationOptions() async throws -> [MedicationOption] {
        guard let url = URL(string: "\(baseURL)/api/medication-options/") else { throw APIError.badURL }
        
        let (data, resp) = try await URLSession.shared.data(from: url)
        
        guard let http = resp as? HTTPURLResponse else { throw APIError.invalidJSON }
        guard (200..<300).contains(http.statusCode) else { throw APIError.badResponse(http.statusCode) }

        // Uses MedicationOptionsResponse from Models.swift
        let env = try JSONDecoder().decode(MedicationOptionsResponse.self, from: data)
        return env.medication_options
    }
    
    func getExerciseTemplates() async throws -> [ExerciseTemplate] {
        guard let url = URL(string: "\(baseURL)/api/exercise-templates/") else { throw APIError.badURL }
        let (data, _) = try await URLSession.shared.data(from: url)
        let decoded = try JSONDecoder().decode(ExerciseTemplateResponse.self, from: data)
        return decoded.exercise_templates
    }

    // MARK: - POST Sync
    func sync(payload: [String: Any]) async throws -> [String: Any] {
        guard let url = URL(string: "\(baseURL)/api/sync/") else { throw APIError.badURL }

        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = try JSONSerialization.data(withJSONObject: payload, options: [])

        let (data, resp) = try await URLSession.shared.data(for: req)
        guard let http = resp as? HTTPURLResponse else { throw APIError.invalidJSON }
        guard (200..<300).contains(http.statusCode) else { throw APIError.badResponse(http.statusCode) }

        let obj = try JSONSerialization.jsonObject(with: data, options: [])
        guard let dict = obj as? [String: Any] else { throw APIError.invalidJSON }
        return dict
    }
}
