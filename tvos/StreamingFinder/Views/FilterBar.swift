import SwiftUI

/// Two rows of filter controls above the grid.
///
/// Row 1 is multi-select and inline: one chip per service and, when people exist, one
/// per person. A press toggles the chip and nothing closes or moves, so picking three
/// services is three presses on a row you can see. Row 2 holds the single-choice
/// filters as menus (score, genre, year, added, sort): click to open, click to pick.
struct FilterBar: View {
    @Binding var filters: Filters
    let services: [String]
    let genres: [String]
    var people: [String] = []
    let kind: Kind

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 14) {
                    Text("On").foregroundStyle(.secondary)
                    ToggleChip(title: "All services", isOn: filters.services.isEmpty) { filters.services = [] }
                    ForEach(services, id: \.self) { s in
                        ToggleChip(title: s, isOn: filters.services.contains(s)) {
                            if filters.services.contains(s) { filters.services.remove(s) } else { filters.services.insert(s) }
                        }
                    }
                    if !people.isEmpty {
                        Divider().frame(height: 40).padding(.horizontal, 6)
                        Text("Hide watched by").foregroundStyle(.secondary)
                        ForEach(people, id: \.self) { person in
                            ToggleChip(title: person, icon: "eye.slash", isOn: filters.hideWatchedBy.contains(person)) {
                                if filters.hideWatchedBy.contains(person) { filters.hideWatchedBy.remove(person) } else { filters.hideWatchedBy.insert(person) }
                            }
                        }
                    }
                }
                .padding(.horizontal, 4).padding(.vertical, 6)
            }
            .focusSection()

            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 16) {
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
                    ToggleChip(title: "Certified Fresh", icon: "checkmark.seal.fill", isOn: filters.certifiedOnly) { filters.certifiedOnly.toggle() }
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
                .padding(.horizontal, 4).padding(.vertical, 6)
            }
            .focusSection()
        }
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

/// An on/off chip that stays put when pressed. The same Button is kept in both states
/// (only its label changes) so focus never jumps after a press.
struct ToggleChip: View {
    let title: String
    var icon: String? = nil
    let isOn: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: 8) {
                Image(systemName: isOn ? "checkmark.circle.fill" : (icon ?? "circle"))
                    .foregroundStyle(isOn ? Color.green : Color.secondary)
                Text(title).fontWeight(isOn ? .semibold : .regular)
            }
            .lineLimit(1)
        }
        .accessibilityAddTraits(isOn ? .isSelected : [])
    }
}
