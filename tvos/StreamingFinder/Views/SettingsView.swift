import SwiftUI

struct SettingsView: View {
    @EnvironmentObject var settings: ServerSettings
    @EnvironmentObject var store: CatalogStore
    @EnvironmentObject var hidden: HiddenStore
    @State private var address = ""
    @State private var testResult: String?
    @State private var testing = false

    var body: some View {
        NavigationStack {
            Form {
                Section("Server") {
                    TextField("http://192.168.1.10:8000", text: $address)
                        .onSubmit { apply(address) }
                    HStack {
                        Button(testing ? "Testing…" : "Save & test") { apply(address) }.disabled(testing || address.isEmpty)
                        if let testResult { Text(testResult).foregroundStyle(.secondary) }
                    }
                    if !settings.discovered.isEmpty {
                        ForEach(settings.discovered, id: \.self) { url in
                            Button { apply(url) } label: {
                                Label("Use \(url)" + (url == settings.serverURL ? " (current)" : ""), systemImage: "antenna.radiowaves.left.and.right")
                            }
                        }
                    } else {
                        Text(settings.isBrowsing ? "Looking for serve.py on this network… (needs `pip install zeroconf` on the server)"
                                                 : "Run `python serve.py --host 0.0.0.0` on your computer.")
                            .font(.callout).foregroundStyle(.secondary)
                    }
                }
                Section("Data") {
                    LabeledContent("Movies", value: "\(store.titles(.movie).count)")
                    LabeledContent("TV series", value: "\(store.titles(.tv).count)")
                    LabeledContent("Last refresh", value: store.lastRefresh.map { $0.formatted(date: .abbreviated, time: .shortened) } ?? "never")
                    if let err = store.lastError { Text(err).foregroundStyle(.orange).font(.callout) }
                    Button(store.isRefreshing ? "Refreshing…" : "Refresh now") { Task { await store.refresh() } }.disabled(store.isRefreshing)
                }
                Section("Display") {
                    Toggle("Hide titles with no Rotten Tomatoes score", isOn: $settings.hideNoScore)
                    Toggle("Show hidden titles", isOn: $settings.showHidden)
                    Button("Un-hide all (\(hidden.ids.count))") { hidden.clear() }.disabled(hidden.ids.isEmpty)
                }
                Section("Streaming apps on this Apple TV") {
                    ForEach(allServices, id: \.self) { s in
                        LabeledContent(s, value: DeepLinks.isInstalled(service: s) ? "installed" : "not found")
                    }
                    Text("“Watch on” launches the service's app at the title where its link format is known (see DeepLinks.swift), otherwise the app's home screen.")
                        .font(.caption).foregroundStyle(.secondary)
                }
            }
            .navigationTitle("Settings")
        }
        .onAppear {
            address = settings.serverURL
            settings.startBrowsing()
        }
        .onDisappear { settings.stopBrowsing() }
    }

    private var allServices: [String] {
        Array(Set(store.services(.movie) + store.services(.tv))).sorted()
    }

    private func apply(_ url: String) {
        testing = true
        testResult = nil
        Task { @MainActor in
            let ok = await settings.ping(url)
            if ok {
                settings.serverURL = url
                address = url
                testResult = "Connected"
                await store.refresh()
            } else {
                testResult = "No Streaming Finder server answered at that address"
            }
            testing = false
        }
    }
}
