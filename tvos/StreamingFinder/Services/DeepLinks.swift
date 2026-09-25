import Foundation
import UIKit

/// Launching the streaming apps on tvOS.
///
/// There is no browser on Apple TV, so an https link does nothing unless the app itself
/// registered it. Each service's app has a URL scheme instead; the table below turns the
/// web link we have (from Watchmode, or the JSON's watch_urls) into that scheme's form.
/// Schemes are undocumented and change over time: edit `rules` when one stops working.
/// The last resort is launching the app to its home screen so the show is one search away.
enum DeepLinks {
    struct Rule {
        /// Scheme that opens the app's home screen, e.g. "nflx://".
        let home: String
        /// Alternative home schemes (older/newer app versions).
        var altHomes: [String] = []
        /// Regex on the web URL -> template with $1, $2 captures.
        var rewrites: [(pattern: String, template: String)] = []
        /// If true, also try the https URL itself (Apple's TV app handles tv.apple.com).
        var tryWeb: Bool = false
    }

    /// Keyed by service slug (see `slug(_:)`), same slugs as the web app's badges.
    static let rules: [String: Rule] = [
        "netflix": Rule(home: "nflx://", rewrites: [
            (#"netflix\.com/(?:title|watch)/(\d+)"#, "nflx://www.netflix.com/title/$1"),
        ]),
        "hulu": Rule(home: "hulu://", rewrites: [
            (#"hulu\.com/watch/([^/?#]+)"#, "hulu://w/$1"),
            (#"hulu\.com/series/[^/?#]*?([0-9a-f]{8}-[0-9a-f-]{27})"#, "hulu://series/$1"),
            (#"hulu\.com/movie/[^/?#]*?([0-9a-f]{8}-[0-9a-f-]{27})"#, "hulu://movie/$1"),
        ]),
        "disney": Rule(home: "disneyplus://", rewrites: [
            (#"disneyplus\.com(/[^?#]*)"#, "disneyplus://www.disneyplus.com$1"),
        ]),
        "hbo-max": Rule(home: "hbomax://", altHomes: ["max://"], rewrites: [
            (#"/movie/([0-9a-f-]{36})"#, "hbomax://feature/$1"),
            (#"/show/([0-9a-f-]{36})"#, "hbomax://series/$1"),
            (#"/video/watch/([0-9a-f-]{36})"#, "hbomax://episode/$1"),
        ]),
        "prime-video": Rule(home: "aiv://", rewrites: [
            (#"/detail/([A-Z0-9]{10})"#, "aiv://aiv/detail?asin=$1"),
        ]),
        "apple-tv": Rule(home: "videos://", altHomes: ["com.apple.tv://"], tryWeb: true),
        "paramount": Rule(home: "paramountplus://", altHomes: ["pplus://"], rewrites: [
            (#"paramountplus\.com(/[^?#]*)"#, "paramountplus://www.paramountplus.com$1"),
        ]),
        "peacock": Rule(home: "peacock://"),
        "starz": Rule(home: "starz://"),
        "amc": Rule(home: "amcplus://"),
        "mgm": Rule(home: "mgmplus://"),
        "criterion-channel": Rule(home: "criterionchannel://"),
        "mubi": Rule(home: "mubi://"),
        "britbox": Rule(home: "britbox://"),
        "acorn-tv": Rule(home: "acorntv://"),
        "shudder": Rule(home: "shudder://"),
        "crunchyroll": Rule(home: "crunchyroll://"),
        "hallmark": Rule(home: "hallmarkplus://"),
        "youtube-premium": Rule(home: "youtube://", rewrites: [
            (#"[?&]v=([A-Za-z0-9_-]{6,})"#, "youtube://watch?v=$1"),
        ]),
        "tubi": Rule(home: "tubitv://"),
        "pluto-tv": Rule(home: "plutotv://"),
    ]

    /// "Paramount+" -> "paramount", "Acorn TV" -> "acorn-tv" (same as the web app).
    static func slug(_ service: String) -> String {
        let folded = service.folding(options: [.diacriticInsensitive, .caseInsensitive], locale: .current)
            .replacingOccurrences(of: "+", with: "")
        var out = ""
        var dash = false
        for ch in folded.lowercased() {
            if ch.isLetter || ch.isNumber { out.append(ch); dash = false }
            else if !dash && !out.isEmpty { out.append("-"); dash = true }
        }
        while out.hasSuffix("-") { out.removeLast() }
        return out
    }

    /// Ordered URLs to try for a title on a service: JSON app link, scheme rewrites of the
    /// web link, the web link itself where the app handles it, then the app's home.
    static func candidates(service: String, title: Title) -> [URL] {
        var urls: [String] = []
        let rule = rules[slug(service)]
        if let app = title.watchAppUrls[service], app.contains("://") { urls.append(app) }
        if let web = title.watchUrls[service], let rule {
            for (pattern, template) in rule.rewrites {
                if let re = try? NSRegularExpression(pattern: pattern),
                   let m = re.firstMatch(in: web, range: NSRange(web.startIndex..., in: web)) {
                    var result = template
                    for i in 1..<max(1, m.numberOfRanges) {
                        if let r = Range(m.range(at: i), in: web) {
                            result = result.replacingOccurrences(of: "$\(i)", with: String(web[r]))
                        }
                    }
                    urls.append(result)
                    break
                }
            }
            if rule.tryWeb { urls.append(web) }
        }
        if let rule { urls.append(rule.home); urls.append(contentsOf: rule.altHomes) }
        var seen = Set<String>()
        return urls.compactMap { s in
            guard !seen.contains(s), let u = URL(string: s) else { return nil }
            seen.insert(s)
            return u
        }
    }

    /// True if the service's app is installed (its home scheme is openable).
    static func isInstalled(service: String) -> Bool {
        guard let rule = rules[slug(service)] else { return false }
        return ([rule.home] + rule.altHomes).contains { s in URL(string: s).map { UIApplication.shared.canOpenURL($0) } ?? false }
    }

    /// Try each candidate in turn; `completion` gets the URL that opened, or nil.
    static func open(service: String, title: Title, completion: @escaping (URL?) -> Void) {
        let list = candidates(service: service, title: title)
        func attempt(_ index: Int) {
            guard index < list.count else { completion(nil); return }
            let url = list[index]
            UIApplication.shared.open(url, options: [:]) { ok in
                if ok { completion(url) } else { attempt(index + 1) }
            }
        }
        attempt(0)
    }

    /// Where a press will land, for the button subtitle: "opens the title", "opens an episode",
    /// "opens the app" (no exact link).
    static func describe(service: String, title: Title) -> String {
        let exact = title.watchUrls[service] != nil || title.watchAppUrls[service] != nil
        if !exact { return "opens the app" }
        if title.watchUrlLevels[service] == "episode" { return "opens an episode" }
        return title.isTV ? "opens the series" : "opens the movie"
    }
}
