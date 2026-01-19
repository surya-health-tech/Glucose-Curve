import SwiftUI

struct AddMedicationView: View {
    @Environment(\.dismiss) private var dismiss
    @ObservedObject var store: PendingStore

    @State private var options: [MedicationOption] = []
    @State private var selectedIndex: Int = 0
    @State private var takenAt = Date()
    @State private var notes: String = ""
    @State private var isLoading = true
    @State private var errorText: String = ""

    var body: some View {
        NavigationView {
            VStack(spacing: 12) {
                if isLoading {
                    ProgressView("Loading medication options...")
                    Spacer()
                } else if !errorText.isEmpty {
                    Text(errorText).foregroundColor(.red)
                    Spacer()
                } else {
                    Picker("Medication", selection: $selectedIndex) {
                        ForEach(options.indices, id: \.self) { idx in
                            Text(options[idx].label).tag(idx)
                        }
                    }
                    .pickerStyle(.menu)

                    DatePicker("Date & Time", selection: $takenAt)
                        .datePickerStyle(.compact)

                    TextField("Notes (optional)", text: $notes)
                        .textFieldStyle(.roundedBorder)

                    Button("Save Medication") { save() }
                        .buttonStyle(.borderedProminent)
                }
            }
            .padding()
            .navigationTitle("Add Medication")
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button("Close") { dismiss() }
                }
            }
            .task { await loadOptions() }
        }
    }

    private func loadOptions() async {
        do {
            isLoading = true
            options = try await APIClient.shared.getMedicationOptions()
            isLoading = false
        } catch {
            isLoading = false
            errorText = "Failed to load options: \(error.localizedDescription)"
        }
    }

    private func save() {
        guard !options.isEmpty else { return }
        let opt = options[selectedIndex]
        let iso = ISO8601DateFormatter().string(from: takenAt)

        let event = PendingMedicationEvent(
            id: UUID(), // client_uuid
            takenAtISO: iso,
            optionId: opt.id,
            notes: notes.isEmpty ? nil : notes
        )

        store.addMed(event)
        dismiss()
    }
}
//
//  AddMedication.swift
//  GlucoseCurve
//
//  Created by Surya Gobi on 12/24/25.
//

