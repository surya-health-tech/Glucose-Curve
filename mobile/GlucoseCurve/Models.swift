//
//  Untitled.swift
//  GlucoseCurve
//
//  Created by Surya Gobi on 12/24/25.
//

import Foundation

struct MealTemplateResponse: Codable {
    let ok: Bool
    let meal_templates: [MealTemplate]
}

struct MealTemplate: Codable, Identifiable {
    let id: Int
    let name: String
    let notes: String?
    let updated_at: String?
    let items: [MealTemplateItem]
}

struct MealTemplateItem: Codable, Identifiable {
    let id: Int
    let food_item_id: Int
    let food_item_name: String
    let grams: String
    let sort_order: Int
}

struct MedicationOptionsResponse: Codable {
    let ok: Bool
    let medication_options: [MedicationOption]
}

struct MedicationOption: Codable, Identifiable {
    let id: Int
    let name: String
    let dose_mg: Int
    let label: String
    let notes: String?
}

// Local (pending) events stored on phone
struct PendingMealEvent: Codable, Identifiable {
    let id: UUID
    var eatenAtISO: String
    var mealTemplateId: Int
    var notes: String?
    var items: [PendingMealEventItem]
}

struct PendingMealEventItem: Codable, Identifiable {
    let id: UUID
    var foodItemId: Int
    var grams: Double
    var sortOrder: Int
}

struct PendingMedicationEvent: Codable, Identifiable {
    let id: UUID
    var takenAtISO: String
    var optionId: Int
    var notes: String?
}

// ... existing structs ...

import Foundation

// ... existing Meal and Med structs ...

struct ExerciseTemplateResponse: Codable {
    let ok: Bool
    let exercise_templates: [ExerciseTemplate]
}

// Added Hashable for the Picker
struct ExerciseTemplate: Codable, Identifiable, Hashable {
    let id: Int
    let name: String
    let default_reps: Int
    let default_weight_kg: String
    let notes: String?
}

struct PendingExerciseSet: Codable, Identifiable {
    let id: UUID
    var performedAtISO: String
    var templateId: Int?
    var name: String
    var reps: Int
    var weightKg: Double
}
