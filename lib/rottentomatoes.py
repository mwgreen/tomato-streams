"""Rotten Tomatoes lookup and page scraping.

Everything that touches rottentomatoes.com lives here so it is easy to fix when
the site changes. Parsing prefers embedded JSON blobs over visible text:

  1. <script id="media-scorecard-json" type="application/json">  (current pages)
  2. <script id="scoreDetails" type="application/json">           (older pages)
  3. <media-scorecard> / <rt-text slot="criticsScore"> elements
  4. <score-board tomatometerscore=... audiencescore=...> element (legacy)
  5. JSON-LD (application/ld+json) aggregateRating              (critic score only)

Strategies are tried in order and merged: later ones only fill in fields the
earlier ones did not provide.
"""
from __future__ import annotations

import json
import logging
import re
import time
import unicodedata
from dataclasses import asdict, dataclass
from typing import Any
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

BASE_URL = "https://www.rottentomatoes.com"
SEARCH_URL = BASE_URL + "/search?search={query}"
USER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")
MOVIE_PATH_RE = re.compile(r"^/m/[A-Za-z0-9_\-]+/?$")
MOVIE_URL_RE = re.compile(r"^(?:https?://(?:www\.)?rottentomatoes\.com)?(/m/[A-Za-z0-9_\-]+)/?", re.I)

STATUS_OK = "ok"
STATUS_NOT_FOUND = "not_found"
STATUS_NO_SCORES = "no_scores"
STATUS_ERROR = "error"


class RTError(Exception):
    pass


@dataclass
class RTScores:
    url: str | None = None
    status: str = STATUS_NOT_FOUND
    critic_score: int | None = None
    critic_count: int | None = None
    certified_fresh: bool = False
    audience_score: int | None = None
    audience_count: str | None = None
    error: str | None = None

    def has_scores(self) -> bool:
        return self.critic_score is not None or self.audience_score is not None

    def to_dict(self) -> dict:
        d = asdict(self)
        if d.get("error") is None:
            d.pop("error")
        return d

    @classmethod
    def from_dict(cls, d: dict | None) -> "RTScores":
        d = d or {}
        return cls(**{k: d.get(k, getattr(cls, k, None)) for k in cls.__dataclass_fields__})


# ---------------------------------------------------------------------------
# URL / title helpers
# ---------------------------------------------------------------------------
def normalize_rt_url(url: str | None) -> str | None:
    """Canonical https://www.rottentomatoes.com/m/<slug> or None."""
    if not url:
        return None
    m = MOVIE_URL_RE.match(url.strip())
    if not m:
        return None
    return BASE_URL + m.group(1).rstrip("/")


_ARTICLE_RE = re.compile(r"^(the|a|an)\s+")


def normalize_title(title: str) -> str:
    t = unicodedata.normalize("NFKD", title or "")
    t = "".join(ch for ch in t if not unicodedata.combining(ch)).lower()
    t = t.replace("&", " and ")
    t = re.sub(r"[^a-z0-9]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def titles_match(a: str, b: str) -> bool:
    na, nb = normalize_title(a), normalize_title(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    return _ARTICLE_RE.sub("", na) == _ARTICLE_RE.sub("", nb)


def _to_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    m = re.search(r"-?\d[\d,]*", str(value))
    if not m:
        return None
    try:
        return int(m.group(0).replace(",", ""))
    except ValueError:
        return None


def _to_score(value: Any) -> int | None:
    """Percent score 0-100 from '94', '94%', 94, 0.94 etc."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, float) and 0 < value <= 1:
        value = round(value * 100)
    n = _to_int(value)
    if n is None or not 0 <= n <= 100:
        return None
    return n


def _clean_count(value: Any) -> str | None:
    """Audience count as display text, e.g. '2,500+' or '10,000+ Ratings' -> '2,500+'."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return f"{int(value):,}" if value > 0 else None
    text = str(value).strip()
    m = re.search(r"\d[\d,]*\s*\+?", text)
    if not m:
        return None
    return m.group(0).replace(" ", "")


# ---------------------------------------------------------------------------
# Search results
# ---------------------------------------------------------------------------
def parse_search_results(html: str, title: str, year: int | None) -> str | None:
    """Pick the RT movie URL whose title matches and whose year is within ±1."""
    soup = BeautifulSoup(html, "html.parser")
    candidates: list[dict] = []

    # Current markup: <search-page-media-row releaseyear="2023"><a slot="title" href=...>Title</a>
    for row in soup.select("search-page-media-row"):
        link = row.find("a", attrs={"slot": "title"}) or row.find("a", href=MOVIE_URL_RE)
        if not link:
            continue
        url = normalize_rt_url(link.get("href"))
        if not url:
            continue
        candidates.append({
            "url": url,
            "title": link.get_text(" ", strip=True),
            "year": _to_int(row.get("releaseyear") or row.get("release-year") or row.get("year")),
        })

    # Fallback: any /m/ link with a nearby 4-digit year.
    if not candidates:
        for link in soup.find_all("a", href=MOVIE_URL_RE):
            url = normalize_rt_url(link.get("href"))
            text = link.get_text(" ", strip=True)
            if not url or not text:
                continue
            parent = link.parent
            context = parent.get_text(" ", strip=True) if parent else ""
            years = [int(y) for y in re.findall(r"\b((?:19|20)\d{2})\b", context)]
            candidates.append({"url": url, "title": text, "year": years[0] if years else None})

    return pick_search_candidate(candidates, title, year)


def pick_search_candidate(candidates: list[dict], title: str, year: int | None) -> str | None:
    def year_distance(c: dict) -> int | None:
        if year is None or c.get("year") is None:
            return None
        return abs(int(c["year"]) - int(year))

    exact_title = [c for c in candidates if titles_match(c["title"], title)]
    if year is None:
        return exact_title[0]["url"] if exact_title else None

    # Exact title + exact year, then exact title ±1 year, then title match with unknown year.
    for max_dist in (0, 1):
        for c in exact_title:
            d = year_distance(c)
            if d is not None and d <= max_dist:
                return c["url"]
    for c in exact_title:
        if c.get("year") is None:
            return c["url"]
    return None


# ---------------------------------------------------------------------------
# Movie page
# ---------------------------------------------------------------------------
_CRITIC_KEY_RE = re.compile(r"critic|tomatometer", re.I)
_AUDIENCE_KEY_RE = re.compile(r"audience|popcorn", re.I)
_SCORE_KEYS = ("score", "scorePercent", "value", "percentage", "tomatometer", "audienceScore")
_COUNT_KEYS = ("reviewCount", "ratingCount", "count", "numReviews", "reviews", "ratings")
_BANDED_KEYS = ("bandedRatingCount", "bandedCount", "ratingCountDisplay", "displayCount")
_CERT_KEYS = ("certified", "certifiedFresh", "isCertifiedFresh", "certified_fresh")
_STATE_KEYS = ("state", "sentiment", "status", "iconType", "type")


def _walk(obj: Any, path: tuple = ()):
    """Yield (path, dict) for every dict in a nested JSON structure."""
    if isinstance(obj, dict):
        yield path, obj
        for k, v in obj.items():
            yield from _walk(v, path + (str(k),))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _walk(v, path + (str(i),))


def _first(d: dict, keys: tuple) -> Any:
    lower = {k.lower(): v for k, v in d.items()}
    for k in keys:
        v = lower.get(k.lower())
        if v not in (None, "", "N/A"):
            return v
    return None


def _has_score_shape(d: dict) -> bool:
    lower = {k.lower() for k in d}
    return any(k.lower() in lower for k in _SCORE_KEYS)


def _section_from_json(data: Any, key_re: re.Pattern) -> dict | None:
    """Find the first dict reached through a key matching `key_re` that looks like a score block."""
    for path, d in _walk(data):
        if path and key_re.search(path[-1]) and _has_score_shape(d):
            return d
    return None


def _apply_json_sections(data: Any, scores: RTScores) -> None:
    critic = _section_from_json(data, _CRITIC_KEY_RE)
    audience = _section_from_json(data, _AUDIENCE_KEY_RE)
    if critic:
        if scores.critic_score is None:
            scores.critic_score = _to_score(_first(critic, _SCORE_KEYS))
        if scores.critic_count is None:
            scores.critic_count = _to_int(_first(critic, _COUNT_KEYS))
        cert = _first(critic, _CERT_KEYS)
        state = str(_first(critic, _STATE_KEYS) or "").lower()
        if cert is True or str(cert).lower() == "true" or "certified" in state:
            scores.certified_fresh = True
    if audience:
        if scores.audience_score is None:
            scores.audience_score = _to_score(_first(audience, _SCORE_KEYS))
        if scores.audience_count is None:
            banded = _first(audience, _BANDED_KEYS)
            scores.audience_count = _clean_count(banded if banded is not None
                                                 else _first(audience, _COUNT_KEYS))


def _parse_json_script(soup: BeautifulSoup, script_id: str) -> Any:
    tag = soup.find("script", id=script_id)
    if not tag or not tag.string:
        return None
    try:
        return json.loads(tag.string)
    except ValueError:
        log.debug("could not parse JSON in <script id=%s>", script_id)
        return None


def _strategy_scorecard_json(soup: BeautifulSoup, scores: RTScores) -> None:
    for script_id in ("media-scorecard-json", "scoreDetails", "score-details"):
        data = _parse_json_script(soup, script_id)
        if data is not None:
            _apply_json_sections(data, scores)


def _strategy_media_scorecard(soup: BeautifulSoup, scores: RTScores) -> None:
    card = soup.find("media-scorecard") or soup
    for el in card.find_all(attrs={"slot": True}):
        slot = str(el.get("slot")).lower()
        text = el.get_text(" ", strip=True)
        if "critic" in slot or "tomatometer" in slot:
            if "score" in slot and scores.critic_score is None:
                scores.critic_score = _to_score(text)
            elif ("review" in slot or "count" in slot) and scores.critic_count is None:
                scores.critic_count = _to_int(text)
        elif "audience" in slot or "popcorn" in slot:
            if "score" in slot and scores.audience_score is None:
                scores.audience_score = _to_score(text)
            elif ("review" in slot or "rating" in slot or "count" in slot) and scores.audience_count is None:
                scores.audience_count = _clean_count(text)
    icon = card.find("score-icon-critics") or card.find("score-icon-critic")
    if icon is not None:
        cert = str(icon.get("certified", "")).lower()
        if cert == "true" or "certified" in str(icon.get("sentiment", "")).lower():
            scores.certified_fresh = True


def _strategy_score_board(soup: BeautifulSoup, scores: RTScores) -> None:
    board = soup.find("score-board") or soup.find("score-board-deprecated")
    if board is None:
        return
    if scores.critic_score is None:
        scores.critic_score = _to_score(board.get("tomatometerscore"))
    if scores.audience_score is None:
        scores.audience_score = _to_score(board.get("audiencescore"))
    if "certified" in str(board.get("tomatometerstate", "")).lower():
        scores.certified_fresh = True
    critics = board.find(attrs={"slot": "critics-count"})
    if critics is not None and scores.critic_count is None:
        scores.critic_count = _to_int(critics.get_text(" ", strip=True))
    audience = board.find(attrs={"slot": "audience-count"})
    if audience is not None and scores.audience_count is None:
        scores.audience_count = _clean_count(audience.get_text(" ", strip=True))


def _strategy_json_ld(soup: BeautifulSoup, scores: RTScores) -> None:
    for tag in soup.find_all("script", type="application/ld+json"):
        if not tag.string:
            continue
        try:
            data = json.loads(tag.string)
        except ValueError:
            continue
        items = data if isinstance(data, list) else [data]
        for item in items:
            if not isinstance(item, dict) or str(item.get("@type", "")).lower() != "movie":
                continue
            agg = item.get("aggregateRating") or {}
            if scores.critic_score is None:
                scores.critic_score = _to_score(agg.get("ratingValue"))
            if scores.critic_count is None:
                scores.critic_count = _to_int(agg.get("reviewCount") or agg.get("ratingCount"))
            if not scores.url:
                scores.url = normalize_rt_url(item.get("url"))


def parse_movie_page(html: str, url: str | None = None) -> RTScores:
    """Extract scores from an RT movie page. Never raises on parse problems."""
    scores = RTScores(url=normalize_rt_url(url) or url)
    soup = BeautifulSoup(html, "html.parser")
    for strategy in (_strategy_scorecard_json, _strategy_media_scorecard,
                     _strategy_score_board, _strategy_json_ld):
        try:
            strategy(soup, scores)
        except Exception as exc:  # noqa: BLE001 - a broken strategy must not break the sync
            log.debug("RT parse strategy %s failed: %s", strategy.__name__, exc)
    if scores.critic_score is None:
        scores.certified_fresh = False
    scores.status = STATUS_OK if scores.has_scores() else STATUS_NO_SCORES
    return scores


# ---------------------------------------------------------------------------
# HTTP client
# ---------------------------------------------------------------------------
class RottenTomatoesClient:
    """Single-threaded, polite client: realistic UA, delay between requests, backoff on 429/5xx."""

    def __init__(self, session: requests.Session | None = None, delay_seconds: float = 1.0,
                 timeout: float = 20, max_retries: int = 3):
        self.session = session or requests.Session()
        self.session.headers.update({
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        })
        self.delay_seconds = max(0.0, delay_seconds)
        self.timeout = timeout
        self.max_retries = max_retries
        self._last_request = 0.0
        self.request_count = 0

    def _wait(self) -> None:
        elapsed = time.monotonic() - self._last_request
        if elapsed < self.delay_seconds:
            time.sleep(self.delay_seconds - elapsed)

    def _get(self, url: str) -> str | None:
        """Page HTML, None on 404. Raises RTError after retries are exhausted."""
        delay = 2.0
        last = "unknown error"
        for attempt in range(1, self.max_retries + 1):
            self._wait()
            self._last_request = time.monotonic()
            self.request_count += 1
            try:
                resp = self.session.get(url, timeout=self.timeout)
            except requests.RequestException as exc:
                last = f"network error: {exc}"
            else:
                if resp.status_code == 404:
                    return None
                if resp.status_code == 429 or resp.status_code >= 500:
                    retry_after = resp.headers.get("Retry-After")
                    wait = float(retry_after) if retry_after and retry_after.isdigit() else delay
                    last = f"HTTP {resp.status_code}"
                    log.warning("RT %s: %s, retrying in %.0fs", url, last, wait)
                    time.sleep(wait)
                    delay *= 2
                    continue
                if not resp.ok:
                    raise RTError(f"HTTP {resp.status_code} for {url}")
                return resp.text
            log.warning("RT %s: %s (attempt %d/%d)", url, last, attempt, self.max_retries)
            time.sleep(delay)
            delay *= 2
        raise RTError(f"{url}: {last}")

    def search(self, title: str, year: int | None) -> str | None:
        html = self._get(SEARCH_URL.format(query=quote(title)))
        if not html:
            return None
        return parse_search_results(html, title, year)

    def fetch_scores(self, url: str) -> RTScores:
        url = normalize_rt_url(url) or url
        html = self._get(url)
        if html is None:
            return RTScores(url=url, status=STATUS_NOT_FOUND)
        return parse_movie_page(html, url)
