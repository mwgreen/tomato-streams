import unittest

from lib.rottentomatoes import (STATUS_NO_SCORES, STATUS_OK, normalize_rt_url, parse_movie_page,
                                parse_search_results, pick_search_candidate, titles_match)

SCORECARD_JSON_PAGE = """
<html><head><title>Oppenheimer | Rotten Tomatoes</title>
<script type="application/ld+json">{"@type":"Movie","name":"Oppenheimer","url":"https://www.rottentomatoes.com/m/oppenheimer_2023","aggregateRating":{"@type":"AggregateRating","ratingValue":93,"reviewCount":512}}</script>
</head><body>
<media-scorecard>
  <rt-text slot="criticsScore">93%</rt-text>
  <rt-link slot="criticsReviews">512 Reviews</rt-link>
  <rt-text slot="audienceScore">91%</rt-text>
  <rt-link slot="audienceReviews">10,000+ Verified Ratings</rt-link>
</media-scorecard>
<script id="media-scorecard-json" type="application/json">
{"audienceScore":{"averageRating":"4.5","bandedRatingCount":"10,000+","likedCount":9000,"notLikedCount":900,"ratingCount":9900,"reviewCount":9900,"scoreType":"VERIFIED","sentiment":"POSITIVE","score":"91","title":"Popcornmeter"},
 "criticsScore":{"averageRating":"8.80","certified":true,"likedCount":476,"notLikedCount":36,"ratingCount":512,"reviewCount":512,"sentiment":"POSITIVE","score":"93","title":"Tomatometer"},
 "overlay":{"hasAudienceAll":true}}
</script>
</body></html>
"""

SCORE_DETAILS_PAGE = """
<html><body>
<script id="scoreDetails" type="application/json">
{"scoreboard":{"audienceScore":{"audienceClass":"verified","averageRating":"4.4","bandedRatingCount":"2,500+","ratingCount":2600,"state":"upright","value":88},
"tomatometerScore":{"averageRating":"8.6","reviewCount":212,"state":"certified-fresh","value":94}}}
</script>
</body></html>
"""

MEDIA_SCORECARD_PAGE = """
<html><body>
<media-scorecard>
  <score-icon-critics certified="true" sentiment="positive" slot="criticsIcon"></score-icon-critics>
  <rt-text slot="criticsScore">96%</rt-text>
  <rt-link slot="criticsReviews">300 Reviews</rt-link>
  <score-icon-audience sentiment="positive" slot="audienceIcon"></score-icon-audience>
  <rt-text slot="audienceScore">77%</rt-text>
  <rt-link slot="audienceReviews">5,000+ Ratings</rt-link>
</media-scorecard>
</body></html>
"""

SCORE_BOARD_PAGE = """
<html><body>
<score-board audiencescore="42" audiencestate="spilled" tomatometerscore="35" tomatometerstate="rotten" rating="PG-13">
  <h1 slot="title">Bad Movie</h1>
  <a slot="critics-count" href="/m/bad_movie/reviews">120 Reviews</a>
  <a slot="audience-count" href="/m/bad_movie/reviews?type=user">1,000+ Ratings</a>
</score-board>
</body></html>
"""

JSON_LD_ONLY_PAGE = """
<html><head>
<script type="application/ld+json">[{"@type":"Movie","name":"Some Film","url":"https://www.rottentomatoes.com/m/some_film","aggregateRating":{"ratingValue":"71","ratingCount":"45"}}]</script>
</head><body></body></html>
"""

NO_SCORES_PAGE = """
<html><body>
<media-scorecard>
  <rt-text slot="criticsScore">- -</rt-text>
  <rt-text slot="audienceScore">- -</rt-text>
</media-scorecard>
<script id="media-scorecard-json" type="application/json">
{"audienceScore":{"score":"","ratingCount":0},"criticsScore":{"score":"","reviewCount":0}}
</script>
</body></html>
"""

SEARCH_PAGE = """
<html><body>
<search-page-result type="movie">
  <ul slot="list">
    <search-page-media-row cast="Jon Voight" releaseyear="1969" tomatometerscore="89" tomatometerstate="certified-fresh">
      <a href="https://www.rottentomatoes.com/m/midnight_cowboy" class="unset" slot="title" data-qa="info-name">Midnight Cowboy</a>
    </search-page-media-row>
    <search-page-media-row cast="Robert De Niro" releaseyear="1995" tomatometerscore="93" tomatometerstate="certified-fresh">
      <a href="https://www.rottentomatoes.com/m/heat_1995" class="unset" slot="title" data-qa="info-name">Heat</a>
    </search-page-media-row>
    <search-page-media-row cast="Someone" releaseyear="1986" tomatometerscore="40" tomatometerstate="rotten">
      <a href="https://www.rottentomatoes.com/m/heat" class="unset" slot="title" data-qa="info-name">Heat</a>
    </search-page-media-row>
    <search-page-media-row releaseyear="2023" tomatometerscore="93">
      <a href="https://www.rottentomatoes.com/m/oppenheimer_2023" slot="title">Oppenheimer</a>
    </search-page-media-row>
  </ul>
</search-page-result>
<search-page-result type="tvSeries">
  <search-page-media-row releaseyear="2000"><a href="https://www.rottentomatoes.com/tv/heat_vision" slot="title">Heat</a></search-page-media-row>
</search-page-result>
</body></html>
"""

TV_SEARCH_PAGE = """
<html><body>
<search-page-result type="tvSeries">
  <search-page-media-row startyear="2022" endyear="" tomatometerscore="97">
    <a href="https://www.rottentomatoes.com/tv/severance/s01" slot="title">Severance</a>
  </search-page-media-row>
</search-page-result>
</body></html>
"""

PLAIN_LINKS_SEARCH_PAGE = """
<html><body><ul>
<li><a href="/m/heat_1995">Heat</a> <span>1995</span></li>
<li><a href="/m/heat">Heat</a> <span>1986</span></li>
</ul></body></html>
"""


class ParseMoviePageTests(unittest.TestCase):
    def test_scorecard_json(self):
        s = parse_movie_page(SCORECARD_JSON_PAGE, "https://www.rottentomatoes.com/m/oppenheimer_2023/")
        self.assertEqual(s.status, STATUS_OK)
        self.assertEqual(s.url, "https://www.rottentomatoes.com/m/oppenheimer_2023")
        self.assertEqual(s.critic_score, 93)
        self.assertEqual(s.critic_count, 512)
        self.assertTrue(s.certified_fresh)
        self.assertEqual(s.audience_score, 91)
        self.assertEqual(s.audience_count, "10,000+")

    def test_score_details_json(self):
        s = parse_movie_page(SCORE_DETAILS_PAGE, "/m/oppenheimer_2023")
        self.assertEqual(s.critic_score, 94)
        self.assertEqual(s.critic_count, 212)
        self.assertTrue(s.certified_fresh)
        self.assertEqual(s.audience_score, 88)
        self.assertEqual(s.audience_count, "2,500+")
        self.assertEqual(s.url, "https://www.rottentomatoes.com/m/oppenheimer_2023")

    def test_media_scorecard_elements(self):
        s = parse_movie_page(MEDIA_SCORECARD_PAGE)
        self.assertEqual((s.critic_score, s.critic_count, s.certified_fresh), (96, 300, True))
        self.assertEqual((s.audience_score, s.audience_count), (77, "5,000+"))

    def test_legacy_score_board(self):
        s = parse_movie_page(SCORE_BOARD_PAGE)
        self.assertEqual((s.critic_score, s.critic_count, s.certified_fresh), (35, 120, False))
        self.assertEqual((s.audience_score, s.audience_count), (42, "1,000+"))
        self.assertEqual(s.status, STATUS_OK)

    def test_json_ld_only_gives_critic_score(self):
        s = parse_movie_page(JSON_LD_ONLY_PAGE)
        self.assertEqual(s.critic_score, 71)
        self.assertEqual(s.critic_count, 45)
        self.assertIsNone(s.audience_score)
        self.assertEqual(s.url, "https://www.rottentomatoes.com/m/some_film")
        self.assertEqual(s.status, STATUS_OK)

    def test_no_scores(self):
        s = parse_movie_page(NO_SCORES_PAGE, "https://www.rottentomatoes.com/m/unreleased")
        self.assertEqual(s.status, STATUS_NO_SCORES)
        self.assertIsNone(s.critic_score)
        self.assertIsNone(s.audience_score)
        self.assertFalse(s.certified_fresh)

    def test_garbage_html_does_not_raise(self):
        s = parse_movie_page("<html><script id='media-scorecard-json'>{not json</script></html>")
        self.assertEqual(s.status, STATUS_NO_SCORES)

    def test_to_dict_round_trip(self):
        from lib.rottentomatoes import RTScores
        s = parse_movie_page(SCORE_DETAILS_PAGE, "/m/x")
        d = s.to_dict()
        self.assertNotIn("error", d)
        self.assertEqual(RTScores.from_dict(d), s)


class SearchTests(unittest.TestCase):
    def test_picks_matching_year(self):
        self.assertEqual(parse_search_results(SEARCH_PAGE, "Heat", 1995),
                         "https://www.rottentomatoes.com/m/heat_1995")
        self.assertEqual(parse_search_results(SEARCH_PAGE, "Heat", 1986),
                         "https://www.rottentomatoes.com/m/heat")

    def test_year_tolerance(self):
        self.assertEqual(parse_search_results(SEARCH_PAGE, "Heat", 1996),
                         "https://www.rottentomatoes.com/m/heat_1995")
        self.assertIsNone(parse_search_results(SEARCH_PAGE, "Heat", 2010))

    def test_title_must_match(self):
        self.assertIsNone(parse_search_results(SEARCH_PAGE, "Heat 2", 1995))
        self.assertEqual(parse_search_results(SEARCH_PAGE, "oppenheimer", 2023),
                         "https://www.rottentomatoes.com/m/oppenheimer_2023")

    def test_ignores_tv_results_for_movies(self):
        self.assertIsNone(parse_search_results(SEARCH_PAGE, "Heat", 2000))

    def test_tv_search_only_matches_series(self):
        self.assertEqual(parse_search_results(SEARCH_PAGE, "Heat", 2000, kind="tv"),
                         "https://www.rottentomatoes.com/tv/heat_vision")
        self.assertIsNone(parse_search_results(SEARCH_PAGE, "Heat", 1995, kind="tv"))
        self.assertEqual(parse_search_results(TV_SEARCH_PAGE, "Severance", 2022, kind="tv"),
                         "https://www.rottentomatoes.com/tv/severance")

    def test_plain_link_fallback(self):
        self.assertEqual(parse_search_results(PLAIN_LINKS_SEARCH_PAGE, "Heat", 1995),
                         "https://www.rottentomatoes.com/m/heat_1995")

    def test_unknown_year_prefers_title_match(self):
        self.assertEqual(parse_search_results(SEARCH_PAGE, "Midnight Cowboy", None),
                         "https://www.rottentomatoes.com/m/midnight_cowboy")

    def test_pick_candidate_unknown_candidate_year(self):
        cands = [{"url": "u1", "title": "Film", "year": None}]
        self.assertEqual(pick_search_candidate(cands, "Film", 2001), "u1")


class HelperTests(unittest.TestCase):
    def test_titles_match(self):
        self.assertTrue(titles_match("The Lord of the Rings: The Fellowship of the Ring",
                                     "Lord of the Rings - The Fellowship of the Ring"))
        self.assertTrue(titles_match("Amélie", "Amelie"))
        self.assertTrue(titles_match("Fast & Furious", "Fast and Furious"))
        self.assertFalse(titles_match("Heat", "Heat 2"))

    def test_normalize_rt_url(self):
        self.assertEqual(normalize_rt_url("http://rottentomatoes.com/m/heat_1995/"),
                         "https://www.rottentomatoes.com/m/heat_1995")
        self.assertEqual(normalize_rt_url("/m/heat_1995"), "https://www.rottentomatoes.com/m/heat_1995")
        self.assertEqual(normalize_rt_url("https://www.rottentomatoes.com/tv/severance/s02"),
                         "https://www.rottentomatoes.com/tv/severance")
        self.assertIsNone(normalize_rt_url("https://www.rottentomatoes.com/tv/show", kind="movie"))
        self.assertIsNone(normalize_rt_url("https://www.rottentomatoes.com/m/heat_1995", kind="tv"))
        self.assertIsNone(normalize_rt_url("https://www.rottentomatoes.com/celebrity/someone"))
        self.assertIsNone(normalize_rt_url("N/A"))
        self.assertIsNone(normalize_rt_url(None))


if __name__ == "__main__":
    unittest.main()
