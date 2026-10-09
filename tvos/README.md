# Streaming Finder for Apple TV

A native tvOS companion to the web app. It reads the same `data/movies.json` and
`data/tv.json` from `serve.py`, so the library, scores, services and filters match,
and a press on **Watch on <service>** launches that service's Apple TV app.

## Requirements

- A Mac with Xcode 16 or newer (the app targets tvOS 17+, SwiftUI only, no packages).
- An Apple developer account. The free one installs to your own Apple TV for 7 days at
  a time; the paid one ($99/yr) keeps it installed for a year or via TestFlight.
- `serve.py` running on a computer on the same network, started with `--host 0.0.0.0`.
  Install `zeroconf` (`pip install zeroconf`) on that computer and the Apple TV finds it
  automatically; otherwise type its address once in Settings.

## Build

The Xcode project is generated from `project.yml` with [XcodeGen](https://github.com/yonaskolb/XcodeGen):

```sh
brew install xcodegen
cd tvos
xcodegen generate
open StreamingFinder.xcodeproj
```

In Xcode: select the StreamingFinder target → Signing & Capabilities → pick your Team
(and change the bundle id from `com.example.streamingfinder` if Xcode asks). Choose an
Apple TV (paired over the Devices window, or the simulator) and Run.

Without XcodeGen: File → New → Project → tvOS App (SwiftUI), name it StreamingFinder,
delete its ContentView, drag the `StreamingFinder/` folder in, and copy the
`info.properties` keys from `project.yml` into the target's Info tab (the App Transport
Security, Bonjour and `LSApplicationQueriesSchemes` entries matter).

### Install on the Apple TV from the terminal

Once Xcode is signed in (Settings → Accounts) and the Apple TV is paired (Window →
Devices and Simulators), this builds, signs, installs and launches without the Xcode UI.
It is also how to renew the free-team install, which expires after 7 days:

```sh
tvos/install-appletv.sh                    # default device: "Entertainment Room"
tvos/install-appletv.sh "Living Room"      # another paired Apple TV
```

The team id and bundle id live in `project.yml`, so regenerating the project keeps them.

### Keeping it installed (atvloadly on sanctarus)

The free-team profile lasts 7 days. Signing and reinstalling run on sanctarus with
[atvloadly](https://github.com/bitxeno/atvloadly), set up alongside TabloTV (see
tablo-proxy's `tvos/README.md`), and it re-signs the app in the early hours once it's within 3 days of expiring. A push to main that touches
`tvos/` runs `.github/workflows/tvos-ipa.yml`, which builds an unsigned IPA
(`tvos/scripts/build-ipa.sh`) and publishes it as a `tvos-N` release. atvloadly picks
the release up within 6 hours. atvloadly installs the app as
`com.mwgreen.streamingfinder.<TEAM_ID>`, a separate app from the one
`install-appletv.sh` installs.

## Using it

- **Movies / TV Series** tabs: two rows of filters above a poster grid. The first row
  is inline toggles, one per service and one per person ("Hide watched by"): a press
  flips a chip and nothing closes, so several services are several presses. The second
  row holds the single-choice filters as menus (minimum critic and audience score,
  Certified Fresh, genre, year, recently added, sort): click to open, click to pick.
  Filters are remembered.
- **Poster** → the title page: scores, description, where it is, and a **Watch on**
  button per service. The first Watch button has focus when the page opens, so
  Play → Play gets you into the show.
- **Search** tab: type or dictate a title (hold the Siri button).
- **Settings**: server address (pick a discovered one or type it), refresh, hide-no-score
  and show-hidden switches, and which streaming apps are installed.
- **Hide title** on the title page keeps a title out of the grid (local to the Apple TV).
- **Watched by**: add people under Settings → People, mark a title on its page with the
  "Watched by" buttons, and use the "Watched" chip on the Movies / TV tabs to hide what
  a person (or anyone) has seen. The list is shared with the web app via `serve.py`.

## How "Watch on" works, and what to do when it doesn't

tvOS has no browser, so the app can't open an `https://` link the way the phone does.
Each streaming app has its own URL scheme, and `StreamingFinder/Services/DeepLinks.swift`
turns the web link we have into that scheme's form, e.g.
`https://www.netflix.com/title/60020810` → `nflx://www.netflix.com/title/60020810`.
It tries, in order: an app link from the JSON if there is one, the scheme rewrite of
the web link, the web link itself for services whose app handles it (Apple TV), and
finally the app's home screen. Settings shows which apps answered as installed.

The schemes are undocumented and change. If a service opens to its home screen instead
of the title, the rewrite for that service in `DeepLinks.swift` needs updating; the
Home Assistant community keeps a running list of what works
(https://community.home-assistant.io/t/appletv-integration-deep-link-urls-which-are-working/592862).
A quick way to find a working link is the Share → Copy Link feature in the service's
iPhone app.

Exact links (rather than the service's search) need `WATCHMODE_API_KEY` on the server;
the title page asks `serve.py` for them the first time it opens, exactly like the web app.

## Notes

- This code was written without access to Xcode, so expect to fix a few compile-time
  nits on first build; the structure is deliberately plain SwiftUI.
- The app never sees any API key. It only talks to `serve.py`.
- The app icon (a layered tomato, so it tilts in 3D on focus) and the Top Shelf banners
  are drawn by `icon/make_icon.swift` into `StreamingFinder/Assets.xcassets`. Change the
  colours or proportions there and run `swift icon/make_icon.swift` from `tvos/`.
