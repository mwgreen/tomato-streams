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
                .task {
                    // Left on screen for hours or days: keep picking up new syncs and watched marks.
                    while !Task.isCancelled {
                        try? await Task.sleep(for: .seconds(30 * 60))
                        await store.refreshIfStale(olderThan: 60 * 60)
                        await watched.load()
                    }
                }
                .onChange(of: scenePhase) { _, phase in
                    // Waking up or coming back from a streaming app: refresh if it has been a while.
                    if phase == .active {
                        Task { await store.refreshIfStale(olderThan: 15 * 60); await watched.load() }
                    }
                }
        }
    }
}
