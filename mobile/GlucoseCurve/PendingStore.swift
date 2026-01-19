import Foundation
import Combine

@MainActor
final class PendingStore: ObservableObject {
    @Published var pendingMeals: [PendingMealEvent] = []
    @Published var pendingMeds: [PendingMedicationEvent] = []
    @Published var pendingExercises: [PendingExerciseSet] = [] // Already present

    private let mealsFile = "pending_meals.json"
    private let medsFile = "pending_meds.json"
    private let exercisesFile = "pending_exercises.json" // 1. Added filename constant

    init() {
        load()
    }

    func addMeal(_ meal: PendingMealEvent) {
        pendingMeals.append(meal)
        save()
    }

    func addMed(_ med: PendingMedicationEvent) {
        pendingMeds.append(med)
        save()
    }

    func addExercise(_ ex: PendingExerciseSet) {
        pendingExercises.append(ex)
        save()
    }

    func clearAll() {
        pendingMeals.removeAll()
        pendingMeds.removeAll()
        pendingExercises.removeAll() // 2. Ensure exercises are cleared after sync
        save()
    }

    private func docsURL(_ filename: String) -> URL {
        FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
            .appendingPathComponent(filename)
    }

    private func load() {
        pendingMeals = loadFile(mealsFile) ?? []
        pendingMeds = loadFile(medsFile) ?? []
        pendingExercises = loadFile(exercisesFile) ?? [] // 3. Load saved exercises
    }

    private func save() {
        saveFile(mealsFile, pendingMeals)
        saveFile(medsFile, pendingMeds)
        saveFile(exercisesFile, pendingExercises) // 4. Save exercises to disk
    }

    private func loadFile<T: Decodable>(_ filename: String) -> T? {
        let url = docsURL(filename)
        guard let data = try? Data(contentsOf: url) else { return nil }
        return try? JSONDecoder().decode(T.self, from: data)
    }

    private func saveFile<T: Encodable>(_ filename: String, _ value: T) {
        let url = docsURL(filename)
        guard let data = try? JSONEncoder().encode(value) else { return }
        try? data.write(to: url, options: [.atomic])
    }
}
