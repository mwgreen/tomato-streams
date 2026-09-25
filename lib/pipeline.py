"""The sync pipeline: discover -> details -> RT scores -> data/movies.json."""
from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass, field

from lib.cache import MovieCache, is_fresh, now_iso
from lib.config import Config, Service
from lib.omdb import OMDbClient, extract_rt_critic_score, extract_rt_url
from lib.rottentomatoes import (STATUS_ERROR, STATUS_NOT_FOUND, STATUS_OK, RTError, RottenTomatoesClient,
                                RTScores, normalize_rt_url)
from lib.tmdb import TMDBClient, TMDBError, normalize_details

log = logging.getLogger(__name__)



@dataclass
class SyncSummary:
    discovered: int = 0
    kept: int = 0
    dropped_no_service: int = 0
    dropped_missing: int = 0
    per_service: Counter = field(default_factory=Counter)
    rt_status: Counter = field(default_factory=Counter)
    both_scores: int = 0
    any_score: int = 0
    scores_fetched: int = 0
    scores_cached: int = 0
    details_fetched: int = 0
    details_cached: int = 0
    omdb_used_today: int | None = None
    failures: list[str] = field(default_factory=list)

    def format(self) -> str:
        lines = ["", "Sync summary", "------------",
                 f"Discovered {self.discovered} candidate titles, kept {self.kept} "
                 f"(dropped {self.dropped_no_service} with no matching subscription service, "
                 f"{self.dropped_missing} missing on TMDB)"]
        lines.append("Movies per service:")
        for name, n in sorted(self.per_service.items(), key=lambda kv: (-kv[1], kv[0])):
            lines.append(f"  {name:<20} {n}")
        lines.append(f"TMDB details: {self.details_fetched} fetched, {self.details_cached} from cache")
        lines.append(f"RT scores:    {self.scores_fetched} fetched, {self.scores_cached} from cache")
        lines.append(f"  both critic + audience score: {self.both_scores}/{self.kept}")
        lines.append(f"  at least one score:          {self.any_score}/{self.kept}")
        for status in (STATUS_OK, "no_scores", STATUS_NOT_FOUND, STATUS_ERROR):
            lines.append(f"  status {status:<10} {self.rt_status.get(status, 0)}")
        if self.omdb_used_today is not None:
            lines.append(f"OMDb requests used today: {self.omdb_used_today}")
        if self.failures:
            lines.append(f"Failures ({len(self.failures)}):")
            lines.extend(f"  - {f}" for f in self.failures[:50])
            if len(self.failures) > 50:
                lines.append(f"  ... and {len(self.failures) - 50} more")
        return "\n".join(lines)


def match_services(provider_ids: list[int] | None, services: list[Service]) -> list[str]:
    """Names of configured services whose provider IDs intersect the movie's flatrate providers."""
    have = {int(p) for p in (provider_ids or []) if p is not None}
    return [s.name for s in services if have.intersection(s.provider_ids)]


# ---------------------------------------------------------------------------
# Step 1: discovery
# ---------------------------------------------------------------------------
def discover(tmdb: TMDBClient, cache: MovieCache, cfg: Config, services: list[Service],
             full: bool, summary: SyncSummary) -> dict[int, dict]:
    """Merge TMDB discover results for every service, keyed by TMDB id."""
    merged: dict[int, dict] = {}
    ok_services = 0
    for service in services:
        key = f"{cfg.region}-{service.slug}-{'-'.join(map(str, service.provider_ids))}"
        cached = None if full else cache.load_discovery(key)
        if cached and is_fresh(cached.get("fetched_at"), cfg.sync.cache_days_providers):
            results = cached.get("results") or []
            log.info("%s: %d titles (discovery cache)", service.name, len(results))
        else:
            try:
                results = []
                for item in tmdb.discover_flatrate(cfg.region, service.provider_ids,
                                                   cfg.sync.min_tmdb_vote_count,
                                                   cfg.sync.max_pages_per_service):
                    results.append({"id": item.get("id"), "title": item.get("title"),
                                    "popularity": item.get("popularity"),
                                    "vote_count": item.get("vote_count")})
                cache.save_discovery(key, results)
                log.info("%s: %d titles discovered on TMDB", service.name, len(results))
            except TMDBError as exc:
                msg = f"discover {service.name}: {exc}"
                log.error(msg)
                summary.failures.append(msg)
                continue
        ok_services += 1
        for item in results:
            tmdb_id = item.get("id")
            if not tmdb_id:
                continue
            entry = merged.setdefault(int(tmdb_id), {"popularity": item.get("popularity") or 0,
                                                     "title": item.get("title") or "",
                                                     "discovered_via": []})
            entry["discovered_via"].append(service.name)
    if services and ok_services == 0:
        raise TMDBError("discovery failed for every service; aborting")
    summary.discovered = len(merged)
    return merged


# ---------------------------------------------------------------------------
# Step 2: details
# ---------------------------------------------------------------------------
def ensure_details(tmdb: TMDBClient, cache: MovieCache, cfg: Config, tmdb_id: int, full: bool,
                   summary: SyncSummary) -> dict | None:
    """Return the cache entry with fresh TMDB details, or None if the movie no longer exists."""
    entry = cache.load(tmdb_id)
    if (not full and entry.get("details")
            and is_fresh(entry.get("details_fetched_at"), cfg.sync.cache_days_providers)):
        summary.details_cached += 1
        return entry
    raw = tmdb.movie_details(tmdb_id)
    summary.details_fetched += 1
    if raw is None:
        entry["details"] = None
        entry["details_fetched_at"] = now_iso()
        cache.save(tmdb_id, entry)
        return None
    entry["details"] = normalize_details(raw, cfg.region)
    entry["details_fetched_at"] = now_iso()
    cache.save(tmdb_id, entry)
    return entry


# ---------------------------------------------------------------------------
# Step 3: Rotten Tomatoes scores
# ---------------------------------------------------------------------------
def resolve_scores(details: dict, omdb: OMDbClient | None, rt: RottenTomatoesClient | None,
                   omdb_cached: dict | None = None) -> tuple[RTScores, dict | None]:
    """Find the RT page (OMDb tomatoURL, then RT search) and scrape it. Never raises."""
    title, year, imdb_id = details.get("title") or "", details.get("year"), details.get("imdb_id")
    omdb_info = omdb_cached
    if omdb_info is None and omdb is not None and omdb.enabled and imdb_id:
        raw = omdb.lookup(imdb_id)
        if raw is not None:
            omdb_info = {"rt_url": extract_rt_url(raw), "critic_score": extract_rt_critic_score(raw),
                         "fetched_at": now_iso()}
    fallback_critic = (omdb_info or {}).get("critic_score")
    url = normalize_rt_url((omdb_info or {}).get("rt_url"))

    scores = RTScores(url=url, status=STATUS_NOT_FOUND)
    if rt is not None:
        try:
            if not url:
                url = rt.search(title, year)
            if url:
                scores = rt.fetch_scores(url)
            else:
                scores = RTScores(status=STATUS_NOT_FOUND)
        except RTError as exc:
            scores = RTScores(url=url, status=STATUS_ERROR, error=str(exc))
        except Exception as exc:  # noqa: BLE001 - a single bad page must never stop the sync
            log.exception("unexpected error scraping RT for %r", title)
            scores = RTScores(url=url, status=STATUS_ERROR, error=f"{type(exc).__name__}: {exc}")

    if scores.critic_score is None and fallback_critic is not None:
        scores.critic_score = fallback_critic
        if scores.status != STATUS_ERROR:
            scores.status = STATUS_OK
    if scores.has_scores() and scores.status != STATUS_ERROR:
        scores.status = STATUS_OK
    if scores.critic_score is None:
        scores.certified_fresh = False
    return scores, omdb_info


def ensure_scores(entry: dict, cache: MovieCache, cfg: Config, omdb: OMDbClient | None,
                  rt: RottenTomatoesClient | None, full: bool, summary: SyncSummary) -> RTScores:
    tmdb_id = entry["tmdb_id"]
    cached = entry.get("rt")
    # Transient errors are always retried on the next run; other results honour the TTL.
    if cached and not full and cached.get("status") != STATUS_ERROR:
        if is_fresh(entry.get("rt_fetched_at"), cfg.sync.cache_days_scores):
            summary.scores_cached += 1
            return RTScores.from_dict(cached)

    omdb_cached = entry.get("omdb")
    if full or not (omdb_cached and is_fresh(omdb_cached.get("fetched_at"), cfg.sync.cache_days_scores)):
        omdb_cached = None
    # Keep a cached RT URL so a transient error does not force a new search.
    if omdb_cached is None and cached and cached.get("url") and cached.get("status") != STATUS_NOT_FOUND:
        omdb_cached = {"rt_url": cached["url"], "critic_score": None, "fetched_at": now_iso(), "_reused": True}

    scores, omdb_info = resolve_scores(entry["details"], omdb, rt, omdb_cached)
    summary.scores_fetched += 1
    entry["rt"] = scores.to_dict()
    entry["rt_fetched_at"] = now_iso()
    if omdb_info and not omdb_info.get("_reused"):
        entry["omdb"] = omdb_info
    cache.save(tmdb_id, entry)
    if scores.status == STATUS_ERROR:
        summary.failures.append(f"{entry['details'].get('title')} ({entry['details'].get('year')}): "
                                f"{scores.error or 'RT error'}")
    return scores


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------
def build_movie(details: dict, services: list[str], scores: RTScores) -> dict:
    return {
        "tmdb_id": details.get("tmdb_id"),
        "imdb_id": details.get("imdb_id"),
        "title": details.get("title"),
        "original_title": details.get("original_title"),
        "year": details.get("year"),
        "overview": details.get("overview"),
        "runtime": details.get("runtime"),
        "genres": details.get("genres") or [],
        "poster": details.get("poster"),
        "poster_large": details.get("poster_large"),
        "backdrop": details.get("backdrop"),
        "trailer_youtube_key": details.get("trailer_youtube_key"),
        "tmdb_vote_average": details.get("tmdb_vote_average"),
        "tmdb_vote_count": details.get("tmdb_vote_count"),
        "services": services,
        "justwatch_link": details.get("justwatch_link"),
        "rt": {
            "url": scores.url,
            "status": scores.status,
            "critic_score": scores.critic_score,
            "critic_count": scores.critic_count,
            "certified_fresh": bool(scores.certified_fresh),
            "audience_score": scores.audience_score,
            "audience_count": scores.audience_count,
        },
    }


def merge_with_previous(new_movies: list[dict], previous: dict | None, synced: list[str]) -> list[dict]:
    """For a partial (--service) sync keep the previous output's other titles."""
    if not previous:
        return new_movies
    seen = {m["tmdb_id"] for m in new_movies}
    merged = list(new_movies)
    for m in previous.get("movies") or []:
        if m.get("tmdb_id") in seen:
            continue
        # A title that used to be on a synced service but was not rediscovered has left it.
        remaining = [s for s in (m.get("services") or []) if s not in synced]
        if not remaining:
            continue
        m = dict(m, services=remaining)
        merged.append(m)
    return merged


def run_sync(cfg: Config, tmdb: TMDBClient, omdb: OMDbClient | None, rt: RottenTomatoesClient | None,
             cache: MovieCache, *, full: bool = False, limit: int | None = None,
             only_services: list[Service] | None = None, previous: dict | None = None,
             progress_every: int = 25) -> tuple[dict, SyncSummary]:
    summary = SyncSummary()
    enabled = cfg.enabled_services
    services = only_services or enabled
    discovered = discover(tmdb, cache, cfg, services, full, summary)

    ordered = sorted(discovered.items(), key=lambda kv: -(kv[1].get("popularity") or 0))
    if limit is not None:
        ordered = ordered[:limit]
    total = len(ordered)
    log.info("processing %d titles", total)

    movies: list[dict] = []
    for i, (tmdb_id, _info) in enumerate(ordered, 1):
        try:
            entry = ensure_details(tmdb, cache, cfg, tmdb_id, full, summary)
        except TMDBError as exc:
            summary.failures.append(f"tmdb {tmdb_id}: {exc}")
            log.error("TMDB details for %s failed: %s", tmdb_id, exc)
            continue
        if entry is None or not entry.get("details"):
            summary.dropped_missing += 1
            continue
        details = entry["details"]
        carried = match_services(details.get("flatrate_provider_ids"), enabled)
        if not carried:
            summary.dropped_no_service += 1
            log.debug("dropping %r: flatrate providers %s match no enabled service",
                      details.get("title"), details.get("flatrate_provider_names"))
            continue
        scores = ensure_scores(entry, cache, cfg, omdb, rt, full, summary)
        movies.append(build_movie(details, carried, scores))
        if progress_every and i % progress_every == 0:
            log.info("  %d/%d  %s (%s) -> %s", i, total, details.get("title"), details.get("year"),
                     scores.status)

    if only_services:
        movies = merge_with_previous(movies, previous, [s.name for s in only_services])

    for m in movies:
        for s in m["services"]:
            summary.per_service[s] += 1
        rt_info = m["rt"]
        summary.rt_status[rt_info["status"]] += 1
        if rt_info["critic_score"] is not None and rt_info["audience_score"] is not None:
            summary.both_scores += 1
        if rt_info["critic_score"] is not None or rt_info["audience_score"] is not None:
            summary.any_score += 1
    summary.kept = len(movies)
    if omdb is not None and omdb.enabled:
        summary.omdb_used_today = omdb.used_today

    output = {
        "generated_at": now_iso(),
        "region": cfg.region,
        "services": [s.name for s in enabled],
        "ui_defaults": {"min_critic_reviews": cfg.ui_defaults.min_critic_reviews,
                        "sort": cfg.ui_defaults.sort},
        "movies": movies,
    }
    return output, summary
