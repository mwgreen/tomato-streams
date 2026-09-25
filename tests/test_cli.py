"""End-to-end run of sync.py against a local mock of TMDB / OMDb / Rotten Tomatoes."""
import io
import json
import tempfile
import textwrap
import threading
import unittest
from contextlib import redirect_stdout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock
from urllib.parse import parse_qs, urlparse

import lib.omdb
import lib.rottentomatoes
import lib.tmdb
import sync

RT_PAGE = """<html><body>
<script id="media-scorecard-json" type="application/json">
{"criticsScore":{"score":"94","reviewCount":212,"certified":true},"audienceScore":{"score":"88","bandedRatingCount":"2,500+"}}
</script></body></html>"""

SEARCH_PAGE = """<html><body><search-page-result type="movie">
<search-page-media-row releaseyear="2023"><a slot="title" href="https://www.rottentomatoes.com/m/oppenheimer_2023">Oppenheimer</a></search-page-media-row>
</search-page-result>
<search-page-result type="tvSeries">
<search-page-media-row startyear="2022"><a slot="title" href="https://www.rottentomatoes.com/tv/severance/s01">Severance</a></search-page-media-row>
</search-page-result></body></html>"""

TV_PAGE = """<html><body><score-board tomatometerscore="97" tomatometerstate="certified-fresh" audiencescore="89">
<a slot="critics-count">150 Reviews</a><a slot="audience-count">5,000+ Ratings</a></score-board></body></html>"""


class MockHandler(BaseHTTPRequestHandler):
    hits = []
    flaky_left = 1  # first details request answers 503 to exercise retries

    def log_message(self, *args):
        pass

    def _send(self, status, body, ctype="application/json"):
        data = body.encode() if isinstance(body, str) else json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        url = urlparse(self.path)
        qs = {k: v[0] for k, v in parse_qs(url.query).items()}
        MockHandler.hits.append(url.path)
        if url.path == "/tmdb/watch/providers/movie":
            return self._send(200, {"results": [{"provider_id": 1899, "provider_name": "HBO Max",
                                                 "display_priorities": {"US": 1}}]})
        if url.path == "/tmdb/discover/movie":
            assert qs["with_watch_monetization_types"] == "flatrate", qs
            assert qs["with_watch_providers"] == "1899"
            return self._send(200, {"page": 1, "total_pages": 1, "results": [
                {"id": 872585, "title": "Oppenheimer", "popularity": 90.1, "vote_count": 9000}]})
        if url.path == "/tmdb/movie/872585":
            if MockHandler.flaky_left > 0:
                MockHandler.flaky_left -= 1
                return self._send(503, {"error": "try again"})
            return self._send(200, {
                "id": 872585, "title": "Oppenheimer", "release_date": "2023-07-19", "overview": "Boom.",
                "runtime": 181, "genres": [{"name": "Drama"}], "poster_path": "/o.jpg", "backdrop_path": "/ob.jpg",
                "vote_average": 8.1, "vote_count": 9000, "popularity": 90.1,
                "external_ids": {"imdb_id": "tt15398776"},
                "videos": {"results": [{"site": "YouTube", "key": "abc", "type": "Trailer", "official": True}]},
                "watch/providers": {"results": {"US": {"link": "https://jw.example/x",
                                                       "flatrate": [{"provider_id": 1899, "provider_name": "HBO Max"}]}}}})
        if url.path == "/tmdb/discover/tv":
            assert qs["with_watch_monetization_types"] == "flatrate", qs
            assert qs["vote_count.gte"] == "20", qs
            return self._send(200, {"page": 1, "total_pages": 1, "results": [
                {"id": 95396, "name": "Severance", "popularity": 300.0, "vote_count": 2000}]})
        if url.path == "/tmdb/tv/95396":
            return self._send(200, {
                "id": 95396, "name": "Severance", "first_air_date": "2022-02-18", "last_air_date": "2022-04-08",
                "in_production": False, "status": "Ended", "number_of_seasons": 1, "number_of_episodes": 9,
                "episode_run_time": [55], "overview": "Innies.", "genres": [{"name": "Drama"}],
                "poster_path": "/s.jpg", "backdrop_path": "/sb.jpg", "vote_average": 8.4, "vote_count": 2000,
                "popularity": 300.0, "external_ids": {"imdb_id": "tt11280740"}, "videos": {"results": []},
                "watch/providers": {"results": {"US": {"link": "https://jw.example/s",
                                                       "flatrate": [{"provider_id": 1899, "provider_name": "HBO Max"}]}}}})
        if url.path == "/rt/tv/severance":
            return self._send(200, TV_PAGE, "text/html")
        if url.path == "/omdb/":
            assert qs["tomatoes"] == "true"
            return self._send(200, {"Response": "True", "tomatoURL": "N/A",
                                    "Ratings": [{"Source": "Rotten Tomatoes", "Value": "93%"}]})
        if url.path == "/rt/search":
            return self._send(200, SEARCH_PAGE, "text/html")
        if url.path == "/rt/m/oppenheimer_2023":
            return self._send(200, RT_PAGE, "text/html")
        return self._send(404, {"error": "not found"})


class CliTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), MockHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def setUp(self):
        MockHandler.hits = []
        MockHandler.flaky_left = 1
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "config.yaml").write_text(textwrap.dedent("""
            region: US
            services:
              - name: HBO Max
                provider_ids: [1899]
            sync: {request_delay_seconds: 0, cache_days_scores: 7, cache_days_providers: 2}
        """))
        patches = [
            mock.patch.object(lib.tmdb, "BASE_URL", self.base + "/tmdb"),
            mock.patch.object(lib.omdb, "BASE_URL", self.base + "/omdb/"),
            mock.patch.object(lib.rottentomatoes, "BASE_URL", self.base + "/rt"),
            mock.patch.object(lib.rottentomatoes, "SEARCH_URL", self.base + "/rt/search?search={query}"),
            mock.patch("time.sleep", lambda s: None),
            mock.patch.dict("os.environ", {"TMDB_API_KEY": "k3y", "OMDB_API_KEY": "omdbkey"}),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def tearDown(self):
        self.tmp.cleanup()

    def args(self, *extra):
        return ["--config", str(self.root / "config.yaml"), "--cache-dir", str(self.root / "cache"),
                "--data-dir", str(self.root / "data"), *extra]

    def test_sync_end_to_end_and_cached_rerun(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = sync.main(self.args())
        self.assertEqual(code, 0, buf.getvalue())
        out = json.loads((self.root / "data" / "movies.json").read_text())
        self.assertEqual(out["services"], ["HBO Max"])
        self.assertEqual(len(out["movies"]), 1)
        m = out["movies"][0]
        self.assertEqual(m["title"], "Oppenheimer")
        self.assertEqual(m["services"], ["HBO Max"])
        # RT URL came from search (OMDb had N/A), page parsed via scorecard JSON; search URL is
        # rewritten to the mock host because normalize_rt_url canonicalises it.
        self.assertEqual(m["rt"], {"url": self.base + "/rt/m/oppenheimer_2023", "status": "ok",
                                   "critic_score": 94, "critic_count": 212, "certified_fresh": True,
                                   "audience_score": 88, "audience_count": "2,500+"})
        self.assertIn("both critic + audience score: 1/1", buf.getvalue())
        self.assertIn("OMDb requests used today: 2", buf.getvalue())

        tv = json.loads((self.root / "data" / "tv.json").read_text())
        self.assertEqual(tv["kind"], "tv")
        self.assertEqual(len(tv["movies"]), 1)
        s = tv["movies"][0]
        self.assertEqual((s["title"], s["year"], s["end_year"], s["seasons"], s["status"]),
                         ("Severance", 2022, 2022, 1, "Ended"))
        self.assertEqual(s["rt"], {"url": self.base + "/rt/tv/severance", "status": "ok",
                                   "critic_score": 97, "critic_count": 150, "certified_fresh": True,
                                   "audience_score": 89, "audience_count": "5,000+"})
        self.assertIn("[TV series]", buf.getvalue())
        self.assertEqual(MockHandler.hits.count("/tmdb/movie/872585"), 2)  # 503 then 200
        self.assertEqual(json.loads((self.root / "cache" / "omdb_usage.json").read_text())["count"], 2)

        MockHandler.hits = []
        with redirect_stdout(io.StringIO()):
            self.assertEqual(sync.main(self.args()), 0)
        self.assertEqual([h for h in MockHandler.hits if not h.startswith("/tmdb/watch")], [])

    def test_kind_movie_only(self):
        with redirect_stdout(io.StringIO()):
            self.assertEqual(sync.main(self.args("--kind", "movie")), 0)
        self.assertTrue((self.root / "data" / "movies.json").exists())
        self.assertFalse((self.root / "data" / "tv.json").exists())
        self.assertNotIn("/tmdb/discover/tv", MockHandler.hits)

    def test_list_providers(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = sync.main(self.args("--list-providers"))
        self.assertEqual(code, 0)
        self.assertIn("1899  HBO Max", buf.getvalue())

    def test_unknown_service_flag(self):
        with redirect_stdout(io.StringIO()):
            self.assertEqual(sync.main(self.args("--service", "Nope")), 2)


if __name__ == "__main__":
    unittest.main()
