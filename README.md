# Streaming Finder

A small local web app that lists movies and TV series **included with your streaming
subscriptions** (no rentals or purchases) and shows each one with its poster, description,
the services it is on, the **Rotten Tomatoes critic score (Tomatometer)** and
**audience score (Popcornmeter)**. Filter and sort by score, service, genre, year and
runtime, in a poster grid or a compact list. Works on desktop and on an iPhone.

Rotten Tomatoes' own "Movies at Home" page mixes in rent/buy titles and its service
filter is unreliable. This app only shows titles TMDB/JustWatch list as `flatrate`
(subscription) on the services you configure.

```
sync.py  ──▶  data/movies.json + data/tv.json  ──▶  web/index.html (vanilla JS, no build step)
   │
   ├── TMDB       discover subscription titles + details, posters, trailers
   ├── OMDb       RT page URL + Tomatometer fallback (free tier, 1,000 req/day)
   └── RT page    critic score, review count, Certified Fresh, audience score
```

Everything fetched is cached under `cache/`, so re-running the sync is fast.
API keys are only used by `sync.py` and never reach the browser.

## Setup

1. **Get API keys** (both free):
   - TMDB: create an account at [themoviedb.org](https://www.themoviedb.org/), then
     Settings → API → request a key. Either the *API Key* (v3) or the
     *API Read Access Token* (v4) works.
   - OMDb: request a key at [omdbapi.com/apikey.aspx](https://www.omdbapi.com/apikey.aspx)
     (free tier: 1,000 requests/day). Optional but recommended, it finds RT pages
     more reliably than searching.
   - Watchmode: request a key at [api.watchmode.com/requestApiKey](https://api.watchmode.com/requestApiKey)
     (free plan: a few thousand requests/month). Optional: with it, the "Watch on
     <service>" buttons open the title itself instead of the service's search page.
2. **Install**:
   ```sh
   python3 -m venv .venv && source .venv/bin/activate   # optional
   pip install -r requirements.txt
   cp .env.example .env        # then fill in TMDB_API_KEY and OMDB_API_KEY
   ```
   Python 3.11 or newer is required.
3. **Verify service IDs**. TMDB identifies streaming services by numeric
   watch-provider IDs which differ per region. Check the ones in `config.yaml`:
   ```sh
   python sync.py --list-providers
   ```
   This prints every provider available in your region, marks the IDs already in
   `config.yaml`, and warns about any that don't exist. Edit `config.yaml` if needed.
4. **Sync and serve**:
   ```sh
   python sync.py              # first run can take a while (one polite RT request per title)
   python serve.py             # then open http://localhost:8000
   ```
   Movies are at `http://localhost:8000/web/` and TV series at
   `http://localhost:8000/web/?kind=tv` (the header has Movies / TV Series tabs).
   `python -m http.server` from the project root also works; open
   `http://localhost:8000/web/` in that case.

## Using it on an iPhone

The app is a plain web page, so the phone just needs to reach the computer that runs
`serve.py` over your home Wi-Fi:

1. Start the server listening on all interfaces:
   ```sh
   python serve.py --host 0.0.0.0
   ```
2. Find the computer's local IP address (macOS: System Settings → Wi-Fi → Details, or
   `ipconfig getifaddr en0`; Linux: `hostname -I`).
3. On the iPhone open `http://<that-ip>:8000` in Safari (both devices on the same Wi-Fi).
4. Optional: tap Share → **Add to Home Screen**. It then opens full-screen like an app,
   with its own icon. Filters slide in from the ☰ button; the × on a card hides a title.

Because the page only reads the JSON files, you can also copy the `web/` and `data/`
folders to any static host you control (a NAS, a private S3 bucket, GitHub Pages on a
private repo, etc.). Just keep `data/movies.json` private; it contains scraped RT data.

## Configuration (`config.yaml`)

```yaml
region: US
services:
  - name: HBO Max
    provider_ids: [1899]     # a service may have several IDs (e.g. ad-supported tiers)
    enabled: true
```

`config.yaml` ships with the services on Rotten Tomatoes' "Movies at Home" filter
(Netflix, Prime Video, Apple TV, HBO Max, Hulu, Disney+, Paramount+, Peacock; Fandango
at Home is rent/buy and deliberately left out) enabled, plus Starz, AMC+, MGM+,
Criterion Channel, Mubi, BritBox, Acorn TV, Shudder, Crunchyroll, Hallmark+, YouTube
Premium and the free Tubi / Pluto TV / Roku Channel entries disabled.

- **Enable a service**: set `enabled: true` on its entry, or append a new entry with
  its name and TMDB provider ID(s), then run `python sync.py`. The UI picks it up
  automatically: the service list, badges and filters all come from the JSON files.
- **Remove a service**: delete its entry, or set `enabled: false` to keep it around
  without syncing it. Re-run `python sync.py`.
- **Check the IDs first.** They are TMDB's usual US IDs but a wrong ID maps silently to
  a different provider, so run `python sync.py --list-providers peacock` (any name
  fragment works) and compare the `configured as` column with the provider names.
- **Free ad-supported services** (Tubi, Pluto TV, The Roku Channel) are filed by TMDB
  under the `free` monetization type rather than `flatrate`; add `free` to
  `sync.monetization_types` if you enable them. `rent` and `buy` are rejected on
  purpose.
- Only the exact IDs you list are matched. Amazon/Apple "Channel" variants such as
  "HBO Max Amazon Channel" are separate providers on TMDB and are ignored unless
  you add their IDs.
- `sync:` controls discovery breadth (`min_tmdb_vote_count`, `max_pages_per_service`),
  cache lifetimes (`cache_days_scores`, `cache_days_providers`) and the politeness
  delay for rottentomatoes.com requests.
- `tv:` enables the TV series sync (`data/tv.json`) and sets its own minimum TMDB vote
  count, since series collect fewer votes than movies. Series use the same service
  list; RT scores are the series-level (all seasons) Tomatometer and audience score.
- `ui_defaults:` sets the default minimum critic review count and sort order in the UI.

## `sync.py` options

| Flag | What it does |
| --- | --- |
| `--list-providers [NAME]` | Print TMDB watch providers for the configured region (optionally filtered by name) and exit |
| `--full` | Ignore the cache and re-fetch everything |
| `--kind movie` / `--kind tv` | Sync only movies or only TV series (default: both, if `tv.enabled`) |
| `--service "HBO Max"` | Sync one service (repeatable); other services keep their previous data |
| `--limit N` | Process at most N movies (handy for testing) |
| `--skip-scores` | TMDB only, don't contact OMDb / Rotten Tomatoes |
| `--watch-links` | Prefill exact Watchmode links for every title (default: on demand via `serve.py`) |
| `-v` | Debug logging |

The sync never stops on a single failure: each movie gets an `rt.status` of
`ok`, `not_found`, `no_scores` or `error`, and a summary at the end lists movies per
service, score coverage and failures. OMDb usage is tracked in
`cache/omdb_usage.json`; lookups pause near the daily limit and resume on the next run.

## Using the app

- **Movies / TV Series** tabs in the header switch between `data/movies.json` and
  `data/tv.json`. Series cards show the run of years (`2022–` while still airing),
  seasons and episode length.
- Every card and list row shows a colored badge for **each service the title is included
  with**; the Services filter lists the same badges with counts.
- **Grid / List** toggle: the list view is a compact sortable table (click the Title,
  Year, Critics, Reviews or Audience headers) that fits more titles on screen and works
  well on a phone.
- Filters: services (any checked service), min critic / audience score, min critic
  review count, Certified Fresh only, genres, release date range (type a year such as
  `2022` or a full date such as `2022-06-01`), "added to service on or after", max
  runtime, title search, and "hide titles with no RT score".
- **Added-to-service dates.** Neither TMDB nor OMDb say when a title joined a
  subscription service, so `sync.py` records the first date it sees each title on each
  service (`services_first_seen` in the cache, `added` in the JSON). Everything present
  on the very first sync gets that day's date and shows as "before <date>"; titles that
  appear on later syncs get their real arrival date, a **New** tag for 30 days, and can
  be sorted with "Recently added". Run the sync regularly (daily is cheap) for this to
  be useful; a title that leaves a service and returns counts as new again.
- Sort: critic score, audience score, combined average, critic review count, year, title.
  Ties are broken by review count.
- Click a card for the backdrop, full description, trailer, links to Rotten Tomatoes and
  JustWatch, and a button per service: **Watch on <service>** when an exact link to the
  title is known, **Find on <service>** when it falls back to the service's search. The service badges on
  cards and list rows are the same links. On an iPhone these open the service's native
  app when it is installed (Universal Links), otherwise its website.
- **Exact links** come from Watchmode when `WATCHMODE_API_KEY` is set. By default they
  are looked up **on demand**: when you open a title, the page asks `serve.py`
  (`/api/watch-links`), which calls Watchmode once for that title, stores the result in
  the same per-title cache `sync.py` uses, and the buttons flip from "Find on" to "Watch
  on" a moment later. Only titles you actually open use quota, and the next sync writes
  those links into the JSON. `python sync.py --watch-links` prefills every title instead
  (one request each) if you have the quota to spare.
  A lookup (by IMDb id, or TMDB id as a fallback) returns each service's own page for the
  title, e.g. `netflix.com/title/60020810`, plus the iOS deep link, stored as
  `watch_app_urls` for a future native app. Only subscription sources that match a
  configured service are kept; "Channel" bundles and rent/buy offers are ignored.
  Results are cached for `sync.cache_days_watch_links` days and re-fetched when a title
  gains a service that has no link yet. Usage is tracked in
  `cache/watchmode_usage.json` and lookups pause near the monthly limit. If Watchmode
  names a service differently from `config.yaml`, add the name under that service's
  `watchmode_names:`; the usual aliases (Max, Amazon Prime Video, Peacock Premium, ...)
  are built in. On-demand lookups need `serve.py` (it holds the key); on a plain static
  host the buttons use whatever links the last sync wrote, else search.
- **Series links.** Watchmode's link for a series often points at an episode rather
  than the show page. `SERIES_URL_RULES` in `lib/watchmode.py` rewrites such links to
  the show page where the URL allows it (Netflix, Paramount+); for the other services
  the show ID cannot be derived, so the episode link is kept (it still beats a search
  that lists every similarly named show) and the button says "episode" with a tooltip.
  The rules apply when links are read, so fixing a rule does not need new lookups.
- **Without a Watchmode key** the buttons open the service's *search* for the title.
  Those URL templates live in `web/watch-links.js`; edit that file if a service changes
  its site. The × on a card hides a title (stored in your browser); toggle
  "Show hidden" to bring them back.
- **Watched by.** Add the people in your household under "Watched by" in the sidebar,
  then on a title's detail page tap a name to mark it watched by them. Tick "Hide
  watched by <name>" to drop everything they have seen from the grid. People and marks
  are stored by `serve.py` in `data/watched.json`, so the Apple TV app and every phone
  see the same list; without a server the browser keeps its own copy.
- Filter, sort and view state lives in the URL hash, so views can be bookmarked. The
  Movies / TV Series tabs carry the current filters across, and the last selections are
  remembered in the browser, so reopening the page brings them back. "Reset filters"
  clears both.

## Apple TV app

`tvos/` holds a native SwiftUI companion app for Apple TV. It reads the same JSON from
`serve.py`, shows the same filters as a row of remote-friendly menus above a poster
grid, and a press on **Watch on <service>** launches that service's Apple TV app.
Run `serve.py --host 0.0.0.0` (with `pip install zeroconf` so the Apple TV can find it),
then see [`tvos/README.md`](tvos/README.md) for building it with Xcode.

## Running on sanctarus

The always-on copy runs on the home server as systemd services, with a daily sync
timer, at https://tomato.sanctarus.com (and http://192.168.68.77:8765 at home). Setup,
deploys and logs: [`deploy/README.md`](deploy/README.md).

## Scheduling refreshes

Run the sync daily: the cache means a run only re-checks availability every
`cache_days_providers` days and scores every `cache_days_scores` days, so a daily run is
a few minutes and keeps the "updated" line in the apps current. The apps re-fetch the
catalog on their own every hour while open, so a new sync shows up without restarting
anything.

**cron** (Linux/macOS), every day at 06:00:
```
0 6 * * *  cd /path/to/tomato-streams && /path/to/.venv/bin/python sync.py >> sync.log 2>&1
```

**launchd** (macOS): save as `~/Library/LaunchAgents/com.user.streaming-finder.plist`
and load with `launchctl load ~/Library/LaunchAgents/com.user.streaming-finder.plist`:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.user.streaming-finder</string>
  <key>ProgramArguments</key><array>
    <string>/path/to/.venv/bin/python</string><string>sync.py</string>
  </array>
  <key>WorkingDirectory</key><string>/path/to/tomato-streams</string>
  <key>StartCalendarInterval</key><dict>
    <key>Hour</key><integer>6</integer><key>Minute</key><integer>0</integer>
  </dict>
  <key>StandardOutPath</key><string>/path/to/tomato-streams/sync.log</string>
  <key>StandardErrorPath</key><string>/path/to/tomato-streams/sync.log</string>
</dict></plist>
```

## When Rotten Tomatoes changes its HTML

All RT-specific code is in `lib/rottentomatoes.py`. The page parser tries, in order,
the embedded `media-scorecard-json` / `scoreDetails` JSON blobs, the
`<media-scorecard>` slots, the legacy `<score-board>` element and JSON-LD, and merges
whatever it finds. If scores stop appearing, save a movie page, look at what the
site embeds now, and add or adjust a strategy there. `tests/test_rottentomatoes.py`
holds HTML fixtures for each strategy:

```sh
python -m unittest discover -s tests -v
```

## Attribution and terms

This product uses the TMDB API but is not endorsed or certified by TMDB. Streaming
availability data is provided by JustWatch via TMDB. Rotten Tomatoes scores are
scraped from rottentomatoes.com for personal use only; do not redistribute
`data/movies.json`.
