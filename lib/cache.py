"""Per-movie JSON cache with timestamps (cache/ directory)."""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def is_fresh(timestamp: str | None, max_days: float) -> bool:
    """True if `timestamp` is within `max_days` of now."""
    dt = parse_iso(timestamp)
    if dt is None:
        return False
    return datetime.now(timezone.utc) - dt < timedelta(days=max_days)


class MovieCache:
    """JSON-file cache: one file per movie plus per-service discovery results."""

    def __init__(self, root: str | Path = "cache"):
        self.root = Path(root)
        self.movies_dir = self.root / "movies"
        self.discover_dir = self.root / "discover"
        self.movies_dir.mkdir(parents=True, exist_ok=True)
        self.discover_dir.mkdir(parents=True, exist_ok=True)

    # -- movies -------------------------------------------------------------
    def _movie_path(self, tmdb_id: int) -> Path:
        return self.movies_dir / f"{int(tmdb_id)}.json"

    def load(self, tmdb_id: int) -> dict:
        entry = _read_json(self._movie_path(tmdb_id)) or {}
        entry["tmdb_id"] = int(tmdb_id)
        return entry

    def save(self, tmdb_id: int, entry: dict) -> None:
        entry = dict(entry)
        entry["tmdb_id"] = int(tmdb_id)
        _write_json(self._movie_path(tmdb_id), entry)

    # -- discovery ----------------------------------------------------------
    def _discover_path(self, key: str) -> Path:
        safe = re.sub(r"[^a-z0-9_\-]+", "-", key.lower()).strip("-") or "default"
        return self.discover_dir / f"{safe}.json"

    def load_discovery(self, key: str) -> dict | None:
        return _read_json(self._discover_path(key))

    def save_discovery(self, key: str, results: list[dict]) -> None:
        _write_json(self._discover_path(key), {"fetched_at": now_iso(), "results": results})


def _read_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)
    tmp.replace(path)
