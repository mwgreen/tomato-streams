import SwiftUI

/// Full-screen title page. The first focus lands on the first "Watch on" button so
/// play is one click away; everything else is secondary.
struct DetailView: View {
    let title: Title
    @EnvironmentObject var store: CatalogStore
    @EnvironmentObject var hidden: HiddenStore
    @EnvironmentObject var watched: WatchedStore
    @State private var opening: String?
    @State private var openFailed: String?
    @FocusState private var focusedService: String?

    private var current: Title { store.current(title) }

    var body: some View {
        ZStack(alignment: .topLeading) {
            backdrop
            ScrollView {
                HStack(alignment: .top, spacing: 60) {
                    PosterImage(url: current.posterLarge ?? current.poster, title: current.title)
                        .frame(width: 400, height: 600)
                        .clipShape(RoundedRectangle(cornerRadius: 16))
                        .shadow(radius: 30)
                    VStack(alignment: .leading, spacing: 22) {
                        Text(current.title).font(.system(size: 56, weight: .bold)).lineLimit(2)
                        Text(meta).font(.title3).foregroundStyle(.secondary)
                        HStack(spacing: 40) {
                            VStack(alignment: .leading, spacing: 4) {
                                ScoreBadge(kind: .critic, rt: current.rt, showCount: true, large: true)
                                Text(current.rt.isCertified ? "Certified Fresh" : "Tomatometer").font(.caption).foregroundStyle(.secondary)
                            }
                            VStack(alignment: .leading, spacing: 4) {
                                ScoreBadge(kind: .audience, rt: current.rt, showCount: true, large: true)
                                Text("Audience").font(.caption).foregroundStyle(.secondary)
                            }
                        }
                        watchButtons
                        watchedRow
                        if let openFailed {
                            Text(openFailed).font(.callout).foregroundStyle(.orange)
                        }
                        Text(current.overview?.isEmpty == false ? current.overview! : "No description available.")
                            .font(.body).lineLimit(8).frame(maxWidth: 900, alignment: .leading)
                        addedLine
                        HStack(spacing: 20) {
                            if current.trailerYoutubeKey != nil {
                                Button { openTrailer() } label: { Label("Trailer", systemImage: "play.rectangle") }
                            }
                            Button { hidden.toggle(current) } label: {
                                Label(hidden.contains(current) ? "Un-hide" : "Hide title", systemImage: hidden.contains(current) ? "eye" : "eye.slash")
                            }
                        }
                        .padding(.top, 10)
                    }
                    Spacer(minLength: 0)
                }
                .padding(.horizontal, 90).padding(.top, 120).padding(.bottom, 80)
            }
        }
        .ignoresSafeArea()
        .task {
            await store.fetchWatchLinks(for: title)
            if focusedService == nil { focusedService = current.services.first }
        }
    }

    private var meta: String {
        var parts = [current.yearsLabel, current.lengthLabel]
        if current.isTV, let n = current.episodes { parts.append("\(n) episodes") }
        if current.isTV, let s = current.status { parts.append(s) }
        parts.append(current.genres.joined(separator: ", "))
        return parts.filter { !$0.isEmpty }.joined(separator: " · ")
    }

    private var backdrop: some View {
        GeometryReader { geo in
            AsyncImage(url: current.backdrop.flatMap(URL.init(string:))) { phase in
                if case .success(let image) = phase { image.resizable().aspectRatio(contentMode: .fill) } else { Color.black }
            }
            .frame(width: geo.size.width, height: geo.size.height)
            .overlay(LinearGradient(colors: [.black.opacity(0.55), .black.opacity(0.85), .black], startPoint: .top, endPoint: .bottom))
        }
    }

    private var watchButtons: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 20) {
                ForEach(current.services, id: \.self) { service in
                    Button { open(service) } label: {
                        VStack(spacing: 2) {
                            Label(opening == service ? "Opening…" : "Watch on \(service)", systemImage: "play.fill")
                            Text(DeepLinks.describe(service: service, title: current)).font(.caption2).foregroundStyle(.secondary)
                        }
                    }
                    .focused($focusedService, equals: service)
                    .disabled(opening != nil)
                }
            }
            if current.services.isEmpty {
                Text("Not on any of your services right now.").foregroundStyle(.secondary)
            }
        }
    }

    /// One toggle per person: "✓ Matt" when they have seen it.
    private var watchedRow: some View {
        HStack(spacing: 14) {
            Text("Watched by").foregroundStyle(.secondary)
            if watched.people.isEmpty {
                Text("add people in Settings").font(.callout).foregroundStyle(.tertiary)
            }
            ForEach(watched.people, id: \.self) { person in
                let seen = watched.isWatched(current, by: person)
                Button { Task { await watched.toggle(current, person: person) } } label: {
                    Label(person, systemImage: seen ? "checkmark.circle.fill" : "circle")
                        .foregroundStyle(seen ? .green : .primary)
                }
            }
            if let err = watched.lastError { Text(err).font(.caption).foregroundStyle(.orange) }
        }
        .font(.callout)
    }

    private var addedLine: some View {
        let lines = current.added.sorted { $0.key < $1.key }.map { "\($0.key): \($0.value)" }
        let release = current.releaseDate.map { "\(current.isTV ? "First aired" : "Released") \($0)" }
        return Text([release, lines.isEmpty ? nil : "Added to " + lines.joined(separator: " · ")].compactMap { $0 }.joined(separator: "   ·   "))
            .font(.caption).foregroundStyle(.secondary)
    }

    private func open(_ service: String) {
        opening = service
        openFailed = nil
        DeepLinks.open(service: service, title: current) { url in
            opening = nil
            if url == nil {
                openFailed = "\(service) does not seem to be installed on this Apple TV."
            }
        }
    }

    private func openTrailer() {
        guard let key = current.trailerYoutubeKey else { return }
        // youtube://watch/<id> is what the tvOS YouTube app accepts; the others are fallbacks.
        let candidates = ["youtube://watch/\(key)", "youtube://watch?v=\(key)", "https://www.youtube.com/watch?v=\(key)"].compactMap(URL.init(string:))
        func attempt(_ i: Int) {
            guard i < candidates.count else { openFailed = "YouTube is not installed on this Apple TV."; return }
            UIApplication.shared.open(candidates[i], options: [:]) { ok in if !ok { attempt(i + 1) } }
        }
        attempt(0)
    }
}
