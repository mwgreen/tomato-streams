# Build Spec: Streaming Movie Finder (Rotten Tomatoes scores × my streaming services)

## Goal

Build a small local web app that lists movies **included with my streaming subscriptions** (no rentals or purchases) and shows each one with its poster, description, **Rotten Tomatoes critic score (Tomatometer)** and **RT audience score (Popcornmeter)**. I want to filter and sort by those scores, by service, genre and year.

This exists because Rotten Tomatoes' own "Movies at Home" browse page mixes in Fandango at Home rent/buy titles and its service filter is unreliable. This app must **only** show titles you can stream as part of a subscription.

## Tech choices

- **Python 3.11+** for data syncing (`requests`, `pyyaml`, `beautifulsoup4`, `python-dotenv`).
- **Static frontend**: one `index.html` + vanilla JS + CSS. No build step, no framework.
- Data flows: `sync.py` → writes `data/movies.json` → frontend reads it.
- Serve locally with `python -m http.server` (or a tiny `serve.py`). API keys never reach the browser.
- A `README.md` with setup and usage.

## Project layout

```
streaming-finder/
  config.yaml          # services + settings (user-editable)
  .env.example         # TMDB_API_KEY=, OMDB_API_KEY=
  sync.py              # fetch + enrich + cache → data/movies.json
  lib/tmdb.py
  lib/omdb.py
  lib/rottentomatoes.py
  cache/               # per-movie cached lookups (gitignored)
  data/movies.json     # output consumed by the UI
  web/index.html
  web/app.js
  web/styles.css
  README.md
```

## Configuration (`config.yaml`) — must be easy to add/remove services

```yaml
region: US

# Add or remove services here. `enabled: false` hides a service without deleting it.
# provider_ids are TMDB watch-provider IDs. A service can have several
# (e.g. ad-supported tiers). Verify IDs with: python sync.py --list-providers
services:
  - name: Netflix
    provider_ids: [8, 1796]        # Netflix, Netflix Standard with Ads
    enabled: true
  - name: Prime Video
    provider_ids: [9, 2100]        # Amazon Prime Video, Prime Video with Ads
    enabled: true
  - name: Apple TV
    provider_ids: [350]
    enabled: true
  - name: HBO Max
    provider_ids: [1899]
    enabled: true
  - name: Hulu
    provider_ids: [15]
    enabled: true
  - name: Disney+
    provider_ids: [337]
    enabled: true

sync:
  min_tmdb_vote_count: 50        # skip ultra-obscure titles at discovery time
  max_pages_per_service: 50      # TMDB pages of 20 results each
  cache_days_scores: 7           # re-fetch RT/OMDb scores after N days
  cache_days_providers: 2        # re-check streaming availability after N days
  request_delay_seconds: 1.0     # politeness delay for rottentomatoes.com requests

ui_defaults:
  min_critic_reviews: 20         # hide titles with too few critic reviews by default
  sort: critic_desc
```

The provider IDs above are my best guess and **must be verified** at runtime. Implement `python sync.py --list-providers`, which calls TMDB `GET /3/watch/providers/movie?watch_region={region}` and prints every provider's `provider_id` + `provider_name`. On a normal sync, warn if any configured ID doesn't exist in that list. Only match the configured IDs exactly: do **not** fuzzy-match names, because Amazon "Channels" variants (e.g. "HBO Max Amazon Channel") are separate providers and should be excluded unless I add them.

## Data pipeline (`sync.py`)

### 1. Discover movies per service (TMDB)
For each enabled service:
`GET /3/discover/movie` with
- `watch_region={region}`
- `with_watch_providers={ids joined with "|"}`
- `with_watch_monetization_types=flatrate` ← **subscription only; this is what removes rent/buy**
- `vote_count.gte={min_tmdb_vote_count}`
- `sort_by=popularity.desc`, paginate up to `max_pages_per_service`

Merge results into one set keyed by TMDB id.

### 2. Details per movie (TMDB)
`GET /3/movie/{id}?append_to_response=watch/providers,external_ids,videos`
Store: title, original_title, year, overview, runtime, genres, poster_path, backdrop_path, imdb_id, YouTube trailer key (official Trailer if present), TMDB vote average.

From `watch/providers.results[region].flatrate`, compute **which configured services** carry the title (a movie often appears on several). Store the JustWatch `link` too. Drop the movie if it matches no enabled service's flatrate list after this check.

Images: `https://image.tmdb.org/t/p/w342{poster_path}` for cards, `w780` for detail views.

### 3. Rotten Tomatoes scores
Audience score is not in any free official API, so:

1. **Find the RT page.** Try, in order:
   - OMDb (`?i={imdb_id}&tomatoes=true`): use `tomatoURL` if it's a valid RT URL; also take the Tomatometer from `Ratings[]` (`Source == "Rotten Tomatoes"`) as a fallback critic score.
   - RT search (`https://www.rottentomatoes.com/search?search={title}`): pick the movie result whose title and release year match (±1 year). Parse the search results' structured data/attributes, not visual layout.
2. **Scrape the RT movie page** for: critic score, critic review count, Certified Fresh flag, audience score, audience rating count, and the RT URL. Prefer embedded JSON (e.g. the scorecard JSON / `application/ld+json` / score-board element attributes) over text scraping. Inspect the live page first and write the parser against what's actually there.
3. Store `rt_status`: `ok` | `not_found` | `no_scores` | `error`. Never crash the sync on a single failure.

Be polite: a single-threaded requests session, a realistic User-Agent, `request_delay_seconds` between RT requests, retry with backoff on 429/5xx, and **cache everything**. Keep the scraper isolated in `lib/rottentomatoes.py` so it's easy to fix when RT changes its HTML.

### 4. Caching and incremental sync
- Cache per-movie results in `cache/` (JSON files or SQLite, your choice) with timestamps.
- Re-fetch scores after `cache_days_scores` and providers after `cache_days_providers`.
- OMDb's free tier allows 1,000 requests/day: track usage, stop OMDb calls gracefully near the limit, and continue on the next run.
- Flags: `--full` (ignore cache), `--service "HBO Max"` (sync one service), `--limit N` (for testing), `--list-providers`.
- Print a summary at the end: movies per service, how many have RT scores, failures.

### 5. Output `data/movies.json`
```json
{
  "generated_at": "ISO timestamp",
  "region": "US",
  "services": ["Netflix", "Prime Video", "..."],
  "movies": [
    {
      "tmdb_id": 0, "imdb_id": "tt...", "title": "", "year": 2024,
      "overview": "", "runtime": 0, "genres": [""],
      "poster": "url", "backdrop": "url", "trailer_youtube_key": "",
      "services": ["HBO Max", "Hulu"], "justwatch_link": "url",
      "rt": {
        "url": "", "status": "ok",
        "critic_score": 94, "critic_count": 212, "certified_fresh": true,
        "audience_score": 88, "audience_count": "2,500+"
      }
    }
  ]
}
```

## Frontend (`web/`)

**Layout:** responsive grid of movie cards; works on desktop and phone widths.

**Card:** poster, title, year, runtime, genres, critic score (tomato icon, fresh/rotten/certified styling), audience score (popcorn icon), a service badge for each service that carries it, and the overview truncated to about 3 lines.

**Detail view (click a card):** backdrop, full description, trailer (embedded YouTube or link), links to the RT page and JustWatch.

**Filters (left sidebar or top bar, collapsible on mobile):**
- Services: checkbox per service from `movies.json` (all checked by default). Show titles on **any** checked service.
- Min critic score and min audience score (sliders 0–100).
- Min critic review count (default from config) to suppress obscure titles.
- "Certified Fresh only" toggle.
- Genre multi-select, year range, runtime max.
- Text search on title.
- "Hide movies with no RT score" toggle (on by default).

**Sort:** critic score, audience score, combined average, critic review count, year (newest/oldest), title. Break ties by review count.

**Nice to have:**
- Keep filter/sort state in the URL hash so views can be bookmarked.
- Show "N movies" and the data's `generated_at` date.
- "Hidden" list: an × on a card hides it (localStorage), with a toggle to show hidden titles.

## Attribution / terms
- Show the TMDB attribution in the footer ("This product uses the TMDB API but is not endorsed or certified by TMDB") and credit JustWatch for availability data, per TMDB's terms.
- This is for personal use only. Don't redistribute scraped RT data.

## Acceptance criteria
1. `python sync.py --list-providers` prints US providers, and the configured IDs are confirmed or corrected.
2. Adding a service to `config.yaml` (or setting `enabled: false`) and re-running `sync.py` adds or removes it in the UI with no code changes.
3. No titles that are only available to rent or buy appear. Spot-check 5 random titles per service on JustWatch.
4. At least 85% of movies with ≥20 TMDB votes have both RT scores; failures are logged, not fatal.
5. A second `sync.py` run finishes much faster thanks to the cache.
6. Filtering "HBO Max + critic ≥ 90 + audience ≥ 85, sorted by audience" returns sensible results with posters and descriptions.

## Setup the README must cover
1. Get a free TMDB API key (themoviedb.org → Settings → API) and an OMDb key (omdbapi.com).
2. `cp .env.example .env` and fill in the keys; `pip install -r requirements.txt`.
3. `python sync.py --list-providers` to verify service IDs, then edit `config.yaml`.
4. `python sync.py` (the first run can take a while), then `python serve.py` and open `http://localhost:8000`.
5. How to add or remove a service, and how to schedule `sync.py` (cron/launchd) for weekly refreshes.
