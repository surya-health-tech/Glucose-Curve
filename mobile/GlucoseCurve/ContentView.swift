import SwiftUI

struct ContentView: View {
    @StateObject private var store = PendingStore()
    @StateObject private var hkSync = HealthKitSyncManager()

    @State private var showMeal = false
    @State private var showMed = false
    @State private var showExercise = false // New State
    @State private var syncStatus: String = ""

    var body: some View {
        NavigationView {
            VStack(spacing: 18) {
                // ... Existing title ...

                Button("Add Meal") { showMeal = true }
                    .buttonStyle(.borderedProminent)

                Button("Add Medication") { showMed = true }
                    .buttonStyle(.bordered)
                
                // New Button
                Button("Log Exercise") { showExercise = true }
                    .buttonStyle(.bordered)

                Button("Sync to Backend") {
                    Task(priority: .userInitiated) { // Explicitly set priority
                        await doSync()
                    }
                }
                .buttonStyle(.bordered)

                // --- INSERT THE CODE BLOCK HERE ---
                            if !syncStatus.isEmpty {
                                Text(syncStatus)
                                    .font(.footnote)
                                    .foregroundColor(.secondary)
                                    .multilineTextAlignment(.center)
                                    .padding()
                                    .frame(maxWidth: .infinity)
                                    .background(Color(.systemGray6))
                                    .cornerRadius(8)
                                    .padding(.horizontal)
                            }
                
                Spacer()
            }
            .padding()
            .sheet(isPresented: $showMeal) { AddMealView(store: store) }
            .sheet(isPresented: $showMed) { AddMedicationView(store: store) }
            .sheet(isPresented: $showExercise) { AddExerciseView(store: store) } // New Sheet
        }
    }

    private func doSync() async {
        syncStatus = "Syncing..."

        // 1) Prepare what user logged in the UI (meals + meds)
        let mealEvents: [[String: Any]] = store.pendingMeals.map { m in
            [
                "client_uuid": m.id.uuidString,
                "eaten_at": m.eatenAtISO,
                "meal_template_id": m.mealTemplateId as Any,
                "notes": m.notes ?? "",
                "items": m.items.map { it in
                    [
                        "food_item_id": it.foodItemId,
                        "grams": String(format: "%.2f", it.grams),
                        "sort_order": it.sortOrder
                    ]
                }
            ]
        }

        let medEvents: [[String: Any]] = store.pendingMeds.map { e in
            [
                "client_uuid": e.id.uuidString,
                "taken_at": e.takenAtISO,
                "option_id": e.optionId as Any,
                "notes": e.notes ?? ""
            ]
        }

        do {
            // 2) Pull HealthKit deltas since last sync
            try await hkSync.requestAuthorizationIfNeeded()
            let hk = try await hkSync.fetchHealthKitDeltaPayload()

            // 3) Build ONE payload for backend /api/sync/
            let payload: [String: Any] = [
                "device": "iphone",
                "notes": "",
                "meal_events": mealEvents,
                "medication_events": medEvents,
                "egv_readings": hk.egvs,
                "workouts": hk.workouts,
                "weight_readings": hk.weights,
                "exercise_sets": store.pendingExercises.map { e in [
                        "client_uuid": e.id.uuidString,
                        "performed_at": e.performedAtISO,
                        "name": e.name,
                        "reps": e.reps,
                        "template_id": e.templateId as Any
                    ]},
                    "sleep_sessions": hk.sleep,
                    "health_metrics": hk.metrics,
            ]

            // 4) POST
            let resp = try await APIClient.shared.sync(payload: payload)

            // 5) If successful: mark last HK sync time and clear local pending UI events
            hkSync.markSuccessfulSyncNow()
            store.clearAll()

            // NEW: Format the dictionary response into a string to display on screen
            let responseString = resp.map { "\($0.key): \($0.value)" }.joined(separator: "\n")
            syncStatus = "Sync OK ✅\n\nServer Response:\n\(responseString)"
        } catch let error as NSError{
            // Specific handling for the -1004 error you received
                        if error.domain == NSURLErrorDomain && error.code == -1004 {
                            syncStatus = "Connection Error ❌\nCannot reach server at 192.168.1.18. Is Django running?"
                        } else {
                            syncStatus = "Sync failed ❌\n\(error.localizedDescription)"
                        }
                        print("Detailed Sync Error: \(error)")
        }
    }
}
