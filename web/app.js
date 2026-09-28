/* Streaming Finder — vanilla JS front end for data/movies.json and data/tv.json */
(function () {
  "use strict";

  const KIND = new URLSearchParams(location.search).get("kind") === "tv" ? "tv" : "movie";
  const DATA_URL = KIND === "tv" ? "../data/tv.json" : "../data/movies.json";
  const NOUN = KIND === "tv" ? ["series", "series"] : ["movie", "movies"];
  const PAGE_SIZE = 120;
  const HIDDEN_KEY = "smf.hidden." + KIND;
  const VIEW_KEY = "smf.view";
  const STATE_KEY = "smf.state";   // last filters/sort, shared by the Movies and TV pages
  const WATCHED_KEY = "smf.watched"; // offline fallback for people + watched marks
  const VIEWS = ["grid", "list"];

  const $ = (id) => document.getElementById(id);
  const el = {
    grid: $("grid"), listWrap: $("list-wrap"), listBody: $("list-body"), list: $("list"),
    empty: $("empty"), error: $("error"), count: $("count"), shown: $("shown"),
    generated: $("generated"), services: $("services"), genres: $("genres"), q: $("q"),
    minCritic: $("min-critic"), minCriticOut: $("min-critic-out"),
    minAudience: $("min-audience"), minAudienceOut: $("min-audience-out"),
    minReviews: $("min-reviews"), certified: $("certified"), hideNoRt: $("hide-no-rt"),
    yearMin: $("year-min"), yearMax: $("year-max"), addedMin: $("added-min"), runtimeMax: $("runtime-max"),
    showHidden: $("show-hidden"), hiddenCount: $("hidden-count"), clearHidden: $("clear-hidden"),
    people: $("people"), personName: $("person-name"), personAdd: $("person-add"),
    sort: $("sort"), reset: $("reset"), loadMore: $("load-more"), sentinel: $("sentinel"),
    sidebar: $("sidebar"), sidebarBackdrop: $("sidebar-backdrop"),
    toggleFilters: $("toggle-filters"), closeFilters: $("close-filters"),
    detail: $("detail"),
  };

  let data = { movies: [], services: [], ui_defaults: {} };
  let allGenres = [];
  let hidden = loadHidden();
  // People and "watched by" marks, shared with the Apple TV app through serve.py.
  let watched = { people: [], watched: {} };
  let watchedApi = true;   // false when there is no server (static hosting): falls back to localStorage
  let visible = [];     // current filtered + sorted list
  let rendered = 0;     // how many of `visible` are in the DOM

  // ---------------------------------------------------------------------
  // State <-> URL hash
  // ---------------------------------------------------------------------
  function storedView() {
    try { const v = localStorage.getItem(VIEW_KEY); return VIEWS.includes(v) ? v : "grid"; } catch { return "grid"; }
  }
  const defaults = () => ({
    q: "", services: null /* null = all */, mc: 0, ma: 0,
    mr: Number(data.ui_defaults.min_critic_reviews ?? 20),
    cf: false, hn: true, g: [], y0: "", y1: "", a0: "", rt: "", sh: false, hw: [],
    sort: data.ui_defaults.sort || "critic_desc",
    view: storedView(),
  });
  let state = defaults();

  function loadStoredState() {
    try {
      const raw = JSON.parse(localStorage.getItem(STATE_KEY) || "null");
      if (!raw || typeof raw !== "object") return null;
      const s = defaults();
      for (const k of Object.keys(s)) {
        if (k === "view" || !(k in raw)) continue;
        if (typeof raw[k] === typeof s[k] || (k === "services" && (raw[k] === null || Array.isArray(raw[k])))) s[k] = raw[k];
      }
      if (!Array.isArray(s.g)) s.g = [];
      if (!Array.isArray(s.hw)) s.hw = [];
      return s;
    } catch { return null; }
  }

  function saveStoredState() {
    try {
      const { view, ...rest } = state;
      localStorage.setItem(STATE_KEY, JSON.stringify(rest));
    } catch { /* ignore */ }
  }

  function readHash() {
    const s = defaults();
    const p = new URLSearchParams(location.hash.replace(/^#/, ""));
    if (!p.toString()) {
      // No hash: restore the last filters used on either page.
      const stored = loadStoredState();
      return stored ? { ...stored, view: s.view } : s;
    }
    if (p.has("q")) s.q = p.get("q");
    if (p.has("s")) s.services = p.get("s") ? p.get("s").split(",") : [];
    if (p.has("mc")) s.mc = num(p.get("mc"), 0);
    if (p.has("ma")) s.ma = num(p.get("ma"), 0);
    if (p.has("mr")) s.mr = num(p.get("mr"), s.mr);
    if (p.has("cf")) s.cf = p.get("cf") === "1";
    if (p.has("hn")) s.hn = p.get("hn") !== "0";
    if (p.has("g")) s.g = p.get("g") ? p.get("g").split(",") : [];
    if (p.has("y0")) s.y0 = p.get("y0");
    if (p.has("y1")) s.y1 = p.get("y1");
    if (p.has("a0")) s.a0 = p.get("a0");
    if (p.has("hw")) s.hw = p.get("hw") ? p.get("hw").split(",") : [];
    if (p.has("rt")) s.rt = p.get("rt");
    if (p.has("sh")) s.sh = p.get("sh") === "1";
    if (p.has("sort")) s.sort = p.get("sort");
    if (p.has("v") && VIEWS.includes(p.get("v"))) s.view = p.get("v");
    return s;
  }

  function writeHash() {
    const d = defaults();
    const p = new URLSearchParams();
    if (state.q) p.set("q", state.q);
    if (state.services !== null) p.set("s", state.services.join(","));
    if (state.mc !== d.mc) p.set("mc", state.mc);
    if (state.ma !== d.ma) p.set("ma", state.ma);
    if (state.mr !== d.mr) p.set("mr", state.mr);
    if (state.cf) p.set("cf", "1");
    if (!state.hn) p.set("hn", "0");
    if (state.g.length) p.set("g", state.g.join(","));
    if (state.y0) p.set("y0", state.y0);
    if (state.y1) p.set("y1", state.y1);
    if (state.a0) p.set("a0", state.a0);
    if (state.hw.length) p.set("hw", state.hw.join(","));
    if (state.rt) p.set("rt", state.rt);
    if (state.sh) p.set("sh", "1");
    if (state.sort !== d.sort) p.set("sort", state.sort);
    if (state.view !== "grid") p.set("v", state.view);
    const hash = p.toString();
    const next = hash ? "#" + hash : location.pathname + location.search;
    if (("#" + hash) !== location.hash) history.replaceState(null, "", next);
    saveStoredState();
    // The Movies / TV Series links carry the current filters across.
    for (const a of document.querySelectorAll(".kind-nav a")) {
      const base = a.getAttribute("href").split("#")[0];
      a.setAttribute("href", hash ? `${base}#${hash}` : base);
    }
  }

  function num(v, fallback) { const n = Number(v); return Number.isFinite(n) ? n : fallback; }

  // ---------------------------------------------------------------------
  // Hidden titles (localStorage)
  // ---------------------------------------------------------------------
  function loadHidden() {
    try { return new Set(JSON.parse(localStorage.getItem(HIDDEN_KEY) || "[]")); }
    catch { return new Set(); }
  }
  function saveHidden() {
    try { localStorage.setItem(HIDDEN_KEY, JSON.stringify([...hidden])); } catch { /* ignore */ }
    el.hiddenCount.textContent = hidden.size;
  }

  // ---------------------------------------------------------------------
  // People & watched marks
  // ---------------------------------------------------------------------
  const titleId = (m) => `${m.kind}-${m.tmdb_id}`;
  const watchedBy = (m) => Object.keys((watched.watched || {})[titleId(m)] || {});

  function loadWatchedLocal() {
    try {
      const raw = JSON.parse(localStorage.getItem(WATCHED_KEY) || "null");
      if (raw && Array.isArray(raw.people)) return { people: raw.people, watched: raw.watched || {} };
    } catch { /* ignore */ }
    return { people: [], watched: {} };
  }
  function saveWatchedLocal() {
    try { localStorage.setItem(WATCHED_KEY, JSON.stringify(watched)); } catch { /* ignore */ }
  }

  async function watchedRequest(path, body) {
    if (!watchedApi) return null;
    try {
      const resp = await fetch(path, body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }
                                         : { cache: "no-store" });
      if (resp.status === 404 && !body) { watchedApi = false; return null; }
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        if (err && err.error) alert(err.error);
        return null;
      }
      return await resp.json();
    } catch {
      if (!body) watchedApi = false;
      return null;
    }
  }

  async function loadWatched() {
    const remote = await watchedRequest("../api/watched");
    watched = remote && Array.isArray(remote.people) ? remote : loadWatchedLocal();
    saveWatchedLocal();
    renderPeople();
  }

  async function addPerson(name) {
    name = (name || "").trim().replace(/\s+/g, " ");
    if (!name) return;
    if (watched.people.some((p) => p.toLowerCase() === name.toLowerCase())) return;
    const remote = await watchedRequest("../api/people", { add: name });
    if (remote) watched = remote; else if (!watchedApi) watched.people.push(name); else return;
    saveWatchedLocal();
    renderPeople();
    refresh();
  }

  async function removePerson(name) {
    if (!confirm(`Remove ${name}? Their watched marks are removed too.`)) return;
    const remote = await watchedRequest("../api/people", { remove: name });
    if (remote) watched = remote;
    else if (!watchedApi) {
      watched.people = watched.people.filter((p) => p !== name);
      for (const [id, marks] of Object.entries(watched.watched)) { delete marks[name]; if (!Object.keys(marks).length) delete watched.watched[id]; }
    } else return;
    state.hw = state.hw.filter((p) => p !== name);
    saveWatchedLocal();
    renderPeople();
    refresh();
  }

  async function toggleWatched(m, person) {
    const id = titleId(m);
    const now = !watchedBy(m).includes(person);
    // optimistic update
    const marks = watched.watched[id] || (watched.watched[id] = {});
    if (now) marks[person] = new Date().toISOString().slice(0, 10); else delete marks[person];
    if (!Object.keys(marks).length) delete watched.watched[id];
    renderWatchedRow(m);
    const remote = await watchedRequest("../api/watched", { id, person, watched: now });
    if (remote) watched = remote;
    saveWatchedLocal();
    renderWatchedRow(m);
    for (const node of document.querySelectorAll(`[data-id="${m.tmdb_id}"] .watched-line`)) node.textContent = watchedLineText(m);
    for (const node of document.querySelectorAll(`[data-id="${m.tmdb_id}"]`)) node.classList.toggle("is-watched", watchedBy(m).length > 0);
  }

  const watchedLineText = (m) => { const w = watchedBy(m); return w.length ? `✓ Watched by ${w.join(", ")}` : ""; };

  function renderPeople() {
    el.people.innerHTML = watched.people.map((p) => `
      <label class="check person"><input type="checkbox" name="hw" value="${escapeHtml(p)}"> Hide watched by ${escapeHtml(p)}
        <button type="button" class="link person-remove" data-person="${escapeHtml(p)}" title="Remove ${escapeHtml(p)}">remove</button></label>`).join("");
    $("people-hint").hidden = watched.people.length > 0;
    for (const cb of el.people.querySelectorAll("input")) cb.checked = state.hw.includes(cb.value);
    for (const b of el.people.querySelectorAll(".person-remove")) {
      b.addEventListener("click", (ev) => { ev.preventDefault(); removePerson(b.dataset.person); });
    }
  }

  function renderWatchedRow(m) {
    const row = $("detail-watched");
    if (!row || (el.detail.open && el.detail.dataset.id !== String(m.tmdb_id))) return;
    if (!watched.people.length) { row.innerHTML = `<span class="lbl">Watched by: add people in the sidebar to track who has seen this.</span>`; return; }
    const seen = watchedBy(m);
    row.innerHTML = `<span class="lbl">Watched by</span>` + watched.people.map((p) =>
      `<button type="button" class="person-chip" data-person="${escapeHtml(p)}" aria-pressed="${seen.includes(p)}">${seen.includes(p) ? "✓ " : ""}${escapeHtml(p)}</button>`).join("");
    for (const b of row.querySelectorAll(".person-chip")) b.addEventListener("click", () => toggleWatched(m, b.dataset.person));
  }

  // ---------------------------------------------------------------------
  // Filtering & sorting
  // ---------------------------------------------------------------------
  const norm = (s) => (s || "").toLowerCase().normalize("NFKD").replace(/[\u0300-\u036f]/g, "");

  /** "2022" -> "2022-01-01" (or "2022-12-31" for an upper bound); "2022-6-1" -> "2022-06-01"; else null. */
  function parseDateBound(text, upper) {
    const t = (text || "").trim();
    if (!t) return null;
    let m = /^(\d{4})$/.exec(t);
    if (m) return upper ? `${m[1]}-12-31` : `${m[1]}-01-01`;
    m = /^(\d{4})[-/.](\d{1,2})(?:[-/.](\d{1,2}))?$/.exec(t);
    if (!m) return null;
    const mm = m[2].padStart(2, "0");
    const dd = m[3] ? m[3].padStart(2, "0") : (upper ? "31" : "01");
    return `${m[1]}-${mm}-${dd}`;
  }
  /** ISO release date for comparisons; falls back to the year. */
  const releaseKey = (m, upper) => m.release_date || (m.year ? `${m.year}-${upper ? "12-31" : "01-01"}` : null);
  /** Latest "first seen" date among the services that are currently checked. */
  function addedKey(m) {
    const svc = state.services === null ? null : new Set(state.services);
    let best = null;
    for (const [name, date] of Object.entries(m.added || {})) {
      if (svc && !svc.has(name)) continue;
      if (!best || date > best) best = date;
    }
    return best;
  }
  const isNew = (m) => {
    const d = addedKey(m);
    if (!d || !data.tracking_since || d <= data.tracking_since) return false;
    return (Date.now() - Date.parse(d)) < 30 * 86400000;
  };
  const fmtDate = (iso) => {
    if (!iso) return "";
    const d = new Date(iso + "T00:00:00");
    return isNaN(d) ? iso : d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
  };

  function applyFilters() {
    const q = norm(state.q).trim();
    const svc = state.services === null ? null : new Set(state.services);
    const genres = new Set(state.g.filter((g) => allGenres.includes(g)));
    const y0 = parseDateBound(state.y0, false);
    const y1 = parseDateBound(state.y1, true);
    const a0 = parseDateBound(state.a0, false);
    const rtMax = state.rt ? Number(state.rt) : null;

    const hideWatched = new Set(state.hw);
    return data.movies.filter((m) => {
      const isHidden = hidden.has(m.tmdb_id);
      if (isHidden && !state.sh) return false;
      if (hideWatched.size && watchedBy(m).some((p) => hideWatched.has(p))) return false;
      if (svc && !m.services.some((s) => svc.has(s))) return false;
      const rt = m.rt || {};
      const hasScore = rt.critic_score != null || rt.audience_score != null;
      if (state.hn && !hasScore) return false;
      if (state.mc > 0 && !(rt.critic_score >= state.mc)) return false;
      if (state.ma > 0 && !(rt.audience_score >= state.ma)) return false;
      if (state.mr > 0 && rt.critic_score != null && !((rt.critic_count || 0) >= state.mr)) return false;
      if (state.cf && !rt.certified_fresh) return false;
      if (genres.size && !(m.genres || []).some((g) => genres.has(g))) return false;
      if (y0 != null && !(releaseKey(m, false) >= y0)) return false;
      if (y1 != null && !(releaseKey(m, true) <= y1)) return false;
      if (a0 != null) { const ak = addedKey(m); if (!ak || ak < a0) return false; }
      if (rtMax != null && m.runtime && m.runtime > rtMax) return false;
      if (q && !norm(m.title).includes(q) && !norm(m.original_title).includes(q)) return false;
      return true;
    });
  }

  const desc = (a, b) => (b ?? -1) - (a ?? -1);
  const count = (m) => m.rt.critic_count || 0;
  const combined = (m) => {
    const c = m.rt.critic_score, a = m.rt.audience_score;
    if (c == null && a == null) return null;
    if (c == null) return a;
    if (a == null) return c;
    return (c + a) / 2;
  };
  const SORTS = {
    critic_desc: (a, b) => desc(a.rt.critic_score, b.rt.critic_score) || desc(count(a), count(b)),
    audience_desc: (a, b) => desc(a.rt.audience_score, b.rt.audience_score) || desc(count(a), count(b)),
    combined_desc: (a, b) => desc(combined(a), combined(b)) || desc(count(a), count(b)),
    critic_count_desc: (a, b) => desc(count(a), count(b)) || desc(a.rt.critic_score, b.rt.critic_score),
    added_desc: (a, b) => (addedKey(b) || "").localeCompare(addedKey(a) || "") || desc(a.rt.critic_score, b.rt.critic_score),
    year_desc: (a, b) => desc(a.year, b.year) || desc(count(a), count(b)),
    year_asc: (a, b) => (a.year ?? 9999) - (b.year ?? 9999) || desc(count(a), count(b)),
    title_asc: (a, b) => a.title.localeCompare(b.title) || desc(count(a), count(b)),
  };

  function refresh() {
    visible = applyFilters();
    visible.sort(SORTS[state.sort] || SORTS.critic_desc);
    el.grid.replaceChildren();
    el.listBody.replaceChildren();
    rendered = 0;
    applyView();
    renderMore();
    el.count.textContent = `${visible.length.toLocaleString()} ${visible.length === 1 ? NOUN[0] : NOUN[1]}`;
    el.empty.hidden = visible.length !== 0;
    writeHash();
  }

  function applyView() {
    const list = state.view === "list";
    el.grid.hidden = list;
    el.listWrap.hidden = !list;
    for (const b of document.querySelectorAll(".view-toggle [data-view]")) {
      b.setAttribute("aria-pressed", String(b.dataset.view === state.view));
    }
    for (const th of el.list.querySelectorAll("th.sortable")) {
      th.classList.toggle("sorted", th.dataset.sort === state.sort || th.dataset.sortAlt === state.sort);
      th.classList.toggle("asc", th.dataset.sortAlt === state.sort);
    }
    try { localStorage.setItem(VIEW_KEY, state.view); } catch { /* ignore */ }
  }

  // ---------------------------------------------------------------------
  // Rendering
  // ---------------------------------------------------------------------
  function renderMore() {
    const frag = document.createDocumentFragment();
    const end = Math.min(rendered + PAGE_SIZE, visible.length);
    const make = state.view === "list" ? row : card;
    for (let i = rendered; i < end; i++) frag.appendChild(make(visible[i]));
    (state.view === "list" ? el.listBody : el.grid).appendChild(frag);
    rendered = end;
    el.loadMore.hidden = rendered >= visible.length;
    el.shown.textContent = visible.length > rendered ? `showing ${rendered} of ${visible.length}` : "";
  }

  function svgIcon(id) {
    return `<svg aria-hidden="true"><use href="#${id}"></use></svg>`;
  }

  function criticScoreHtml(rt, withCount) {
    if (rt.critic_score == null) return `<span class="score none" title="No Tomatometer">${svgIcon("icon-tomato")}–</span>`;
    const icon = rt.certified_fresh ? "icon-certified" : rt.critic_score >= 60 ? "icon-tomato" : "icon-splat";
    const label = rt.certified_fresh ? "Certified Fresh" : rt.critic_score >= 60 ? "Fresh" : "Rotten";
    const cnt = withCount && rt.critic_count ? `<small>${rt.critic_count.toLocaleString()}</small>` : "";
    return `<span class="score critic" title="Tomatometer: ${label}${rt.critic_count ? ", " + rt.critic_count + " reviews" : ""}">${svgIcon(icon)}${rt.critic_score}%${cnt}</span>`;
  }

  function audienceScoreHtml(rt, withCount) {
    if (rt.audience_score == null) return `<span class="score none" title="No audience score">${svgIcon("icon-popcorn")}–</span>`;
    const icon = rt.audience_score >= 60 ? "icon-popcorn" : "icon-spilled";
    const cnt = withCount && rt.audience_count ? `<small>${escapeHtml(rt.audience_count)}</small>` : "";
    return `<span class="score audience" title="Audience score${rt.audience_count ? ", " + rt.audience_count + " ratings" : ""}">${svgIcon(icon)}${rt.audience_score}%${cnt}</span>`;
  }

  const slug = (s) => norm(s).replace(/\+/g, "").replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, "");

  function badgesHtml(services) {
    if (!services.length) return `<span class="badge badge-none">no service</span>`;
    return services.map((s) => `<span class="badge" data-service="${slug(s)}">${escapeHtml(s)}</span>`).join("");
  }

  /** Direct link for a title on a service: an exact per-title URL from the JSON if present,
   *  else the service's search page from watch-links.js, else the JustWatch page. */
  function watchUrl(m, service) {
    const exact = m.watch_urls && m.watch_urls[service];
    if (exact) return exact;
    const tpl = (window.WATCH_LINKS || {})[slug(service)];
    if (tpl) return tpl.replace("{q}", encodeURIComponent(m.title));
    return m.justwatch_link || null;
  }

  /** Badges that open the service directly (used on cards and list rows). */
  function watchBadgesHtml(m) {
    if (!m.services.length) return `<span class="badge badge-none">no service</span>`;
    return m.services.map((s) => {
      const url = watchUrl(m, s);
      const label = escapeHtml(s);
      return url
        ? `<a class="badge" data-service="${slug(s)}" href="${escapeHtml(url)}" target="_blank" rel="noopener" title="Open ${label}">${label}</a>`
        : `<span class="badge" data-service="${slug(s)}">${label}</span>`;
    }).join("");
  }

  function watchButtonsHtml(m) {
    const buttons = m.services.map((s) => {
      const url = watchUrl(m, s);
      if (!url) return "";
      const exact = !!(m.watch_urls && m.watch_urls[s]);
      const episode = exact && m.watch_url_levels && m.watch_url_levels[s] === "episode";
      const tip = !exact ? `Search for this title on ${s}` : episode ? `Opens an episode of this series on ${s} (${s} gives no show-page link)` : `Open this title on ${s}`;
      return `<a class="watch-btn${exact ? "" : " watch-btn-search"}" data-service="${slug(s)}" href="${escapeHtml(url)}" target="_blank" rel="noopener" title="${escapeHtml(tip)}"><span class="play">${exact ? "▶" : "⌕"}</span> ${exact ? "Watch on" : "Find on"} ${escapeHtml(s)}${episode ? '<small class="lvl">episode</small>' : ""}</a>`;
    }).join("");
    return buttons || `<span class="badge badge-none">not on a configured service</span>`;
  }

  /** "2016–2022", "2022–" (still running) or "1995". */
  function yearsLabel(m) {
    if (m.kind !== "tv") return m.year ? String(m.year) : "";
    if (!m.year) return "";
    if (m.end_year == null) return `${m.year}–`;
    return m.end_year !== m.year ? `${m.year}–${m.end_year}` : String(m.year);
  }

  /** "121 min" for movies, "3 seasons · 50 min" for series. */
  function lengthLabel(m) {
    if (m.kind === "tv") {
      const parts = [];
      if (m.seasons) parts.push(`${m.seasons} season${m.seasons === 1 ? "" : "s"}`);
      if (m.runtime) parts.push(`${m.runtime} min`);
      return parts.join(" · ");
    }
    return m.runtime ? `${m.runtime} min` : "";
  }

  /** "Oct 2, 2026" or "before Sep 25, 2026" when it predates tracking. */
  function addedLabel(m) {
    const d = addedKey(m);
    if (!d) return "";
    return d <= (data.tracking_since || "") ? `before ${fmtDate(d)}` : fmtDate(d);
  }

  function card(m) {
    const node = document.createElement("article");
    node.className = "card" + (hidden.has(m.tmdb_id) ? " is-hidden" : "") + (watchedBy(m).length ? " is-watched" : "");
    node.tabIndex = 0;
    node.dataset.id = m.tmdb_id;
    const meta = [yearsLabel(m), lengthLabel(m)].filter(Boolean).join(" · ");
    node.innerHTML = `
      <button class="hide-btn" type="button" title="${hidden.has(m.tmdb_id) ? "Un-hide" : "Hide this title"}" aria-label="Hide">✕</button>
      <div class="poster">${m.poster ? `<img loading="lazy" src="${m.poster}" alt="">` : `<div class="no-poster">${escapeHtml(m.title)}</div>`}</div>
      <div class="card-body">
        <h3>${escapeHtml(m.title)}${isNew(m) ? `<span class="tag-new" title="Added ${fmtDate(addedKey(m))}">New</span>` : ""}</h3>
        <div class="meta">${meta}</div>
        <div class="badges">${watchBadgesHtml(m)}</div>
        <div class="scores">${criticScoreHtml(m.rt, true)}${audienceScoreHtml(m.rt, false)}</div>
        <div class="watched-line">${watchedLineText(m)}</div>
        <div class="genres">${escapeHtml((m.genres || []).join(", "))}</div>
        <p class="overview">${escapeHtml(m.overview || "")}</p>
      </div>`;
    const img = node.querySelector(".poster img");
    if (img) img.addEventListener("error", () => img.remove(), { once: true });
    node.querySelector(".hide-btn").addEventListener("click", (ev) => {
      ev.stopPropagation();
      toggleHidden(m, node);
    });
    node.addEventListener("click", (ev) => { if (!ev.target.closest("a.badge")) openDetail(m); });
    node.addEventListener("keydown", (ev) => { if (ev.key === "Enter" && !ev.target.closest("a.badge")) openDetail(m); });
    return node;
  }

  function row(m) {
    const node = document.createElement("tr");
    node.className = "list-row" + (hidden.has(m.tmdb_id) ? " is-hidden" : "") + (watchedBy(m).length ? " is-watched" : "");
    node.tabIndex = 0;
    node.dataset.id = m.tmdb_id;
    node.innerHTML = `
      <td class="col-poster">${m.poster ? `<img loading="lazy" src="${m.poster}" alt="">` : `<span class="thumb-empty"></span>`}</td>
      <td class="col-title">
        <span class="title">${escapeHtml(m.title)}</span>
        <span class="sub">${[yearsLabel(m), lengthLabel(m), (m.genres || []).slice(0, 2).join(", ")].filter(Boolean).map(escapeHtml).join(" · ")}</span>
        <span class="watched-line">${watchedLineText(m)}</span>
        <div class="badges badges-inline">${watchBadgesHtml(m)}</div>
      </td>
      <td class="col-year">${yearsLabel(m)}</td>
      <td class="col-added">${addedLabel(m)}</td>
      <td class="col-runtime">${lengthLabel(m)}</td>
      <td class="col-genres">${escapeHtml((m.genres || []).join(", "))}</td>
      <td class="col-score">${criticScoreHtml(m.rt, false)}</td>
      <td class="col-count">${m.rt.critic_count ? m.rt.critic_count.toLocaleString() : ""}</td>
      <td class="col-score">${audienceScoreHtml(m.rt, false)}</td>
      <td class="col-services"><div class="badges">${watchBadgesHtml(m)}</div></td>
      <td class="col-actions"><button class="hide-btn" type="button" title="${hidden.has(m.tmdb_id) ? "Un-hide" : "Hide this title"}" aria-label="Hide">✕</button></td>`;
    const img = node.querySelector("img");
    if (img) img.addEventListener("error", () => img.replaceWith(Object.assign(document.createElement("span"), { className: "thumb-empty" })), { once: true });
    node.querySelector(".hide-btn").addEventListener("click", (ev) => {
      ev.stopPropagation();
      toggleHidden(m, node);
    });
    node.addEventListener("click", (ev) => { if (!ev.target.closest("a.badge")) openDetail(m); });
    node.addEventListener("keydown", (ev) => { if (ev.key === "Enter" && !ev.target.closest("a.badge")) openDetail(m); });
    return node;
  }

  function toggleHidden(m, node) {
    if (hidden.has(m.tmdb_id)) hidden.delete(m.tmdb_id); else hidden.add(m.tmdb_id);
    saveHidden();
    if (hidden.has(m.tmdb_id) && !state.sh) {
      node.remove();
      visible = visible.filter((x) => x !== m);
      rendered = Math.max(0, rendered - 1);
      el.count.textContent = `${visible.length.toLocaleString()} ${visible.length === 1 ? NOUN[0] : NOUN[1]}`;
      el.empty.hidden = visible.length !== 0;
    } else {
      node.classList.toggle("is-hidden", hidden.has(m.tmdb_id));
    }
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }

  // ---------------------------------------------------------------------
  // Detail dialog
  // ---------------------------------------------------------------------
  function openDetail(m) {
    $("detail-backdrop").style.backgroundImage = m.backdrop ? `url("${m.backdrop}")` : "none";
    const poster = $("detail-poster");
    poster.hidden = false;
    if (m.poster_large || m.poster) { poster.src = m.poster_large || m.poster; poster.alt = `${m.title} poster`; }
    else { poster.removeAttribute("src"); poster.hidden = true; }
    poster.onerror = () => { poster.hidden = true; };
    $("detail-title").textContent = m.title;
    const meta = [yearsLabel(m), lengthLabel(m), m.kind === "tv" && m.episodes ? `${m.episodes} episodes` : null,
                  m.kind === "tv" ? m.status : null, (m.genres || []).join(", ")].filter(Boolean).join(" · ");
    $("detail-meta").textContent = meta;
    const rt = m.rt || {};
    $("detail-scores").innerHTML = `
      <span>${criticScoreHtml(rt, false)}<span class="sub">${rt.certified_fresh ? "Certified Fresh · " : "Tomatometer · "}${rt.critic_count ? rt.critic_count.toLocaleString() + " reviews" : "no reviews"}</span></span>
      <span>${audienceScoreHtml(rt, false)}<span class="sub">Audience · ${rt.audience_count ? escapeHtml(rt.audience_count) + " ratings" : "no ratings"}</span></span>`;
    $("detail-watch").innerHTML = watchButtonsHtml(m);
    const addedLines = Object.entries(m.added || {}).map(([name, d]) =>
      `${escapeHtml(name)}: ${d <= (data.tracking_since || "") ? "before " + fmtDate(d) : fmtDate(d)}`);
    const releaseLine = m.release_date ? `${m.kind === "tv" ? "First aired" : "Released"} ${fmtDate(m.release_date)}` : "";
    $("detail-added").textContent = [releaseLine, addedLines.length ? "Added to " + addedLines.join(" · ") : ""].filter(Boolean).join("  ·  ");
    $("detail-overview").textContent = m.overview || "No description available.";
    const trailer = $("detail-trailer");
    trailer.innerHTML = m.trailer_youtube_key
      ? `<iframe src="https://www.youtube-nocookie.com/embed/${encodeURIComponent(m.trailer_youtube_key)}" title="Trailer" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" allowfullscreen loading="lazy"></iframe>`
      : "";
    const links = [];
    if (rt.url) links.push(`<a href="${escapeHtml(rt.url)}" target="_blank" rel="noopener">Rotten Tomatoes ↗</a>`);
    if (m.justwatch_link) links.push(`<a href="${escapeHtml(m.justwatch_link)}" target="_blank" rel="noopener">JustWatch ↗</a>`);
    if (m.trailer_youtube_key) links.push(`<a href="https://www.youtube.com/watch?v=${encodeURIComponent(m.trailer_youtube_key)}" target="_blank" rel="noopener">Trailer on YouTube ↗</a>`);
    if (m.imdb_id) links.push(`<a href="https://www.imdb.com/title/${encodeURIComponent(m.imdb_id)}/" target="_blank" rel="noopener">IMDb ↗</a>`);
    links.push(`<a href="https://www.themoviedb.org/${m.kind === "tv" ? "tv" : "movie"}/${m.tmdb_id}" target="_blank" rel="noopener">TMDB ↗</a>`);
    $("detail-links").innerHTML = links.join("");
    el.detail.dataset.id = String(m.tmdb_id);
    renderWatchedRow(m);
    el.detail.showModal();
    el.detail.querySelector(".detail-body").scrollTop = 0;
    lookupWatchLinks(m);
  }

  // ---------------------------------------------------------------------
  // On-demand exact links (serve.py -> Watchmode), fetched when a title is opened
  // ---------------------------------------------------------------------
  let watchApiAvailable = true;   // false after a 404 (static hosting) or when the server has no key
  const watchLookups = new Map(); // tmdb_id -> Promise

  function needsWatchLookup(m) {
    return m.services.some((s) => !(m.watch_urls && m.watch_urls[s]));
  }

  function refreshWatchLinks(m) {
    for (const node of document.querySelectorAll(`[data-id="${m.tmdb_id}"] .badges`)) node.innerHTML = watchBadgesHtml(m);
    if (el.detail.open && el.detail.dataset.id === String(m.tmdb_id)) $("detail-watch").innerHTML = watchButtonsHtml(m);
  }

  function lookupWatchLinks(m) {
    if (!watchApiAvailable || !needsWatchLookup(m) || m._watchLookedUp) return;
    if (watchLookups.has(m.tmdb_id)) return;
    const p = fetch(`../api/watch-links?kind=${encodeURIComponent(m.kind)}&id=${encodeURIComponent(m.tmdb_id)}`, { cache: "no-store" })
      .then(async (resp) => {
        if (resp.status === 404) {
          const body = await resp.json().catch(() => ({}));
          // 404 from the API means "title not cached"; a plain 404 page means there is no API at all.
          if (!body || !body.error) watchApiAvailable = false;
          return;
        }
        if (!resp.ok) return;
        const body = await resp.json();
        m._watchLookedUp = true;
        if (body.watch_urls && Object.keys(body.watch_urls).length) {
          m.watch_urls = { ...(m.watch_urls || {}), ...body.watch_urls };
          m.watch_app_urls = { ...(m.watch_app_urls || {}), ...(body.watch_app_urls || {}) };
          m.watch_url_levels = { ...(m.watch_url_levels || {}), ...(body.watch_url_levels || {}) };
          refreshWatchLinks(m);
        }
        if (body.enabled === false && !Object.keys(body.watch_urls || {}).length) watchApiAvailable = false;
      })
      .catch(() => { /* offline or no server: keep search links */ })
      .finally(() => watchLookups.delete(m.tmdb_id));
    watchLookups.set(m.tmdb_id, p);
  }

  function closeDetail() {
    $("detail-trailer").innerHTML = "";  // stop playback
    el.detail.close();
  }

  // ---------------------------------------------------------------------
  // Form wiring
  // ---------------------------------------------------------------------
  function buildServiceChecks() {
    const counts = {};
    for (const m of data.movies) for (const s of m.services) counts[s] = (counts[s] || 0) + 1;
    el.services.innerHTML = data.services.map((s) => `
      <label class="check"><input type="checkbox" name="service" value="${escapeHtml(s)}"> <span class="badge" data-service="${slug(s)}">${escapeHtml(s)}</span> <span class="n">${counts[s] || 0}</span></label>`).join("");
  }

  function buildGenreChecks() {
    const counts = {};
    for (const m of data.movies) for (const g of m.genres || []) counts[g] = (counts[g] || 0) + 1;
    allGenres = Object.keys(counts).sort();
    el.genres.innerHTML = allGenres.map((g) => `
      <label class="check"><input type="checkbox" name="genre" value="${escapeHtml(g)}"> ${escapeHtml(g)}</label>`).join("");
  }

  function stateToForm() {
    el.q.value = state.q;
    for (const cb of el.services.querySelectorAll("input")) {
      cb.checked = state.services === null || state.services.includes(cb.value);
    }
    el.minCritic.value = state.mc; el.minCriticOut.textContent = state.mc;
    el.minAudience.value = state.ma; el.minAudienceOut.textContent = state.ma;
    el.minReviews.value = state.mr;
    el.certified.checked = state.cf;
    el.hideNoRt.checked = state.hn;
    for (const cb of el.genres.querySelectorAll("input")) cb.checked = state.g.includes(cb.value);
    el.yearMin.value = state.y0; el.yearMax.value = state.y1; el.addedMin.value = state.a0;
    el.runtimeMax.value = state.rt;
    el.showHidden.checked = state.sh;
    for (const cb of el.people.querySelectorAll("input")) cb.checked = state.hw.includes(cb.value);
    el.sort.value = SORTS[state.sort] ? state.sort : "critic_desc";
  }

  function formToState() {
    state.q = el.q.value;
    const checked = [...el.services.querySelectorAll("input:checked")].map((c) => c.value);
    state.services = checked.length === data.services.length ? null : checked;
    state.mc = num(el.minCritic.value, 0);
    state.ma = num(el.minAudience.value, 0);
    state.mr = Math.max(0, num(el.minReviews.value, 0));
    state.cf = el.certified.checked;
    state.hn = el.hideNoRt.checked;
    // Keep genre picks that only exist on the other page (movie vs TV genre names differ).
    state.g = [...el.genres.querySelectorAll("input:checked")].map((c) => c.value)
      .concat(state.g.filter((g) => !allGenres.includes(g)));
    state.y0 = el.yearMin.value; state.y1 = el.yearMax.value; state.a0 = el.addedMin.value;
    state.rt = el.runtimeMax.value;
    state.sh = el.showHidden.checked;
    state.hw = [...el.people.querySelectorAll("input:checked")].map((c) => c.value);
    state.sort = el.sort.value;
    el.minCriticOut.textContent = state.mc;
    el.minAudienceOut.textContent = state.ma;
  }

  let debounceTimer = null;
  function onChange(immediate) {
    formToState();
    clearTimeout(debounceTimer);
    if (immediate) refresh(); else debounceTimer = setTimeout(refresh, 120);
  }

  function wire() {
    $("filters").addEventListener("input", (ev) => {
      const t = ev.target;
      onChange(!(t.type === "search" || t.type === "number" || t.type === "range" || t.type === "text"));
    });
    $("filters").addEventListener("change", () => onChange(true));
    el.sort.addEventListener("change", () => onChange(true));
    $("services-all").addEventListener("click", () => { el.services.querySelectorAll("input").forEach((c) => (c.checked = true)); onChange(true); });
    $("services-none").addEventListener("click", () => { el.services.querySelectorAll("input").forEach((c) => (c.checked = false)); onChange(true); });
    $("genres-clear").addEventListener("click", () => { el.genres.querySelectorAll("input").forEach((c) => (c.checked = false)); onChange(true); });
    el.reset.addEventListener("click", () => {
      const view = state.view; state = defaults(); state.view = view;
      try { localStorage.removeItem(STATE_KEY); } catch { /* ignore */ }
      stateToForm(); refresh();
    });
    el.clearHidden.addEventListener("click", () => { hidden.clear(); saveHidden(); refresh(); });
    el.personAdd.addEventListener("click", () => { addPerson(el.personName.value); el.personName.value = ""; });
    el.personName.addEventListener("keydown", (ev) => { if (ev.key === "Enter") { ev.preventDefault(); addPerson(el.personName.value); el.personName.value = ""; } });
    el.loadMore.addEventListener("click", renderMore);
    if ("IntersectionObserver" in window) {
      new IntersectionObserver((entries) => {
        if (entries.some((e) => e.isIntersecting) && rendered < visible.length) renderMore();
      }, { rootMargin: "600px" }).observe(el.sentinel);
    }
    // grid / list
    for (const b of document.querySelectorAll(".view-toggle [data-view]")) {
      b.addEventListener("click", () => { if (state.view !== b.dataset.view) { state.view = b.dataset.view; refresh(); } });
    }
    for (const th of el.list.querySelectorAll("th.sortable")) {
      th.addEventListener("click", () => {
        const primary = th.dataset.sort, alt = th.dataset.sortAlt;
        state.sort = (alt && state.sort === primary) ? alt : primary;
        el.sort.value = state.sort;
        refresh();
      });
    }
    // detail dialog
    $("detail-close").addEventListener("click", closeDetail);
    el.detail.addEventListener("click", (ev) => { if (ev.target === el.detail) closeDetail(); });
    el.detail.addEventListener("cancel", (ev) => { ev.preventDefault(); closeDetail(); });
    // mobile sidebar
    const setSidebar = (open) => {
      el.sidebar.classList.toggle("open", open);
      el.sidebarBackdrop.hidden = !open;
      el.toggleFilters.setAttribute("aria-expanded", String(open));
      document.body.classList.toggle("sidebar-open", open);
    };
    el.toggleFilters.addEventListener("click", () => setSidebar(!el.sidebar.classList.contains("open")));
    el.closeFilters.addEventListener("click", () => setSidebar(false));
    el.sidebarBackdrop.addEventListener("click", () => setSidebar(false));
    window.addEventListener("hashchange", () => { state = readHash(); stateToForm(); refresh(); });
  }

  // ---------------------------------------------------------------------
  // Boot
  // ---------------------------------------------------------------------
  function applyKind() {
    for (const a of document.querySelectorAll(".kind-nav a")) {
      const active = a.dataset.kind === KIND;
      a.classList.toggle("active", active);
      if (active) a.setAttribute("aria-current", "page");
    }
    document.title = KIND === "tv" ? "Streaming Finder · TV Series" : "Streaming Finder · Movies";
    if (KIND === "tv") {
      $("release-legend").textContent = "First aired";
      $("runtime-label").textContent = "Max episode length (minutes)";
      $("col-runtime").textContent = "Length";
    }
  }

  async function boot() {
    applyKind();
    let json;
    try {
      const resp = await fetch(DATA_URL, { cache: "no-store" });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      json = await resp.json();
    } catch (err) {
      el.count.textContent = "";
      el.error.hidden = false;
      const file = KIND === "tv" ? "data/tv.json" : "data/movies.json";
      el.error.innerHTML = `Could not load <code>${file}</code> (${escapeHtml(err.message)}). Run <code>python sync.py</code> first, then serve with <code>python serve.py</code>.`;
      return;
    }
    data = { movies: [], services: [], ui_defaults: {}, ...json };
    for (const m of data.movies) { m.rt = m.rt || {}; m.services = m.services || []; m.genres = m.genres || []; m.kind = m.kind || KIND; }
    if (data.generated_at) {
      const d = new Date(data.generated_at);
      el.generated.textContent = `updated ${isNaN(d) ? data.generated_at : d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })}`;
      el.generated.title = data.generated_at;
    }
    if (data.tracking_since) {
      $("added-hint").textContent = `Tracked by this app since ${fmtDate(data.tracking_since)}; titles already there then show as “before” that date.`;
      el.addedMin.min = data.tracking_since;
    }
    buildServiceChecks();
    buildGenreChecks();
    el.hiddenCount.textContent = hidden.size;
    await loadWatched();
    state = readHash();
    stateToForm();
    wire();
    refresh();
  }

  // ---------------------------------------------------------------------
  // Keep a long-open page current: re-fetch when the tab becomes visible and
  // every 15 minutes; only re-render when the server has a newer sync.
  // ---------------------------------------------------------------------
  let lastCheck = Date.now();
  async function checkForNewData() {
    lastCheck = Date.now();
    try {
      const resp = await fetch(DATA_URL, { cache: "no-store" });
      if (!resp.ok) return;
      const json = await resp.json();
      if (json.generated_at && json.generated_at !== data.generated_at) {
        data = { movies: [], services: [], ui_defaults: {}, ...json };
        for (const m of data.movies) { m.rt = m.rt || {}; m.services = m.services || []; m.genres = m.genres || []; m.kind = m.kind || KIND; }
        const d = new Date(data.generated_at);
        el.generated.textContent = `updated ${isNaN(d) ? data.generated_at : d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })}`;
        buildServiceChecks();
        buildGenreChecks();
        stateToForm();
        refresh();
      }
      const remote = await watchedRequest("../api/watched");
      if (remote && Array.isArray(remote.people)) { watched = remote; saveWatchedLocal(); renderPeople(); refresh(); }
    } catch { /* offline: keep what we have */ }
  }
  setInterval(checkForNewData, 15 * 60 * 1000);
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible" && Date.now() - lastCheck > 60 * 1000) checkForNewData();
  });

  boot();
})();
