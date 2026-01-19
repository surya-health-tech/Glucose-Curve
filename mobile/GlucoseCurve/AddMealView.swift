//
//  AddMealView.swift
//  GlucoseCurve
//
//  Created by Surya Gobi on 12/24/25.
//

import SwiftUI

struct AddMealView: View {
    @Environment(\.dismiss) private var dismiss
    @ObservedObject var store: PendingStore

    @State private var templates: [MealTemplate] = []
    @State private var selectedTemplateIndex: Int = 0
    @State private var eatenAt = Date()
    @State private var notes: String = ""
    @State private var editableGrams: [UUID: String] = [:]
    @State private var isLoading = true
    @State private var errorText: String = ""

    var body: some View {
        NavigationView {
            VStack(spacing: 12) {
                if isLoading {
                    ProgressView("Loading meal templates...")
                    Spacer()
                } else if !errorText.isEmpty {
                    Text(errorText).foregroundColor(.red)
                    Spacer()
                } else {
                    Picker("Meal Template", selection: $selectedTemplateIndex) {
                        ForEach(templates.indices, id: \.self) { idx in
                            Text(templates[idx].name).tag(idx)
                        }
                    }
                    .pickerStyle(.menu)

                    DatePicker("Date & Time", selection: $eatenAt)
                        .datePickerStyle(.compact)

                    if !templates.isEmpty {
                        List {
                            ForEach(templates[selectedTemplateIndex].items) { item in
                                HStack {
                                    VStack(alignment: .leading) {
                                        Text(item.food_item_name)
                                        Text("Default: \(item.grams) g")
                                            .font(.caption)
                                            .foregroundColor(.secondary)
                                    }
                                    Spacer()
                                    TextField("grams", text: Binding(
                                        get: { editableGrams[key(for: item)] ?? item.grams },
                                        set: { editableGrams[key(for: item)] = $0 }
                                    ))
                                    .keyboardType(.decimalPad)
                                    .multilineTextAlignment(.trailing)
                                    .frame(width: 90)
                                }
                            }
                        }
                    }

                    TextField("Notes (optional)", text: $notes)
                        .textFieldStyle(.roundedBorder)

                    Button("Save Meal") {
                        save()
                    }
                    .buttonStyle(.borderedProminent)
                }
            }
            .padding()
            .navigationTitle("Add Meal")
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button("Close") { dismiss() }
                }
            }
            .task { await loadTemplates() }
        }
    }

    private func key(for item: MealTemplateItem) -> UUID {
        // stable mapping for editableGrams
        UUID(uuidString: "00000000-0000-0000-0000-\(String(format: "%012d", item.id))") ?? UUID()
    }

    private func loadTemplates() async {
        do {
            isLoading = true
            templates = try await APIClient.shared.getMealTemplates()
            isLoading = false
        } catch {
            isLoading = false
            errorText = "Failed to load templates: \(error.localizedDescription)"
        }
    }

    private func save() {
        guard !templates.isEmpty else { return }
        let t = templates[selectedTemplateIndex]

        let iso = ISO8601DateFormatter().string(from: eatenAt)

        let items: [PendingMealEventItem] = t.items.enumerated().map { idx, it in
            let raw = editableGrams[key(for: it)] ?? it.grams
            let grams = Double(raw) ?? (Double(it.grams) ?? 0)
            return PendingMealEventItem(
                id: UUID(),
                foodItemId: it.food_item_id,
                grams: grams,
                sortOrder: it.sort_order
            )
        }

        let event = PendingMealEvent(
            id: UUID(), // client_uuid
            eatenAtISO: iso,
            mealTemplateId: t.id,
            notes: notes.isEmpty ? nil : notes,
            items: items
        )

        store.addMeal(event)
        dismiss()
    }
}
