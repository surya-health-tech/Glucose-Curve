import SwiftUI

struct AddExerciseView: View {
    @ObservedObject var store: PendingStore
    @Environment(\.dismiss) var dismiss
    
    @State private var templates: [ExerciseTemplate] = []
    @State private var selectedTemplate: ExerciseTemplate?
    @State private var reps: String = ""
    @State private var performedAt: Date = Date() // Defaults to current date/time

    var body: some View {
        NavigationView {
            Form {
                Section(header: Text("Exercise Details")) {
                    // 1. Template Picker
                    Picker("Select Exercise", selection: $selectedTemplate) {
                        if templates.isEmpty {
                            Text("Loading...").tag(nil as ExerciseTemplate?)
                        }
                        ForEach(templates) { t in
                            Text(t.name).tag(t as ExerciseTemplate?)
                        }
                    }
                    // Triggered whenever the user changes the template
                    .onChange(of: selectedTemplate) { newValue in
                        if let template = newValue {
                            reps = "\(template.default_reps)"
                        }
                    }
                    
                    // 2. Repetitions (Pre-populated from template)
                    TextField("Repetitions", text: $reps)
                        .keyboardType(.numberPad)
                    
                    // 3. Date Picker (Defaults to Now, allows editing)
                    DatePicker("Date & Time", selection: $performedAt, displayedComponents: [.date, .hourAndMinute])
                }
            }
            .navigationTitle("Log Exercise")
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button("Save") {
                        saveExercise()
                    }
                    .disabled(selectedTemplate == nil)
                }
                ToolbarItem(placement: .navigationBarLeading) {
                    Button("Cancel") { dismiss() }
                }
            }
            .task {
                await loadTemplates()
            }
        }
    }

    // Load templates and pre-select the first one
    private func loadTemplates() async {
        do {
            let fetched = try await APIClient.shared.getExerciseTemplates()
            self.templates = fetched
            
            // Pre-populate with the first template as default
            if let firstTemplate = fetched.first {
                self.selectedTemplate = firstTemplate
                self.reps = "\(firstTemplate.default_reps)"
            }
        } catch {
            print("Failed to load templates: \(error)")
        }
    }

    private func saveExercise() {
        guard let t = selectedTemplate else { return }
        
        let newSet = PendingExerciseSet(
            id: UUID(),
            performedAtISO: ISO8601DateFormatter().string(from: performedAt),
            templateId: t.id,
            name: t.name,
            reps: Int(reps) ?? 0,
            weightKg: Double(t.default_weight_kg) ?? 0.0
        )
        
        store.addExercise(newSet)
        dismiss()
    }
}
