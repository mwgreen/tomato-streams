/* Where "Watch on <service>" buttons go.
 *
 * Each entry is a URL template for the service's own search page; {q} is replaced
 * with the URL-encoded title. Keys are the service names from config.yaml, lower-cased
 * with "+" dropped and non-letters turned into "-" (e.g. "Paramount+" -> "paramount",
 * "Acorn TV" -> "acorn-tv"). Edit freely if a service changes its site; nothing else
 * needs to change.
 *
 * On an iPhone these https links open the service's native app when it is installed
 * (Universal Links), otherwise the website.
 *
 * If a title in movies.json / tv.json carries a `watch_urls` object
 * ({"Netflix": "https://www.netflix.com/title/123"}), that exact link is used instead.
 */
window.WATCH_LINKS = {
  "netflix":          "https://www.netflix.com/search?q={q}",
  "prime-video":      "https://www.amazon.com/gp/video/search?phrase={q}",
  "apple-tv":         "https://tv.apple.com/search?term={q}",
  "hbo-max":          "https://play.hbomax.com/search/result?q={q}",
  "hulu":             "https://www.hulu.com/search?q={q}",
  "disney":           "https://www.disneyplus.com/search/{q}",
  "paramount":        "https://www.paramountplus.com/search/?q={q}",
  "peacock":          "https://www.peacocktv.com/search?q={q}",
  "starz":            "https://www.starz.com/us/en/search?q={q}",
  "amc":              "https://www.amcplus.com/search?q={q}",
  "mgm":              "https://www.mgmplus.com/search?q={q}",
  "criterion-channel":"https://www.criterionchannel.com/search?q={q}",
  "mubi":             "https://mubi.com/en/search/films?query={q}",
  "britbox":          "https://www.britbox.com/us/search?q={q}",
  "acorn-tv":         "https://acorn.tv/search?q={q}",
  "shudder":          "https://www.shudder.com/search?q={q}",
  "crunchyroll":      "https://www.crunchyroll.com/search?q={q}",
  "hallmark":         "https://www.hallmarkplus.com/search?q={q}",
  "youtube-premium":  "https://www.youtube.com/results?search_query={q}",
  "tubi":             "https://tubitv.com/search/{q}",
  "pluto-tv":         "https://pluto.tv/en/search/details?q={q}",
  "the-roku-channel": "https://therokuchannel.roku.com/search/{q}",
};
