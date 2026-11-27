import SwiftUI

/// The shared watchlist: movies and series together, most recently added first.
/// Titles are added and removed on their title page; the list is shared with the web app.
struct WatchlistView: View {
    @EnvironmentObject var store: CatalogStore
    @EnvironmentObject var watched: WatchedStore

    /// A watchlist entry whose title is in neither catalog any more.
    private struct Gone: Identifiable {
        let id: String
        let entry: WatchlistEntry

        var label: String {
            let name = entry.title ?? id
            return entry.year.map { "\(name) (\($0))" } ?? name
        }
    }

    private var titles: [Title] {
        (store.titles(.movie) + store.titles(.tv))
            .filter { watched.isOnWatchlist($0) }
            .sorted { a, b in
                let x = watched.watchlist[a.id]?.added ?? "", y = watched.watchlist[b.id]?.added ?? ""
                return x == y ? a.title.localizedCaseInsensitiveCompare(b.title) == .orderedAscending : x > y
            }
    }

    private func gone(besides titles: [Title]) -> [Gone] {
        guard store.hasData else { return [] }
        let known = Set(titles.map(\.id))
        return watched.watchlist
            .filter { !known.contains($0.key) }
            .map { Gone(id: $0.key, entry: $0.value) }
            .sorted { $0.label.localizedCaseInsensitiveCompare($1.label) == .orderedAscending }
    }

    var body: some View {
        let titles = titles   // computed once per render, not once per use
        let missing = gone(besides: titles)
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 24) {
                    if titles.isEmpty && missing.isEmpty {
                        Text("Your watchlist is empty.\nOpen a movie or series and choose Add to Watchlist.")
                            .multilineTextAlignment(.center).foregroundStyle(.secondary)
                            .padding(.top, 80).frame(maxWidth: .infinity)
                    } else {
                        Text("\(titles.count + missing.count) on your watchlist").font(.callout).foregroundStyle(.secondary)
                        TitleGrid(titles: titles)
                    }
                    if !missing.isEmpty {
                        Text("Not on your services right now").font(.headline).padding(.top, 20)
                        ForEach(missing) { item in
                            HStack(spacing: 30) {
                                Text(item.label)
                                Spacer()
                                Button("Remove") { Task { await watched.removeFromWatchlist(id: item.id) } }
                            }
                        }
                    }
                }
                .padding(.horizontal, 60).padding(.top, 20).padding(.bottom, 60)
            }
            .navigationDestination(for: Title.self) { DetailView(title: $0) }
        }
        .task { await watched.load() }   // pick up titles added from a phone or the web
    }
}
