import json
import tempfile
import unittest
from pathlib import Path

from lib.omdb import OMDbClient, extract_rt_critic_score, extract_rt_url


class FakeResponse:
    def __init__(self, status, payload=None, text=""):
        self.status_code = status
        self._payload = payload
        self.text = text or json.dumps(payload or {})

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append(params)
        return self.responses.pop(0)


OMDB_OK = {"Response": "True", "Title": "Heat", "tomatoURL": "https://www.rottentomatoes.com/m/heat_1995",
           "Ratings": [{"Source": "Internet Movie Database", "Value": "8.3/10"},
                       {"Source": "Rotten Tomatoes", "Value": "88%"}]}


class OMDbTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.usage = Path(self.tmp.name) / "omdb_usage.json"

    def tearDown(self):
        self.tmp.cleanup()

    def test_lookup_and_extractors(self):
        session = FakeSession([FakeResponse(200, OMDB_OK)])
        client = OMDbClient("key", self.usage, session=session)
        data = client.lookup("tt0113277")
        self.assertEqual(extract_rt_url(data), "https://www.rottentomatoes.com/m/heat_1995")
        self.assertEqual(extract_rt_critic_score(data), 88)
        self.assertEqual(session.calls[0]["tomatoes"], "true")
        self.assertEqual(client.used_today, 1)
        self.assertEqual(json.loads(self.usage.read_text())["count"], 1)

    def test_na_url_is_ignored(self):
        self.assertIsNone(extract_rt_url({"tomatoURL": "N/A"}))
        self.assertIsNone(extract_rt_critic_score({"Ratings": []}))

    def test_stops_near_daily_limit(self):
        session = FakeSession([])
        client = OMDbClient("key", self.usage, session=session, daily_limit=100, reserve=10)
        client._usage["count"] = 90
        self.assertTrue(client.exhausted)
        self.assertIsNone(client.lookup("tt1"))
        self.assertEqual(session.calls, [])

    def test_limit_reached_response_marks_exhausted(self):
        session = FakeSession([FakeResponse(401, {"Response": "False", "Error": "Request limit reached!"})])
        client = OMDbClient("key", self.usage, session=session)
        self.assertIsNone(client.lookup("tt1"))
        self.assertTrue(client.exhausted)

    def test_disabled_without_key(self):
        client = OMDbClient("", self.usage, session=FakeSession([]))
        self.assertFalse(client.enabled)
        self.assertIsNone(client.lookup("tt1"))


if __name__ == "__main__":
    unittest.main()
