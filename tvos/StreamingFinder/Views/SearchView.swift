import SwiftUI

/// Search across movies and series. tvOS supplies the on-screen keyboard and Siri dictation.
struct SearchView: View {
    @EnvironmentObject var store: CatalogStore
    @EnvironmentObject var settings: ServerSettings
    @EnvironmentObject var hidden: HiddenStore
    @EnvironmentObject var watched: WatchedStore
    @State private var query = ""
    @State private var path: [Title] = []

    private var results: [Title] {
        let q = query.trimmingCharacters(in: .whitespaces)
        guard q.count >= 2 else { return [] }
        var f = Filters()
        f.minReviews = 0
        f.sort = .critic
        let all = store.titles(.movie) + store.titles(.tv)
        let found = f.apply(all, hidden: hidden.ids, showHidden: settings.showHidden, hideNoScore: false, query: q, watched: watched.watched)
        // Best title match first; within a tier keep the critic-score order from apply.
        let search = TitleSearch(q)
        return found.enumerated()
            .map { (rank: search.rank($1) ?? 9, index: $0, title: $1) }
            .sorted { ($0.rank, $0.index) < ($1.rank, $1.index) }
            .map(\.title)
    }

    var body: some View {
        let results = results   // computed once per render, not once per use
        NavigationStack(path: $path) {
            ScrollView {
                VStack(alignment: .leading, spacing: 24) {
                    if results.isEmpty {
                        Text(query.count < 2 ? "Type a title, or hold the Siri button and say it." : "No matches on your services.")
                            .foregroundStyle(.secondary).padding(.top, 60).frame(maxWidth: .infinity)
                    } else {
                        Text("\(results.count) results").foregroundStyle(.secondary)
                        TitleGrid(titles: results)
                    }
                }
                .padding(.horizontal, 60).padding(.bottom, 60)
            }
            // Search belongs to the results page, inside the stack: attached outside it, the keyboard
            // stayed on screen over an opened title and typing updated results hidden behind it.
            .searchable(text: $query, prompt: "Movie or series title")
            .navigationDestination(for: Title.self) { DetailView(title: $0) }
        }
        .onChange(of: query) { path = [] }   // a new search always shows its results
    }
}
