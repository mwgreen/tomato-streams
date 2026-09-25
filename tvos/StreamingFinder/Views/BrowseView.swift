import SwiftUI

/// Movies or TV tab: filter chips on top, poster grid below.
struct BrowseView: View {
    let kind: Kind
    @EnvironmentObject var store: CatalogStore
    @EnvironmentObject var settings: ServerSettings
    @EnvironmentObject var hidden: HiddenStore
    @EnvironmentObject var watched: WatchedStore
    @State private var filters: Filters

    init(kind: Kind) {
        self.kind = kind
        _filters = State(initialValue: Filters.load(kind))
    }

    private var catalog: Catalog? { store.catalogs[kind] }

    private var titles: [Title] {
        filters.apply(store.titles(kind), hidden: hidden.ids, showHidden: settings.showHidden, hideNoScore: settings.hideNoScore,
                      watched: watched.watched)
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 24) {
                    FilterBar(filters: $filters, services: store.services(kind), genres: catalog?.allGenres ?? [], people: watched.people, kind: kind)
                    HStack {
                        Text("\(titles.count) \(kind.noun)").foregroundStyle(.secondary)
                        if let generated = catalog?.generatedAt {
                            Text("· data from \(String(generated.prefix(10)))").foregroundStyle(.tertiary)
                        }
                        Spacer()
                        if store.isRefreshing { ProgressView().scaleEffect(0.7) }
                    }
                    .font(.callout)
                    TitleGrid(titles: titles, trackingSince: catalog?.trackingSince, selectedService: filters.service)
                    if titles.isEmpty {
                        Text(store.titles(kind).isEmpty ? "Nothing loaded yet." : "Nothing matches these filters.")
                            .foregroundStyle(.secondary).padding(.top, 80).frame(maxWidth: .infinity)
                    }
                }
                .padding(.horizontal, 60).padding(.top, 20).padding(.bottom, 60)
            }
            .navigationDestination(for: Title.self) { DetailView(title: $0) }
        }
        .onChange(of: filters) { _, new in new.save(kind) }
    }
}

/// Shared poster grid.
struct TitleGrid: View {
    let titles: [Title]
    var trackingSince: String?
    var selectedService: String?
    @EnvironmentObject var hidden: HiddenStore
    @EnvironmentObject var watched: WatchedStore

    private var columns: [GridItem] {
        [GridItem(.adaptive(minimum: TitleCard.posterWidth, maximum: TitleCard.posterWidth), spacing: 48, alignment: .top)]
    }
    private var thirtyDaysAgo: String { Filters.isoDay(Calendar.current.date(byAdding: .day, value: -30, to: Date()) ?? Date()) }

    var body: some View {
        LazyVGrid(columns: columns, alignment: .leading, spacing: 56) {
            ForEach(titles) { t in
                TitleCard(title: t, isNew: isNew(t), isHidden: hidden.contains(t), watchedBy: watched.watchedBy(t))
            }
        }
    }

    private func isNew(_ t: Title) -> Bool {
        guard let since = trackingSince,
              let added = t.addedKey(services: selectedService.map { [$0] }) else { return false }
        return added > since && added >= thirtyDaysAgo
    }
}
