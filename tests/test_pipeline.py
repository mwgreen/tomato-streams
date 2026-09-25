import io
import json
import tempfile
import textwrap
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from lib.cache import MovieCache
from lib.config import ConfigError, load_config
from lib.pipeline import match_services, merge_with_previous, run_sync
from lib.rottentomatoes import RTError, RTScores
from lib.tmdb import TMDBError

CONFIG = textwrap.dedent("""
    region: US
    services:
      - name: Netflix
        provider_ids: [8, 1796]
      - name: HBO Max
        provider_ids: [1899]
      - name: Hulu
        provider_ids: [15]
        enabled: false
      - name: Apple TV
        provider_ids: [350]
    tv:
      min_tmdb_vote_count: 20
    sync:
      min_tmdb_vote_count: 50
      max_pages_per_service: 2
      cache_days_scores: 7
      cache_days_providers: 2
      request_delay_seconds: 0
    ui_defaults:
      min_critic_reviews: 20
      sort: audience_desc
""")


def details(tmdb_id, title, year, flatrate, imdb_id=None, videos=None):
    return {
        "id": tmdb_id, "title": title, "original_title": title, "release_date": f"{year}-05-01",
        "overview": f"About {title}.", "runtime": 100 + tmdb_id, "genres": [{"id": 1, "name": "Drama"}],
        "poster_path": f"/p{tmdb_id}.jpg", "backdrop_path": f"/b{tmdb_id}.jpg",
        "vote_average": 7.5, "vote_count": 500, "popularity": 10.0 * tmdb_id,
        "external_ids": {"imdb_id": imdb_id},
        "videos": {"results": videos or [
            {"site": "YouTube", "key": "teaser", "type": "Teaser", "official": True},
            {"site": "YouTube", "key": "official", "type": "Trailer", "official": True, "name": "Official Trailer"},
            {"site": "YouTube", "key": "fan", "type": "Trailer", "official": False}]},
        "watch/providers": {"results": {"US": {
            "link": f"https://www.themoviedb.org/movie/{tmdb_id}/watch?locale=US",
            "flatrate": [{"provider_id": pid, "provider_name": f"P{pid}"} for pid in flatrate],
            "rent": [{"provider_id": 10, "provider_name": "Amazon Video"}],
        }}},
    }


class FakeTMDB:
    def __init__(self):
        self.calls = {"discover": 0, "details": 0}
        self.movies = {
            1: details(1, "Heat", 1995, [8, 1899], "tt0113277"),
            2: details(2, "Oppenheimer", 2023, [1899], "tt15398776"),
            3: details(3, "Rent Only", 2020, []),                  # left subscription -> dropped
            4: details(4, "Channel Only", 2021, [1825]),           # HBO Max Amazon Channel -> dropped
            5: details(5, "Hulu Only", 2019, [15]),                # disabled service -> dropped
            6: details(6, "No Scores", 2024, [1796], None),        # ad tier of Netflix
        }
        self.discover_by_provider = {"8|1796": [1, 3, 6], "1899": [1, 2, 4, 5], "15": [5]}
        self.tv = {
            7: {"id": 7, "name": "Severance", "original_name": "Severance", "first_air_date": "2022-02-18",
                "last_air_date": "2025-03-21", "in_production": True, "status": "Returning Series",
                "number_of_seasons": 2, "number_of_episodes": 19, "episode_run_time": [50],
                "overview": "Work-life balance.", "genres": [{"name": "Drama"}], "poster_path": "/sev.jpg",
                "backdrop_path": "/sevb.jpg", "vote_average": 8.4, "vote_count": 2000, "popularity": 300.0,
                "external_ids": {"imdb_id": "tt11280740"}, "videos": {"results": []},
                "watch/providers": {"results": {"US": {"link": "https://jw/sev",
                                                       "flatrate": [{"provider_id": 350, "provider_name": "Apple TV+"}]}}}},
        }
        self.min_votes_seen = {}

    def list_watch_providers(self, region):
        return [{"provider_id": i, "provider_name": f"P{i}", "display_priority": i} for i in (8, 1796, 1899, 15, 1825)]


    def discover_flatrate(self, region, provider_ids, min_vote_count, max_pages, sort_by="popularity.desc",
                          kind="movie"):
        self.calls["discover"] += 1
        self.min_votes_seen[kind] = min_vote_count
        key = "|".join(map(str, provider_ids))
        if kind == "tv":
            if key == "350":
                yield {"id": 7, "name": "Severance", "popularity": 300.0, "vote_count": 2000}
            return
        for tmdb_id in self.discover_by_provider.get(key, []):
            m = self.movies[tmdb_id]
            yield {"id": tmdb_id, "title": m["title"], "popularity": m["popularity"], "vote_count": 500}

    def details(self, kind, tmdb_id):
        self.calls["details"] += 1
        if kind == "tv":
            return self.tv.get(tmdb_id)
        if tmdb_id == 99:
            return None
        return self.movies[tmdb_id]


class FakeOMDb:
    enabled = True
    used_today = 0

    def __init__(self):
        self.calls = []

    def lookup(self, imdb_id):
        self.calls.append(imdb_id)
        self.used_today += 1
        if imdb_id == "tt0113277":
            return {"Response": "True", "tomatoURL": "https://www.rottentomatoes.com/m/heat_1995",
                    "Ratings": [{"Source": "Rotten Tomatoes", "Value": "88%"}]}
        return {"Response": "True", "tomatoURL": "N/A", "Ratings": []}


class FakeRT:
    def __init__(self):
        self.searches = []
        self.fetches = []
        self.fail_urls = set()

    def search(self, title, year, kind="movie"):
        self.searches.append((title, year))
        if title == "Oppenheimer":
            return "https://www.rottentomatoes.com/m/oppenheimer_2023"
        if title == "Severance" and kind == "tv":
            return "https://www.rottentomatoes.com/tv/severance"
        return None

    def fetch_scores(self, url):
        self.fetches.append(url)
        if url in self.fail_urls:
            raise RTError("HTTP 503")
        if "heat" in url:
            return RTScores(url=url, status="ok", critic_score=88, critic_count=80, certified_fresh=True,
                            audience_score=94, audience_count="250,000+")
        return RTScores(url=url, status="ok", critic_score=93, critic_count=512, certified_fresh=True,
                        audience_score=91, audience_count="10,000+")


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        (root / "config.yaml").write_text(CONFIG)
        self.cfg = load_config(root / "config.yaml")
        self.cache = MovieCache(root / "cache")
        self.tmdb, self.omdb, self.rt = FakeTMDB(), FakeOMDb(), FakeRT()

    def tearDown(self):
        self.tmp.cleanup()

    def run_it(self, **kw):
        return run_sync(self.cfg, self.tmdb, self.omdb, self.rt, self.cache, **kw)

    def test_full_pipeline(self):
        out, summary = self.run_it()
        by_title = {m["title"]: m for m in out["movies"]}
        self.assertEqual(set(by_title), {"Heat", "Oppenheimer", "No Scores"})
        self.assertEqual(out["services"], ["Netflix", "HBO Max", "Apple TV"])
        self.assertEqual(out["kind"], "movie")
        self.assertEqual(out["ui_defaults"], {"min_critic_reviews": 20, "sort": "audience_desc"})
        self.assertEqual(out["region"], "US")

        heat = by_title["Heat"]
        self.assertEqual(heat["kind"], "movie")
        self.assertNotIn("seasons", heat)
        self.assertEqual(heat["services"], ["Netflix", "HBO Max"])
        self.assertEqual(heat["rt"]["url"], "https://www.rottentomatoes.com/m/heat_1995")
        self.assertEqual(heat["rt"]["critic_score"], 88)
        self.assertEqual(heat["rt"]["audience_score"], 94)
        self.assertTrue(heat["rt"]["certified_fresh"])
        self.assertEqual(heat["poster"], "https://image.tmdb.org/t/p/w342/p1.jpg")
        self.assertEqual(heat["backdrop"], "https://image.tmdb.org/t/p/w780/b1.jpg")
        self.assertEqual(heat["trailer_youtube_key"], "official")
        self.assertEqual(heat["justwatch_link"], "https://www.themoviedb.org/movie/1/watch?locale=US")
        self.assertEqual(heat["genres"], ["Drama"])
        self.assertEqual(heat["year"], 1995)
        self.assertEqual(heat["imdb_id"], "tt0113277")

        # OMDb supplied the URL, so no RT search was needed for Heat; Oppenheimer used search.
        self.assertEqual(sorted(self.rt.searches), [("No Scores", 2024), ("Oppenheimer", 2023)])
        self.assertEqual(by_title["Oppenheimer"]["services"], ["HBO Max"])
        self.assertEqual(by_title["No Scores"]["rt"]["status"], "not_found")
        self.assertEqual(by_title["No Scores"]["services"], ["Netflix"])

        self.assertEqual(summary.kept, 3)
        self.assertEqual(summary.dropped_no_service, 3)
        self.assertEqual(summary.both_scores, 2)
        self.assertEqual(summary.per_service, {"Netflix": 2, "HBO Max": 2})
        self.assertEqual(summary.rt_status, {"ok": 2, "not_found": 1})
        self.assertEqual(self.tmdb.calls, {"discover": 3, "details": 6})
        self.assertEqual(self.tmdb.min_votes_seen, {"movie": 50})
        text = summary.format()
        self.assertIn("HBO Max", text)
        self.assertIn("both critic + audience score: 2/3", text)

    def test_second_run_uses_cache(self):
        self.run_it()
        self.tmdb.calls = {"discover": 0, "details": 0}
        self.rt.searches, self.rt.fetches, self.omdb.calls = [], [], []
        out, summary = self.run_it()
        self.assertEqual(self.tmdb.calls, {"discover": 0, "details": 0})
        self.assertEqual(self.rt.fetches, [])
        self.assertEqual(self.tmdb.calls["details"], 0)
        self.assertEqual(self.rt.searches, [])
        self.assertEqual(self.omdb.calls, [])
        self.assertEqual(len(out["movies"]), 3)
        self.assertEqual(summary.scores_cached, 3)
        self.assertEqual(summary.details_cached, 6)  # dropped titles are cached too

    def test_full_flag_ignores_cache(self):
        self.run_it()
        self.tmdb.calls = {"discover": 0, "details": 0}
        self.rt.fetches = []
        self.run_it(full=True)
        self.assertEqual(self.tmdb.calls["discover"], 3)
        self.assertEqual(self.tmdb.calls["details"], 6)
        self.assertEqual(len(self.rt.fetches), 2)

    def test_limit(self):
        out, summary = self.run_it(limit=2)
        # popularity is 10*id, so ids 6 and 5 come first; 5 is dropped (disabled service)
        self.assertEqual([m["title"] for m in out["movies"]], ["No Scores"])

    def test_rt_error_is_logged_not_fatal(self):
        self.rt.fail_urls.add("https://www.rottentomatoes.com/m/heat_1995")
        out, summary = self.run_it()
        heat = next(m for m in out["movies"] if m["title"] == "Heat")
        self.assertEqual(heat["rt"]["status"], "error")
        # the OMDb Tomatometer fallback still fills in the critic score
        self.assertEqual(heat["rt"]["critic_score"], 88)
        self.assertIsNone(heat["rt"]["audience_score"])
        self.assertEqual(len(summary.failures), 1)
        self.assertIn("HTTP 503", summary.failures[0])
        # errors are retried on the next run, reusing the known URL without a new search
        self.rt.fail_urls.clear()
        self.rt.searches = []
        out, _ = self.run_it()
        heat = next(m for m in out["movies"] if m["title"] == "Heat")
        self.assertEqual(heat["rt"]["status"], "ok")
        self.assertEqual(heat["rt"]["audience_score"], 94)
        self.assertNotIn(("Heat", 1995), self.rt.searches)

    def test_single_service_sync_merges_previous(self):
        first, _ = self.run_it()
        hbo = self.cfg.service_by_name("HBO Max")
        # Oppenheimer leaves HBO Max; Heat stays
        self.tmdb.discover_by_provider["1899"] = [1]
        self.tmdb.movies[2]["watch/providers"]["results"]["US"]["flatrate"] = []
        out, _ = self.run_it(only_services=[hbo], previous=first, full=True)
        titles = {m["title"]: m for m in out["movies"]}
        self.assertNotIn("Oppenheimer", titles)
        self.assertEqual(titles["Heat"]["services"], ["Netflix", "HBO Max"])
        self.assertEqual(titles["No Scores"]["services"], ["Netflix"])  # kept from previous output

    def test_discovery_failure_for_all_services_raises(self):
        class BrokenTMDB(FakeTMDB):
            def discover_flatrate(self, *a, **k):
                raise TMDBError("boom")
                yield  # noqa
        with self.assertRaises(TMDBError):
            run_sync(self.cfg, BrokenTMDB(), self.omdb, self.rt, self.cache)

    def test_tv_pipeline(self):
        tv_cache = MovieCache(Path(self.tmp.name) / "cache", "tv")
        out, summary = run_sync(self.cfg, self.tmdb, self.omdb, self.rt, tv_cache, kind="tv")
        self.assertEqual(out["kind"], "tv")
        self.assertEqual(self.tmdb.min_votes_seen["tv"], 20)
        self.assertEqual(len(out["movies"]), 1)
        sev = out["movies"][0]
        self.assertEqual(sev["kind"], "tv")
        self.assertEqual(sev["title"], "Severance")
        self.assertEqual(sev["year"], 2022)
        self.assertIsNone(sev["end_year"])  # still in production
        self.assertEqual((sev["seasons"], sev["episodes"], sev["runtime"]), (2, 19, 50))
        self.assertEqual(sev["status"], "Returning Series")
        self.assertEqual(sev["services"], ["Apple TV"])
        self.assertEqual(sev["rt"]["url"], "https://www.rottentomatoes.com/tv/severance")
        self.assertEqual(sev["rt"]["status"], "ok")
        # TV and movie caches are separate directories
        self.assertTrue((Path(self.tmp.name) / "cache" / "tv" / "7.json").exists())
        self.assertFalse((Path(self.tmp.name) / "cache" / "movies" / "7.json").exists())

    def test_without_omdb_and_rt(self):
        out, summary = run_sync(self.cfg, self.tmdb, None, None, self.cache)
        self.assertEqual(len(out["movies"]), 3)
        self.assertTrue(all(m["rt"]["status"] == "not_found" for m in out["movies"]))


class HelperTests(unittest.TestCase):
    def test_match_services(self):
        cfg = load_config_from_text(CONFIG)
        self.assertEqual(match_services([1796, 1825], cfg.enabled_services), ["Netflix"])
        self.assertEqual(match_services([1825], cfg.enabled_services), [])
        self.assertEqual(match_services(None, cfg.enabled_services), [])

    def test_merge_with_previous(self):
        previous = {"movies": [{"tmdb_id": 1, "title": "A", "services": ["HBO Max"]},
                               {"tmdb_id": 2, "title": "B", "services": ["HBO Max", "Hulu"]},
                               {"tmdb_id": 3, "title": "C", "services": ["Netflix"]}]}
        new = [{"tmdb_id": 3, "title": "C", "services": ["Netflix", "HBO Max"]}]
        merged = merge_with_previous(new, previous, ["HBO Max"])
        self.assertEqual({m["tmdb_id"]: m["services"] for m in merged}, {3: ["Netflix", "HBO Max"], 2: ["Hulu"]})

    def test_config_validation(self):
        with self.assertRaises(ConfigError):
            load_config_from_text("region: US\nservices: []\n")
        with self.assertRaises(ConfigError):
            load_config_from_text("services:\n  - name: X\n    provider_ids: [a]\n")
        with self.assertRaises(ConfigError):
            load_config_from_text("services:\n  - name: X\n    provider_ids: [1]\n  - name: x\n    provider_ids: [2]\n")
        cfg = load_config_from_text("services:\n  - name: X\n    provider_ids: 5\n")
        self.assertEqual(cfg.services[0].provider_ids, [5])
        self.assertEqual(cfg.region, "US")

    def test_list_providers_output(self):
        import sync
        cfg = load_config_from_text(CONFIG)
        cfg.services[0].provider_ids.append(4242)  # not in region
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = sync.list_providers(FakeTMDB(), cfg)
        text = buf.getvalue()
        self.assertEqual(code, 1)
        self.assertIn("1899  P1899", text)
        self.assertIn("HBO Max", text)
        self.assertIn("WARNING: provider id 4242 (Netflix)", text)
        self.assertIn("Hulu (disabled)", text)


def load_config_from_text(text):
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as fh:
        fh.write(text)
        path = fh.name
    return load_config(path)


if __name__ == "__main__":
    unittest.main()
