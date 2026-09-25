import SwiftUI

/// Search across movies and series. tvOS supplies the on-screen keyboard and Siri dictation.
struct SearchView: View {
    @EnvironmentObject var store: CatalogStore
    @EnvironmentObject var settings: ServerSettings
    @EnvironmentObject var hidden: HiddenStore
    @EnvironmentObject var watched: WatchedStore
    @State private var query = ""

    private var results: [Title] {
        let q = query.trimmingCharacters(in: .whitespaces)
        guard q.count >= 2 else { return [] }
        var f = Filters()
        f.minReviews = 0
        f.sort = .critic
        let all = store.titles(.movie) + store.titles(.tv)
        return f.apply(all, hidden: hidden.ids, showHidden: settings.showHidden, hideNoScore: false, query: q, watched: watched.watched)
    }

    var body: some View {
        NavigationStack {
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
            .navigationDestination(for: Title.self) { DetailView(title: $0) }
        }
        .searchable(text: $query, prompt: "Movie or series title")
    }
}
