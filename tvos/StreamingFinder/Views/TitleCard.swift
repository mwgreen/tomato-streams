import SwiftUI
import UIKit

/// Poster card for the browse grid. The poster is the focusable element (tvOS card style
/// gives it the lift-and-parallax); title, scores and services sit underneath.
struct TitleCard: View {
    let title: Title
    var isNew = false
    var isHidden = false
    var watchedBy: [String] = []

    static let posterWidth: CGFloat = 250
    static var posterHeight: CGFloat { posterWidth * 1.5 }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            NavigationLink(value: title) {
                PosterImage(url: title.poster, title: title.title)
                    .frame(width: Self.posterWidth, height: Self.posterHeight)
                    .overlay(alignment: .topTrailing) {
                        if isNew {
                            Text("NEW").font(.caption2.bold()).padding(.horizontal, 8).padding(.vertical, 4)
                                .background(.yellow, in: Capsule()).foregroundStyle(.black).padding(10)
                        }
                    }
            }
            .buttonStyle(.card)
            .opacity(isHidden ? 0.45 : 1)

            VStack(alignment: .leading, spacing: 4) {
                Text(title.title).font(.callout.weight(.semibold)).lineLimit(1)
                Text(title.metaLine).font(.caption).foregroundStyle(.secondary).lineLimit(1)
                HStack(spacing: 14) {
                    ScoreBadge(kind: .critic, rt: title.rt)
                    ScoreBadge(kind: .audience, rt: title.rt)
                }
                HStack(spacing: 6) {
                    ForEach(title.services.prefix(3), id: \.self) { ServiceBadge(name: $0) }
                }
                if !watchedBy.isEmpty {
                    Label(watchedBy.joined(separator: ", "), systemImage: "checkmark.circle.fill")
                        .font(.caption).foregroundStyle(.green).lineLimit(1)
                }
            }
            .frame(width: Self.posterWidth, alignment: .leading)
        }
    }
}

/// Poster with retry and an in-memory cache. AsyncImage is not used here: it shows its
/// failure state for good once a load fails *or is cancelled*, which happened to the first
/// rows whenever the grid redrew while the catalogs were still downloading.
struct PosterImage: View {
    let url: String?
    let title: String
    @State private var image: UIImage?
    @State private var gaveUp = false

    var body: some View {
        ZStack {
            if let image {
                Image(uiImage: image).resizable().aspectRatio(contentMode: .fill)
            } else {
                placeholder.overlay { if !gaveUp && url != nil { ProgressView() } }
            }
        }
        .clipped()
        .task(id: url) { await load() }
    }

    private func load() async {
        guard let url, let target = URL(string: url) else { gaveUp = true; return }
        if let cached = PosterCache.shared.object(forKey: url as NSString) { image = cached; return }
        image = nil
        gaveUp = false
        for attempt in 1...3 {
            if Task.isCancelled { return }  // view went away; .task runs again when it comes back
            if let (data, resp) = try? await URLSession.shared.data(from: target),
               (resp as? HTTPURLResponse)?.statusCode == 200, let loaded = UIImage(data: data) {
                PosterCache.shared.setObject(loaded, forKey: url as NSString)
                image = loaded
                return
            }
            try? await Task.sleep(for: .seconds(Double(attempt)))
        }
        if !Task.isCancelled { gaveUp = true }
    }

    private var placeholder: some View {
        ZStack {
            Color(white: 0.12)
            Text(title).font(.callout).foregroundStyle(.secondary).multilineTextAlignment(.center).padding()
        }
    }
}

/// Decoded posters shared by every card and the detail page.
enum PosterCache {
    static let shared: NSCache<NSString, UIImage> = {
        let cache = NSCache<NSString, UIImage>()
        cache.countLimit = 600
        return cache
    }()
}
