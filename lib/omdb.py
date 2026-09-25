"""OMDb client with daily-usage tracking (free tier: 1,000 requests/day)."""
from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

log = logging.getLogger(__name__)

BASE_URL = "https://www.omdbapi.com/"
RT_URL_RE = re.compile(r"^https?://(?:www\.)?rottentomatoes\.com/m/[^\s?#]+", re.I)


class OMDbClient:
    def __init__(self, api_key: str, usage_file: str | Path = "cache/omdb_usage.json",
                 session: requests.Session | None = None, daily_limit: int = 1000,
                 reserve: int = 25, timeout: float = 15, max_retries: int = 3):
        self.api_key = (api_key or "").strip()
        self.usage_file = Path(usage_file)
        self.session = session or requests.Session()
        self.daily_limit = daily_limit
        self.reserve = reserve  # stop this far before the hard limit
        self.timeout = timeout
        self.max_retries = max_retries
        self._warned = False
        self._usage = self._load_usage()

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    # -- usage tracking ------------------------------------------------------
    @staticmethod
    def _today() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def _load_usage(self) -> dict:
        try:
            data = json.loads(self.usage_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        if data.get("date") != self._today():
            data = {"date": self._today(), "count": 0}
        data.setdefault("count", 0)
        return data

    def _save_usage(self) -> None:
        try:
            self.usage_file.parent.mkdir(parents=True, exist_ok=True)
            self.usage_file.write_text(json.dumps(self._usage), encoding="utf-8")
        except OSError as exc:
            log.warning("could not write OMDb usage file: %s", exc)

    @property
    def used_today(self) -> int:
        if self._usage.get("date") != self._today():
            self._usage = {"date": self._today(), "count": 0}
        return int(self._usage.get("count", 0))

    @property
    def remaining(self) -> int:
        return max(0, self.daily_limit - self.reserve - self.used_today)

    @property
    def exhausted(self) -> bool:
        return self.remaining <= 0

    def _mark_exhausted(self) -> None:
        self._usage = {"date": self._today(), "count": self.daily_limit}
        self._save_usage()

    # -- lookups -------------------------------------------------------------
    def lookup(self, imdb_id: str) -> dict | None:
        """Raw OMDb payload for an IMDb id, or None if unavailable / quota exhausted."""
        if not self.enabled or not imdb_id:
            return None
        if self.exhausted:
            if not self._warned:
                log.warning("OMDb daily quota nearly reached (%d used); skipping OMDb until tomorrow",
                            self.used_today)
                self._warned = True
            return None

        params = {"i": imdb_id, "tomatoes": "true", "apikey": self.api_key}
        delay = 1.0
        for attempt in range(1, self.max_retries + 1):
            self._usage["count"] = self.used_today + 1
            self._save_usage()
            try:
                resp = self.session.get(BASE_URL, params=params, timeout=self.timeout)
            except requests.RequestException as exc:
                log.warning("OMDb %s: network error %s (attempt %d)", imdb_id, exc, attempt)
                time.sleep(delay)
                delay *= 2
                continue
            if resp.status_code == 401:
                # OMDb answers 401 both for bad keys and for "Request limit reached!"
                text = resp.text.lower()
                if "limit" in text:
                    log.warning("OMDb reports the daily request limit is reached; pausing OMDb lookups")
                    self._mark_exhausted()
                else:
                    log.error("OMDb rejected the API key (HTTP 401); disabling OMDb for this run")
                    self.api_key = ""
                return None
            if resp.status_code == 429 or resp.status_code >= 500:
                log.warning("OMDb %s: HTTP %d, retrying", imdb_id, resp.status_code)
                time.sleep(delay)
                delay *= 2
                continue
            try:
                data = resp.json()
            except ValueError:
                return None
            if str(data.get("Response", "")).lower() != "true":
                err = str(data.get("Error", "")).lower()
                if "limit" in err:
                    self._mark_exhausted()
                return None
            return data
        return None


def extract_rt_url(data: dict | None) -> str | None:
    """RT movie URL from OMDb's `tomatoURL`, if it points at a real RT movie page."""
    if not data:
        return None
    url = str(data.get("tomatoURL") or "").strip()
    if url and url.upper() != "N/A" and RT_URL_RE.match(url):
        return url
    return None


def extract_rt_critic_score(data: dict | None) -> int | None:
    """Tomatometer from OMDb's Ratings[] (source "Rotten Tomatoes"), e.g. "94%" -> 94."""
    if not data:
        return None
    for rating in data.get("Ratings") or []:
        if str(rating.get("Source", "")).lower() == "rotten tomatoes":
            m = re.search(r"(\d{1,3})\s*%", str(rating.get("Value", "")))
            if m:
                return int(m.group(1))
    meter = str(data.get("tomatoMeter") or "")
    if meter.isdigit():
        return int(meter)
    return None
