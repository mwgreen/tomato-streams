"""Load and validate config.yaml."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml


class ConfigError(Exception):
    pass


@dataclass
class Service:
    name: str
    provider_ids: list[int]
    enabled: bool = True

    @property
    def slug(self) -> str:
        return re.sub(r"[^a-z0-9]+", "-", self.name.lower()).strip("-")


@dataclass
class SyncSettings:
    min_tmdb_vote_count: int = 50
    max_pages_per_service: int = 50
    cache_days_scores: float = 7
    cache_days_providers: float = 2
    request_delay_seconds: float = 1.0


@dataclass
class UIDefaults:
    min_critic_reviews: int = 20
    sort: str = "critic_desc"


@dataclass
class Config:
    region: str
    services: list[Service]
    sync: SyncSettings = field(default_factory=SyncSettings)
    ui_defaults: UIDefaults = field(default_factory=UIDefaults)

    @property
    def enabled_services(self) -> list[Service]:
        return [s for s in self.services if s.enabled]

    def service_by_name(self, name: str) -> Service | None:
        wanted = name.strip().lower()
        for s in self.services:
            if s.name.lower() == wanted:
                return s
        return None


def _as_int_list(value, context: str) -> list[int]:
    if value is None:
        raise ConfigError(f"{context}: provider_ids is required")
    if isinstance(value, int):
        value = [value]
    if not isinstance(value, list) or not value:
        raise ConfigError(f"{context}: provider_ids must be a non-empty list of integers")
    out: list[int] = []
    for v in value:
        if isinstance(v, bool) or not isinstance(v, int):
            raise ConfigError(f"{context}: provider id {v!r} is not an integer")
        out.append(v)
    return out


def load_config(path: str | Path = "config.yaml") -> Config:
    path = Path(path)
    if not path.exists():
        raise ConfigError(f"config file not found: {path}")
    with path.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    if not isinstance(raw, dict):
        raise ConfigError("config.yaml must be a mapping")

    region = str(raw.get("region") or "US").upper()
    if not re.fullmatch(r"[A-Z]{2}", region):
        raise ConfigError(f"region must be a 2-letter country code, got {region!r}")

    raw_services = raw.get("services") or []
    if not isinstance(raw_services, list) or not raw_services:
        raise ConfigError("config.yaml needs at least one entry under `services`")
    services: list[Service] = []
    seen: set[str] = set()
    for i, item in enumerate(raw_services):
        if not isinstance(item, dict) or not item.get("name"):
            raise ConfigError(f"services[{i}]: each service needs a `name`")
        name = str(item["name"]).strip()
        if name.lower() in seen:
            raise ConfigError(f"services: duplicate service name {name!r}")
        seen.add(name.lower())
        services.append(
            Service(
                name=name,
                provider_ids=_as_int_list(item.get("provider_ids"), f"services[{i}] ({name})"),
                enabled=bool(item.get("enabled", True)),
            )
        )

    sync_raw = raw.get("sync") or {}
    sync = SyncSettings(
        min_tmdb_vote_count=int(sync_raw.get("min_tmdb_vote_count", 50)),
        max_pages_per_service=max(1, int(sync_raw.get("max_pages_per_service", 50))),
        cache_days_scores=float(sync_raw.get("cache_days_scores", 7)),
        cache_days_providers=float(sync_raw.get("cache_days_providers", 2)),
        request_delay_seconds=float(sync_raw.get("request_delay_seconds", 1.0)),
    )
    ui_raw = raw.get("ui_defaults") or {}
    ui = UIDefaults(
        min_critic_reviews=int(ui_raw.get("min_critic_reviews", 20)),
        sort=str(ui_raw.get("sort", "critic_desc")),
    )
    return Config(region=region, services=services, sync=sync, ui_defaults=ui)
