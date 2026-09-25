#!/usr/bin/env python3
"""Serve the web UI and data/*.json locally, plus one small API for on-demand
Watchmode lookups (exact "Watch on <service>" links) so the API key stays server-side.

    python serve.py                  # http://localhost:8000
    python serve.py --host 0.0.0.0   # reachable from your phone on the same Wi-Fi
    python serve.py --port 9000

GET /api/ping                  -> {"ok": true, ...}   (used by the Apple TV app to test the address)
GET /api/watch-links?kind=movie|tv&id=<tmdb id>
    -> {"enabled": bool, "watch_urls": {service: url}, "watch_app_urls": {service: url}}
    Looks the title up on Watchmode the first time (if WATCHMODE_API_KEY is set),
    stores the result in the same per-title cache sync.py uses, and returns it.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from lib.cache import MovieCache  # noqa: E402
from lib.config import ConfigError, load_config  # noqa: E402
from lib.pipeline import SyncSummary, ensure_watch_links, match_services  # noqa: E402
from lib.watchmode import WatchmodeClient  # noqa: E402

log = logging.getLogger("serve")

BONJOUR_TYPE = "_streamingfinder._tcp.local."


def lan_ip() -> str | None:
    """Best-effort LAN address of this machine (no packets are sent)."""
    import socket
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("10.255.255.255", 1))
            return sock.getsockname()[0]
    except OSError:
        return None


def advertise_bonjour(port: int):
    """Announce this server on the LAN so the Apple TV app can find it without typing
    an address. Needs the optional `zeroconf` package; silently skipped otherwise."""
    try:
        from zeroconf import ServiceInfo, Zeroconf  # type: ignore
    except ImportError:
        log.info("zeroconf not installed; the Apple TV app will need the server address typed in "
                 "(pip install zeroconf to enable discovery)")
        return None
    import socket
    ip = lan_ip()
    if not ip:
        log.info("could not determine a LAN address; skipping Bonjour advertisement")
        return None
    info = ServiceInfo(
        BONJOUR_TYPE, f"Streaming Finder.{BONJOUR_TYPE}", addresses=[socket.inet_aton(ip)], port=port,
        properties={"url": f"http://{ip}:{port}", "path": "/"}, server=f"{socket.gethostname().split('.')[0]}.local.",
    )
    try:
        zc = Zeroconf()
        zc.register_service(info)
        log.info("advertising on Bonjour as http://%s:%d", ip, port)
        return zc
    except OSError as exc:
        log.warning("Bonjour advertisement failed: %s", exc)
        return None


class AppContext:
    """Lazily-built config + Watchmode client shared by request threads."""

    def __init__(self, root: Path = ROOT, config_path: Path | None = None, cache_dir: Path | None = None,
                 watchmode: WatchmodeClient | None = None):
        self.root = root
        self.config_path = config_path or root / "config.yaml"
        self.cache_dir = cache_dir or root / "cache"
        self._config = None
        self._watchmode = watchmode
        self._watchmode_built = watchmode is not None
        self.lock = threading.Lock()

    @property
    def config(self):
        if self._config is None:
            self._config = load_config(self.config_path)
        return self._config

    @property
    def watchmode(self) -> WatchmodeClient | None:
        if not self._watchmode_built:
            self._watchmode_built = True
            key = os.environ.get("WATCHMODE_API_KEY", "")
            if key:
                self._watchmode = WatchmodeClient(key, usage_file=self.cache_dir / "watchmode_usage.json")
                log.info("Watchmode on-demand lookups enabled")
            else:
                log.info("WATCHMODE_API_KEY not set; /api/watch-links serves cached links only")
        return self._watchmode

    def watch_links(self, kind: str, tmdb_id: str) -> tuple[int, dict]:
        if kind not in ("movie", "tv") or not tmdb_id.isdigit():
            return 400, {"error": "kind must be movie|tv and id a TMDB id"}
        try:
            cfg = self.config
        except ConfigError as exc:
            return 500, {"error": f"config error: {exc}"}
        cache = MovieCache(self.cache_dir, kind)
        entry = cache.load(int(tmdb_id))
        details = entry.get("details")
        if not details:
            return 404, {"error": "title not in the cache; run sync.py first"}
        carried = match_services(details.get("flatrate_provider_ids"), cfg.enabled_services)
        wm = self.watchmode
        summary = SyncSummary()
        with self.lock:
            links = ensure_watch_links(entry, cache, cfg, wm, carried, cfg.enabled_services, False, summary)
        return 200, {
            "enabled": bool(wm is not None and wm.enabled),
            "fetched": summary.watch_links_fetched > 0,
            "watch_urls": {k: v["web"] for k, v in links.items() if v.get("web")},
            "watch_app_urls": {k: v["ios"] for k, v in links.items() if v.get("ios")},
            "watch_url_levels": {k: v["level"] for k, v in links.items() if v.get("level")},
        }


class Handler(SimpleHTTPRequestHandler):
    ctx: AppContext | None = None

    def do_GET(self):
        url = urlparse(self.path)
        if url.path in ("", "/", "/index.html"):
            self.send_response(302)
            self.send_header("Location", "/web/")
            self.end_headers()
            return
        if url.path == "/api/ping":
            data_dir = self.ctx.root / "data"
            self._send_json(200, {"ok": True, "app": "streaming-finder",
                                  "movies": (data_dir / "movies.json").exists(),
                                  "tv": (data_dir / "tv.json").exists()})
            return
        if url.path == "/api/watch-links":
            qs = {k: v[0] for k, v in parse_qs(url.query).items()}
            try:
                status, payload = self.ctx.watch_links(qs.get("kind", "movie"), qs.get("id", ""))
            except Exception as exc:  # noqa: BLE001 - never take the server down for one lookup
                log.exception("watch-links lookup failed")
                status, payload = 500, {"error": f"{type(exc).__name__}: {exc}"}
            self._send_json(status, payload)
            return
        if url.path.startswith("/api/"):
            self._send_json(404, {"error": "unknown API endpoint"})
            return
        super().do_GET()

    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, fmt, *args):  # quieter logs
        msg = fmt % args
        if "movies.json" in msg or "tv.json" in msg or "/api/" in msg or self.command != "GET":
            super().log_message(fmt, *args)


def make_server(host: str, port: int, ctx: AppContext) -> ThreadingHTTPServer:
    Handler.ctx = ctx
    return ThreadingHTTPServer((host, port), partial(Handler, directory=str(ctx.root)))


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--host", default="127.0.0.1", help="use 0.0.0.0 to reach it from other devices")
    p.add_argument("--port", type=int, default=8000)
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s", datefmt="%H:%M:%S")
    load_dotenv(ROOT / ".env")
    if not (ROOT / "data" / "movies.json").exists():
        print("note: data/movies.json does not exist yet; run `python sync.py` first", file=sys.stderr)
    server = make_server(args.host, args.port, AppContext())
    print(f"Serving on http://{args.host}:{args.port}/  (Ctrl+C to stop)")
    if args.host == "127.0.0.1":
        print("note: only this machine can reach it; use --host 0.0.0.0 for your phone / Apple TV")
    zc = advertise_bonjour(args.port) if args.host != "127.0.0.1" else None
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        if zc is not None:
            zc.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
