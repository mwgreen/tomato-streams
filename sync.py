#!/usr/bin/env python3
"""Fetch subscription-streaming movies from TMDB, enrich with Rotten Tomatoes scores,
cache everything, and write data/movies.json for the web UI.

    python sync.py                     # normal incremental sync
    python sync.py --list-providers    # print TMDB watch providers for your region
    python sync.py --list-providers peacock   # ...filtered by name
    python sync.py --full              # ignore the cache
    python sync.py --service "HBO Max" # sync a single service
    python sync.py --limit 30          # quick test run
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from lib.cache import MovieCache  # noqa: E402
from lib.config import ConfigError, load_config  # noqa: E402
from lib.omdb import OMDbClient  # noqa: E402
from lib.pipeline import run_sync  # noqa: E402
from lib.rottentomatoes import RottenTomatoesClient  # noqa: E402
from lib.tmdb import TMDBClient, TMDBError  # noqa: E402
from lib.watchmode import WatchmodeClient  # noqa: E402

log = logging.getLogger("sync")


def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--config", default=str(ROOT / "config.yaml"), help="path to config.yaml")
    p.add_argument("--data-dir", default=str(ROOT / "data"),
                   help="output directory (writes movies.json and tv.json)")
    p.add_argument("--kind", choices=["movie", "tv", "all"], default="all",
                   help="what to sync: movies, TV series, or both (default: all enabled in config)")
    p.add_argument("--cache-dir", default=str(ROOT / "cache"), help="cache directory")
    p.add_argument("--list-providers", nargs="?", const="", default=None, metavar="NAME",
                   help="print TMDB watch providers for the configured region and exit; "
                        "an optional NAME filters by provider name (case-insensitive)")
    p.add_argument("--full", action="store_true", help="ignore the cache and re-fetch everything")
    p.add_argument("--service", action="append", metavar="NAME",
                   help='sync only this service (repeatable), e.g. --service "HBO Max"')
    p.add_argument("--limit", type=int, metavar="N", help="process at most N movies (for testing)")
    p.add_argument("--skip-scores", action="store_true",
                   help="do not contact OMDb / Rotten Tomatoes (TMDB only; keeps cached scores)")
    p.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    return p.parse_args(argv)


def list_providers(tmdb: TMDBClient, cfg, query: str = "") -> int:
    providers = tmdb.list_watch_providers(cfg.region)
    configured: dict[int, list[str]] = {}
    for s in cfg.services:
        for pid in s.provider_ids:
            configured.setdefault(pid, []).append(s.name + ("" if s.enabled else " (disabled)"))
    query = (query or "").strip().lower()
    shown = [p for p in providers if not query or query in str(p["provider_name"]).lower()
             or p["provider_id"] in configured and query in " ".join(configured[p["provider_id"]]).lower()]
    title = f"TMDB movie watch providers for region {cfg.region}"
    print(f"{title} matching {query!r} ({len(shown)} of {len(providers)}):\n" if query
          else f"{title} ({len(providers)}):\n")
    print(f"{'id':>6}  {'provider':<45} configured as")
    print(f"{'-'*6}  {'-'*45} {'-'*20}")
    for p in shown:
        marker = ", ".join(configured.get(p["provider_id"], []))
        print(f"{p['provider_id']:>6}  {p['provider_name']:<45} {marker}")
    known = {p["provider_id"] for p in providers}
    missing = [(pid, names) for pid, names in configured.items() if pid not in known]
    print()
    if missing:
        for pid, names in missing:
            print(f"WARNING: provider id {pid} ({', '.join(names)}) is not available in {cfg.region}")
        return 1
    print("All configured provider IDs exist in this region. Compare the names in the "
          "'configured as' column with the provider names to catch wrong IDs.")
    return 0


def warn_unknown_providers(tmdb: TMDBClient, cfg) -> None:
    try:
        known = {p["provider_id"] for p in tmdb.list_watch_providers(cfg.region)}
    except TMDBError as exc:
        log.warning("could not verify provider IDs: %s", exc)
        return
    for s in cfg.enabled_services:
        for pid in s.provider_ids:
            if pid not in known:
                log.warning("config: provider id %s for %s does not exist in region %s "
                            "(run `python sync.py --list-providers`)", pid, s.name, cfg.region)


def main(argv=None) -> int:
    args = parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(message)s", datefmt="%H:%M:%S")
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    load_dotenv(ROOT / ".env")

    try:
        cfg = load_config(args.config)
    except ConfigError as exc:
        log.error("config error: %s", exc)
        return 2

    try:
        tmdb = TMDBClient(os.environ.get("TMDB_API_KEY", ""))
    except TMDBError as exc:
        log.error("%s", exc)
        return 2

    if args.list_providers is not None:
        try:
            return list_providers(tmdb, cfg, args.list_providers)
        except TMDBError as exc:
            log.error("%s", exc)
            return 1

    only_services = None
    if args.service:
        only_services = []
        for name in args.service:
            svc = cfg.service_by_name(name)
            if svc is None:
                log.error("unknown service %r; configured: %s", name, ", ".join(s.name for s in cfg.services))
                return 2
            if not svc.enabled:
                log.warning("service %r is disabled in config.yaml; syncing it anyway", svc.name)
                svc.enabled = True
            only_services.append(svc)

    if not cfg.enabled_services:
        log.error("no enabled services in config.yaml")
        return 2

    warn_unknown_providers(tmdb, cfg)

    omdb = rt = watchmode = None
    watchmode_key = os.environ.get("WATCHMODE_API_KEY", "")
    if watchmode_key and not args.skip_scores:
        watchmode = WatchmodeClient(watchmode_key, usage_file=Path(args.cache_dir) / "watchmode_usage.json")
    elif not watchmode_key:
        log.info("WATCHMODE_API_KEY not set; Watch buttons will use service search pages")
    if not args.skip_scores:
        omdb_key = os.environ.get("OMDB_API_KEY", "")
        if omdb_key:
            omdb = OMDbClient(omdb_key, usage_file=Path(args.cache_dir) / "omdb_usage.json")
        else:
            log.warning("OMDB_API_KEY not set; RT pages will be found via RT search only")
        rt = RottenTomatoesClient(delay_seconds=cfg.sync.request_delay_seconds)

    kinds = ["movie", "tv"] if args.kind == "all" else [args.kind]
    if args.kind == "all" and not cfg.tv.enabled:
        kinds = ["movie"]
    data_dir = Path(args.data_dir)
    exit_code = 0
    for kind in kinds:
        output_path = data_dir / ("movies.json" if kind == "movie" else "tv.json")
        label = "movies" if kind == "movie" else "TV series"
        log.info("=== syncing %s ===", label)
        previous = None
        if output_path.exists():
            try:
                previous = json.loads(output_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                previous = None
        try:
            output, summary = run_sync(cfg, tmdb, omdb, rt, MovieCache(args.cache_dir, kind),
                                       full=args.full, limit=args.limit, only_services=only_services,
                                       previous=previous, kind=kind, watchmode=watchmode)
        except TMDBError as exc:
            log.error("%s", exc)
            exit_code = 1
            continue
        except KeyboardInterrupt:
            log.warning("interrupted; cached results are kept, re-run to continue")
            return 130

        output_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = output_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(output, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(output_path)
        log.info("wrote %s (%d %s)", output_path, len(output["movies"]), label)
        print(f"\n[{label}]" + summary.format())
    if rt is not None:
        print(f"Rotten Tomatoes requests this run: {rt.request_count}")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
