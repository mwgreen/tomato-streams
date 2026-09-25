import Foundation

/// Which catalog a title belongs to. Mirrors `kind` in the JSON.
enum Kind: String, CaseIterable, Codable, Identifiable {
    case movie, tv
    var id: String { rawValue }
    var label: String { self == .movie ? "Movies" : "TV Series" }
    var noun: String { self == .movie ? "movies" : "series" }
    var dataFile: String { self == .movie ? "data/movies.json" : "data/tv.json" }
}

/// Rotten Tomatoes scores as written by sync.py.
struct RTScores: Codable, Hashable {
    var url: String?
    var status: String?
    var criticScore: Int?
    var criticCount: Int?
    var certifiedFresh: Bool?
    var audienceScore: Int?
    var audienceCount: String?

    var hasScores: Bool { criticScore != nil || audienceScore != nil }
    var isCertified: Bool { certifiedFresh ?? false }
}

/// One movie or series from data/movies.json or data/tv.json.
/// Decoded with `.convertFromSnakeCase`, so `tmdb_id` -> `tmdbId` etc.
struct Title: Codable, Hashable, Identifiable {
    var kind: String
    var tmdbId: Int
    var imdbId: String?
    var title: String
    var originalTitle: String?
    var year: Int?
    var releaseDate: String?
    var overview: String?
    var runtime: Int?
    var seasons: Int?
    var episodes: Int?
    var endYear: Int?
    var status: String?
    var genres: [String]
    var poster: String?
    var posterLarge: String?
    var backdrop: String?
    var trailerYoutubeKey: String?
    var services: [String]
    var added: [String: String]
    var addedAt: String?
    var watchUrls: [String: String]
    var watchAppUrls: [String: String]
    var watchUrlLevels: [String: String]
    var justwatchLink: String?
    var rt: RTScores

    var id: String { "\(kind)-\(tmdbId)" }
    var isTV: Bool { kind == "tv" }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        kind = try c.decodeIfPresent(String.self, forKey: .kind) ?? "movie"
        tmdbId = try c.decode(Int.self, forKey: .tmdbId)
        imdbId = try c.decodeIfPresent(String.self, forKey: .imdbId)
        title = try c.decodeIfPresent(String.self, forKey: .title) ?? ""
        originalTitle = try c.decodeIfPresent(String.self, forKey: .originalTitle)
        year = try c.decodeIfPresent(Int.self, forKey: .year)
        releaseDate = try c.decodeIfPresent(String.self, forKey: .releaseDate)
        overview = try c.decodeIfPresent(String.self, forKey: .overview)
        runtime = try c.decodeIfPresent(Int.self, forKey: .runtime)
        seasons = try c.decodeIfPresent(Int.self, forKey: .seasons)
        episodes = try c.decodeIfPresent(Int.self, forKey: .episodes)
        endYear = try c.decodeIfPresent(Int.self, forKey: .endYear)
        status = try c.decodeIfPresent(String.self, forKey: .status)
        genres = try c.decodeIfPresent([String].self, forKey: .genres) ?? []
        poster = try c.decodeIfPresent(String.self, forKey: .poster)
        posterLarge = try c.decodeIfPresent(String.self, forKey: .posterLarge)
        backdrop = try c.decodeIfPresent(String.self, forKey: .backdrop)
        trailerYoutubeKey = try c.decodeIfPresent(String.self, forKey: .trailerYoutubeKey)
        services = try c.decodeIfPresent([String].self, forKey: .services) ?? []
        added = try c.decodeIfPresent([String: String].self, forKey: .added) ?? [:]
        addedAt = try c.decodeIfPresent(String.self, forKey: .addedAt)
        watchUrls = try c.decodeIfPresent([String: String].self, forKey: .watchUrls) ?? [:]
        watchAppUrls = try c.decodeIfPresent([String: String].self, forKey: .watchAppUrls) ?? [:]
        watchUrlLevels = try c.decodeIfPresent([String: String].self, forKey: .watchUrlLevels) ?? [:]
        justwatchLink = try c.decodeIfPresent(String.self, forKey: .justwatchLink)
        rt = try c.decodeIfPresent(RTScores.self, forKey: .rt) ?? RTScores()
    }

    // MARK: display helpers

    /// "2016–2022", "2022–" (still running) or "1995".
    var yearsLabel: String {
        guard let year else { return "" }
        if !isTV { return String(year) }
        guard let endYear else { return "\(year)–" }
        return endYear == year ? String(year) : "\(year)–\(endYear)"
    }

    /// "121 min" or "3 seasons · 50 min".
    var lengthLabel: String {
        if isTV {
            var parts: [String] = []
            if let seasons { parts.append("\(seasons) season\(seasons == 1 ? "" : "s")") }
            if let runtime { parts.append("\(runtime) min") }
            return parts.joined(separator: " · ")
        }
        return runtime.map { "\($0) min" } ?? ""
    }

    var metaLine: String { [yearsLabel, lengthLabel].filter { !$0.isEmpty }.joined(separator: " · ") }

    /// ISO date for release comparisons, falling back to the year.
    var releaseKey: String? { releaseDate ?? year.map { "\($0)-01-01" } }

    /// Latest "first seen" date among the given services (nil = any service).
    func addedKey(services only: Set<String>?) -> String? {
        var best: String?
        for (name, date) in added {
            if let only, !only.contains(name) { continue }
            if best == nil || date > best! { best = date }
        }
        return best
    }

    var combinedScore: Double? {
        switch (rt.criticScore, rt.audienceScore) {
        case (nil, nil): return nil
        case (let c?, nil): return Double(c)
        case (nil, let a?): return Double(a)
        case (let c?, let a?): return Double(c + a) / 2
        }
    }
}

/// The whole JSON file.
struct Catalog: Codable {
    var generatedAt: String?
    var kind: String?
    var region: String?
    var services: [String]
    var trackingSince: String?
    var movies: [Title]

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        generatedAt = try c.decodeIfPresent(String.self, forKey: .generatedAt)
        kind = try c.decodeIfPresent(String.self, forKey: .kind)
        region = try c.decodeIfPresent(String.self, forKey: .region)
        services = try c.decodeIfPresent([String].self, forKey: .services) ?? []
        trackingSince = try c.decodeIfPresent(String.self, forKey: .trackingSince)
        movies = try c.decodeIfPresent([Title].self, forKey: .movies) ?? []
    }

    var allGenres: [String] {
        Array(Set(movies.flatMap(\.genres))).sorted()
    }
}

/// Response of GET /api/watch-links.
struct WatchLinksResponse: Codable {
    var enabled: Bool?
    var fetched: Bool?
    var watchUrls: [String: String]?
    var watchAppUrls: [String: String]?
    var watchUrlLevels: [String: String]?
}

extension JSONDecoder {
    static var catalog: JSONDecoder {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return d
    }
}

// MARK: - Filters

enum SortKey: String, CaseIterable, Codable, Identifiable {
    case critic, audience, combined, reviews, added, newest, oldest, title
    var id: String { rawValue }
    var label: String {
        switch self {
        case .critic: return "Critic score"
        case .audience: return "Audience score"
        case .combined: return "Combined"
        case .reviews: return "Review count"
        case .added: return "Recently added"
        case .newest: return "Newest"
        case .oldest: return "Oldest"
        case .title: return "Title"
        }
    }
}

/// Browse filters, one set per kind, persisted in UserDefaults.
struct Filters: Codable, Equatable {
    var service: String? = nil          // nil = all services
    var minCritic: Int = 0
    var minAudience: Int = 0
    var minReviews: Int = 20
    var certifiedOnly: Bool = false
    var genre: String? = nil
    var yearFrom: Int? = nil
    var addedWithinDays: Int? = nil
    var hideWatchedBy: Set<String> = []  // people whose watched titles are hidden
    var sort: SortKey = .critic

    static let scoreSteps = [0, 50, 60, 70, 80, 90]
    static let yearSteps: [Int?] = [nil, 2025, 2024, 2023, 2022, 2020, 2015, 2010, 2000, 1990]
    static let addedSteps: [Int?] = [nil, 7, 30, 90, 365]

    var isDefault: Bool { self == Filters() }

    static func load(_ kind: Kind) -> Filters {
        guard let data = UserDefaults.standard.data(forKey: "filters.\(kind.rawValue)"),
              let f = try? JSONDecoder().decode(Filters.self, from: data) else { return Filters() }
        return f
    }

    func save(_ kind: Kind) {
        if let data = try? JSONEncoder().encode(self) {
            UserDefaults.standard.set(data, forKey: "filters.\(kind.rawValue)")
        }
    }

    /// Filter + sort. `hidden` are title ids the user hid; `hideNoScore` drops titles without RT scores.
    func apply(_ titles: [Title], hidden: Set<String>, showHidden: Bool, hideNoScore: Bool,
               query: String = "", watched: [String: [String: String]] = [:]) -> [Title] {
        let q = query.trimmingCharacters(in: .whitespaces).lowercased()
        let onlyService: Set<String>? = service.map { [$0] }
        let yearKey = yearFrom.map { "\($0)-01-01" }
        let addedKeyMin: String? = addedWithinDays.flatMap { days in
            Calendar.current.date(byAdding: .day, value: -days, to: Date()).map(Self.isoDay)
        }
        var out = titles.filter { t in
            if hidden.contains(t.id) && !showHidden { return false }
            if !hideWatchedBy.isEmpty, let marks = watched[t.id], marks.keys.contains(where: { hideWatchedBy.contains($0) }) { return false }
            if let service, !t.services.contains(service) { return false }
            if hideNoScore && !t.rt.hasScores { return false }
            if minCritic > 0 && (t.rt.criticScore ?? -1) < minCritic { return false }
            if minAudience > 0 && (t.rt.audienceScore ?? -1) < minAudience { return false }
            if minReviews > 0, t.rt.criticScore != nil, (t.rt.criticCount ?? 0) < minReviews { return false }
            if certifiedOnly && !t.rt.isCertified { return false }
            if let genre, !t.genres.contains(genre) { return false }
            if let yearKey, (t.releaseKey ?? "") < yearKey { return false }
            if let addedKeyMin {
                guard let ak = t.addedKey(services: onlyService), ak >= addedKeyMin else { return false }
            }
            if !q.isEmpty && !t.title.lowercased().contains(q) && !(t.originalTitle ?? "").lowercased().contains(q) { return false }
            return true
        }
        let count = { (t: Title) in t.rt.criticCount ?? 0 }
        func desc(_ a: Int?, _ b: Int?) -> Bool? { let x = a ?? -1, y = b ?? -1; return x == y ? nil : x > y }
        out.sort { a, b in
            switch sort {
            case .critic: return desc(a.rt.criticScore, b.rt.criticScore) ?? (count(a) > count(b))
            case .audience: return desc(a.rt.audienceScore, b.rt.audienceScore) ?? (count(a) > count(b))
            case .combined:
                let x = a.combinedScore ?? -1, y = b.combinedScore ?? -1
                return x == y ? count(a) > count(b) : x > y
            case .reviews: return count(a) == count(b) ? (a.rt.criticScore ?? -1) > (b.rt.criticScore ?? -1) : count(a) > count(b)
            case .added:
                let x = a.addedKey(services: onlyService) ?? "", y = b.addedKey(services: onlyService) ?? ""
                return x == y ? (a.rt.criticScore ?? -1) > (b.rt.criticScore ?? -1) : x > y
            case .newest: return desc(a.year, b.year) ?? (count(a) > count(b))
            case .oldest: return (a.year ?? 9999) == (b.year ?? 9999) ? count(a) > count(b) : (a.year ?? 9999) < (b.year ?? 9999)
            case .title: return a.title.localizedCaseInsensitiveCompare(b.title) == .orderedAscending
            }
        }
        return out
    }

    static func isoDay(_ date: Date) -> String {
        let f = DateFormatter()
        f.calendar = Calendar(identifier: .gregorian)
        f.locale = Locale(identifier: "en_US_POSIX")
        f.dateFormat = "yyyy-MM-dd"
        return f.string(from: date)
    }
}
