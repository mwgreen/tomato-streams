"""People and "watched by" marks, shared by the web app and the Apple TV app.

Stored in data/watched.json:
    {"people": ["Matt", "Deb"],
     "watched": {"movie-872585": {"Matt": "2026-09-25"}, "tv-95396": {"Deb": "2026-09-20"}}}

Title ids are "<kind>-<tmdb id>", the same ids the front ends use.
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path

MAX_PEOPLE = 20
MAX_NAME = 40


class WatchedError(ValueError):
    pass


class WatchedStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.lock = threading.Lock()

    # -- storage -------------------------------------------------------------
    def _read(self) -> dict:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        people = [str(p) for p in (data.get("people") or []) if str(p).strip()]
        watched = {}
        for tid, marks in (data.get("watched") or {}).items():
            if isinstance(marks, dict):
                clean = {str(p): str(d) for p, d in marks.items() if str(p) in people}
            elif isinstance(marks, list):  # tolerate ["Matt"] form
                clean = {str(p): "" for p in marks if str(p) in people}
            else:
                continue
            if clean:
                watched[str(tid)] = clean
        return {"people": people, "watched": watched}

    def _write(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(self.path)

    def snapshot(self) -> dict:
        with self.lock:
            return self._read()

    # -- people --------------------------------------------------------------
    @staticmethod
    def _clean_name(name) -> str:
        name = " ".join(str(name or "").split())
        if not name:
            raise WatchedError("name is empty")
        if len(name) > MAX_NAME:
            raise WatchedError(f"name is longer than {MAX_NAME} characters")
        return name

    def set_people(self, people: list) -> dict:
        names: list[str] = []
        for p in people or []:
            n = self._clean_name(p)
            if n.lower() not in {x.lower() for x in names}:
                names.append(n)
        if len(names) > MAX_PEOPLE:
            raise WatchedError(f"at most {MAX_PEOPLE} people")
        with self.lock:
            data = self._read()
            data["people"] = names
            # drop marks of removed people
            data["watched"] = {t: {p: d for p, d in m.items() if p in names} for t, m in data["watched"].items()}
            data["watched"] = {t: m for t, m in data["watched"].items() if m}
            self._write(data)
            return data

    def add_person(self, name) -> dict:
        n = self._clean_name(name)
        with self.lock:
            people = self._read()["people"]
        if n.lower() in {p.lower() for p in people}:
            return self.snapshot()
        return self.set_people(people + [n])

    def remove_person(self, name) -> dict:
        n = self._clean_name(name)
        with self.lock:
            people = self._read()["people"]
        return self.set_people([p for p in people if p.lower() != n.lower()])

    # -- marks ---------------------------------------------------------------
    def mark(self, title_id, person, watched: bool) -> dict:
        tid = str(title_id or "").strip()
        if not tid or "-" not in tid:
            raise WatchedError("id must look like movie-123 or tv-123")
        n = self._clean_name(person)
        with self.lock:
            data = self._read()
            match = next((p for p in data["people"] if p.lower() == n.lower()), None)
            if match is None:
                raise WatchedError(f"unknown person {n!r}; add them first")
            marks = data["watched"].setdefault(tid, {})
            if watched:
                marks.setdefault(match, datetime.now(timezone.utc).strftime("%Y-%m-%d"))
            else:
                marks.pop(match, None)
            if not marks:
                data["watched"].pop(tid, None)
            self._write(data)
            return data
