import Foundation

/// People and "watched by" marks, shared with the web app through serve.py
/// (GET/POST /api/watched, POST /api/people). Cached locally so the grid can filter offline.
@MainActor
final class WatchedStore: ObservableObject {
    struct Snapshot: Codable {
        var people: [String] = []
        var watched: [String: [String: String]] = [:]   // title id -> person -> date
    }

    @Published private(set) var people: [String] = []
    @Published private(set) var watched: [String: [String: String]] = [:]
    @Published private(set) var lastError: String?

    private let settings: ServerSettings
    private let cacheKey = "watched.snapshot"

    init(settings: ServerSettings) {
        self.settings = settings
        if let data = UserDefaults.standard.data(forKey: cacheKey),
           let snap = try? JSONDecoder().decode(Snapshot.self, from: data) {
            apply(snap)
        }
    }

    func watchedBy(_ title: Title) -> [String] {
        (watched[title.id] ?? [:]).keys.sorted { $0.localizedCaseInsensitiveCompare($1) == .orderedAscending }
    }

    func isWatched(_ title: Title, by person: String) -> Bool {
        watched[title.id]?[person] != nil
    }

    /// GET /api/watched.
    func load() async {
        guard let url = settings.url("api/watched") else { return }
        var req = URLRequest(url: url)
        req.timeoutInterval = 15
        req.cachePolicy = .reloadIgnoringLocalCacheData
        guard let (data, resp) = try? await URLSession.shared.data(for: req),
              (resp as? HTTPURLResponse)?.statusCode == 200,
              let snap = try? JSONDecoder().decode(Snapshot.self, from: data) else { return }
        apply(snap)
    }

    func toggle(_ title: Title, person: String) async {
        let now = !isWatched(title, by: person)
        // optimistic
        var marks = watched[title.id] ?? [:]
        if now { marks[person] = Filters.isoDay(Date()) } else { marks[person] = nil }
        watched[title.id] = marks.isEmpty ? nil : marks
        persist()
        await post("api/watched", ["id": title.id, "person": person, "watched": now])
    }

    func addPerson(_ name: String) async {
        let n = name.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !n.isEmpty, !people.contains(where: { $0.caseInsensitiveCompare(n) == .orderedSame }) else { return }
        people.append(n)
        persist()
        await post("api/people", ["add": n])
    }

    func removePerson(_ name: String) async {
        people.removeAll { $0 == name }
        for (id, marks) in watched {
            var m = marks
            m[name] = nil
            watched[id] = m.isEmpty ? nil : m
        }
        persist()
        await post("api/people", ["remove": name])
    }

    // MARK: private

    private func apply(_ snap: Snapshot) {
        people = snap.people
        watched = snap.watched
        persist()
    }

    private func persist() {
        if let data = try? JSONEncoder().encode(Snapshot(people: people, watched: watched)) {
            UserDefaults.standard.set(data, forKey: cacheKey)
        }
    }

    /// POST JSON; on success the server's snapshot replaces ours.
    private func post(_ path: String, _ body: [String: Any]) async {
        guard let url = settings.url(path) else { lastError = "No server address set."; return }
        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        req.timeoutInterval = 15
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = try? JSONSerialization.data(withJSONObject: body)
        do {
            let (data, resp) = try await URLSession.shared.data(for: req)
            let status = (resp as? HTTPURLResponse)?.statusCode ?? 0
            if status == 200, let snap = try? JSONDecoder().decode(Snapshot.self, from: data) {
                apply(snap)
                lastError = nil
            } else {
                let msg = (try? JSONSerialization.jsonObject(with: data) as? [String: Any])?["error"] as? String
                lastError = msg ?? "Server answered HTTP \(status)"
            }
        } catch {
            lastError = "Could not reach the server; change kept on this Apple TV only."
        }
    }
}
