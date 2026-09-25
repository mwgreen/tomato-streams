/* Streaming Movie Finder — vanilla JS front end for data/movies.json */
(function () {
  "use strict";

  const DATA_URL = "../data/movies.json";
  const PAGE_SIZE = 120;
  const HIDDEN_KEY = "smf.hidden";

  const $ = (id) => document.getElementById(id);
  const el = {
    grid: $("grid"), empty: $("empty"), error: $("error"), count: $("count"), shown: $("shown"),
    generated: $("generated"), services: $("services"), genres: $("genres"), q: $("q"),
    minCritic: $("min-critic"), minCriticOut: $("min-critic-out"),
    minAudience: $("min-audience"), minAudienceOut: $("min-audience-out"),
    minReviews: $("min-reviews"), certified: $("certified"), hideNoRt: $("hide-no-rt"),
    yearMin: $("year-min"), yearMax: $("year-max"), runtimeMax: $("runtime-max"),
    showHidden: $("show-hidden"), hiddenCount: $("hidden-count"), clearHidden: $("clear-hidden"),
    sort: $("sort"), reset: $("reset"), loadMore: $("load-more"), sentinel: $("sentinel"),
    sidebar: $("sidebar"), sidebarBackdrop: $("sidebar-backdrop"),
    toggleFilters: $("toggle-filters"), closeFilters: $("close-filters"),
    detail: $("detail"),
  };

  let data = { movies: [], services: [], ui_defaults: {} };
  let allGenres = [];
  let hidden = loadHidden();
  let visible = [];     // current filtered + sorted list
  let rendered = 0;     // how many of `visible` are in the DOM

  // ---------------------------------------------------------------------
  // State <-> URL hash
  // ---------------------------------------------------------------------
  const defaults = () => ({
    q: "", services: null /* null = all */, mc: 0, ma: 0,
    mr: Number(data.ui_defaults.min_critic_reviews ?? 20),
    cf: false, hn: true, g: [], y0: "", y1: "", rt: "", sh: false,
    sort: data.ui_defaults.sort || "critic_desc",
  });
  let state = defaults();

  function readHash() {
    const s = defaults();
    const p = new URLSearchParams(location.hash.replace(/^#/, ""));
    if (!p.toString()) return s;
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
    if (p.has("rt")) s.rt = p.get("rt");
    if (p.has("sh")) s.sh = p.get("sh") === "1";
    if (p.has("sort")) s.sort = p.get("sort");
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
    if (state.rt) p.set("rt", state.rt);
    if (state.sh) p.set("sh", "1");
    if (state.sort !== d.sort) p.set("sort", state.sort);
    const hash = p.toString();
    const next = hash ? "#" + hash : location.pathname + location.search;
    if (("#" + hash) !== location.hash) history.replaceState(null, "", next);
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
  // Filtering & sorting
  // ---------------------------------------------------------------------
  const norm = (s) => (s || "").toLowerCase().normalize("NFKD").replace(/[̀-ͯ]/g, "");

  function applyFilters() {
    const q = norm(state.q).trim();
    const svc = state.services === null ? null : new Set(state.services);
    const genres = new Set(state.g);
    const y0 = state.y0 ? Number(state.y0) : null;
    const y1 = state.y1 ? Number(state.y1) : null;
    const rtMax = state.rt ? Number(state.rt) : null;

    return data.movies.filter((m) => {
      const isHidden = hidden.has(m.tmdb_id);
      if (isHidden && !state.sh) return false;
      if (svc && !m.services.some((s) => svc.has(s))) return false;
      const rt = m.rt || {};
      const hasScore = rt.critic_score != null || rt.audience_score != null;
      if (state.hn && !hasScore) return false;
      if (state.mc > 0 && !(rt.critic_score >= state.mc)) return false;
      if (state.ma > 0 && !(rt.audience_score >= state.ma)) return false;
      if (state.mr > 0 && rt.critic_score != null && !((rt.critic_count || 0) >= state.mr)) return false;
      if (state.cf && !rt.certified_fresh) return false;
      if (genres.size && !(m.genres || []).some((g) => genres.has(g))) return false;
      if (y0 != null && !(m.year >= y0)) return false;
      if (y1 != null && !(m.year <= y1)) return false;
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
    year_desc: (a, b) => desc(a.year, b.year) || desc(count(a), count(b)),
    year_asc: (a, b) => (a.year ?? 9999) - (b.year ?? 9999) || desc(count(a), count(b)),
    title_asc: (a, b) => a.title.localeCompare(b.title) || desc(count(a), count(b)),
  };

  function refresh() {
    visible = applyFilters();
    visible.sort(SORTS[state.sort] || SORTS.critic_desc);
    el.grid.replaceChildren();
    rendered = 0;
    renderMore();
    el.count.textContent = `${visible.length.toLocaleString()} movie${visible.length === 1 ? "" : "s"}`;
    el.empty.hidden = visible.length !== 0;
    writeHash();
  }

  // ---------------------------------------------------------------------
  // Rendering
  // ---------------------------------------------------------------------
  function renderMore() {
    const frag = document.createDocumentFragment();
    const end = Math.min(rendered + PAGE_SIZE, visible.length);
    for (let i = rendered; i < end; i++) frag.appendChild(card(visible[i]));
    el.grid.appendChild(frag);
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
    return services.map((s) => `<span class="badge" data-service="${slug(s)}">${escapeHtml(s)}</span>`).join("");
  }

  function card(m) {
    const node = document.createElement("article");
    node.className = "card" + (hidden.has(m.tmdb_id) ? " is-hidden" : "");
    node.tabIndex = 0;
    node.dataset.id = m.tmdb_id;
    const meta = [m.year, m.runtime ? `${m.runtime} min` : null].filter(Boolean).join(" · ");
    node.innerHTML = `
      <button class="hide-btn" type="button" title="${hidden.has(m.tmdb_id) ? "Un-hide" : "Hide this title"}" aria-label="Hide">✕</button>
      <div class="poster">${m.poster ? `<img loading="lazy" src="${m.poster}" alt="">` : `<div class="no-poster">${escapeHtml(m.title)}</div>`}</div>
      <div class="card-body">
        <h3>${escapeHtml(m.title)}</h3>
        <div class="meta">${meta}</div>
        <div class="genres">${escapeHtml((m.genres || []).join(", "))}</div>
        <div class="scores">${criticScoreHtml(m.rt, true)}${audienceScoreHtml(m.rt, false)}</div>
        <p class="overview">${escapeHtml(m.overview || "")}</p>
        <div class="badges">${badgesHtml(m.services)}</div>
      </div>`;
    const img = node.querySelector(".poster img");
    if (img) img.addEventListener("error", () => img.remove(), { once: true });
    node.querySelector(".hide-btn").addEventListener("click", (ev) => {
      ev.stopPropagation();
      toggleHidden(m, node);
    });
    node.addEventListener("click", () => openDetail(m));
    node.addEventListener("keydown", (ev) => { if (ev.key === "Enter") openDetail(m); });
    return node;
  }

  function toggleHidden(m, node) {
    if (hidden.has(m.tmdb_id)) hidden.delete(m.tmdb_id); else hidden.add(m.tmdb_id);
    saveHidden();
    if (hidden.has(m.tmdb_id) && !state.sh) {
      node.remove();
      visible = visible.filter((x) => x !== m);
      rendered = Math.max(0, rendered - 1);
      el.count.textContent = `${visible.length.toLocaleString()} movies`;
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
    else { poster.removeAttribute("src"); }
    poster.onerror = () => { poster.hidden = true; };
    $("detail-title").textContent = m.title;
    const meta = [m.year, m.runtime ? `${m.runtime} min` : null, (m.genres || []).join(", ")].filter(Boolean).join(" · ");
    $("detail-meta").textContent = meta;
    const rt = m.rt || {};
    $("detail-scores").innerHTML = `
      <span>${criticScoreHtml(rt, false)}<span class="sub">${rt.certified_fresh ? "Certified Fresh · " : "Tomatometer · "}${rt.critic_count ? rt.critic_count.toLocaleString() + " reviews" : "no reviews"}</span></span>
      <span>${audienceScoreHtml(rt, false)}<span class="sub">Audience · ${rt.audience_count ? escapeHtml(rt.audience_count) + " ratings" : "no ratings"}</span></span>`;
    $("detail-services").innerHTML = badgesHtml(m.services);
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
    links.push(`<a href="https://www.themoviedb.org/movie/${m.tmdb_id}" target="_blank" rel="noopener">TMDB ↗</a>`);
    $("detail-links").innerHTML = links.join("");
    el.detail.showModal();
    el.detail.querySelector(".detail-body").scrollTop = 0;
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
      <label class="check"><input type="checkbox" name="service" value="${escapeHtml(s)}"> ${escapeHtml(s)} <span class="n">${counts[s] || 0}</span></label>`).join("");
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
    el.yearMin.value = state.y0; el.yearMax.value = state.y1;
    el.runtimeMax.value = state.rt;
    el.showHidden.checked = state.sh;
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
    state.g = [...el.genres.querySelectorAll("input:checked")].map((c) => c.value);
    state.y0 = el.yearMin.value; state.y1 = el.yearMax.value;
    state.rt = el.runtimeMax.value;
    state.sh = el.showHidden.checked;
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
      onChange(!(t.type === "search" || t.type === "number" || t.type === "range"));
    });
    $("filters").addEventListener("change", () => onChange(true));
    el.sort.addEventListener("change", () => onChange(true));
    $("services-all").addEventListener("click", () => { el.services.querySelectorAll("input").forEach((c) => (c.checked = true)); onChange(true); });
    $("services-none").addEventListener("click", () => { el.services.querySelectorAll("input").forEach((c) => (c.checked = false)); onChange(true); });
    $("genres-clear").addEventListener("click", () => { el.genres.querySelectorAll("input").forEach((c) => (c.checked = false)); onChange(true); });
    el.reset.addEventListener("click", () => { state = defaults(); stateToForm(); refresh(); });
    el.clearHidden.addEventListener("click", () => { hidden.clear(); saveHidden(); refresh(); });
    el.loadMore.addEventListener("click", renderMore);
    if ("IntersectionObserver" in window) {
      new IntersectionObserver((entries) => {
        if (entries.some((e) => e.isIntersecting) && rendered < visible.length) renderMore();
      }, { rootMargin: "600px" }).observe(el.sentinel);
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
    };
    el.toggleFilters.addEventListener("click", () => setSidebar(!el.sidebar.classList.contains("open")));
    el.closeFilters.addEventListener("click", () => setSidebar(false));
    el.sidebarBackdrop.addEventListener("click", () => setSidebar(false));
    window.addEventListener("hashchange", () => { state = readHash(); stateToForm(); refresh(); });
  }

  // ---------------------------------------------------------------------
  // Boot
  // ---------------------------------------------------------------------
  async function boot() {
    let json;
    try {
      const resp = await fetch(DATA_URL, { cache: "no-store" });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      json = await resp.json();
    } catch (err) {
      el.count.textContent = "";
      el.error.hidden = false;
      el.error.innerHTML = `Could not load <code>data/movies.json</code> (${escapeHtml(err.message)}). Run <code>python sync.py</code> first, then serve with <code>python serve.py</code>.`;
      return;
    }
    data = { movies: [], services: [], ui_defaults: {}, ...json };
    for (const m of data.movies) { m.rt = m.rt || {}; m.services = m.services || []; m.genres = m.genres || []; }
    if (data.generated_at) {
      const d = new Date(data.generated_at);
      el.generated.textContent = `data from ${isNaN(d) ? data.generated_at : d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" })}`;
      el.generated.title = data.generated_at;
    }
    buildServiceChecks();
    buildGenreChecks();
    el.hiddenCount.textContent = hidden.size;
    state = readHash();
    stateToForm();
    wire();
    refresh();
  }

  boot();
})();
