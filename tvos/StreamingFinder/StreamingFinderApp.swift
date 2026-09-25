import SwiftUI

@main
struct StreamingFinderApp: App {
    @StateObject private var settings: ServerSettings
    @StateObject private var store: CatalogStore
    @StateObject private var hidden = HiddenStore()
    @StateObject private var watched: WatchedStore
    @Environment(\.scenePhase) private var scenePhase

    init() {
        let settings = ServerSettings()
        _settings = StateObject(wrappedValue: settings)
        _store = StateObject(wrappedValue: CatalogStore(settings: settings))
        _watched = StateObject(wrappedValue: WatchedStore(settings: settings))
    }

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(settings)
                .environmentObject(store)
                .environmentObject(hidden)
                .environmentObject(watched)
                .task { await store.refresh(); await watched.load() }
                .onChange(of: scenePhase) { _, phase in
                    // Coming back from a streaming app: pick up a fresh sync if there is one.
                    if phase == .active, let last = store.lastRefresh, Date().timeIntervalSince(last) > 6 * 3600 {
                        Task { await store.refresh(); await watched.load() }
                    }
                }
        }
    }
}
