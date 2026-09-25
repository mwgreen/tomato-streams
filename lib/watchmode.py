"""Watchmode client: exact per-service links for a title (optional enrichment).

Watchmode (api.watchmode.com) returns, for a title identified by IMDb id or TMDB id,
every streaming source with its offer type and web / iOS / Android links. We keep
only subscription (and, if configured, free) sources that map to a configured
service, and store the web link (opens the native app on iPhone via Universal
Links) plus the iOS deep link for a future native app.

The free plan allows a few thousand requests per month; usage is tracked in
cache/watchmode_usage.json and lookups pause near the limit.
"""
from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

from lib.config import Service

log = logging.getLogger(__name__)

BASE_URL = "https://api.watchmode.com/v1"

# Watchmode source names -> our service names (keys are normalized service names).
# Names are normalized with `normalize_name` before comparison.
SERVICE_ALIASES: dict[str, list[str]] = {
    "netflix": ["netflix", "netflix standard with ads", "netflix basic with ads"],
    "prime video": ["amazon prime video", "prime video", "amazon prime", "prime video with ads"],
    "apple tv": ["apple tv+", "apple tv", "apple tv plus"],
    "hbo max": ["max", "hbo max", "hbo max with ads"],
    "hulu": ["hulu", "hulu with ads"],
    "disney+": ["disney+", "disney plus"],
    "paramount+": ["paramount+", "paramount plus", "paramount+ with showtime", "paramount+ essential"],
    "peacock": ["peacock", "peacock premium", "peacock premium plus"],
    "starz": ["starz"],
    "amc+": ["amc+", "amc plus"],
    "mgm+": ["mgm+", "mgm plus", "epix"],
    "criterion channel": ["criterion channel", "the criterion channel"],
    "mubi": ["mubi"],
    "britbox": ["britbox"],
    "acorn tv": ["acorn tv", "acorntv"],
    "shudder": ["shudder"],
    "crunchyroll": ["crunchyroll"],
    "hallmark+": ["hallmark+", "hallmark plus", "hallmark movies now"],
    "youtube premium": ["youtube premium", "youtube"],
    "tubi": ["tubi", "tubi tv"],
    "pluto tv": ["pluto tv"],
    "the roku channel": ["the roku channel", "roku channel"],
}

SUBSCRIPTION_TYPES = {"sub", "subscription"}
FREE_TYPES = {"free"}


def normalize_name(name: str) -> str:
    n = (name or "").lower().strip()
    n = re.sub(r"\bplus\b", "+", n)
    n = re.sub(r"[^a-z0-9+]+", " ", n)
    n = re.sub(r"\s*\+", "+", n)
    return re.sub(r"\s+", " ", n).strip()


def _aliases_for(service: Service) -> set[str]:
    key = normalize_name(service.name)
    names = {key}
    names.update(normalize_name(a) for a in SERVICE_ALIASES.get(key, []))
    names.update(normalize_name(a) for a in (getattr(service, "watchmode_names", None) or []))
    return names


def map_sources_to_services(sources: list[dict], services: list[Service], region: str = "US",
                            include_free: bool = False) -> dict[str, dict]:
    """{service name: {"web": url, "ios": url}} for sources that match a configured service."""
    allowed = set(SUBSCRIPTION_TYPES) | (FREE_TYPES if include_free else set())
    lookup = [(s.name, _aliases_for(s)) for s in services]
    out: dict[str, dict] = {}
    for src in sources or []:
        if str(src.get("region") or region).upper() != region.upper():
            continue
        if str(src.get("type") or "").lower() not in allowed:
            continue
        name = normalize_name(src.get("name") or "")
        for service_name, aliases in lookup:
            if name in aliases:
                links = out.setdefault(service_name, {})
                if src.get("web_url") and not links.get("web"):
                    links["web"] = src["web_url"]
                if src.get("ios_url") and not links.get("ios"):
                    links["ios"] = src["ios_url"]
                break
        else:
            log.debug("watchmode source %r (%s) matches no configured service", src.get("name"), src.get("type"))
    return {k: v for k, v in out.items() if v.get("web") or v.get("ios")}


class WatchmodeClient:
    def __init__(self, api_key: str, usage_file: str | Path = "cache/watchmode_usage.json",
                 session: requests.Session | None = None, monthly_limit: int = 2500,
                 reserve: int = 50, timeout: float = 15, max_retries: int = 3):
        self.api_key = (api_key or "").strip()
        self.usage_file = Path(usage_file)
        self.session = session or requests.Session()
        self.monthly_limit = monthly_limit
        self.reserve = reserve
        self.timeout = timeout
        self.max_retries = max_retries
        self._warned = False
        self._usage = self._load_usage()

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    # -- usage tracking (monthly quota) -------------------------------------
    @staticmethod
    def _month() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m")

    def _load_usage(self) -> dict:
        try:
            data = json.loads(self.usage_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        if data.get("month") != self._month():
            data = {"month": self._month(), "count": 0}
        data.setdefault("count", 0)
        return data

    def _save_usage(self) -> None:
        try:
            self.usage_file.parent.mkdir(parents=True, exist_ok=True)
            self.usage_file.write_text(json.dumps(self._usage), encoding="utf-8")
        except OSError as exc:
            log.warning("could not write Watchmode usage file: %s", exc)

    @property
    def used_this_month(self) -> int:
        if self._usage.get("month") != self._month():
            self._usage = {"month": self._month(), "count": 0}
        return int(self._usage.get("count", 0))

    @property
    def remaining(self) -> int:
        return max(0, self.monthly_limit - self.reserve - self.used_this_month)

    @property
    def exhausted(self) -> bool:
        return self.remaining <= 0

    # -- lookups -------------------------------------------------------------
    @staticmethod
    def title_id(kind: str, tmdb_id: int | None, imdb_id: str | None) -> str | None:
        if imdb_id:
            return imdb_id
        if tmdb_id:
            return f"{'tv' if kind == 'tv' else 'movie'}-{int(tmdb_id)}"
        return None

    def sources(self, kind: str, tmdb_id: int | None, imdb_id: str | None, region: str = "US") -> list[dict] | None:
        """Raw source list for a title ([] if Watchmode has no sources or does not know it),
        None if unavailable (no key, quota reached, network/API error)."""
        title_id = self.title_id(kind, tmdb_id, imdb_id)
        if not self.enabled or not title_id:
            return None
        if self.exhausted:
            if not self._warned:
                log.warning("Watchmode monthly quota nearly reached (%d used); skipping until next month",
                            self.used_this_month)
                self._warned = True
            return None
        url = f"{BASE_URL}/title/{title_id}/sources/"
        params = {"apiKey": self.api_key, "regions": region.upper()}
        delay = 1.0
        for attempt in range(1, self.max_retries + 1):
            self._usage["count"] = self.used_this_month + 1
            self._save_usage()
            try:
                resp = self.session.get(url, params=params, timeout=self.timeout)
            except requests.RequestException as exc:
                log.warning("Watchmode %s: network error %s (attempt %d)", title_id, exc, attempt)
                time.sleep(delay)
                delay *= 2
                continue
            if resp.status_code in (401, 403):
                log.error("Watchmode rejected the API key (HTTP %d); disabling for this run", resp.status_code)
                self.api_key = ""
                return None
            if resp.status_code == 404:
                return []  # Watchmode does not know the title: cache "no links" rather than retrying
            if resp.status_code == 429 or resp.status_code >= 500:
                log.warning("Watchmode %s: HTTP %d, retrying", title_id, resp.status_code)
                time.sleep(delay)
                delay *= 2
                continue
            try:
                data = resp.json()
            except ValueError:
                return None
            if isinstance(data, dict) and data.get("success") is False:
                log.debug("Watchmode %s: %s", title_id, data.get("statusMessage"))
                return None
            return data if isinstance(data, list) else []
        return None
