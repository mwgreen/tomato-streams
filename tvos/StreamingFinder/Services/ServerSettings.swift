import Foundation
import Network

/// Where serve.py lives, plus Bonjour discovery so nobody has to type an address on a TV.
@MainActor
final class ServerSettings: ObservableObject {
    @Published var serverURL: String {
        didSet { UserDefaults.standard.set(serverURL, forKey: "serverURL") }
    }
    @Published var hideNoScore: Bool {
        didSet { UserDefaults.standard.set(hideNoScore, forKey: "hideNoScore") }
    }
    @Published var showHidden: Bool {
        didSet { UserDefaults.standard.set(showHidden, forKey: "showHidden") }
    }
    /// Servers found on the LAN, as base URLs.
    @Published private(set) var discovered: [String] = []
    @Published private(set) var isBrowsing = false

    private var browser: NWBrowser?

    init() {
        serverURL = UserDefaults.standard.string(forKey: "serverURL") ?? ""
        hideNoScore = UserDefaults.standard.object(forKey: "hideNoScore") as? Bool ?? true
        showHidden = UserDefaults.standard.bool(forKey: "showHidden")
    }

    /// Normalised base URL ("http://host:port"), or nil if unset / invalid.
    var baseURL: URL? {
        var text = serverURL.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return nil }
        if !text.lowercased().hasPrefix("http") { text = "http://" + text }
        while text.hasSuffix("/") { text.removeLast() }
        return URL(string: text)
    }

    func url(_ path: String) -> URL? {
        guard let base = baseURL else { return nil }
        return URL(string: base.absoluteString + "/" + path)
    }

    /// GET /api/ping on a candidate address.
    func ping(_ base: String) async -> Bool {
        var text = base.trimmingCharacters(in: .whitespaces)
        if !text.lowercased().hasPrefix("http") { text = "http://" + text }
        while text.hasSuffix("/") { text.removeLast() }
        guard let url = URL(string: text + "/api/ping") else { return false }
        var req = URLRequest(url: url)
        req.timeoutInterval = 6
        guard let (data, resp) = try? await URLSession.shared.data(for: req),
              (resp as? HTTPURLResponse)?.statusCode == 200,
              let body = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else { return false }
        return body["app"] as? String == "streaming-finder"
    }

    // MARK: Bonjour

    /// Look for serve.py instances advertising `_streamingfinder._tcp` (needs `pip install zeroconf` on the server).
    func startBrowsing() {
        stopBrowsing()
        let params = NWParameters.tcp
        params.includePeerToPeer = true
        // The TXT record carries the server's url; plain `.bonjour` results come back without it.
        let browser = NWBrowser(for: .bonjourWithTXTRecord(type: "_streamingfinder._tcp", domain: nil), using: params)
        browser.browseResultsChangedHandler = { [weak self] results, _ in
            let urls: [String] = results.compactMap { result in
                if case .bonjour(let txt) = result.metadata, let url = txt["url"], !url.isEmpty { return url }
                return nil
            }
            Task { @MainActor in self?.discovered = Array(Set(urls)).sorted() }
        }
        browser.stateUpdateHandler = { [weak self] state in
            Task { @MainActor in
                switch state {
                case .ready: self?.isBrowsing = true
                case .failed, .cancelled: self?.isBrowsing = false
                default: break
                }
            }
        }
        browser.start(queue: .main)
        self.browser = browser
    }

    func stopBrowsing() {
        browser?.cancel()
        browser = nil
        isBrowsing = false
    }
}

/// Titles the user hid with the remote, stored locally on the Apple TV.
@MainActor
final class HiddenStore: ObservableObject {
    @Published private(set) var ids: Set<String> {
        didSet { UserDefaults.standard.set(Array(ids), forKey: "hiddenTitles") }
    }

    init() { ids = Set(UserDefaults.standard.stringArray(forKey: "hiddenTitles") ?? []) }

    func contains(_ title: Title) -> Bool { ids.contains(title.id) }
    func toggle(_ title: Title) { if ids.contains(title.id) { ids.remove(title.id) } else { ids.insert(title.id) } }
    func clear() { ids = [] }
}
