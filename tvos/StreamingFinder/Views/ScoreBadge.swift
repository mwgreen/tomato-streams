import SwiftUI

/// Tomatometer / Popcornmeter pill, colour-coded like the web app.
struct ScoreBadge: View {
    enum Kind { case critic, audience }
    let kind: Kind
    let rt: RTScores
    var showCount = false
    var large = false

    private var score: Int? { kind == .critic ? rt.criticScore : rt.audienceScore }

    private var symbol: String {
        switch kind {
        case .critic:
            if score == nil { return "circle.dashed" }
            return rt.isCertified ? "checkmark.seal.fill" : (score! >= 60 ? "leaf.fill" : "drop.fill")
        case .audience:
            if score == nil { return "circle.dashed" }
            return score! >= 60 ? "popcorn.fill" : "popcorn"
        }
    }

    private var tint: Color {
        guard let score else { return .secondary }
        if kind == .critic { return rt.isCertified ? .red : (score >= 60 ? .red : .green) }
        return score >= 60 ? .orange : .green
    }

    private var countText: String? {
        guard showCount else { return nil }
        if kind == .critic, let n = rt.criticCount { return "\(n)" }
        if kind == .audience, let s = rt.audienceCount { return s }
        return nil
    }

    var body: some View {
        HStack(spacing: 6) {
            Image(systemName: symbol).foregroundStyle(tint)
            Text(score.map { "\($0)%" } ?? "–").fontWeight(.bold)
                .lineLimit(1).fixedSize()   // never split "100%" across lines on narrow cards
            if let countText { Text(countText).font(large ? .callout : .caption).foregroundStyle(.secondary) }
        }
        .font(large ? .title2 : .callout)
        .accessibilityLabel(kind == .critic ? "Critic score" : "Audience score")
    }
}

/// Small coloured service chip.
struct ServiceBadge: View {
    let name: String
    var large = false

    static let colors: [String: Color] = [
        "netflix": Color(red: 0.55, green: 0.10, blue: 0.13),
        "prime-video": Color(red: 0.06, green: 0.30, blue: 0.45),
        "apple-tv": Color(white: 0.25),
        "hbo-max": Color(red: 0.25, green: 0.13, blue: 0.50),
        "hulu": Color(red: 0.06, green: 0.36, blue: 0.20),
        "disney": Color(red: 0.08, green: 0.18, blue: 0.42),
        "paramount": Color(red: 0.05, green: 0.22, blue: 0.42),
        "peacock": Color(red: 0.35, green: 0.25, blue: 0.05),
        "starz": Color(white: 0.15),
    ]

    var body: some View {
        Text(name)
            .font(large ? .callout.weight(.semibold) : .caption2.weight(.semibold))
            .padding(.horizontal, large ? 12 : 8).padding(.vertical, large ? 6 : 3)
            .background(Self.colors[DeepLinks.slug(name)] ?? Color(white: 0.25), in: Capsule())
            .foregroundStyle(.white)
    }
}
