import json
import tempfile
import unittest
from pathlib import Path

from lib.config import Service
from lib.watchmode import WatchmodeClient, links_for_kind, map_sources_to_services, normalize_name, series_page_url


class FakeResponse:
    def __init__(self, status, payload=None):
        self.status_code = status
        self._payload = payload

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, params))
        return self.responses.pop(0)


SOURCES = [
    {"source_id": 203, "name": "Netflix", "type": "sub", "region": "US",
     "web_url": "https://www.netflix.com/title/60020810", "ios_url": "nflx://www.netflix.com/title/60020810"},
    {"source_id": 387, "name": "Max", "type": "sub", "region": "US",
     "web_url": "https://play.max.com/movie/abc", "ios_url": "hbomax://feature/abc"},
    {"source_id": 26, "name": "Amazon Prime Video", "type": "sub", "region": "US", "web_url": "https://www.amazon.com/gp/video/detail/B0"},
    {"source_id": 10, "name": "Amazon", "type": "rent", "region": "US", "web_url": "https://www.amazon.com/rent"},
    {"source_id": 444, "name": "Paramount+ Amazon Channel", "type": "sub", "region": "US", "web_url": "https://www.amazon.com/channel"},
    {"source_id": 73, "name": "Tubi TV", "type": "free", "region": "US", "web_url": "https://tubitv.com/movies/1"},
    {"source_id": 203, "name": "Netflix", "type": "sub", "region": "GB", "web_url": "https://www.netflix.com/gb/title/1"},
]
SERVICES = [Service("Netflix", [8]), Service("HBO Max", [1899]), Service("Prime Video", [9]),
            Service("Paramount+", [531]), Service("Tubi", [73]), Service("My Channel", [999], watchmode_names=["Amazon"])]


class MappingTests(unittest.TestCase):
    def test_normalize(self):
        self.assertEqual(normalize_name("Paramount Plus"), "paramount+")
        self.assertEqual(normalize_name("Apple TV+ "), "apple tv+")
        self.assertEqual(normalize_name("The Criterion Channel"), "the criterion channel")

    def test_map_sources(self):
        links = map_sources_to_services(SOURCES, SERVICES, "US")
        self.assertEqual(links["Netflix"], {"web": "https://www.netflix.com/title/60020810",
                                            "ios": "nflx://www.netflix.com/title/60020810"})
        self.assertEqual(links["HBO Max"], {"web": "https://play.max.com/movie/abc", "ios": "hbomax://feature/abc"})
        self.assertEqual(links["Prime Video"], {"web": "https://www.amazon.com/gp/video/detail/B0"})
        self.assertNotIn("Paramount+", links)    # channel variant is not the service
        self.assertNotIn("Tubi", links)          # free sources excluded unless configured
        self.assertNotIn("My Channel", links)    # "Amazon" source is rent, not sub
        self.assertNotIn("GB", json.dumps(links))

    def test_free_sources_when_enabled(self):
        links = map_sources_to_services(SOURCES, SERVICES, "US", include_free=True)
        self.assertEqual(links["Tubi"], {"web": "https://tubitv.com/movies/1"})


class SeriesPageTests(unittest.TestCase):
    def test_rewrites(self):
        self.assertEqual(series_page_url("Netflix", "https://www.netflix.com/watch/80057281?trackId=1"),
                         ("https://www.netflix.com/title/80057281", "show"))
        self.assertEqual(series_page_url("Netflix", "https://www.netflix.com/title/80057281"),
                         ("https://www.netflix.com/title/80057281", "show"))
        self.assertEqual(series_page_url("Paramount+", "https://www.paramountplus.com/shows/star-trek/video/abc123/pilot/"),
                         ("https://www.paramountplus.com/shows/star-trek/", "show"))

    def test_episode_links_kept_and_marked(self):
        self.assertEqual(series_page_url("Hulu", "https://www.hulu.com/watch/0000-1111"), ("https://www.hulu.com/watch/0000-1111", "episode"))
        self.assertEqual(series_page_url("Hulu", "https://www.hulu.com/series/the-bear-abc"), ("https://www.hulu.com/series/the-bear-abc", "show"))
        self.assertEqual(series_page_url("HBO Max", "https://play.max.com/video/watch/abc/def")[1], "episode")
        self.assertEqual(series_page_url("HBO Max", "https://play.max.com/show/abc")[1], "show")
        self.assertEqual(series_page_url("Prime Video", "https://www.amazon.com/gp/video/detail/B0X")[1], "show")
        self.assertEqual(series_page_url("Apple TV", "https://tv.apple.com/us/episode/pilot/umc.cmc.1")[1], "episode")
        self.assertEqual(series_page_url("Peacock", "https://www.peacocktv.com/watch/playback/vod/abc")[1], "episode")
        self.assertEqual(series_page_url("Unknown Service", "https://x.example/watch/1"), ("https://x.example/watch/1", "show"))
        self.assertEqual(series_page_url("Netflix", None), (None, "show"))

    def test_links_for_kind(self):
        links = {"Netflix": {"web": "https://www.netflix.com/watch/1", "ios": "nflx://www.netflix.com/watch/1"},
                 "Hulu": {"web": "https://www.hulu.com/watch/x", "ios": "hulu://watch/x"},
                 "Apple TV": {"web": "https://tv.apple.com/us/show/s/umc.cmc.2", "ios": "tv://show"}}
        self.assertEqual(links_for_kind(links, "movie"), links)
        tv = links_for_kind(links, "tv")
        self.assertEqual(tv, {"Netflix": {"web": "https://www.netflix.com/title/1", "level": "show"},
                              "Hulu": {"web": "https://www.hulu.com/watch/x", "ios": "hulu://watch/x", "level": "episode"},
                              "Apple TV": {"web": "https://tv.apple.com/us/show/s/umc.cmc.2", "ios": "tv://show", "level": "show"}})


class ClientTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.usage = Path(self.tmp.name) / "watchmode_usage.json"

    def tearDown(self):
        self.tmp.cleanup()

    def test_sources_by_imdb_and_tmdb_id(self):
        session = FakeSession([FakeResponse(200, SOURCES), FakeResponse(200, [])])
        client = WatchmodeClient("key", self.usage, session=session)
        self.assertEqual(len(client.sources("movie", 1, "tt0113277")), len(SOURCES))
        self.assertEqual(client.sources("tv", 95396, None), [])
        self.assertTrue(session.calls[0][0].endswith("/title/tt0113277/sources/"))
        self.assertTrue(session.calls[1][0].endswith("/title/tv-95396/sources/"))
        self.assertEqual(session.calls[0][1]["regions"], "US")
        self.assertEqual(client.used_this_month, 2)
        self.assertEqual(json.loads(self.usage.read_text())["count"], 2)

    def test_quota_and_errors(self):
        session = FakeSession([FakeResponse(404), FakeResponse(401)])
        client = WatchmodeClient("key", self.usage, session=session, monthly_limit=100, reserve=10)
        self.assertEqual(client.sources("movie", 1, "tt1"), [])    # 404 -> unknown title, cacheable
        self.assertIsNone(client.sources("movie", 2, "tt2"))       # 401 -> key disabled
        self.assertFalse(client.enabled)
        client = WatchmodeClient("key", self.usage, session=FakeSession([]), monthly_limit=100, reserve=10)
        client._usage["count"] = 95
        self.assertTrue(client.exhausted)
        self.assertIsNone(client.sources("movie", 3, "tt3"))

    def test_disabled_without_key(self):
        client = WatchmodeClient("", self.usage, session=FakeSession([]))
        self.assertFalse(client.enabled)
        self.assertIsNone(client.sources("movie", 1, "tt1"))


if __name__ == "__main__":
    unittest.main()
