"""Thin TMDB API v3 client (discover, watch providers, movie details)."""
from __future__ import annotations

import logging
import time
from collections.abc import Iterator

import requests

log = logging.getLogger(__name__)

BASE_URL = "https://api.themoviedb.org/3"
IMAGE_BASE = "https://image.tmdb.org/t/p/"
MAX_PAGE = 500  # TMDB hard limit


class TMDBError(Exception):
    pass


class TMDBClient:
    def __init__(self, api_key: str, session: requests.Session | None = None,
                 timeout: float = 20, max_retries: int = 4):
        if not api_key:
            raise TMDBError("TMDB_API_KEY is not set (see .env.example)")
        self.api_key = api_key.strip()
        self.session = session or requests.Session()
        self.timeout = timeout
        self.max_retries = max_retries
        # A v4 "API Read Access Token" is a JWT; a v3 key is a 32-char hex string.
        self._bearer = self.api_key.startswith("eyJ")

    def _get(self, path: str, **params) -> dict | None:
        url = BASE_URL + path
        headers = {"Accept": "application/json"}
        if self._bearer:
            headers["Authorization"] = f"Bearer {self.api_key}"
        else:
            params["api_key"] = self.api_key
        delay = 1.0
        last_error = "unknown error"
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self.session.get(url, params=params, headers=headers, timeout=self.timeout)
            except requests.RequestException as exc:
                last_error = f"network error: {exc}"
                log.warning("TMDB %s: %s (attempt %d/%d)", path, last_error, attempt, self.max_retries)
            else:
                if resp.status_code == 404:
                    return None
                if resp.status_code == 401:
                    raise TMDBError("TMDB rejected the API key (HTTP 401). Check TMDB_API_KEY in .env")
                if resp.status_code == 429 or resp.status_code >= 500:
                    retry_after = resp.headers.get("Retry-After")
                    wait = float(retry_after) if retry_after and retry_after.isdigit() else delay
                    last_error = f"HTTP {resp.status_code}"
                    log.warning("TMDB %s: %s, retrying in %.0fs", path, last_error, wait)
                    time.sleep(wait)
                    delay *= 2
                    continue
                if not resp.ok:
                    raise TMDBError(f"TMDB {path} returned HTTP {resp.status_code}: {resp.text[:200]}")
                try:
                    return resp.json()
                except ValueError as exc:
                    raise TMDBError(f"TMDB {path} returned invalid JSON") from exc
            time.sleep(delay)
            delay *= 2
        raise TMDBError(f"TMDB {path} failed after {self.max_retries} attempts ({last_error})")

    # -- endpoints ----------------------------------------------------------
    def list_watch_providers(self, region: str) -> list[dict]:
        """All movie watch providers available in `region`, sorted by TMDB's display priority."""
        data = self._get("/watch/providers/movie", watch_region=region) or {}
        providers = []
        for p in data.get("results", []):
            priority = (p.get("display_priorities") or {}).get(region, p.get("display_priority", 9999))
            providers.append({
                "provider_id": p.get("provider_id"),
                "provider_name": p.get("provider_name"),
                "display_priority": priority,
            })
        providers.sort(key=lambda p: (p["display_priority"], p["provider_name"] or ""))
        return providers

    def discover_flatrate(self, region: str, provider_ids: list[int], min_vote_count: int,
                          max_pages: int, sort_by: str = "popularity.desc",
                          kind: str = "movie") -> Iterator[dict]:
        """Titles included with a subscription (`flatrate`) on any of `provider_ids`.

        `kind` is "movie" or "tv" (TMDB discover endpoints share the same parameters).
        """
        page = 1
        while page <= min(max_pages, MAX_PAGE):
            data = self._get(
                f"/discover/{kind}",
                watch_region=region,
                with_watch_providers="|".join(str(i) for i in provider_ids),
                with_watch_monetization_types="flatrate",
                **{"vote_count.gte": min_vote_count},
                sort_by=sort_by,
                include_adult="false",
                page=page,
            ) or {}
            results = data.get("results") or []
            yield from results
            total_pages = int(data.get("total_pages") or 0)
            if not results or page >= total_pages:
                break
            page += 1

    def details(self, kind: str, tmdb_id: int) -> dict | None:
        """Movie or TV details with providers, external ids and videos appended."""
        return self._get(f"/{kind}/{int(tmdb_id)}",
                         append_to_response="watch/providers,external_ids,videos")

    def movie_details(self, tmdb_id: int) -> dict | None:
        return self.details("movie", tmdb_id)

    def tv_details(self, tmdb_id: int) -> dict | None:
        return self.details("tv", tmdb_id)


# -- helpers on raw TMDB payloads ------------------------------------------
def image_url(path: str | None, size: str) -> str | None:
    return f"{IMAGE_BASE}{size}{path}" if path else None


def flatrate_providers(details: dict, region: str) -> list[dict]:
    results = ((details.get("watch/providers") or {}).get("results") or {})
    return list((results.get(region) or {}).get("flatrate") or [])


def justwatch_link(details: dict, region: str) -> str | None:
    results = ((details.get("watch/providers") or {}).get("results") or {})
    return (results.get(region) or {}).get("link")


def trailer_key(details: dict) -> str | None:
    """YouTube key of the official trailer if present, else the best available trailer/teaser."""
    videos = [v for v in ((details.get("videos") or {}).get("results") or [])
              if v.get("site") == "YouTube" and v.get("key")]
    if not videos:
        return None

    def rank(v: dict) -> tuple:
        vtype = v.get("type") or ""
        name = (v.get("name") or "").lower()
        return (
            0 if vtype == "Trailer" else 1 if vtype == "Teaser" else 2,
            0 if v.get("official") else 1,
            0 if "official trailer" in name else 1,
            0 if (v.get("iso_639_1") or "en") == "en" else 1,
            v.get("published_at") or "",
        )

    return sorted(videos, key=rank)[0]["key"]


def _year(date: str | None) -> int | None:
    date = date or ""
    return int(date[:4]) if date[:4].isdigit() else None


def normalize_details(details: dict, region: str, kind: str = "movie") -> dict:
    """Reduce a TMDB movie or TV details payload to the fields the app stores."""
    if kind == "tv":
        release = details.get("first_air_date") or ""
        title = details.get("name") or details.get("original_name") or ""
        original_title = details.get("original_name") or ""
        run_times = [r for r in (details.get("episode_run_time") or []) if r]
        runtime = run_times[0] if run_times else None
        extra = {
            "seasons": details.get("number_of_seasons"),
            "episodes": details.get("number_of_episodes"),
            "end_year": _year(details.get("last_air_date")) if not details.get("in_production") else None,
            "status": details.get("status"),
            "in_production": bool(details.get("in_production")),
        }
    else:
        release = details.get("release_date") or ""
        title = details.get("title") or details.get("original_title") or ""
        original_title = details.get("original_title") or ""
        runtime = details.get("runtime") or None
        extra = {}
    return {
        "kind": kind,
        "tmdb_id": details.get("id"),
        "imdb_id": (details.get("external_ids") or {}).get("imdb_id") or details.get("imdb_id"),
        "title": title,
        "original_title": original_title,
        "year": _year(release),
        "release_date": release or None,
        "overview": details.get("overview") or "",
        "runtime": runtime,
        **extra,
        "genres": [g.get("name") for g in (details.get("genres") or []) if g.get("name")],
        "poster": image_url(details.get("poster_path"), "w342"),
        "poster_large": image_url(details.get("poster_path"), "w780"),
        "backdrop": image_url(details.get("backdrop_path"), "w780"),
        "backdrop_large": image_url(details.get("backdrop_path"), "w1280"),
        "trailer_youtube_key": trailer_key(details),
        "tmdb_vote_average": details.get("vote_average"),
        "tmdb_vote_count": details.get("vote_count"),
        "popularity": details.get("popularity"),
        "justwatch_link": justwatch_link(details, region),
        "flatrate_provider_ids": [p.get("provider_id") for p in flatrate_providers(details, region)],
        "flatrate_provider_names": [p.get("provider_name") for p in flatrate_providers(details, region)],
    }
