import SwiftUI

/// Poster card for the browse grid. The poster is the focusable element (tvOS card style
/// gives it the lift-and-parallax); title, scores and services sit underneath.
struct TitleCard: View {
    let title: Title
    var isNew = false
    var isHidden = false

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
            }
            .frame(width: Self.posterWidth, alignment: .leading)
        }
    }
}

struct PosterImage: View {
    let url: String?
    let title: String

    var body: some View {
        AsyncImage(url: url.flatMap(URL.init(string:))) { phase in
            switch phase {
            case .success(let image):
                image.resizable().aspectRatio(contentMode: .fill)
            case .failure:
                placeholder
            default:
                placeholder.overlay(ProgressView())
            }
        }
        .clipped()
    }

    private var placeholder: some View {
        ZStack {
            Color(white: 0.12)
            Text(title).font(.callout).foregroundStyle(.secondary).multilineTextAlignment(.center).padding()
        }
    }
}
