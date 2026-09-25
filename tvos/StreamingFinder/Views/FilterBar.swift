import SwiftUI

/// A row of drop-down chips. On the TV a menu of a handful of choices beats sliders and
/// text fields: one click opens it, one click picks.
struct FilterBar: View {
    @Binding var filters: Filters
    let services: [String]
    let genres: [String]
    let kind: Kind

    var body: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 16) {
                chipMenu(label: filters.service ?? "All services", icon: "tv") {
                    choice("All services", selected: filters.service == nil) { filters.service = nil }
                    ForEach(services, id: \.self) { s in
                        choice(s, selected: filters.service == s) { filters.service = s }
                    }
                }
                chipMenu(label: filters.minCritic == 0 ? "Any critic score" : "Critics ≥ \(filters.minCritic)%", icon: "leaf") {
                    ForEach(Filters.scoreSteps, id: \.self) { n in
                        choice(n == 0 ? "Any" : "≥ \(n)%", selected: filters.minCritic == n) { filters.minCritic = n }
                    }
                }
                chipMenu(label: filters.minAudience == 0 ? "Any audience score" : "Audience ≥ \(filters.minAudience)%", icon: "popcorn") {
                    ForEach(Filters.scoreSteps, id: \.self) { n in
                        choice(n == 0 ? "Any" : "≥ \(n)%", selected: filters.minAudience == n) { filters.minAudience = n }
                    }
                }
                Button {
                    filters.certifiedOnly.toggle()
                } label: {
                    Label("Certified Fresh", systemImage: filters.certifiedOnly ? "checkmark.seal.fill" : "seal")
                }
                chipMenu(label: filters.genre ?? "Any genre", icon: "theatermasks") {
                    choice("Any genre", selected: filters.genre == nil) { filters.genre = nil }
                    ForEach(genres, id: \.self) { g in
                        choice(g, selected: filters.genre == g) { filters.genre = g }
                    }
                }
                chipMenu(label: filters.yearFrom.map { "\(kind == .tv ? "Aired" : "Released") \($0)+" } ?? "Any year", icon: "calendar") {
                    ForEach(Array(Filters.yearSteps.enumerated()), id: \.offset) { _, y in
                        choice(y.map { "\($0) or later" } ?? "Any year", selected: filters.yearFrom == y) { filters.yearFrom = y }
                    }
                }
                chipMenu(label: filters.addedWithinDays.map { "Added in last \($0) days" } ?? "Added any time", icon: "sparkles") {
                    ForEach(Array(Filters.addedSteps.enumerated()), id: \.offset) { _, d in
                        choice(d.map { "Last \($0) days" } ?? "Any time", selected: filters.addedWithinDays == d) { filters.addedWithinDays = d }
                    }
                }
                chipMenu(label: "Sort: \(filters.sort.label)", icon: "arrow.up.arrow.down") {
                    ForEach(SortKey.allCases) { s in
                        choice(s.label, selected: filters.sort == s) { filters.sort = s }
                    }
                }
                if !filters.isDefault {
                    Button { filters = Filters() } label: { Label("Reset", systemImage: "arrow.counterclockwise") }
                }
            }
            .padding(.horizontal, 4).padding(.vertical, 8)
        }
        .focusSection()
    }

    @ViewBuilder
    private func chipMenu<Content: View>(label: String, icon: String, @ViewBuilder content: () -> Content) -> some View {
        Menu {
            content()
        } label: {
            Label(label, systemImage: icon).lineLimit(1)
        }
    }

    private func choice(_ text: String, selected: Bool, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Label(text, systemImage: selected ? "checkmark.circle.fill" : "circle")
        }
    }
}
