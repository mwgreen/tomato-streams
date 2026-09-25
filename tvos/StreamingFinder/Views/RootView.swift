import SwiftUI

struct RootView: View {
    @EnvironmentObject var settings: ServerSettings
    @EnvironmentObject var store: CatalogStore

    var body: some View {
        TabView {
            BrowseView(kind: .movie)
                .tabItem { Text("Movies") }
            BrowseView(kind: .tv)
                .tabItem { Text("TV Series") }
            SearchView()
                .tabItem { Image(systemName: "magnifyingglass") }
            SettingsView()
                .tabItem { Text("Settings") }
        }
        .overlay(alignment: .center) {
            if !store.hasData {
                FirstRunView()
            }
        }
    }
}

/// Shown until the first catalog has been loaded.
struct FirstRunView: View {
    @EnvironmentObject var settings: ServerSettings
    @EnvironmentObject var store: CatalogStore

    var body: some View {
        VStack(spacing: 24) {
            Image(systemName: "popcorn.fill").font(.system(size: 72)).foregroundStyle(.orange)
            Text("Streaming Finder").font(.largeTitle.bold())
            if store.isRefreshing {
                ProgressView("Loading your library…")
            } else if settings.baseURL == nil {
                Text("Point the app at the computer running serve.py.\nOpen Settings to pick it from the network or type its address.")
                    .multilineTextAlignment(.center).foregroundStyle(.secondary)
            } else {
                Text(store.lastError ?? "No data yet.").multilineTextAlignment(.center).foregroundStyle(.secondary)
                Button("Try again") { Task { await store.refresh() } }
            }
        }
        .padding(60)
        .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 24))
    }
}
