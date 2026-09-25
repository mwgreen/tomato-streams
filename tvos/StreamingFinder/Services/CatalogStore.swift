import Foundation

/// Loads data/movies.json and data/tv.json from serve.py, keeps a copy on disk so the
/// app opens instantly, and fetches exact watch links on demand.
@MainActor
final class CatalogStore: ObservableObject {
    @Published private(set) var catalogs: [Kind: Catalog] = [:]
    @Published private(set) var isRefreshing = false
    @Published private(set) var lastError: String?
    @Published private(set) var lastRefresh: Date?

    private let settings: ServerSettings
    private var linkLookups: Set<String> = []

    init(settings: ServerSettings) {
        self.settings = settings
        for kind in Kind.allCases {
            if let data = try? Data(contentsOf: cacheURL(kind)),
               let catalog = try? JSONDecoder.catalog.decode(Catalog.self, from: data) {
                catalogs[kind] = catalog
            }
        }
        if let stamp = UserDefaults.standard.object(forKey: "lastRefresh") as? Date { lastRefresh = stamp }
    }

    func titles(_ kind: Kind) -> [Title] { catalogs[kind]?.movies ?? [] }
    func services(_ kind: Kind) -> [String] { catalogs[kind]?.services ?? [] }
    var hasData: Bool { !catalogs.isEmpty }

    /// Fresh copy of a title (watch links may have been filled in since a view captured it).
    func current(_ title: Title) -> Title {
        guard let kind = Kind(rawValue: title.kind) else { return title }
        return catalogs[kind]?.movies.first { $0.tmdbId == title.tmdbId } ?? title
    }

    /// Re-download both catalogs. Safe to call often; errors are reported, not thrown.
    func refresh() async {
        guard !isRefreshing else { return }
        guard settings.baseURL != nil else {
            lastError = hasData ? nil : "Set the server address in Settings."
            return
        }
        isRefreshing = true
        defer { isRefreshing = false }
        var failures: [String] = []
        for kind in Kind.allCases {
            guard let url = settings.url(kind.dataFile) else { continue }
            var req = URLRequest(url: url)
            req.timeoutInterval = 20
            req.cachePolicy = .reloadIgnoringLocalCacheData
            do {
                let (data, resp) = try await URLSession.shared.data(for: req)
                let status = (resp as? HTTPURLResponse)?.statusCode ?? 0
                guard status == 200 else {
                    if status == 404 && kind == .tv { continue }  // tv sync disabled: fine
                    failures.append("\(kind.label): HTTP \(status)")
                    continue
                }
                let catalog = try JSONDecoder.catalog.decode(Catalog.self, from: data)
                catalogs[kind] = catalog
                try? data.write(to: cacheURL(kind), options: .atomic)
            } catch {
                failures.append("\(kind.label): \(error.localizedDescription)")
            }
        }
        if failures.isEmpty {
            lastRefresh = Date()
            UserDefaults.standard.set(lastRefresh, forKey: "lastRefresh")
            lastError = nil
        } else {
            lastError = failures.joined(separator: "\n")
        }
    }

    /// Ask serve.py for exact links (it calls Watchmode once and caches). Updates the catalog in place.
    func fetchWatchLinks(for title: Title) async {
        let missing = title.services.contains { title.watchUrls[$0] == nil }
        guard missing, !linkLookups.contains(title.id),
              let url = settings.url("api/watch-links?kind=\(title.kind)&id=\(title.tmdbId)") else { return }
        linkLookups.insert(title.id)
        defer { linkLookups.remove(title.id) }
        var req = URLRequest(url: url)
        req.timeoutInterval = 20
        guard let (data, resp) = try? await URLSession.shared.data(for: req),
              (resp as? HTTPURLResponse)?.statusCode == 200,
              let body = try? JSONDecoder.catalog.decode(WatchLinksResponse.self, from: data),
              let urls = body.watchUrls, !urls.isEmpty,
              let kind = Kind(rawValue: title.kind),
              var catalog = catalogs[kind],
              let index = catalog.movies.firstIndex(where: { $0.tmdbId == title.tmdbId }) else { return }
        catalog.movies[index].watchUrls.merge(urls) { _, new in new }
        catalog.movies[index].watchAppUrls.merge(body.watchAppUrls ?? [:]) { _, new in new }
        catalog.movies[index].watchUrlLevels.merge(body.watchUrlLevels ?? [:]) { _, new in new }
        catalogs[kind] = catalog
    }

    private func cacheURL(_ kind: Kind) -> URL {
        let dir = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("StreamingFinder", isDirectory: true)
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        return dir.appendingPathComponent("\(kind.rawValue).json")
    }
}
