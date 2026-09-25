"""The on-demand /api/watch-links endpoint in serve.py."""
import json
import tempfile
import textwrap
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

import serve
from lib.cache import MovieCache


class FakeWatchmode:
    enabled = True
    used_this_month = 0

    def __init__(self):
        self.calls = []

    def sources(self, kind, tmdb_id, imdb_id, region="US"):
        self.calls.append((kind, tmdb_id, imdb_id))
        return [{"name": "Netflix", "type": "sub", "region": "US", "web_url": "https://www.netflix.com/title/1",
                 "ios_url": "nflx://www.netflix.com/title/1"},
                {"name": "Hulu", "type": "sub", "region": "US", "web_url": "https://www.hulu.com/movie/x"}]


class ServeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "config.yaml").write_text(textwrap.dedent("""
            services:
              - name: Netflix
                provider_ids: [8]
              - name: Hulu
                provider_ids: [15]
                enabled: false
        """))
        (self.root / "web").mkdir()
        (self.root / "web" / "index.html").write_text("<html>ok</html>")
        cache = MovieCache(self.root / "cache", "movie")
        cache.save(1, {"details": {"kind": "movie", "tmdb_id": 1, "imdb_id": "tt1", "title": "Heat",
                                   "flatrate_provider_ids": [8, 15]}, "details_fetched_at": "2026-01-01T00:00:00+00:00"})
        self.wm = FakeWatchmode()
        self.ctx = serve.AppContext(root=self.root, watchmode=self.wm)
        self.server = serve.make_server("127.0.0.1", 0, self.ctx)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.tmp.cleanup()

    def post(self, path, body):
        req = urllib.request.Request(self.base + path, data=json.dumps(body).encode(), method="POST",
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req) as resp:
                return resp.status, json.loads(resp.read())
        except urllib.error.HTTPError as err:
            return err.code, json.loads(err.read())

    def get(self, path):
        try:
            with urllib.request.urlopen(self.base + path) as resp:
                raw = resp.read()
                try:
                    return resp.status, json.loads(raw)
                except ValueError:
                    return resp.status, raw.decode(errors="replace")
        except urllib.error.HTTPError as err:
            body = err.read()
            try:
                return err.code, json.loads(body)
            except ValueError:
                return err.code, body.decode(errors="replace")

    def test_lookup_caches_and_filters_to_enabled_services(self):
        status, body = self.get("/api/watch-links?kind=movie&id=1")
        self.assertEqual(status, 200)
        self.assertTrue(body["enabled"])
        self.assertTrue(body["fetched"])
        self.assertEqual(body["watch_urls"], {"Netflix": "https://www.netflix.com/title/1"})  # Hulu disabled
        self.assertEqual(body["watch_app_urls"], {"Netflix": "nflx://www.netflix.com/title/1"})
        self.assertEqual(self.wm.calls, [("movie", 1, "tt1")])
        # second request served from the shared cache
        status, body = self.get("/api/watch-links?kind=movie&id=1")
        self.assertEqual(status, 200)
        self.assertFalse(body["fetched"])
        self.assertEqual(len(self.wm.calls), 1)
        cached = MovieCache(self.root / "cache", "movie").load(1)["watch_links"]["links"]
        self.assertIn("Netflix", cached)

    def test_people_and_watched(self):
        self.assertEqual(self.get("/api/watched")[1], {"people": [], "watched": {}})
        status, body = self.post("/api/people", {"add": "Matt"})
        self.assertEqual((status, body["people"]), (200, ["Matt"]))
        self.assertEqual(self.post("/api/people", {"add": " deb "})[1]["people"], ["Matt", "deb"])
        self.assertEqual(self.post("/api/people", {"add": "MATT"})[1]["people"], ["Matt", "deb"])  # case-insensitive dedupe
        status, body = self.post("/api/watched", {"id": "movie-1", "person": "matt", "watched": True})
        self.assertEqual(status, 200)
        self.assertEqual(list(body["watched"]["movie-1"]), ["Matt"])
        self.assertRegex(body["watched"]["movie-1"]["Matt"], r"^\d{4}-\d{2}-\d{2}$")
        self.post("/api/watched", {"id": "movie-1", "person": "deb"})
        self.post("/api/watched", {"id": "tv-7", "person": "deb"})
        snap = self.get("/api/watched")[1]
        self.assertEqual(sorted(snap["watched"]["movie-1"]), ["Matt", "deb"])
        # unmark, unknown person, bad id
        body = self.post("/api/watched", {"id": "movie-1", "person": "Matt", "watched": False})[1]
        self.assertEqual(list(body["watched"]["movie-1"]), ["deb"])
        self.assertEqual(self.post("/api/watched", {"id": "movie-1", "person": "Nobody"})[0], 400)
        self.assertEqual(self.post("/api/watched", {"id": "x", "person": "Matt"})[0], 400)
        self.assertEqual(self.post("/api/people", {})[0], 400)
        self.assertEqual(self.post("/api/nope", {})[0], 404)
        # removing a person drops their marks; the file is what the other app reads
        body = self.post("/api/people", {"remove": "deb"})[1]
        self.assertEqual(body, {"people": ["Matt"], "watched": {}})
        self.assertTrue((self.root / "data" / "watched.json").exists())
        self.assertEqual(self.post("/api/people", {"people": ["Deb", "Matt", "Deb"]})[1]["people"], ["Deb", "Matt"])

    def test_ping(self):
        status, body = self.get("/api/ping")
        self.assertEqual(status, 200)
        self.assertTrue(body["ok"])
        self.assertFalse(body["movies"])

    def test_errors(self):
        self.assertEqual(self.get("/api/watch-links?kind=movie&id=999")[0], 404)
        self.assertEqual(self.get("/api/watch-links?kind=book&id=1")[0], 400)
        self.assertEqual(self.get("/api/nope")[0], 404)
        status, body = self.get("/")
        self.assertEqual(status, 200)  # redirected to /web/
        self.assertIn("ok", body)

    def test_without_watchmode_serves_cached_links_only(self):
        self.get("/api/watch-links?kind=movie&id=1")  # populate the cache via the fake
        self.ctx._watchmode = None
        status, body = self.get("/api/watch-links?kind=movie&id=1")
        self.assertEqual(status, 200)
        self.assertFalse(body["enabled"])
        self.assertEqual(body["watch_urls"], {"Netflix": "https://www.netflix.com/title/1"})


if __name__ == "__main__":
    unittest.main()
