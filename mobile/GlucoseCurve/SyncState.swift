//
//  SyncState.swift
//  GlucoseCurve
//
//  Created by Surya Gobi on 12/25/25.
//

import Foundation

final class SyncState {
    private let lastSyncKey = "last_sync_iso"

    func getLastSyncDate(defaultDaysBack: Int = 7) -> Date {
        if let iso = UserDefaults.standard.string(forKey: lastSyncKey),
           let d = ISO8601DateFormatter().date(from: iso) {
            return d
        }
        // first run: pull last N days
        return Calendar.current.date(byAdding: .day, value: -defaultDaysBack, to: Date())!
    }

    func setLastSyncDate(_ date: Date) {
        let iso = ISO8601DateFormatter().string(from: date)
        UserDefaults.standard.set(iso, forKey: lastSyncKey)
    }
}
