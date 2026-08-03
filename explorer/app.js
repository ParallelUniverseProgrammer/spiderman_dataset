/* Spider-Man dataset explorer — vanilla, no dependencies. */

const SVGNS = "http://www.w3.org/2000/svg";

function el(tag, attrs, ...kids) {
  const n = document.createElement(tag);
  apply(n, attrs, kids);
  return n;
}

function s(tag, attrs, ...kids) {
  const n = document.createElementNS(SVGNS, tag);
  apply(n, attrs, kids);
  return n;
}

function apply(n, attrs, kids) {
  if (attrs) {
    for (const [k, v] of Object.entries(attrs)) {
      if (v === null || v === undefined || v === false) continue;
      if (k === "class") n.setAttribute("class", v);
      else if (k === "text") n.textContent = v;
      else if (k === "html") n.innerHTML = v; // only ever called with literal markup
      else if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
      else if (k === "style" && typeof v === "object") Object.assign(n.style, v);
      else n.setAttribute(k, v);
    }
  }
  for (const kid of kids.flat(4)) {
    if (kid === null || kid === undefined || kid === false) continue;
    n.appendChild(typeof kid === "object" ? kid : document.createTextNode(String(kid)));
  }
}

const ICONS = {
  search: '<path d="M11 11 15 15M12.5 7.25a5.25 5.25 0 1 1-10.5 0 5.25 5.25 0 0 1 10.5 0Z" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>',
  theme: '<path d="M14 8.6A6 6 0 1 1 7.4 2a4.8 4.8 0 0 0 6.6 6.6Z" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/>',
  spider: '<path d="M12 2.6c1.4 0 2.7.5 3.6 1.3M12 2.6c-1.4 0-2.7.5-3.6 1.3M12 21.4c1.4 0 2.7-.5 3.6-1.3M12 21.4c-1.4 0-2.7-.5-3.6-1.3M2.6 8.3 7 10.4M2.6 15.7 7 13.6M21.4 8.3 17 10.4M21.4 15.7 17 13.6" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/><circle cx="12" cy="12" r="3.6" fill="none" stroke="currentColor" stroke-width="1.5"/>',
  back: '<path d="M9 3 4 8l5 5" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>',
};

const icon = (name, size = 16) =>
  s("svg", { viewBox: name === "spider" ? "0 0 24 24" : "0 0 16 16", width: size, height: size, "aria-hidden": "true", html: ICONS[name] });

/* ---------- formatting ---------- */

const TYPE = {
  movie: { label: "Movies", one: "Movie", color: "var(--series-1)" },
  tv_show: { label: "TV series", one: "TV series", color: "var(--series-2)" },
  game: { label: "Games", one: "Game", color: "var(--series-3)" },
};

const ALIGN = {
  hero: { label: "Hero", color: "var(--series-1)" },
  villain: { label: "Villain", color: "var(--series-2)" },
  antihero: { label: "Antihero", color: "var(--series-3)" },
  neutral: { label: "Neutral", color: "var(--deemph)" },
};

function money(v) {
  if (v == null) return "—";
  if (v >= 1e9) return "$" + (v / 1e9).toFixed(v >= 1e10 ? 0 : 2) + "B";
  if (v >= 1e6) return "$" + (v / 1e6).toFixed(v >= 1e8 ? 0 : 1) + "M";
  if (v >= 1e3) return "$" + Math.round(v / 1e3) + "K";
  return "$" + v;
}

const num = (v) => (v == null ? "—" : v.toLocaleString("en-US"));
const yr = (w) => w.year || "TBA";
const pct = (v) => (v == null ? "—" : Math.round(v) + "");

/* ---------- data prep ---------- */

const DATA = window.SPIDERMAN_DATA;
const works = DATA.works;
const characters = DATA.characters;
const people = DATA.people;
const workById = new Map(works.map((w) => [w.id, w]));
const charById = new Map(characters.map((c) => [c.id, c]));
const personById = new Map(people.map((p) => [p.id, p]));

for (const w of works) {
  w.cast = w.cast || [];
  w.crew = w.crew || [];
  w.characters = w.characters || [];
  w.reviews = w.reviews || [];
  w.studios = w.studios || [];
  w.relations = w.relations || [];
  w.awards = w.awards || [];
  w.episodes = w.episodes || [];
  w.game_releases = w.game_releases || [];
  w.platforms = w.platforms || [];
  w.sources = w.sources || [];
  w.soundtracks = w.soundtracks || [];
  const scored = w.reviews.filter((r) => r.pct != null);
  w.avg_pct = scored.length ? scored.reduce((a, r) => a + r.pct, 0) / scored.length : null;
  w.gross = w.box_office?.worldwide ?? null;
  w.n_credits = w.cast.length + w.crew.length;
  w.awards_won = w.awards.filter((a) => a.result === "won").length;
  w.maker =
    w.type === "movie"
      ? w.movie?.director || w.movie?.studio
      : w.type === "tv_show"
        ? w.tv?.network
        : w.game_releases[0]?.developer || w.game?.genre;
}
for (const c of characters) {
  c.appearances = c.appearances || [];
  c.variants = c.variants || [];
  c.n_works = c.n_works || 0;
  c.by_type = { movie: 0, tv_show: 0, game: 0 };
  for (const wid of new Set(c.appearances.map((a) => a.work_id))) c.by_type[workById.get(wid).type]++;
}
for (const p of people) {
  p.credits = p.credits || [];
  p.n_works = new Set(p.credits.map((c) => c.work_id)).size;
  p.roles = [...new Set(p.credits.map((c) => c.role))];
  p.is_actor = p.roles.some((r) => r === "actor" || r === "voice actor");
  p.years = p.credits.map((c) => workById.get(c.work_id).year).filter(Boolean).sort();
}

const FRANCHISES = [...new Set(works.map((w) => w.franchise).filter(Boolean))].sort();

/* ---------- derived indexes: dimensions the database holds but no single row names ---------- */

function groupInto(map, key, seed) {
  if (!map.has(key)) map.set(key, seed(key));
  return map.get(key);
}

function summarise(group) {
  const ws = group.works;
  const years = ws.map((w) => w.year).filter(Boolean);
  const scored = ws.filter((w) => w.avg_pct != null);
  group.n_works = ws.length;
  group.first_year = years.length ? Math.min(...years) : null;
  group.last_year = years.length ? Math.max(...years) : null;
  group.gross = ws.reduce((a, w) => a + (w.gross || 0), 0) || null;
  group.budget = ws.reduce((a, w) => a + (w.budget_usd || 0), 0) || null;
  group.avg_pct = scored.length ? scored.reduce((a, w) => a + w.avg_pct, 0) / scored.length : null;
  group.by_type = { movie: 0, tv_show: 0, game: 0 };
  for (const w of ws) group.by_type[w.type]++;
  return group;
}

const franchiseIndex = new Map();
for (const f of DATA.franchises || []) franchiseIndex.set(f.name, { name: f.name, description: f.description, works: [] });
for (const w of works) if (w.franchise) groupInto(franchiseIndex, w.franchise, (n) => ({ name: n, works: [] })).works.push(w);
for (const g of franchiseIndex.values()) summarise(g);

const studioIndex = new Map();
for (const w of works) {
  for (const st of w.studios) {
    const g = groupInto(studioIndex, st.name, (n) => ({ name: n, works: [], roles: new Set() }));
    g.roles.add(st.role);
    if (!g.works.includes(w)) g.works.push(w);
  }
}
for (const g of studioIndex.values()) summarise(g);

const platformIndex = new Map();
for (const w of works) {
  for (const name of w.platforms) {
    const g = groupInto(platformIndex, name, (n) => ({ name: n, works: [], releases: [] }));
    if (!g.works.includes(w)) g.works.push(w);
  }
  for (const r of w.game_releases) {
    if (!r.platform) continue;
    const g = groupInto(platformIndex, r.platform, (n) => ({ name: n, works: [], releases: [] }));
    if (!g.works.includes(w)) g.works.push(w);
    g.releases.push({ ...r, work: w });
  }
}
for (const g of platformIndex.values()) {
  summarise(g);
  const mc = g.releases.map((r) => r.metacritic).filter((v) => v != null);
  g.avg_metacritic = mc.length ? mc.reduce((a, b) => a + b, 0) / mc.length : null;
  const dates = g.releases.map((r) => r.date).filter(Boolean).sort();
  g.first_release = dates[0] || null;
  g.last_release = dates[dates.length - 1] || null;
}

/* Every normalized score, grouped by the outlet that published it. */
const publicationIndex = new Map();
for (const w of works) {
  for (const r of w.reviews) {
    if (r.pct == null) continue;
    const g = groupInto(publicationIndex, r.publication, (n) => ({ name: n, scores: [] }));
    g.scores.push({ ...r, work: w });
  }
}
for (const g of publicationIndex.values()) {
  g.n = g.scores.length;
  g.avg_pct = g.scores.reduce((a, r) => a + r.pct, 0) / g.n;
  g.lo = Math.min(...g.scores.map((r) => r.pct));
  g.hi = Math.max(...g.scores.map((r) => r.pct));
  g.by_type = { movie: 0, tv_show: 0, game: 0 };
  for (const r of g.scores) g.by_type[r.work.type]++;
}

/* Comic storylines, and how long each took to reach a screen. */
const comicIndex = new Map();
const adaptations = [];
for (const w of works) {
  for (const src of w.sources) {
    if (!src.comic) continue;
    const g = groupInto(comicIndex, src.comic, (n) => ({ title: n, uses: [] }));
    g.uses.push({ ...src, work: w });
    if (src.year && w.year) adaptations.push({ work: w, src, lag: w.year - src.year });
  }
}
for (const g of comicIndex.values()) {
  g.n = g.uses.length;
  const yrs = g.uses.map((u) => u.year).filter(Boolean);
  g.year = yrs.length ? Math.min(...yrs) : null;
  g.writer = g.uses.find((u) => u.writer)?.writer || null;
}

const allAwards = works.flatMap((w) => w.awards.map((a) => ({ ...a, work: w })));
const awardBodies = new Map();
for (const a of allAwards) {
  const g = groupInto(awardBodies, a.body, (n) => ({ name: n, won: 0, nominated: 0, rows: [] }));
  g[a.result === "won" ? "won" : "nominated"]++;
  g.rows.push(a);
}

/* Characters sharing a work with this one, most-shared first. */
function coAppearances(ident) {
  const workIds = new Set(ident.appearances.map((a) => a.work_id));
  const counts = new Map();
  for (const wid of workIds) {
    for (const wc of workById.get(wid).characters) {
      if (wc.identity_id === ident.id) continue;
      counts.set(wc.identity_id, (counts.get(wc.identity_id) || 0) + 1);
    }
  }
  return [...counts.entries()]
    .map(([id, n]) => ({ character: charById.get(id), n }))
    .filter((x) => x.character)
    .sort((a, b) => b.n - a.n || a.character.name.localeCompare(b.character.name));
}

/* People credited on more than one of the same works as this one. */
function collaborators(person) {
  const workIds = new Set(person.credits.map((c) => c.work_id));
  const counts = new Map();
  for (const wid of workIds) {
    const w = workById.get(wid);
    for (const c of [...w.cast, ...w.crew]) {
      if (c.person_id === person.id) continue;
      counts.set(c.person_id, (counts.get(c.person_id) || 0) + 1);
    }
  }
  return [...counts.entries()]
    .map(([id, n]) => ({ person: personById.get(id), n }))
    .filter((x) => x.person && x.n > 1)
    .sort((a, b) => b.n - a.n || a.person.name.localeCompare(b.person.name));
}

/* ---------- routing ---------- */

/* Every list view's filter defaults. Absent from the URL means "this value". */
const DEFAULTS = {
  works: { type: "all", franchise: "all", era: "all", sort: "year", dir: 1, q: "" },
  characters: { align: "all", sort: "n_works", dir: -1, q: "" },
  people: { kind: "all", sort: "n_works", dir: -1, q: "" },
  franchises: { sort: "n_works", dir: -1, q: "" },
  studios: { sort: "n_works", dir: -1, q: "" },
  platforms: { sort: "n_works", dir: -1, q: "" },
};

function go(hash) {
  if (location.hash === hash) render();
  else location.hash = hash;
}

function currentRoute() {
  const raw = location.hash.replace(/^#\/?/, "");
  const qi = raw.indexOf("?");
  const path = (qi < 0 ? raw : raw.slice(0, qi)) || "overview";
  const query = qi < 0 ? "" : raw.slice(qi + 1);
  const slash = path.indexOf("/");
  return slash < 0
    ? { view: path, id: null, query }
    : { view: path.slice(0, slash), id: decodeURIComponent(path.slice(slash + 1)), query };
}

/* Filter state lives in the URL, so any view a reader reaches is a link they can share.
   A bare "#/works" therefore means "no filters" — which is what the nav tabs link to. */
function readFilters(defaults, query) {
  const out = { ...defaults };
  const params = new URLSearchParams(query);
  for (const k of Object.keys(defaults)) {
    if (!params.has(k)) continue;
    const v = params.get(k);
    out[k] = typeof defaults[k] === "number" ? Number(v) : v;
  }
  return out;
}

function filterHash(view, filters, defaults) {
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(filters)) {
    if (v !== defaults[k] && v !== "" && v != null) params.set(k, String(v));
  }
  const q = params.toString();
  return "#/" + view + (q ? "?" + q : "");
}

/* ---------- shell ---------- */

const app = document.getElementById("app");
const LIST_VIEWS = ["works", "characters", "people", "franchises", "studios", "platforms"];
const LAST_LIST = {};
const listHash = (view) => LAST_LIST[view] || "#/" + view;

function render() {
  const { view, id, query } = currentRoute();
  const TAB_OF = {
    work: "works", character: "characters", person: "people",
    franchise: "franchises", studio: "studios", platform: "platforms",
  };
  const activeTab = TAB_OF[view] || view;
  document.querySelectorAll("nav.tabs a").forEach((a) => {
    const target = a.getAttribute("href").replace("#/", "");
    if (target === activeTab) a.setAttribute("aria-current", "page");
    else a.removeAttribute("aria-current");
  });
  if (LIST_VIEWS.includes(view)) LAST_LIST[view] = location.hash;
  app.replaceChildren();
  const map = {
    overview: viewOverview,
    works: viewWorks,
    work: viewWork,
    characters: viewCharacters,
    character: viewCharacter,
    people: viewPeople,
    person: viewPerson,
    franchises: viewFranchises,
    franchise: viewFranchise,
    studios: viewStudios,
    studio: viewStudio,
    platforms: viewPlatforms,
    platform: viewPlatform,
    analysis: viewAnalysis,
    about: viewAbout,
  };
  const fn = map[view] || viewOverview;
  app.appendChild(fn(id, query));
  window.scrollTo(0, window.__keepScroll ? window.scrollY : 0);
  window.__keepScroll = false;
  document.title =
    (app.querySelector("h1")?.textContent || "Spider-Man dataset") + " · Spider-Man Media Dataset";
}

function rerenderInPlace() {
  window.__keepScroll = true;
  render();
}

/* ---------- reusable pieces ---------- */

function backLink(label, hash) {
  return el("button", { class: "back", onclick: () => go(hash) }, icon("back", 13), label);
}

function statTile(label, value, hash) {
  const inner = [el("div", { class: "label" }, label), el("div", { class: "value", text: value })];
  return hash
    ? el("a", { class: "kpi", href: hash }, inner)
    : el("div", { class: "kpi" }, inner);
}

function dotLabel(color, label) {
  return el("span", { class: "dot-label" }, el("span", { class: "dot", style: { background: color } }), label);
}

function typeBadge(type) {
  return dotLabel(TYPE[type].color, TYPE[type].one);
}

function workLink(w, extra) {
  return el(
    "button",
    { class: "row-link", onclick: () => go("#/work/" + w.id) },
    w.title,
    extra === false ? null : el("span", { class: "muted" }, " " + yr(w))
  );
}

function personLink(pid) {
  const p = personById.get(pid);
  if (!p) return el("span", { class: "muted" }, "—");
  return el("button", { class: "row-link", onclick: () => go("#/person/" + p.id), text: p.name });
}

function franchiseLink(name, maxLen) {
  return el("button", {
    class: "row-link",
    style: { fontWeight: "400" },
    text: maxLen && name.length > maxLen ? name.slice(0, maxLen - 1) + "\u2026" : name,
    title: name,
    onclick: () => go("#/franchise/" + encodeURIComponent(name)),
  });
}

function dimChip(name, hash, sub) {
  return el(
    "button",
    { class: "chip", onclick: () => go(hash) },
    name,
    sub ? el("span", { class: "as", text: sub }) : null
  );
}

function charChip(c) {
  const a = ALIGN[c.alignment] || ALIGN.neutral;
  return el(
    "button",
    { class: "chip", onclick: () => go("#/character/" + c.identity_id) },
    el("span", { class: "dot", style: { background: a.color } }),
    c.name,
    c.as && c.as !== c.name ? el("span", { class: "as", text: "as “" + c.as + "”" }) : null
  );
}

function section(title, count, ...body) {
  return el(
    "section",
    { class: "block" },
    el("h2", null, title, count != null ? el("span", { class: "n", text: String(count) }) : null),
    ...body
  );
}

function table(cols, rows, opts = {}) {
  const sortKey = opts.sortKey;
  const head = el(
    "tr",
    null,
    cols.map((c) =>
      el(
        "th",
        {
          class: (c.num ? "num " : "") + (opts.onSort ? "sortable" : ""),
          onclick: opts.onSort ? () => opts.onSort(c.key) : null,
        },
        c.label,
        sortKey === c.key ? el("span", { class: "arrow", text: opts.dir > 0 ? "▲" : "▼" }) : null
      )
    )
  );
  const body = rows.map((r) =>
    el(
      "tr",
      null,
      cols.map((c) => {
        const v = c.cell(r);
        return el("td", { class: (c.num ? "num " : "") + (c.wrap ? "wrap " : "") + (c.cls || "") }, v);
      })
    )
  );
  return el(
    "div",
    { class: "table-wrap" + (opts.plain ? " plain" : "") },
    el("table", null, el("thead", null, head), el("tbody", null, body))
  );
}

function chips(options, current, onPick) {
  return el(
    "div",
    { class: "chips" },
    options.map((o) =>
      el(
        "button",
        { "aria-pressed": String(o.value === current), onclick: () => onPick(o.value) },
        o.color ? el("span", { class: "dot", style: { background: o.color } }) : null,
        o.label,
        o.n != null ? el("span", { class: "n", text: String(o.n) }) : null
      )
    )
  );
}

function selectBox(label, options, current, onPick) {
  const sel = el(
    "select",
    { "aria-label": label, onchange: (e) => onPick(e.target.value) },
    options.map((o) => el("option", { value: o.value, selected: o.value === current }, o.label))
  );
  return sel;
}

/* ---------- chart helpers ---------- */

function chartFigure({ title, sub, plot, legend, tableFn, note }) {
  const plotWrap = el("div", { class: "plot" }, plot.node);
  if (plot.tip) plotWrap.appendChild(plot.tip);
  let tableNode = null;
  const btn = el("button", {
    class: "toggle",
    "aria-pressed": "false",
    text: "Table",
    onclick: () => {
      const on = btn.getAttribute("aria-pressed") === "true";
      btn.setAttribute("aria-pressed", String(!on));
      if (!on) {
        tableNode = tableNode || el("div", { style: { marginTop: "10px" } }, tableFn());
        plotWrap.style.display = "none";
        if (legend) legend.style.display = "none";
        fig.appendChild(tableNode);
      } else {
        plotWrap.style.display = "";
        if (legend) legend.style.display = "";
        tableNode.remove();
        tableNode = null;
      }
    },
  });
  const fig = el(
    "figure",
    { class: "chart" },
    el(
      "figcaption",
      null,
      el("div", { class: "cap-text" }, el("h2", { text: title }), sub ? el("div", { class: "sub", text: sub }) : null),
      tableFn ? btn : null
    ),
    legend,
    plotWrap,
    note ? el("div", { class: "sub", style: { marginTop: "8px" } }, note) : null
  );
  return fig;
}

function makeTip() {
  const tip = el("div", { class: "tip" });
  tip.show = (x, y, nodes, host) => {
    tip.replaceChildren(...nodes);
    tip.classList.add("on");
    const hw = host.clientWidth;
    const tw = tip.offsetWidth;
    tip.style.left = Math.max(4, Math.min(x + 14, hw - tw - 4)) + "px";
    tip.style.top = y + 14 + "px";
  };
  tip.hide = () => tip.classList.remove("on");
  return tip;
}

const tipTitle = (t) => el("div", { class: "t-title", text: t });
const tipRow = (color, name, val) =>
  el(
    "div",
    { class: "t-row" },
    color ? el("span", { class: "key", style: { background: color } }) : null,
    el("span", { class: "name", text: name }),
    el("span", { class: "val", text: val })
  );

function legendBox(items, shape = "rect") {
  return el(
    "div",
    { class: "legend" },
    items.map((it) =>
      el(
        "div",
        { style: { display: "flex", alignItems: "center", gap: "6px" } },
        el("span", { class: "swatch" + (shape === "line" ? " line" : ""), style: { background: it.color } }),
        it.label
      )
    )
  );
}

/* ============================================================
   OVERVIEW
   ============================================================ */

function viewOverview() {
  const c = DATA.meta.counts;
  const frag = document.createDocumentFragment();

  frag.appendChild(
    el(
      "div",
      { class: "page-head" },
      el("h1", { text: "Every Spider-Man movie, series and game" }),
      el("p", {
        text:
          `${c.works} works released between ${DATA.meta.year_min} and ${DATA.meta.year_max}, with their casts, ` +
          `characters, studios, budgets, box office, review scores and comic sources. ` +
          `Click anything — every name here is a link into the rest of the data.`,
      })
    )
  );

  frag.appendChild(
    el(
      "div",
      { class: "hero" },
      el(
        "div",
        { class: "hero-fig" },
        el("div", { class: "value", text: String(c.works) }),
        el("div", { class: "label", text: "works catalogued" })
      ),
      el(
        "div",
        { class: "kpis" },
        el(
          "a",
          { class: "kpi", href: "#/works?type=movie" },
          el("div", { class: "label" }, dotLabel(TYPE.movie.color, "Movies")),
          el("div", { class: "value", text: String(c.movies) })
        ),
        el(
          "a",
          { class: "kpi", href: "#/works?type=tv_show" },
          el("div", { class: "label" }, dotLabel(TYPE.tv_show.color, "TV series")),
          el("div", { class: "value", text: String(c.tv_shows) })
        ),
        el(
          "a",
          { class: "kpi", href: "#/works?type=game" },
          el("div", { class: "label" }, dotLabel(TYPE.game.color, "Games")),
          el("div", { class: "value", text: String(c.games) })
        ),
        statTile("Characters", String(c.characters), "#/characters"),
        statTile("People", String(c.people), "#/people"),
        statTile("Credits", String(c.credits), "#/people"),
        statTile("Franchises", String(franchiseIndex.size), "#/franchises"),
        statTile("Studios", String(studioIndex.size), "#/studios"),
        statTile("Platforms", String(platformIndex.size), "#/platforms")
      )
    )
  );

  frag.appendChild(el("div", { class: "grid", style: { marginTop: "14px" } }, timelineChart()));
  frag.appendChild(
    el("div", { class: "grid cols-2", style: { marginTop: "14px" } }, economicsChart(), receptionChart())
  );
  frag.appendChild(el("div", { class: "grid", style: { marginTop: "14px" } }, topCharactersChart()));

  frag.appendChild(
    el(
      "div",
      { class: "caveat", style: { marginTop: "22px" } },
      el("strong", { text: "Before you count anything. " }),
      "Appearance totals are not comparable across media — games hold 61% of all character links and television 10%, " +
        "and for a series the whole show counts once. Character names are collapsed from 416 credit strings to ",
      el("button", { class: "linkish", text: "264 identities", onclick: () => go("#/characters") }),
      ". ",
      el("button", { class: "linkish", text: "Full notes on the data →", onclick: () => go("#/about") }),
      " ",
      el("button", { class: "linkish", text: "Deeper cuts in Analysis →", onclick: () => go("#/analysis") })
    )
  );

  return frag;
}

/* ---- timeline: stacked columns per year, by media type ---- */

function timelineChart() {
  const y0 = DATA.meta.year_min;
  const y1 = DATA.meta.year_max;
  const years = [];
  for (let y = y0; y <= y1; y++) years.push(y);
  const byYear = new Map(years.map((y) => [y, { movie: [], tv_show: [], game: [] }]));
  for (const w of works) if (w.year) byYear.get(w.year)[w.type].push(w);
  const maxN = Math.max(...years.map((y) => {
    const b = byYear.get(y);
    return b.movie.length + b.tv_show.length + b.game.length;
  }));

  const W = Math.max(880, years.length * 15);
  const H = 250;
  const M = { t: 10, r: 10, b: 28, l: 30 };
  const pw = W - M.l - M.r;
  const ph = H - M.t - M.b;
  const bandW = pw / years.length;
  const barW = Math.min(14, bandW - 3);
  const yScale = (v) => ph - (v / maxN) * ph;

  const svg = s("svg", { viewBox: `0 0 ${W} ${H}`, width: W, height: H, role: "img", style: { minWidth: "820px" } });
  const g = s("g", { transform: `translate(${M.l},${M.t})` });
  svg.appendChild(g);

  for (let v = 0; v <= maxN; v++) {
    g.appendChild(s("line", { x1: 0, x2: pw, y1: yScale(v), y2: yScale(v), class: v === 0 ? "baseline" : "gridline" }));
    g.appendChild(s("text", { x: -8, y: yScale(v) + 4, "text-anchor": "end", class: "tick-num", text: String(v) }));
  }

  const tip = makeTip();
  const order = ["movie", "tv_show", "game"];

  years.forEach((y, i) => {
    const b = byYear.get(y);
    const total = order.reduce((a, k) => a + b[k].length, 0);
    const x = i * bandW + (bandW - barW) / 2;
    let acc = 0;
    order.forEach((k) => {
      const n = b[k].length;
      if (!n) return;
      const yTop = yScale(acc + n);
      const yBot = yScale(acc);
      const h = Math.max(1, yBot - yTop - (acc > 0 ? 2 : 0));
      g.appendChild(s("rect", { x, y: yTop, width: barW, height: h, rx: 2, fill: TYPE[k].color }));
      acc += n;
    });
    const hit = s("rect", {
      x: i * bandW,
      y: 0,
      width: bandW,
      height: ph,
      fill: "transparent",
      style: "cursor:pointer",
      tabindex: total ? "0" : null,
      role: total ? "button" : null,
      "aria-label": total ? `${y}: ${total} works` : null,
    });
    const showTip = (ev) => {
      if (!total) return;
      const host = svg.parentNode;
      const r = host.getBoundingClientRect();
      const px = ev.clientX != null ? ev.clientX - r.left + host.scrollLeft : (i * bandW + M.l) * (host.clientWidth / W);
      const py = ev.clientY != null ? ev.clientY - r.top : 40;
      const rows = order.filter((k) => b[k].length).map((k) => tipRow(TYPE[k].color, TYPE[k].label, String(b[k].length)));
      const titles = order.flatMap((k) => b[k]).slice(0, 5).map((w) => el("div", { class: "t-note", text: w.title }));
      tip.show(px, py, [tipTitle(String(y)), ...rows, ...titles, total > 5 ? el("div", { class: "t-note", text: `+${total - 5} more` }) : null].filter(Boolean), host);
    };
    hit.addEventListener("pointermove", showTip);
    hit.addEventListener("focus", showTip);
    hit.addEventListener("pointerleave", () => tip.hide());
    hit.addEventListener("blur", () => tip.hide());
    if (total) hit.addEventListener("click", () => go(`#/works?era=${y}`));
    g.appendChild(hit);
  });

  years.forEach((y, i) => {
    if (y % 5 !== 0) return;
    g.appendChild(
      s("text", { x: i * bandW + bandW / 2, y: ph + 18, "text-anchor": "middle", class: "tick-num", text: String(y) })
    );
  });

  return chartFigure({
    title: "Releases per year",
    sub: "Every catalogued work, stacked by medium. Click a year to filter the works list.",
    legend: legendBox(order.map((k) => ({ color: TYPE[k].color, label: TYPE[k].label }))),
    plot: { node: svg, tip },
    tableFn: () =>
      table(
        [
          { key: "year", label: "Year", num: true, cell: (r) => String(r.year) },
          { key: "movie", label: "Movies", num: true, cell: (r) => String(r.movie) },
          { key: "tv", label: "TV series", num: true, cell: (r) => String(r.tv_show) },
          { key: "game", label: "Games", num: true, cell: (r) => String(r.game) },
          { key: "total", label: "Total", num: true, cell: (r) => String(r.total) },
        ],
        years
          .map((y) => {
            const b = byYear.get(y);
            return { year: y, movie: b.movie.length, tv_show: b.tv_show.length, game: b.game.length, total: b.movie.length + b.tv_show.length + b.game.length };
          })
          .filter((r) => r.total),
        { plain: true }
      ),
  });
}

/* ---- film economics: dumbbell budget → worldwide gross ---- */

function economicsChart() {
  const films = works
    .filter((w) => w.budget_usd && w.gross)
    .sort((a, b) => b.gross - a.gross);
  const max = Math.max(...films.map((f) => f.gross));

  const W = 560;
  const rowH = 26;
  const M = { t: 8, r: 66, b: 26, l: 172 };
  const ph = films.length * rowH;
  const H = ph + M.t + M.b;
  const pw = W - M.l - M.r;
  const x = (v) => (v / max) * pw;

  const svg = s("svg", { viewBox: `0 0 ${W} ${H}`, width: W, height: H, role: "img", style: { minWidth: "430px" } });
  const g = s("g", { transform: `translate(${M.l},${M.t})` });
  svg.appendChild(g);

  const ticks = [0, 500e6, 1e9, 1.5e9];
  for (const t of ticks) {
    g.appendChild(s("line", { x1: x(t), x2: x(t), y1: 0, y2: ph, class: t === 0 ? "baseline" : "gridline" }));
    g.appendChild(s("text", { x: x(t), y: ph + 17, "text-anchor": "middle", class: "tick-num", text: t === 0 ? "$0" : money(t) }));
  }

  const tip = makeTip();
  films.forEach((f, i) => {
    const cy = i * rowH + rowH / 2;
    g.appendChild(s("line", { x1: x(f.budget_usd), x2: x(f.gross), y1: cy, y2: cy, stroke: "var(--series-1-soft)", "stroke-width": 2, "stroke-linecap": "round" }));
    g.appendChild(s("circle", { cx: x(f.budget_usd), cy, r: 4.5, fill: "var(--series-1-soft)", stroke: "var(--surface-1)", "stroke-width": 2 }));
    g.appendChild(s("circle", { cx: x(f.gross), cy, r: 4.5, fill: "var(--series-1)", stroke: "var(--surface-1)", "stroke-width": 2 }));
    g.appendChild(s("text", { x: x(f.gross) + 10, y: cy + 4, class: "dlabel", text: money(f.gross) }));
    const label = s("text", { x: -10, y: cy + 4, "text-anchor": "end", class: "tick", fill: "var(--text-secondary)", style: "cursor:pointer", text: f.title.length > 26 ? f.title.slice(0, 25) + "…" : f.title });
    label.addEventListener("click", () => go("#/work/" + f.id));
    g.appendChild(label);

    const hit = s("rect", { x: -M.l, y: i * rowH, width: W, height: rowH, fill: "transparent", style: "cursor:pointer", tabindex: "0", role: "button", "aria-label": `${f.title}: budget ${money(f.budget_usd)}, worldwide ${money(f.gross)}` });
    const show = (ev) => {
      const host = svg.parentNode;
      const r = host.getBoundingClientRect();
      const px = ev.clientX != null ? ev.clientX - r.left : 200;
      const py = ev.clientY != null ? ev.clientY - r.top : i * rowH;
      tip.show(px, py, [
        tipTitle(f.title + " (" + yr(f) + ")"),
        tipRow("var(--series-1-soft)", "Budget", money(f.budget_usd)),
        tipRow("var(--series-1)", "Worldwide", money(f.gross)),
        el("div", { class: "t-note", text: (f.gross / f.budget_usd).toFixed(2) + "× return on budget" }),
      ], host);
    };
    hit.addEventListener("pointermove", show);
    hit.addEventListener("focus", show);
    hit.addEventListener("pointerleave", () => tip.hide());
    hit.addEventListener("blur", () => tip.hide());
    hit.addEventListener("click", () => go("#/work/" + f.id));
    g.appendChild(hit);
  });

  return chartFigure({
    title: "What each film cost and what it made",
    sub: `${films.length} films with both figures on record. Worldwide lifetime gross, not inflation-adjusted.`,
    legend: legendBox([
      { color: "var(--series-1-soft)", label: "Production budget" },
      { color: "var(--series-1)", label: "Worldwide gross" },
    ]),
    plot: { node: svg, tip },
    tableFn: () =>
      table(
        [
          { key: "t", label: "Film", cell: (f) => workLink(f) },
          { key: "b", label: "Budget", num: true, cell: (f) => money(f.budget_usd) },
          { key: "g", label: "Worldwide", num: true, cell: (f) => money(f.gross) },
          { key: "m", label: "Multiple", num: true, cell: (f) => (f.gross / f.budget_usd).toFixed(2) + "×" },
        ],
        films,
        { plain: true }
      ),
  });
}

/* ---- reception: score vs year, coloured by medium ---- */

function receptionChart() {
  const pts = works.filter((w) => w.avg_pct != null && w.year);
  const W = 560;
  const H = 300;
  const M = { t: 12, r: 14, b: 30, l: 34 };
  const pw = W - M.l - M.r;
  const ph = H - M.t - M.b;
  const y0 = DATA.meta.year_min;
  const y1 = DATA.meta.year_max;
  const x = (v) => ((v - y0) / (y1 - y0)) * pw;
  const y = (v) => ph - (v / 100) * ph;

  const svg = s("svg", { viewBox: `0 0 ${W} ${H}`, width: W, height: H, role: "img", style: { minWidth: "380px" } });
  const g = s("g", { transform: `translate(${M.l},${M.t})` });
  svg.appendChild(g);

  for (const v of [0, 25, 50, 75, 100]) {
    g.appendChild(s("line", { x1: 0, x2: pw, y1: y(v), y2: y(v), class: v === 0 ? "baseline" : "gridline" }));
    g.appendChild(s("text", { x: -8, y: y(v) + 4, "text-anchor": "end", class: "tick-num", text: String(v) }));
  }
  for (let t = 1970; t <= y1; t += 10) {
    g.appendChild(s("text", { x: x(t), y: ph + 18, "text-anchor": "middle", class: "tick-num", text: String(t) }));
  }

  const tip = makeTip();
  for (const w of pts) {
    g.appendChild(
      s("circle", { cx: x(w.year), cy: y(w.avg_pct), r: 5, fill: TYPE[w.type].color, stroke: "var(--surface-1)", "stroke-width": 2 })
    );
  }
  for (const w of pts) {
    const hit = s("circle", { cx: x(w.year), cy: y(w.avg_pct), r: 12, fill: "transparent", style: "cursor:pointer", tabindex: "0", role: "button", "aria-label": `${w.title}, ${w.year}, ${pct(w.avg_pct)} out of 100` });
    const show = (ev) => {
      const host = svg.parentNode;
      const r = host.getBoundingClientRect();
      tip.show(
        (ev.clientX ?? r.left + 200) - r.left,
        (ev.clientY ?? r.top + 100) - r.top,
        [
          tipTitle(w.title + " (" + yr(w) + ")"),
          tipRow(TYPE[w.type].color, TYPE[w.type].one, pct(w.avg_pct) + " / 100"),
          el("div", { class: "t-note", text: `mean of ${w.reviews.length} normalized score${w.reviews.length === 1 ? "" : "s"}` }),
        ],
        host
      );
    };
    hit.addEventListener("pointermove", show);
    hit.addEventListener("focus", show);
    hit.addEventListener("pointerleave", () => tip.hide());
    hit.addEventListener("blur", () => tip.hide());
    hit.addEventListener("click", () => go("#/work/" + w.id));
    g.appendChild(hit);
  }

  return chartFigure({
    title: "Reception over time",
    sub: `Mean review score for each of the ${pts.length} works carrying at least one score, normalized to 0–100.`,
    legend: legendBox(["movie", "tv_show", "game"].map((k) => ({ color: TYPE[k].color, label: TYPE[k].label }))),
    plot: { node: svg, tip },
    tableFn: () =>
      table(
        [
          { key: "t", label: "Work", cell: (w) => workLink(w) },
          { key: "ty", label: "Medium", cell: (w) => typeBadge(w.type) },
          { key: "y", label: "Year", num: true, cell: (w) => yr(w) },
          { key: "s", label: "Score", num: true, cell: (w) => pct(w.avg_pct) },
          { key: "n", label: "Sources", num: true, cell: (w) => String(w.reviews.length) },
        ],
        [...pts].sort((a, b) => b.avg_pct - a.avg_pct),
        { plain: true }
      ),
  });
}

/* ---- top characters ---- */

function topCharactersChart() {
  const top = characters.slice(0, 16);
  const max = top[0].n_works;
  const W = 900;
  const rowH = 24;
  const M = { t: 6, r: 44, b: 24, l: 200 };
  const ph = top.length * rowH;
  const H = ph + M.t + M.b;
  const pw = W - M.l - M.r;
  const x = (v) => (v / max) * pw;

  const svg = s("svg", { viewBox: `0 0 ${W} ${H}`, width: W, height: H, role: "img", style: { minWidth: "680px" } });
  const g = s("g", { transform: `translate(${M.l},${M.t})` });
  svg.appendChild(g);

  for (let t = 0; t <= max; t += 10) {
    g.appendChild(s("line", { x1: x(t), x2: x(t), y1: 0, y2: ph, class: t === 0 ? "baseline" : "gridline" }));
    g.appendChild(s("text", { x: x(t), y: ph + 16, "text-anchor": "middle", class: "tick-num", text: String(t) }));
  }

  const tip = makeTip();
  const order = ["movie", "tv_show", "game"];
  top.forEach((c, i) => {
    const yTop = i * rowH + 3;
    const barH = Math.min(16, rowH - 8);
    let acc = 0;
    order.forEach((k) => {
      const n = c.by_type[k];
      if (!n) return;
      const x0 = x(acc);
      const w = Math.max(1, x(acc + n) - x0 - (acc > 0 ? 2 : 0));
      g.appendChild(s("rect", { x: acc > 0 ? x0 + 2 : x0, y: yTop, width: w, height: barH, rx: 3, fill: TYPE[k].color }));
      acc += n;
    });
    g.appendChild(s("text", { x: x(c.n_works) + 9, y: yTop + barH - 3, class: "dlabel", text: String(c.n_works) }));
    const label = s("text", { x: -10, y: yTop + barH - 3, "text-anchor": "end", class: "tick", fill: "var(--text-secondary)", style: "cursor:pointer", text: c.name.length > 30 ? c.name.slice(0, 29) + "…" : c.name });
    label.addEventListener("click", () => go("#/character/" + c.id));
    g.appendChild(label);

    const hit = s("rect", { x: -M.l, y: i * rowH, width: W, height: rowH, fill: "transparent", style: "cursor:pointer", tabindex: "0", role: "button", "aria-label": `${c.name}: ${c.n_works} works` });
    const show = (ev) => {
      const host = svg.parentNode;
      const r = host.getBoundingClientRect();
      tip.show(
        (ev.clientX ?? r.left + 300) - r.left,
        (ev.clientY ?? r.top + i * rowH) - r.top,
        [
          tipTitle(c.name),
          ...order.filter((k) => c.by_type[k]).map((k) => tipRow(TYPE[k].color, TYPE[k].label, String(c.by_type[k]))),
          tipRow(null, "Total", String(c.n_works)),
        ],
        host
      );
    };
    hit.addEventListener("pointermove", show);
    hit.addEventListener("focus", show);
    hit.addEventListener("pointerleave", () => tip.hide());
    hit.addEventListener("blur", () => tip.hide());
    hit.addEventListener("click", () => go("#/character/" + c.id));
    g.appendChild(hit);
  });

  return chartFigure({
    title: "Most-adapted characters",
    sub: "Works each character appears in, split by medium. Credit spellings are already collapsed to one identity.",
    legend: legendBox(order.map((k) => ({ color: TYPE[k].color, label: TYPE[k].label }))),
    plot: { node: svg, tip },
    note: "A television series counts once however many episodes it ran, and game rosters are researched more deeply than TV — compare within a medium, not across.",
    tableFn: () =>
      table(
        [
          { key: "c", label: "Character", cell: (c) => el("button", { class: "row-link", text: c.name, onclick: () => go("#/character/" + c.id) }) },
          { key: "m", label: "Movies", num: true, cell: (c) => String(c.by_type.movie) },
          { key: "t", label: "TV series", num: true, cell: (c) => String(c.by_type.tv_show) },
          { key: "g", label: "Games", num: true, cell: (c) => String(c.by_type.game) },
          { key: "n", label: "Total", num: true, cell: (c) => String(c.n_works) },
        ],
        top,
        { plain: true }
      ),
  });
}

/* ============================================================
   WORKS
   ============================================================ */

/* ---------- list-view plumbing: URL-backed filters, sorting, CSV ---------- */

function applyFilters(view, filters) {
  history.replaceState(null, "", filterHash(view, filters, DEFAULTS[view]));
  rerenderInPlace();
}

function sortHandler(view, filters, ascKeys) {
  return (k) => {
    const next = { ...filters };
    if (filters.sort === k) next.dir = filters.dir * -1;
    else {
      next.sort = k;
      next.dir = ascKeys.includes(k) ? 1 : -1;
    }
    applyFilters(view, next);
  };
}

function sortRows(rows, get, dir, tieBreak) {
  return [...rows].sort((a, b) => {
    const va = get(a), vb = get(b);
    if (va < vb) return -dir;
    if (va > vb) return dir;
    return tieBreak(a).localeCompare(tieBreak(b));
  });
}

/* Re-rendering replaces the input, so the caret has to be put back by hand. */
function filterInput(placeholder, value, onChange) {
  return el("input", {
    class: "txt",
    type: "search",
    placeholder,
    value,
    oninput: (e) => {
      const at = e.target.selectionStart;
      onChange(e.target.value);
      const nx = app.querySelector('.filters input[type="search"]');
      if (nx) {
        nx.focus();
        nx.setSelectionRange(at, at);
      }
    },
  });
}

function resetButton(view, filters) {
  const dirty = Object.keys(DEFAULTS[view]).some((k) => filters[k] !== DEFAULTS[view][k]);
  return dirty ? el("button", { class: "linkish", text: "Reset", onclick: () => go("#/" + view) }) : null;
}

function csvEscape(s) {
  return /[",\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
}

/* The download is built from the rendered table, so the file always matches the screen. */
function csvFromTable(tableEl) {
  return [...tableEl.querySelectorAll("tr")]
    .map((tr) => [...tr.children].map((c) => csvEscape(c.textContent.trim().replace(/\s+/g, " "))).join(","))
    .join("\n");
}

window.csvFromTable = csvFromTable;

function downloadText(filename, text) {
  const url = URL.createObjectURL(new Blob([text], { type: "text/csv;charset=utf-8" }));
  const a = el("a", { href: url, download: filename });
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}

function csvButton(filename, getTableNode) {
  return el("button", {
    class: "toggle",
    text: "Download CSV",
    title: "Download the rows currently shown",
    onclick: () => {
      const node = getTableNode();
      if (node) downloadText(filename, csvFromTable(node));
    },
  });
}

function viewWorks(_id, query) {
  const f = readFilters(DEFAULTS.works, query);
  const eras = [...new Set(works.map((w) => (w.year ? Math.floor(w.year / 10) * 10 : null)).filter(Boolean))].sort();
  const exactYear = /^\d{4}$/.test(String(f.era)) && Number(f.era) % 10 !== 0;

  const rows0 = works.filter((w) => {
    if (f.type !== "all" && w.type !== f.type) return false;
    if (f.franchise !== "all" && w.franchise !== f.franchise) return false;
    if (f.era !== "all") {
      const e = Number(f.era);
      if (exactYear) {
        if (w.year !== e) return false;
      } else if (!w.year || w.year < e || w.year >= e + 10) return false;
    }
    if (f.q) {
      const hay = (w.title + " " + (w.franchise || "") + " " + (w.maker || "")).toLowerCase();
      if (!hay.includes(f.q.toLowerCase())) return false;
    }
    return true;
  });

  const get = {
    year: (w) => w.year ?? 9999,
    title: (w) => w.title.toLowerCase(),
    type: (w) => w.type,
    franchise: (w) => (w.franchise || "~").toLowerCase(),
    maker: (w) => (w.maker || "~").toLowerCase(),
    score: (w) => w.avg_pct ?? -1,
    gross: (w) => w.gross ?? -1,
    chars: (w) => w.characters.length,
    credits: (w) => w.n_credits,
  }[f.sort] || ((w) => w.year ?? 9999);
  const rows = sortRows(rows0, get, f.dir, (w) => w.title);

  const counts = { all: works.length };
  for (const k of Object.keys(TYPE)) counts[k] = works.filter((w) => w.type === k).length;

  let tableNode = null;
  const frag = document.createDocumentFragment();
  frag.appendChild(
    el(
      "div",
      { class: "page-head" },
      el("h1", { text: "Works" }),
      el("p", { text: "Every movie, television series and game in the dataset. Sort by any column, click a title for its full record, and share the URL — it carries your filters." })
    )
  );

  frag.appendChild(
    el(
      "div",
      { class: "filters" },
      chips(
        [
          { value: "all", label: "All", n: counts.all },
          ...Object.keys(TYPE).map((k) => ({ value: k, label: TYPE[k].label, n: counts[k], color: TYPE[k].color })),
        ],
        f.type,
        (v) => applyFilters("works", { ...f, type: v })
      ),
      selectBox(
        "Era",
        [
          { value: "all", label: "All years" },
          ...(exactYear ? [{ value: String(f.era), label: String(f.era) }] : []),
          ...eras.map((e) => ({ value: String(e), label: e + "s" })),
        ],
        String(f.era),
        (v) => applyFilters("works", { ...f, era: v })
      ),
      selectBox(
        "Franchise",
        [{ value: "all", label: "All franchises" }, ...FRANCHISES.map((x) => ({ value: x, label: x }))],
        f.franchise,
        (v) => applyFilters("works", { ...f, franchise: v })
      ),
      filterInput("Filter titles…", f.q, (v) => applyFilters("works", { ...f, q: v })),
      resetButton("works", f),
      csvButton("spiderman-works.csv", () => tableNode),
      el("span", { class: "result-count", text: `${rows.length} of ${works.length}` })
    )
  );

  if (rows.length) {
    tableNode = table(
      [
        { key: "title", label: "Title", cell: (w) => workLink(w, false) },
        { key: "year", label: "Year", num: true, cell: (w) => yr(w) },
        { key: "type", label: "Medium", cell: (w) => typeBadge(w.type) },
        { key: "franchise", label: "Franchise", cell: (w) => (w.franchise ? franchiseLink(w.franchise, 24) : el("span", { class: "muted", text: "—" })) },
        { key: "maker", label: "Made by", cell: (w) => trunc(w.maker, 22) },
        { key: "score", label: "Score", num: true, cell: (w) => (w.avg_pct == null ? el("span", { class: "muted", text: "—" }) : pct(w.avg_pct)) },
        { key: "gross", label: "Gross", num: true, cell: (w) => (w.gross == null ? el("span", { class: "muted", text: "—" }) : money(w.gross)) },
        { key: "chars", label: "Chars", num: true, cell: (w) => String(w.characters.length) },
        { key: "credits", label: "Credits", num: true, cell: (w) => String(w.n_credits) },
      ],
      rows,
      { onSort: sortHandler("works", f, ["title", "year", "type", "franchise", "maker"]), sortKey: f.sort, dir: f.dir, scroll: true }
    );
    frag.appendChild(tableNode);
    tableNode = tableNode.querySelector("table");
  } else {
    frag.appendChild(el("div", { class: "table-wrap" }, el("div", { class: "empty-state", text: "No works match these filters." })));
  }

  return frag;
}

function trunc(v, n) {
  if (!v) return el("span", { class: "muted", text: "—" });
  return v.length > n ? v.slice(0, n - 1) + "…" : v;
}

/* ---------- work detail ---------- */

function viewWork(id) {
  const w = workById.get(Number(id));
  if (!w) return el("div", { class: "empty-state", text: "Unknown work." });
  const frag = document.createDocumentFragment();
  frag.appendChild(backLink("All works", listHash("works")));

  const sub = w.type === "movie" ? w.movie?.sub_type : w.type === "tv_show" ? w.tv?.sub_type : w.game?.genre;
  frag.appendChild(
    el(
      "div",
      { class: "detail-head" },
      el("h1", { text: w.title }),
      el(
        "div",
        { class: "meta-line" },
        el("span", { class: "badge" }, el("span", { class: "dot", style: { background: TYPE[w.type].color } }), TYPE[w.type].one),
        el("span", { text: w.date || String(yr(w)) }),
        sub ? el("span", { text: sub }) : null,
        w.franchise
          ? el("button", {
              class: "linkish",
              text: w.franchise,
              onclick: () => go("#/franchise/" + encodeURIComponent(w.franchise)),
            })
          : null
      ),
      w.notes ? el("div", { class: "note", style: { marginTop: "10px" }, text: w.notes }) : null
    )
  );

  /* stat tiles */
  const tiles = [];
  if (w.avg_pct != null) tiles.push(statTile("Mean review score", pct(w.avg_pct) + " / 100"));
  if (w.budget_usd) tiles.push(statTile("Production budget", money(w.budget_usd)));
  if (w.gross) tiles.push(statTile("Worldwide gross", money(w.gross)));
  if (w.budget_usd && w.gross) tiles.push(statTile("Return on budget", (w.gross / w.budget_usd).toFixed(2) + "×"));
  if (w.movie?.runtime_minutes) tiles.push(statTile("Runtime", w.movie.runtime_minutes + " min"));
  if (w.tv?.episodes) tiles.push(statTile("Episodes", num(w.tv.episodes)));
  if (w.tv?.seasons) tiles.push(statTile("Seasons", String(w.tv.seasons)));
  if (w.characters.length) tiles.push(statTile("Characters", String(w.characters.length)));
  if (w.n_credits) tiles.push(statTile("Credited people", String(w.n_credits)));
  if (tiles.length) frag.appendChild(el("div", { class: "kpis", style: { marginTop: "16px" } }, tiles));

  /* facts */
  const facts = [];
  const addFact = (k, v) => v && facts.push(el("div", null, el("div", { class: "k", text: k }), el("div", { class: "v" }, v)));
  if (w.type === "movie" && w.movie) {
    addFact("Director", w.movie.director);
    addFact("Producer", w.movie.producer);
    addFact("Distributor", w.movie.distributor);
    addFact("Rating", w.movie.mpaa_rating);
  }
  if (w.type === "tv_show" && w.tv) {
    addFact("Network", w.tv.network);
    addFact("Format", w.tv.format);
    addFact("Ran", [w.tv.start_year, w.tv.end_year].filter(Boolean).join("–"));
    addFact("Head writer", w.tv.head_writer);
    addFact("Spider-Man voice", w.tv.voice_actor_spider_man);
    addFact("Status", w.tv.status);
  }
  if (w.type === "game" && w.game) {
    addFact("Genre", w.game.genre);
    addFact("Universe", w.game.universe);
    addFact("Engine", w.game.engine);
    addFact("Platforms", w.platforms.join(", "));
  }
  if (w.box_office?.domestic) addFact("Domestic gross", money(w.box_office.domestic));
  if (w.box_office?.international) addFact("International gross", money(w.box_office.international));
  if (facts.length) frag.appendChild(section("Details", null, el("div", { class: "card deflist" }, facts)));

  /* characters */
  if (w.characters.length) {
    const sorted = [...w.characters].sort((a, b) => (a.billing ?? 99) - (b.billing ?? 99));
    frag.appendChild(
      section(
        "Characters",
        w.characters.length,
        el("div", { class: "chip-list" }, sorted.map((c) => charChip(c)))
      )
    );
  }

  /* cast */
  if (w.cast.length) {
    frag.appendChild(
      section(
        "Cast",
        w.cast.length,
        table(
          [
            { key: "p", label: "Person", cell: (c) => personLink(c.person_id) },
            { key: "c", label: "Credited as", wrap: true, cell: (c) => c.character || el("span", { class: "muted", text: "—" }) },
            { key: "r", label: "Role", cell: (c) => el("span", { class: "muted", text: c.role }) },
          ],
          w.cast,
          { plain: true }
        )
      )
    );
  }

  /* crew */
  if (w.crew.length) {
    frag.appendChild(
      section(
        "Crew",
        w.crew.length,
        table(
          [
            { key: "r", label: "Role", cell: (c) => c.role },
            { key: "p", label: "Person", cell: (c) => personLink(c.person_id) },
          ],
          [...w.crew].sort((a, b) => a.role.localeCompare(b.role)),
          { plain: true }
        )
      )
    );
  }

  /* reviews */
  if (w.reviews.length) {
    const withPct = w.reviews.filter((r) => r.pct != null);
    frag.appendChild(
      section(
        "Review scores",
        w.reviews.length,
        table(
          [
            { key: "s", label: "Source", wrap: true, cell: (r) => r.source },
            { key: "raw", label: "Raw", num: true, cell: (r) => (r.max ? `${r.score} / ${r.max}` : String(r.score)) },
            {
              key: "n",
              label: "Normalized",
              cell: (r) =>
                r.pct == null
                  ? el("span", { class: "muted", text: "—" })
                  : el(
                      "span",
                      { class: "score-row" },
                      el("span", { class: "track" }, el("span", { class: "fill", style: { width: r.pct + "%" } })),
                      el("span", { style: { fontVariantNumeric: "tabular-nums" }, text: pct(r.pct) })
                    ),
            },
            { key: "c", label: "Reviews", num: true, cell: (r) => (r.count == null ? el("span", { class: "muted", text: "—" }) : num(r.count)) },
          ],
          w.reviews,
          { plain: true }
        ),
        withPct.length > 1
          ? el("div", { class: "sub", style: { marginTop: "8px" }, text: `Mean of the ${withPct.length} normalized scores: ${pct(w.avg_pct)} / 100. Every scale — 10-point, 5-star, percentage — is mapped onto 0–100 so the sources are comparable.` })
          : null
      )
    );
  }

  /* episodes */
  if (w.episodes.length) {
    frag.appendChild(
      section(
        "Episodes on record",
        w.episodes.length,
        table(
          [
            { key: "s", label: "S", num: true, cell: (e) => (e.season == null ? "—" : String(e.season)) },
            { key: "e", label: "E", num: true, cell: (e) => (e.episode == null ? "—" : String(e.episode)) },
            { key: "t", label: "Title", wrap: true, cell: (e) => e.title || el("span", { class: "muted", text: "—" }) },
            { key: "a", label: "Air date", cell: (e) => e.air_date || el("span", { class: "muted", text: "—" }) },
            { key: "d", label: "Director", wrap: true, cell: (e) => e.director || el("span", { class: "muted", text: "—" }) },
            { key: "v", label: "US viewers", num: true, cell: (e) => (e.viewers_m == null ? el("span", { class: "muted", text: "—" }) : e.viewers_m + "M") },
          ],
          w.episodes,
          { plain: true }
        ),
        w.tv?.episodes && w.episodes.length < w.tv.episodes
          ? el("div", { class: "sub", style: { marginTop: "8px" }, text: `The series ran ${w.tv.episodes} episodes; ${w.episodes.length} are itemised here.` })
          : null
      )
    );
  }

  /* game releases */
  if (w.game_releases.length) {
    frag.appendChild(
      section(
        "Releases",
        w.game_releases.length,
        table(
          [
            { key: "p", label: "Platform", cell: (r) => r.platform || "—" },
            { key: "d", label: "Date", cell: (r) => r.date || el("span", { class: "muted", text: "—" }) },
            { key: "pub", label: "Publisher", wrap: true, cell: (r) => r.publisher || el("span", { class: "muted", text: "—" }) },
            { key: "dev", label: "Developer", wrap: true, cell: (r) => r.developer || el("span", { class: "muted", text: "—" }) },
            { key: "m", label: "Metacritic", num: true, cell: (r) => (r.metacritic == null ? el("span", { class: "muted", text: "—" }) : String(r.metacritic)) },
            { key: "e", label: "ESRB", cell: (r) => r.esrb || el("span", { class: "muted", text: "—" }) },
          ],
          w.game_releases,
          { plain: true }
        )
      )
    );
  }

  /* studios */
  if (w.studios.length) {
    frag.appendChild(
      section(
        "Studios",
        w.studios.length,
        el(
          "div",
          { class: "chip-list" },
          w.studios.map((st) => dimChip(st.name, "#/studio/" + encodeURIComponent(st.name), st.role))
        )
      )
    );
  }

  if (w.platforms.length) {
    frag.appendChild(
      section(
        "Platforms",
        w.platforms.length,
        el("div", { class: "chip-list" }, [...w.platforms].sort().map((n) => dimChip(n, "#/platform/" + encodeURIComponent(n))))
      )
    );
  }

  if (w.budgets && w.budgets.length > 1) {
    frag.appendChild(
      section(
        "Reported budgets",
        w.budgets.length,
        table(
          [
            { key: "c", label: "Component", cell: (b) => b.component || "—" },
            { key: "a", label: "Amount", num: true, cell: (b) => money(b.amount) },
            { key: "y", label: "Source year", num: true, cell: (b) => (b.source_year ?? el("span", { class: "muted", text: "—" })) },
            { key: "p", label: "Used above", cell: (b) => (b.primary ? "yes" : el("span", { class: "muted", text: "no" })) },
            { key: "n", label: "Note", wrap: true, cell: (b) => b.note || el("span", { class: "muted", text: "—" }) },
          ],
          w.budgets,
          { plain: true }
        ),
        el("div", { class: "sub", style: { marginTop: "8px" }, text: "Where published figures disagree the catalogue keeps every one and marks the estimate it treats as primary." })
      )
    );
  }

  if (w.weekly && w.weekly.length > 1) {
    frag.appendChild(el("div", { class: "grid", style: { marginTop: "22px" } }, weeklyGrossChart(w)));
  }

  /* source material */
  if (w.sources.length) {
    frag.appendChild(
      section(
        "Comic sources",
        w.sources.length,
        table(
          [
            { key: "c", label: "Comic", wrap: true, cell: (r) => r.comic || el("span", { class: "muted", text: "—" }) },
            { key: "i", label: "Issues", wrap: true, cell: (r) => r.issues || el("span", { class: "muted", text: "—" }) },
            { key: "w", label: "Writer", wrap: true, cell: (r) => r.writer || el("span", { class: "muted", text: "—" }) },
            { key: "y", label: "Year", num: true, cell: (r) => (r.year == null ? el("span", { class: "muted", text: "—" }) : String(r.year)) },
            { key: "a", label: "Arc", wrap: true, cell: (r) => r.arc || el("span", { class: "muted", text: "—" }) },
          ],
          w.sources,
          { plain: true }
        )
      )
    );
  }

  /* awards */
  if (w.awards.length) {
    frag.appendChild(
      section(
        "Awards",
        w.awards.length,
        table(
          [
            { key: "b", label: "Body", cell: (a) => a.body },
            { key: "y", label: "Year", num: true, cell: (a) => (a.year == null ? "—" : String(a.year)) },
            { key: "c", label: "Category", wrap: true, cell: (a) => a.category },
            { key: "r", label: "Result", cell: (a) => (a.result === "won" ? el("strong", { text: "Won" }) : el("span", { class: "muted", text: "Nominated" })) },
            { key: "p", label: "Recipient", cell: (a) => (a.person_id ? personLink(a.person_id) : el("span", { class: "muted", text: "—" })) },
          ],
          w.awards,
          { plain: true }
        )
      )
    );
  }

  /* soundtracks */
  if (w.soundtracks.length) {
    frag.appendChild(
      section(
        "Music",
        w.soundtracks.length,
        table(
          [
            { key: "t", label: "Type", cell: (t) => t.type },
            { key: "n", label: "Title", wrap: true, cell: (t) => t.title || el("span", { class: "muted", text: "—" }) },
            { key: "b", label: "By", wrap: true, cell: (t) => t.by || el("span", { class: "muted", text: "—" }) },
            { key: "us", label: "US peak", num: true, cell: (t) => t.peak_us || el("span", { class: "muted", text: "—" }) },
            { key: "uk", label: "UK peak", num: true, cell: (t) => t.peak_uk || el("span", { class: "muted", text: "—" }) },
          ],
          w.soundtracks,
          { plain: true }
        )
      )
    );
  }

  /* relations */
  if (w.relations.length) {
    const byLabel = new Map();
    for (const r of w.relations) {
      if (!byLabel.has(r.label)) byLabel.set(r.label, []);
      byLabel.get(r.label).push(workById.get(r.work_id));
    }
    frag.appendChild(
      section(
        "Connected works",
        w.relations.length,
        el(
          "div",
          { class: "card", style: { display: "grid", gap: "12px" } },
          [...byLabel.entries()].map(([label, list]) =>
            el(
              "div",
              null,
              el("div", { class: "k", style: { fontSize: "12px", color: "var(--text-muted)", marginBottom: "5px" }, text: label }),
              el(
                "div",
                { class: "chip-list" },
                list
                  .sort((a, b) => (a.year ?? 9999) - (b.year ?? 9999))
                  .map((o) =>
                    el(
                      "button",
                      { class: "chip", onclick: () => go("#/work/" + o.id) },
                      el("span", { class: "dot", style: { background: TYPE[o.type].color } }),
                      o.title,
                      el("span", { class: "as", text: String(yr(o)) })
                    )
                  )
              )
            )
          )
        )
      )
    );
  }

  return frag;
}

/* Weekly domestic takings — the one film in the catalogue with a real week-by-week series. */
function weeklyGrossChart(w) {
  const rows = w.weekly.filter((r) => r.domestic != null);
  const max = Math.max(...rows.map((r) => r.domestic));
  const W = 620;
  const H = 240;
  const M = { t: 12, r: 14, b: 34, l: 52 };
  const pw = W - M.l - M.r;
  const ph = H - M.t - M.b;
  const band = pw / rows.length;
  const barW = Math.min(24, band - 10);
  const y = (v) => ph - (v / max) * ph;

  const svg = s("svg", { viewBox: `0 0 ${W} ${H}`, width: W, height: H, role: "img", style: { minWidth: "360px" } });
  const g = s("g", { transform: `translate(${M.l},${M.t})` });
  svg.appendChild(g);
  const step = 20e6;
  for (let v = 0; v <= max; v += step) {
    g.appendChild(s("line", { x1: 0, x2: pw, y1: y(v), y2: y(v), class: v === 0 ? "baseline" : "gridline" }));
    g.appendChild(s("text", { x: -8, y: y(v) + 4, "text-anchor": "end", class: "tick-num", text: money(v) }));
  }

  const tip = makeTip();
  rows.forEach((r, i) => {
    const x = i * band + (band - barW) / 2;
    g.appendChild(s("rect", { x, y: y(r.domestic), width: barW, height: Math.max(1, ph - y(r.domestic)), rx: 4, fill: "var(--series-1)" }));
    g.appendChild(s("text", { x: x + barW / 2, y: y(r.domestic) - 6, "text-anchor": "middle", class: "dlabel", text: money(r.domestic) }));
    g.appendChild(s("text", { x: i * band + band / 2, y: ph + 18, "text-anchor": "middle", class: "tick-num", text: "wk " + r.week }));
    const hit = s("rect", { x: i * band, y: 0, width: band, height: ph, fill: "transparent", tabindex: "0", role: "button", "aria-label": `Week ${r.week}: ${money(r.domestic)} domestic` });
    const show = (ev) => {
      const host = svg.parentNode;
      const rect = host.getBoundingClientRect();
      tip.show((ev.clientX ?? rect.left + 200) - rect.left, (ev.clientY ?? rect.top + 60) - rect.top, [
        tipTitle("Week " + r.week),
        tipRow("var(--series-1)", "Domestic", money(r.domestic)),
        r.international != null ? tipRow(null, "International", money(r.international)) : null,
      ].filter(Boolean), host);
    };
    hit.addEventListener("pointermove", show);
    hit.addEventListener("focus", show);
    hit.addEventListener("pointerleave", () => tip.hide());
    hit.addEventListener("blur", () => tip.hide());
    g.appendChild(hit);
  });

  return chartFigure({
    title: "Week by week at the domestic box office",
    sub: `${rows.length} weeks on record.`,
    note: "This is the only film in the catalogue with a genuine weekly series — for every other film the source filed a single lifetime total under week 1, which is why the totals above are read from the lifetime rows instead.",
    plot: { node: svg, tip },
    tableFn: () =>
      table(
        [
          { key: "w", label: "Week", num: true, cell: (r) => String(r.week) },
          { key: "d", label: "Domestic", num: true, cell: (r) => money(r.domestic) },
          { key: "i", label: "International", num: true, cell: (r) => (r.international == null ? "—" : money(r.international)) },
        ],
        w.weekly,
        { plain: true }
      ),
  });
}

/* ============================================================
   CHARACTERS
   ============================================================ */

function viewCharacters(_id, query) {
  const f = readFilters(DEFAULTS.characters, query);
  const rows0 = characters.filter((c) => {
    if (f.align !== "all" && c.alignment !== f.align) return false;
    if (f.q) {
      const hay = (c.name + " " + c.variants.join(" ")).toLowerCase();
      if (!hay.includes(f.q.toLowerCase())) return false;
    }
    return true;
  });
  const get = {
    name: (c) => c.name.toLowerCase(),
    align: (c) => c.alignment || "~",
    n_works: (c) => c.n_works,
    variants: (c) => c.variants.length,
    first_year: (c) => c.first_year ?? 9999,
    first_media_year: (c) => c.first_media_year ?? 9999,
  }[f.sort] || ((c) => c.n_works);
  const rows = sortRows(rows0, get, f.dir, (c) => c.name);
  const maxWorks = Math.max(...characters.map((c) => c.n_works));

  const counts = { all: characters.length };
  for (const a of Object.keys(ALIGN)) counts[a] = characters.filter((c) => c.alignment === a).length;

  let tableNode = null;
  const frag = document.createDocumentFragment();
  frag.appendChild(
    el(
      "div",
      { class: "page-head" },
      el("h1", { text: "Characters" }),
      el("p", {
        text: `${characters.length} distinct characters, resolved from 416 different credit spellings. “Peter Parker”, “Spider-Man” and “Spider-Man / Peter Parker” are one row here, not three.`,
      })
    )
  );

  frag.appendChild(
    el(
      "div",
      { class: "filters" },
      chips(
        [
          { value: "all", label: "All", n: counts.all },
          ...Object.keys(ALIGN).map((a) => ({ value: a, label: ALIGN[a].label, n: counts[a], color: ALIGN[a].color })),
        ],
        f.align,
        (v) => applyFilters("characters", { ...f, align: v })
      ),
      filterInput("Filter characters…", f.q, (v) => applyFilters("characters", { ...f, q: v })),
      resetButton("characters", f),
      csvButton("spiderman-characters.csv", () => tableNode),
      el("span", { class: "result-count", text: `${rows.length} of ${characters.length}` })
    )
  );

  if (rows.length) {
    tableNode = table(
      [
        { key: "name", label: "Character", cell: (c) => el("button", { class: "row-link", text: c.name, onclick: () => go("#/character/" + c.id) }) },
        { key: "align", label: "Alignment", cell: (c) => dotLabel((ALIGN[c.alignment] || ALIGN.neutral).color, (ALIGN[c.alignment] || ALIGN.neutral).label) },
        {
          key: "n_works",
          label: "Appears in",
          cell: (c) =>
            el(
              "span",
              { class: "bar-cell" },
              el("span", { class: "n", text: String(c.n_works) }),
              el("span", { class: "track" }, el("span", { class: "fill", style: { width: (c.n_works / maxWorks) * 100 + "%" } }))
            ),
        },
        { key: "first_media_year", label: "First on screen", num: true, cell: (c) => (c.first_media_year ?? "—") },
        { key: "first_year", label: "First in comics", num: true, cell: (c) => (c.first_year ?? el("span", { class: "muted", text: "—" })) },
        { key: "variants", label: "Spellings", num: true, cell: (c) => String(c.variants.length) },
      ],
      rows,
      { onSort: sortHandler("characters", f, ["name", "align", "first_year", "first_media_year"]), sortKey: f.sort, dir: f.dir, scroll: true }
    );
    frag.appendChild(tableNode);
    tableNode = tableNode.querySelector("table");
  } else {
    frag.appendChild(el("div", { class: "table-wrap" }, el("div", { class: "empty-state", text: "No characters match." })));
  }

  return frag;
}

function viewCharacter(id) {
  const c = charById.get(Number(id));
  if (!c) return el("div", { class: "empty-state", text: "Unknown character." });
  const a = ALIGN[c.alignment] || ALIGN.neutral;
  const frag = document.createDocumentFragment();
  frag.appendChild(backLink("All characters", listHash("characters")));

  frag.appendChild(
    el(
      "div",
      { class: "detail-head" },
      el("h1", { text: c.name }),
      el(
        "div",
        { class: "meta-line" },
        el("span", { class: "badge" }, el("span", { class: "dot", style: { background: a.color } }), a.label),
        c.first_comic ? el("span", { text: "First appeared in " + c.first_comic }) : null
      )
    )
  );

  const tiles = [statTile("Works", String(c.n_works))];
  for (const t of ["movie", "tv_show", "game"]) if (c.by_type[t]) tiles.push(statTile(TYPE[t].label, String(c.by_type[t])));
  if (c.first_media_year) tiles.push(statTile("First on screen", String(c.first_media_year)));
  frag.appendChild(el("div", { class: "kpis", style: { marginTop: "16px" } }, tiles));

  const rows = c.appearances
    .map((ap) => ({ ...ap, w: workById.get(ap.work_id) }))
    .sort((x, y) => (x.w.year ?? 9999) - (y.w.year ?? 9999));

  const uniqueWorks = [...new Map(rows.map((r) => [r.w.id, r.w])).values()];
  frag.appendChild(
    el("div", { class: "grid", style: { marginTop: "16px" } },
      yearStrip(uniqueWorks.map((w) => ({ year: w.year, type: w.type, title: w.title, work: w })), {
        title: "When this character turns up",
        sub: "Every work the character appears in, across the catalogue's full span.",
        onPick: (e) => go("#/work/" + e.work.id),
      }))
  );

  const co = coAppearances(c).slice(0, 14);
  if (co.length >= 3) {
    frag.appendChild(
      el("div", { class: "grid", style: { marginTop: "14px" } },
        hbarChart({
          title: "Appears alongside",
          sub: `Characters sharing a work with ${c.name}, most-shared first.`,
          items: co.map((x) => ({ label: x.character.name, value: x.n, key: x.character.id, sub: (ALIGN[x.character.alignment] || ALIGN.neutral).label })),
          onPick: (d) => go("#/character/" + d.key),
          labelWidth: 240,
          valueLabel: "Shared works",
          tableCols: [
            { key: "c", label: "Character", cell: (d) => el("button", { class: "row-link", text: d.label, onclick: () => go("#/character/" + d.key) }) },
            { key: "n", label: "Shared works", num: true, cell: (d) => String(d.value) },
            { key: "a", label: "Alignment", cell: (d) => d.sub },
          ],
        }))
    );
  }

  frag.appendChild(
    section(
      "Appearances",
      rows.length,
      table(
        [
          { key: "w", label: "Work", cell: (r) => workLink(r.w, false) },
          { key: "y", label: "Year", num: true, cell: (r) => yr(r.w) },
          { key: "t", label: "Medium", cell: (r) => typeBadge(r.w.type) },
          { key: "as", label: "Credited as", wrap: true, cell: (r) => (r.as === c.name ? el("span", { class: "muted", text: r.as }) : r.as) },
          { key: "a", label: "Played by", cell: (r) => (r.actor_person_id ? personLink(r.actor_person_id) : el("span", { class: "muted", text: "—" })) },
        ],
        rows,
        { plain: true }
      )
    )
  );

  if (c.variants.length > 1) {
    frag.appendChild(
      section(
        "Credit spellings collapsed into this identity",
        c.variants.length,
        el("div", { class: "chip-list" }, c.variants.map((v) => el("span", { class: "chip", text: v }))),
        el("div", { class: "sub", style: { marginTop: "8px" }, text: "These are the exact strings the source research used. Counting the raw credit table instead of this identity would split this character across every spelling above." })
      )
    );
  }

  const actors = [...new Set(c.appearances.map((ap) => ap.actor_person_id).filter(Boolean))];
  if (actors.length > 1) {
    frag.appendChild(
      section(
        "Performers",
        actors.length,
        el(
          "div",
          { class: "chip-list" },
          actors
            .map((pid) => personById.get(pid))
            .filter(Boolean)
            .sort((x, y) => (x.years[0] ?? 9999) - (y.years[0] ?? 9999))
            .map((p) => el("button", { class: "chip", onclick: () => go("#/person/" + p.id) }, p.name))
        )
      )
    );
  }

  return frag;
}

/* ============================================================
   PEOPLE
   ============================================================ */

function viewPeople(_id, query) {
  const f = readFilters(DEFAULTS.people, query);
  const rows0 = people.filter((p) => {
    if (f.kind === "cast" && !p.is_actor) return false;
    if (f.kind === "crew" && p.is_actor) return false;
    if (f.q && !p.name.toLowerCase().includes(f.q.toLowerCase())) return false;
    return true;
  });
  const get = {
    name: (p) => p.name.toLowerCase(),
    roles: (p) => p.roles.join(", ").toLowerCase(),
    n_works: (p) => p.n_works,
    credits: (p) => p.credits.length,
    first: (p) => p.years[0] ?? 9999,
    last: (p) => p.years[p.years.length - 1] ?? -1,
  }[f.sort] || ((p) => p.n_works);
  const rows = sortRows(rows0, get, f.dir, (p) => p.name);

  let tableNode = null;
  const frag = document.createDocumentFragment();
  frag.appendChild(
    el(
      "div",
      { class: "page-head" },
      el("h1", { text: "People" }),
      el("p", { text: `${people.length} actors, directors, writers, composers and developers holding ${DATA.meta.counts.credits} credits across the catalogue.` })
    )
  );

  frag.appendChild(
    el(
      "div",
      { class: "filters" },
      chips(
        [
          { value: "all", label: "Everyone", n: people.length },
          { value: "cast", label: "Performers", n: people.filter((p) => p.is_actor).length },
          { value: "crew", label: "Crew only", n: people.filter((p) => !p.is_actor).length },
        ],
        f.kind,
        (v) => applyFilters("people", { ...f, kind: v })
      ),
      filterInput("Filter names…", f.q, (v) => applyFilters("people", { ...f, q: v })),
      resetButton("people", f),
      csvButton("spiderman-people.csv", () => tableNode),
      el("span", { class: "result-count", text: `${rows.length} of ${people.length}` })
    )
  );

  if (rows.length) {
    tableNode = table(
      [
        { key: "name", label: "Name", cell: (p) => el("button", { class: "row-link", text: p.name, onclick: () => go("#/person/" + p.id) }) },
        { key: "roles", label: "Roles", wrap: true, cell: (p) => trunc(p.roles.join(", "), 46) },
        { key: "n_works", label: "Works", num: true, cell: (p) => String(p.n_works) },
        { key: "credits", label: "Credits", num: true, cell: (p) => String(p.credits.length) },
        { key: "first", label: "First", num: true, cell: (p) => (p.years[0] ?? el("span", { class: "muted", text: "—" })) },
        { key: "last", label: "Latest", num: true, cell: (p) => (p.years[p.years.length - 1] ?? el("span", { class: "muted", text: "—" })) },
      ],
      rows,
      { onSort: sortHandler("people", f, ["name", "roles", "first", "last"]), sortKey: f.sort, dir: f.dir, scroll: true }
    );
    frag.appendChild(tableNode);
    tableNode = tableNode.querySelector("table");
  } else {
    frag.appendChild(el("div", { class: "table-wrap" }, el("div", { class: "empty-state", text: "No people match." })));
  }

  return frag;
}

function viewPerson(id) {
  const p = personById.get(Number(id));
  if (!p) return el("div", { class: "empty-state", text: "Unknown person." });
  const frag = document.createDocumentFragment();
  frag.appendChild(backLink("All people", listHash("people")));

  frag.appendChild(
    el(
      "div",
      { class: "detail-head" },
      el("h1", { text: p.name }),
      el(
        "div",
        { class: "meta-line" },
        p.birth ? el("span", { text: p.birth.slice(0, 4) + (p.death ? "–" + p.death.slice(0, 4) : "") }) : null,
        p.place ? el("span", { text: p.place }) : null,
        p.imdb ? el("a", { class: "badge", href: "https://www.imdb.com/name/" + p.imdb + "/", text: "IMDb" }) : null,
        p.wikidata ? el("a", { class: "badge", href: "https://www.wikidata.org/wiki/" + p.wikidata, text: "Wikidata" }) : null
      )
    )
  );

  frag.appendChild(
    el(
      "div",
      { class: "kpis", style: { marginTop: "16px" } },
      statTile("Works", String(p.n_works)),
      statTile("Credits", String(p.credits.length)),
      p.years.length ? statTile("Active", p.years[0] === p.years[p.years.length - 1] ? String(p.years[0]) : p.years[0] + "–" + p.years[p.years.length - 1]) : null
    )
  );

  const rows = p.credits
    .map((c) => ({ ...c, w: workById.get(c.work_id) }))
    .sort((a, b) => (a.w.year ?? 9999) - (b.w.year ?? 9999));

  const charFor = (r) => {
    if (!r.character) return el("span", { class: "muted", text: "—" });
    const match = r.w.characters.find((wc) => wc.as === r.character);
    return match
      ? el("button", { class: "row-link", style: { fontWeight: "400" }, text: r.character, onclick: () => go("#/character/" + match.identity_id) })
      : r.character;
  };

  const careerWorks = [...new Map(rows.map((r) => [r.w.id, r.w])).values()];
  if (careerWorks.length > 1) {
    frag.appendChild(
      el("div", { class: "grid", style: { marginTop: "16px" } },
        yearStrip(careerWorks.map((w) => ({ year: w.year, type: w.type, title: w.title, work: w })), {
          title: "Career in this catalogue",
          sub: "Every catalogued work this person is credited on.",
          onPick: (e) => go("#/work/" + e.work.id),
        }))
    );
  }

  const mates = collaborators(p).slice(0, 14);
  if (mates.length >= 3) {
    frag.appendChild(
      el("div", { class: "grid", style: { marginTop: "14px" } },
        hbarChart({
          title: "Worked with",
          sub: `People credited on more than one of the same works as ${p.name}.`,
          items: mates.map((x) => ({ label: x.person.name, value: x.n, key: x.person.id, sub: x.person.roles.slice(0, 3).join(", ") })),
          onPick: (d) => go("#/person/" + d.key),
          labelWidth: 220,
          valueLabel: "Shared works",
          tableCols: [
            { key: "p", label: "Person", cell: (d) => el("button", { class: "row-link", text: d.label, onclick: () => go("#/person/" + d.key) }) },
            { key: "n", label: "Shared works", num: true, cell: (d) => String(d.value) },
            { key: "r", label: "Roles", wrap: true, cell: (d) => d.sub },
          ],
        }))
    );
  }

  if (p.roles.length > 1) {
    const mix = new Map();
    for (const c of p.credits) mix.set(c.role, (mix.get(c.role) || 0) + 1);
    frag.appendChild(
      section(
        "Roles held",
        p.roles.length,
        el(
          "div",
          { class: "chip-list" },
          [...mix.entries()].sort((a, b) => b[1] - a[1]).map(([r, n]) => el("span", { class: "chip" }, r, el("span", { class: "as", text: "\u00d7" + n })))
        )
      )
    );
  }

  frag.appendChild(
    section(
      "Credits",
      rows.length,
      table(
        [
          { key: "w", label: "Work", cell: (r) => workLink(r.w, false) },
          { key: "y", label: "Year", num: true, cell: (r) => yr(r.w) },
          { key: "t", label: "Medium", cell: (r) => typeBadge(r.w.type) },
          { key: "r", label: "Role", cell: (r) => r.role },
          { key: "c", label: "As", wrap: true, cell: charFor },
        ],
        rows,
        { plain: true }
      )
    )
  );

  return frag;
}

/* ============================================================
   REUSABLE CHART FORMS
   ============================================================ */

/* Horizontal bars for "which of these is biggest" — one hue, or split by medium. */
function hbarChart({ title, sub, note, items, unit = "", onPick, splitByMedium = false, tableCols, labelWidth = 200, maxRows = 16, valueLabel = "Total" }) {
  const shown = items.slice(0, maxRows);
  const max = Math.max(...shown.map((d) => d.value), 1);
  const W = 900;
  const rowH = 24;
  const M = { t: 6, r: 52, b: 24, l: labelWidth };
  const ph = shown.length * rowH;
  const H = ph + M.t + M.b;
  const pw = W - M.l - M.r;
  const x = (v) => (v / max) * pw;
  const step = max <= 5 ? 1 : max <= 12 ? 2 : max <= 30 ? 5 : max <= 120 ? 20 : Math.pow(10, Math.floor(Math.log10(max)));

  const svg = s("svg", { viewBox: `0 0 ${W} ${H}`, width: W, height: H, role: "img", style: { minWidth: "620px" } });
  const g = s("g", { transform: `translate(${M.l},${M.t})` });
  svg.appendChild(g);

  for (let v = 0; v <= max; v += step) {
    g.appendChild(s("line", { x1: x(v), x2: x(v), y1: 0, y2: ph, class: v === 0 ? "baseline" : "gridline" }));
    g.appendChild(s("text", { x: x(v), y: ph + 16, "text-anchor": "middle", class: "tick-num", text: String(v) }));
  }

  const tip = makeTip();
  const order = ["movie", "tv_show", "game"];
  shown.forEach((d, i) => {
    const yTop = i * rowH + 3;
    const barH = Math.min(16, rowH - 8);
    if (splitByMedium && d.parts) {
      let acc = 0;
      order.forEach((k) => {
        const n = d.parts[k] || 0;
        if (!n) return;
        const x0 = x(acc);
        const w = Math.max(1, x(acc + n) - x0 - (acc > 0 ? 2 : 0));
        g.appendChild(s("rect", { x: acc > 0 ? x0 + 2 : x0, y: yTop, width: w, height: barH, rx: 3, fill: TYPE[k].color }));
        acc += n;
      });
    } else {
      g.appendChild(s("rect", { x: 0, y: yTop, width: Math.max(1, x(d.value)), height: barH, rx: 3, fill: "var(--series-1)" }));
    }
    g.appendChild(s("text", { x: x(d.value) + 9, y: yTop + barH - 3, class: "dlabel", text: d.display ?? String(d.value) + unit }));
    const lbl = s("text", {
      x: -10, y: yTop + barH - 3, "text-anchor": "end", class: "tick",
      fill: "var(--text-secondary)", style: onPick ? "cursor:pointer" : null,
      text: d.label.length > 32 ? d.label.slice(0, 31) + "…" : d.label,
    });
    if (onPick) lbl.addEventListener("click", () => onPick(d));
    g.appendChild(lbl);

    const hit = s("rect", {
      x: -M.l, y: i * rowH, width: W, height: rowH, fill: "transparent",
      style: onPick ? "cursor:pointer" : null, tabindex: "0", role: "button",
      "aria-label": `${d.label}: ${d.display ?? d.value + unit}`,
    });
    const show = (ev) => {
      const host = svg.parentNode;
      const r = host.getBoundingClientRect();
      const rows = splitByMedium && d.parts
        ? order.filter((k) => d.parts[k]).map((k) => tipRow(TYPE[k].color, TYPE[k].label, String(d.parts[k])))
        : [];
      tip.show((ev.clientX ?? r.left + 300) - r.left, (ev.clientY ?? r.top + i * rowH) - r.top, [
        tipTitle(d.label),
        ...rows,
        tipRow(rows.length ? null : "var(--series-1)", valueLabel, d.display ?? String(d.value) + unit),
        d.sub ? el("div", { class: "t-note", text: d.sub }) : null,
      ].filter(Boolean), host);
    };
    hit.addEventListener("pointermove", show);
    hit.addEventListener("focus", show);
    hit.addEventListener("pointerleave", () => tip.hide());
    hit.addEventListener("blur", () => tip.hide());
    if (onPick) hit.addEventListener("click", () => onPick(d));
    g.appendChild(hit);
  });

  return chartFigure({
    title,
    sub: sub + (items.length > shown.length ? ` Showing the top ${shown.length} of ${items.length}.` : ""),
    note,
    legend: splitByMedium ? legendBox(order.map((k) => ({ color: TYPE[k].color, label: TYPE[k].label }))) : null,
    plot: { node: svg, tip },
    tableFn: () => table(tableCols, items, { plain: true }),
  });
}

/* A compact per-year presence strip — one mark per year the subject appears in. */
function yearStrip(entries, { title, sub, onPick }) {
  const y0 = DATA.meta.year_min;
  const y1 = DATA.meta.year_max;
  const byYear = new Map();
  for (const e of entries) {
    if (!e.year) continue;
    if (!byYear.has(e.year)) byYear.set(e.year, []);
    byYear.get(e.year).push(e);
  }
  const W = 900;
  const H = 76;
  const M = { t: 8, r: 8, b: 24, l: 8 };
  const pw = W - M.l - M.r;
  const ph = H - M.t - M.b;
  const x = (v) => ((v - y0) / (y1 - y0)) * pw;
  const maxN = Math.max(...[...byYear.values()].map((v) => v.length), 1);

  const svg = s("svg", { viewBox: `0 0 ${W} ${H}`, width: W, height: H, role: "img", style: { minWidth: "520px" } });
  const g = s("g", { transform: `translate(${M.l},${M.t})` });
  svg.appendChild(g);
  g.appendChild(s("line", { x1: 0, x2: pw, y1: ph, y2: ph, class: "baseline" }));
  for (let t = 1970; t <= y1; t += 10) {
    g.appendChild(s("line", { x1: x(t), x2: x(t), y1: 0, y2: ph, class: "gridline" }));
    g.appendChild(s("text", { x: x(t), y: ph + 16, "text-anchor": "middle", class: "tick-num", text: String(t) }));
  }

  const tip = makeTip();
  const barW = Math.max(4, pw / (y1 - y0) - 1);
  const order = ["movie", "tv_show", "game"];
  const unit = ph / maxN;
  for (const [year, list] of byYear) {
    let acc = 0;
    for (const k of order) {
      const n = list.filter((e) => e.type === k).length;
      if (!n) continue;
      const h = Math.max(5, n * unit - (acc > 0 ? 2 : 0));
      g.appendChild(s("rect", { x: x(year) - barW / 2, y: ph - acc * unit - h, width: barW, height: h, rx: 2, fill: TYPE[k].color }));
      acc += n;
    }
  }
  for (const [year, list] of byYear) {
    const hit = s("rect", {
      x: x(year) - 10, y: 0, width: 20, height: ph, fill: "transparent",
      style: "cursor:pointer", tabindex: "0", role: "button",
      "aria-label": `${year}: ${list.map((e) => e.title).join(", ")}`,
    });
    const show = (ev) => {
      const host = svg.parentNode;
      const r = host.getBoundingClientRect();
      tip.show((ev.clientX ?? r.left + 200) - r.left, (ev.clientY ?? r.top) - r.top, [
        tipTitle(String(year)),
        ...list.map((e) => tipRow(TYPE[e.type]?.color, e.title, TYPE[e.type]?.one || "")),
      ], host);
    };
    hit.addEventListener("pointermove", show);
    hit.addEventListener("focus", show);
    hit.addEventListener("pointerleave", () => tip.hide());
    hit.addEventListener("blur", () => tip.hide());
    if (onPick) hit.addEventListener("click", () => onPick(list[0]));
    g.appendChild(hit);
  }

  return chartFigure({
    title,
    sub,
    legend: legendBox(["movie", "tv_show", "game"].filter((k) => entries.some((e) => e.type === k)).map((k) => ({ color: TYPE[k].color, label: TYPE[k].label }))),
    plot: { node: svg, tip },
    tableFn: () =>
      table(
        [
          { key: "y", label: "Year", num: true, cell: (e) => (e.year ?? "—") },
          { key: "t", label: "Work", cell: (e) => (e.work ? workLink(e.work, false) : e.title) },
          { key: "m", label: "Medium", cell: (e) => (e.type ? typeBadge(e.type) : "—") },
        ],
        [...entries].sort((a, b) => (a.year ?? 9999) - (b.year ?? 9999)),
        { plain: true }
      ),
  });
}

/* ============================================================
   FRANCHISES · STUDIOS · PLATFORMS
   ============================================================ */

function dimensionListView({ view, title, blurb, index, columns, chart, unit }) {
  return (_id, query) => {
    const f = readFilters(DEFAULTS[view], query);
    const all = [...index.values()];
    const rows0 = f.q ? all.filter((g) => g.name.toLowerCase().includes(f.q.toLowerCase())) : all;
    const get = columns.find((c) => c.key === f.sort)?.value || ((g) => g.n_works);
    const rows = sortRows(rows0, get, f.dir, (g) => g.name);

    let tableNode = null;
    const frag = document.createDocumentFragment();
    frag.appendChild(el("div", { class: "page-head" }, el("h1", { text: title }), el("p", { text: blurb })));
    frag.appendChild(
      el(
        "div",
        { class: "filters" },
        filterInput(`Filter ${title.toLowerCase()}…`, f.q, (v) => applyFilters(view, { ...f, q: v })),
        resetButton(view, f),
        csvButton(`spiderman-${view}.csv`, () => tableNode),
        el("span", { class: "result-count", text: `${rows.length} of ${all.length}` })
      )
    );
    if (chart) frag.appendChild(el("div", { class: "grid", style: { marginBottom: "14px" } }, chart(all)));

    if (rows.length) {
      tableNode = table(
        columns.map((c) => ({ key: c.key, label: c.label, num: c.num, wrap: c.wrap, cell: c.cell })),
        rows,
        { onSort: sortHandler(view, f, columns.filter((c) => c.asc).map((c) => c.key)), sortKey: f.sort, dir: f.dir, scroll: true }
      );
      frag.appendChild(tableNode);
      tableNode = tableNode.querySelector("table");
    } else {
      frag.appendChild(el("div", { class: "table-wrap" }, el("div", { class: "empty-state", text: "Nothing matches." })));
    }
    return frag;
  };
}

const spanText = (g) => (g.first_year == null ? "—" : g.first_year === g.last_year ? String(g.first_year) : `${g.first_year}–${g.last_year}`);

const viewFranchises = dimensionListView({
  view: "franchises",
  title: "Franchises",
  blurb: "The continuities the catalogue is organised into — a franchise groups works that share a universe, a cast or a production lineage.",
  index: franchiseIndex,
  chart: (all) =>
    hbarChart({
      title: "Works per franchise",
      sub: "Split by medium.",
      items: [...all].sort((a, b) => b.n_works - a.n_works).map((g) => ({ label: g.name, value: g.n_works, parts: g.by_type, key: g.name })),
      splitByMedium: true,
      onPick: (d) => go("#/franchise/" + encodeURIComponent(d.key)),
      tableCols: [
        { key: "n", label: "Franchise", cell: (d) => franchiseLink(d.label) },
        { key: "m", label: "Movies", num: true, cell: (d) => String(d.parts.movie) },
        { key: "t", label: "TV series", num: true, cell: (d) => String(d.parts.tv_show) },
        { key: "g", label: "Games", num: true, cell: (d) => String(d.parts.game) },
        { key: "v", label: "Total", num: true, cell: (d) => String(d.value) },
      ],
    }),
  columns: [
    { key: "name", label: "Franchise", asc: true, value: (g) => g.name.toLowerCase(), cell: (g) => el("button", { class: "row-link", text: g.name, onclick: () => go("#/franchise/" + encodeURIComponent(g.name)) }) },
    { key: "desc", label: "Description", wrap: true, asc: true, value: (g) => (g.description || "~").toLowerCase(), cell: (g) => g.description || el("span", { class: "muted", text: "—" }) },
    { key: "n_works", label: "Works", num: true, value: (g) => g.n_works, cell: (g) => String(g.n_works) },
    { key: "span", label: "Span", num: true, asc: true, value: (g) => g.first_year ?? 9999, cell: (g) => spanText(g) },
    { key: "gross", label: "Gross", num: true, value: (g) => g.gross ?? -1, cell: (g) => (g.gross ? money(g.gross) : el("span", { class: "muted", text: "—" })) },
    { key: "score", label: "Score", num: true, value: (g) => g.avg_pct ?? -1, cell: (g) => (g.avg_pct == null ? el("span", { class: "muted", text: "—" }) : pct(g.avg_pct)) },
  ],
});

const viewStudios = dimensionListView({
  view: "studios",
  title: "Studios",
  blurb: "Every production company, distributor and network credited on a work, with the works they were involved in.",
  index: studioIndex,
  chart: (all) =>
    hbarChart({
      title: "Busiest studios",
      sub: "Works credited to each company, split by medium.",
      items: [...all].sort((a, b) => b.n_works - a.n_works).map((g) => ({ label: g.name, value: g.n_works, parts: g.by_type, key: g.name })),
      splitByMedium: true,
      onPick: (d) => go("#/studio/" + encodeURIComponent(d.key)),
      tableCols: [
        { key: "n", label: "Studio", cell: (d) => el("button", { class: "row-link", text: d.label, onclick: () => go("#/studio/" + encodeURIComponent(d.key)) }) },
        { key: "v", label: "Works", num: true, cell: (d) => String(d.value) },
      ],
    }),
  columns: [
    { key: "name", label: "Studio", asc: true, value: (g) => g.name.toLowerCase(), cell: (g) => el("button", { class: "row-link", text: g.name, onclick: () => go("#/studio/" + encodeURIComponent(g.name)) }) },
    { key: "roles", label: "Credited as", asc: true, value: (g) => [...g.roles].sort().join(", "), cell: (g) => [...g.roles].sort().join(", ") },
    { key: "n_works", label: "Works", num: true, value: (g) => g.n_works, cell: (g) => String(g.n_works) },
    { key: "span", label: "Span", num: true, asc: true, value: (g) => g.first_year ?? 9999, cell: (g) => spanText(g) },
    { key: "gross", label: "Gross", num: true, value: (g) => g.gross ?? -1, cell: (g) => (g.gross ? money(g.gross) : el("span", { class: "muted", text: "—" })) },
    { key: "score", label: "Score", num: true, value: (g) => g.avg_pct ?? -1, cell: (g) => (g.avg_pct == null ? el("span", { class: "muted", text: "—" }) : pct(g.avg_pct)) },
  ],
});

const viewPlatforms = dimensionListView({
  view: "platforms",
  title: "Platforms",
  blurb: "Every console, handheld and computer a Spider-Man game shipped on, with the per-platform release records behind them.",
  index: platformIndex,
  chart: (all) =>
    hbarChart({
      title: "Games per platform",
      sub: "Distinct games catalogued on each platform.",
      items: [...all].sort((a, b) => b.n_works - a.n_works).map((g) => ({ label: g.name, value: g.n_works, key: g.name, sub: g.avg_metacritic ? `mean Metacritic ${Math.round(g.avg_metacritic)}` : null })),
      onPick: (d) => go("#/platform/" + encodeURIComponent(d.key)),
      tableCols: [
        { key: "n", label: "Platform", cell: (d) => el("button", { class: "row-link", text: d.label, onclick: () => go("#/platform/" + encodeURIComponent(d.key)) }) },
        { key: "v", label: "Games", num: true, cell: (d) => String(d.value) },
      ],
    }),
  columns: [
    { key: "name", label: "Platform", asc: true, value: (g) => g.name.toLowerCase(), cell: (g) => el("button", { class: "row-link", text: g.name, onclick: () => go("#/platform/" + encodeURIComponent(g.name)) }) },
    { key: "n_works", label: "Games", num: true, value: (g) => g.n_works, cell: (g) => String(g.n_works) },
    { key: "releases", label: "Release rows", num: true, value: (g) => g.releases.length, cell: (g) => String(g.releases.length) },
    { key: "span", label: "Span", num: true, asc: true, value: (g) => g.first_year ?? 9999, cell: (g) => spanText(g) },
    { key: "mc", label: "Mean Metacritic", num: true, value: (g) => g.avg_metacritic ?? -1, cell: (g) => (g.avg_metacritic == null ? el("span", { class: "muted", text: "—" }) : String(Math.round(g.avg_metacritic))) },
  ],
});

function dimensionHead(group, kind, backView, backLabel, extra) {
  return [
    backLink(backLabel, listHash(backView)),
    el(
      "div",
      { class: "detail-head" },
      el("h1", { text: group.name }),
      el(
        "div",
        { class: "meta-line" },
        el("span", { class: "badge", text: kind }),
        el("span", { text: spanText(group) }),
        extra
      ),
      group.description ? el("div", { class: "note", style: { marginTop: "10px" }, text: group.description }) : null
    ),
  ];
}

function worksOfTable(list, { showFranchise = true } = {}) {
  return table(
    [
      { key: "t", label: "Title", cell: (w) => workLink(w, false) },
      { key: "y", label: "Year", num: true, cell: (w) => yr(w) },
      { key: "m", label: "Medium", cell: (w) => typeBadge(w.type) },
      showFranchise && { key: "f", label: "Franchise", cell: (w) => (w.franchise ? franchiseLink(w.franchise, 26) : el("span", { class: "muted", text: "—" })) },
      { key: "s", label: "Score", num: true, cell: (w) => (w.avg_pct == null ? el("span", { class: "muted", text: "—" }) : pct(w.avg_pct)) },
      { key: "g", label: "Gross", num: true, cell: (w) => (w.gross == null ? el("span", { class: "muted", text: "—" }) : money(w.gross)) },
      { key: "c", label: "Chars", num: true, cell: (w) => String(w.characters.length) },
    ].filter(Boolean),
    [...list].sort((a, b) => (a.year ?? 9999) - (b.year ?? 9999)),
    { plain: true }
  );
}

function dimensionTiles(g, extras = []) {
  const kinds = ["movie", "tv_show", "game"].filter((k) => g.by_type[k]);
  const tiles = [statTile("Works", String(g.n_works))];
  // Only break down by medium when there is actually more than one — otherwise the
  // breakdown tile just repeats the total.
  if (kinds.length > 1) for (const k of kinds) tiles.push(statTile(TYPE[k].label, String(g.by_type[k])));
  if (g.gross) tiles.push(statTile("Combined gross", money(g.gross)));
  if (g.avg_pct != null) tiles.push(statTile("Mean score", pct(g.avg_pct) + " / 100"));
  return el("div", { class: "kpis", style: { marginTop: "16px" } }, tiles, extras);
}

function viewFranchise(name) {
  const g = franchiseIndex.get(name);
  if (!g) return el("div", { class: "empty-state", text: "Unknown franchise." });
  const frag = document.createDocumentFragment();
  frag.append(...dimensionHead(g, "Franchise", "franchises", "All franchises"));
  frag.appendChild(dimensionTiles(g));
  frag.appendChild(
    el("div", { class: "grid", style: { marginTop: "16px" } },
      yearStrip(g.works.map((w) => ({ year: w.year, type: w.type, title: w.title, work: w })), {
        title: "Release history",
        sub: "Every work in this franchise on the catalogue's full 1967–2026 span.",
        onPick: (e) => go("#/work/" + e.work.id),
      }))
  );
  frag.appendChild(section("Works", g.n_works, worksOfTable(g.works, { showFranchise: false })));

  const inside = new Set(g.works.map((w) => w.id));
  const links = [];
  const seenPairs = new Set();
  const rank = (w) => (w.year ?? 9999) * 1000 + w.id;
  for (const w of g.works) {
    for (const r of w.relations) {
      if (!inside.has(r.work_id)) continue;
      const other = workById.get(r.work_id);
      // Each relation is stored from both ends; show it once, from the earlier work.
      if (rank(w) > rank(other)) continue;
      const key = [Math.min(w.id, other.id), Math.max(w.id, other.id)].join("-") + "|" + r.label;
      if (seenPairs.has(key)) continue;
      seenPairs.add(key);
      links.push({ from: w, label: r.label, to: other });
    }
  }
  if (links.length) {
    frag.appendChild(
      section(
        "How these works connect",
        links.length,
        table(
          [
            { key: "a", label: "Work", cell: (r) => workLink(r.from, false) },
            { key: "l", label: "Relation", cell: (r) => el("span", { class: "muted", text: r.label }) },
            { key: "b", label: "Other work", cell: (r) => workLink(r.to, false) },
          ],
          links.sort((a, b) => (a.from.year ?? 0) - (b.from.year ?? 0) || a.label.localeCompare(b.label)),
          { plain: true }
        )
      )
    );
  }
  return frag;
}

function viewStudio(name) {
  const g = studioIndex.get(name);
  if (!g) return el("div", { class: "empty-state", text: "Unknown studio." });
  const frag = document.createDocumentFragment();
  frag.append(...dimensionHead(g, "Studio", "studios", "All studios", el("span", { text: [...g.roles].sort().join(" · ") })));
  frag.appendChild(dimensionTiles(g));
  frag.appendChild(section("Works", g.n_works, worksOfTable(g.works)));

  const partners = new Map();
  for (const w of g.works) {
    for (const st of w.studios) {
      if (st.name === g.name) continue;
      partners.set(st.name, (partners.get(st.name) || 0) + 1);
    }
  }
  if (partners.size) {
    frag.appendChild(
      section(
        "Frequent co-credits",
        partners.size,
        el(
          "div",
          { class: "chip-list" },
          [...partners.entries()]
            .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
            .slice(0, 24)
            .map(([n, c]) => dimChip(n, "#/studio/" + encodeURIComponent(n), `${c} work${c === 1 ? "" : "s"}`))
        )
      )
    );
  }
  return frag;
}

function viewPlatform(name) {
  const g = platformIndex.get(name);
  if (!g) return el("div", { class: "empty-state", text: "Unknown platform." });
  const frag = document.createDocumentFragment();
  frag.append(...dimensionHead(g, "Platform", "platforms", "All platforms"));
  const extras = [];
  if (g.avg_metacritic != null) extras.push(statTile("Mean Metacritic", String(Math.round(g.avg_metacritic))));
  if (g.releases.length) extras.push(statTile("Release rows", String(g.releases.length)));
  frag.appendChild(dimensionTiles(g, extras));

  const scored = g.releases.filter((r) => r.metacritic != null);
  if (scored.length >= 3) {
    frag.appendChild(
      el("div", { class: "grid", style: { marginTop: "16px" } },
        hbarChart({
          title: "Metacritic scores on this platform",
          sub: "The score recorded for each release row, highest first.",
          items: scored
            .sort((a, b) => b.metacritic - a.metacritic)
            .map((r) => ({ label: r.work.title, value: r.metacritic, key: r.work.id, sub: r.date || null })),
          onPick: (d) => go("#/work/" + d.key),
          labelWidth: 240,
          tableCols: [
            { key: "t", label: "Game", cell: (d) => el("button", { class: "row-link", text: d.label, onclick: () => go("#/work/" + d.key) }) },
            { key: "v", label: "Metacritic", num: true, cell: (d) => String(d.value) },
          ],
        }))
    );
  }

  if (g.releases.length) {
    frag.appendChild(
      section(
        "Releases",
        g.releases.length,
        table(
          [
            { key: "t", label: "Game", cell: (r) => workLink(r.work, false) },
            { key: "d", label: "Date", cell: (r) => r.date || el("span", { class: "muted", text: "—" }) },
            { key: "p", label: "Publisher", wrap: true, cell: (r) => r.publisher || el("span", { class: "muted", text: "—" }) },
            { key: "v", label: "Developer", wrap: true, cell: (r) => r.developer || el("span", { class: "muted", text: "—" }) },
            { key: "m", label: "Metacritic", num: true, cell: (r) => (r.metacritic == null ? el("span", { class: "muted", text: "—" }) : String(r.metacritic)) },
            { key: "e", label: "ESRB", cell: (r) => r.esrb || el("span", { class: "muted", text: "—" }) },
          ],
          [...g.releases].sort((a, b) => String(a.date || "9").localeCompare(String(b.date || "9"))),
          { plain: true }
        )
      )
    );
  }
  const gamesOnly = g.works.filter((w) => !g.releases.some((r) => r.work === w));
  if (gamesOnly.length) {
    frag.appendChild(section("Also listed on this platform", gamesOnly.length, worksOfTable(gamesOnly)));
  }
  return frag;
}

/* ============================================================
   ANALYSIS
   ============================================================ */

/* Comic publication year against screen year. The 45° rule is "adapted the same year",
   so vertical distance above it is how long the story waited. */
function adaptationLagChart() {
  const pts = adaptations;
  const lo = 1960;
  const hi = 2030;
  const W = 620;
  const H = 420;
  const M = { t: 12, r: 16, b: 40, l: 44 };
  const pw = W - M.l - M.r;
  const ph = H - M.t - M.b;
  const x = (v) => ((v - lo) / (hi - lo)) * pw;
  const y = (v) => ph - ((v - lo) / (hi - lo)) * ph;

  const svg = s("svg", { viewBox: `0 0 ${W} ${H}`, width: W, height: H, role: "img", style: { minWidth: "380px" } });
  const g = s("g", { transform: `translate(${M.l},${M.t})` });
  svg.appendChild(g);

  for (let t = 1960; t <= 2020; t += 20) {
    g.appendChild(s("line", { x1: x(t), x2: x(t), y1: 0, y2: ph, class: "gridline" }));
    g.appendChild(s("line", { x1: 0, x2: pw, y1: y(t), y2: y(t), class: "gridline" }));
    g.appendChild(s("text", { x: x(t), y: ph + 17, "text-anchor": "middle", class: "tick-num", text: String(t) }));
    g.appendChild(s("text", { x: -8, y: y(t) + 4, "text-anchor": "end", class: "tick-num", text: String(t) }));
  }
  g.appendChild(s("line", { x1: 0, x2: pw, y1: ph, y2: ph, class: "baseline" }));
  g.appendChild(s("line", { x1: 0, x2: 0, y1: 0, y2: ph, class: "baseline" }));
  g.appendChild(s("line", { x1: x(lo), x2: x(hi), y1: y(lo), y2: y(hi), stroke: "var(--axis)", "stroke-width": 1 }));
  g.appendChild(s("text", { x: x(2004), y: y(1998), class: "tick", fill: "var(--text-muted)", transform: `rotate(-45 ${x(2004)} ${y(1998)})`, text: "adapted the same year" }));
  g.appendChild(s("text", { x: pw / 2, y: ph + 34, "text-anchor": "middle", class: "tick", text: "Comic published" }));

  const tip = makeTip();
  for (const p of pts) g.appendChild(s("circle", { cx: x(p.src.year), cy: y(p.work.year), r: 4.5, fill: TYPE[p.work.type].color, stroke: "var(--surface-1)", "stroke-width": 2 }));
  for (const p of pts) {
    const hit = s("circle", {
      cx: x(p.src.year), cy: y(p.work.year), r: 12, fill: "transparent", style: "cursor:pointer",
      tabindex: "0", role: "button",
      "aria-label": `${p.src.comic} (${p.src.year}) adapted in ${p.work.title}, ${p.work.year}, after ${p.lag} years`,
    });
    const show = (ev) => {
      const host = svg.parentNode;
      const r = host.getBoundingClientRect();
      tip.show((ev.clientX ?? r.left + 200) - r.left, (ev.clientY ?? r.top + 100) - r.top, [
        tipTitle(p.work.title + " (" + yr(p.work) + ")"),
        tipRow(TYPE[p.work.type].color, p.src.comic, String(p.src.year)),
        el("div", { class: "t-note", text: p.lag === 0 ? "adapted the same year" : p.lag > 0 ? `${p.lag} years after publication` : `${-p.lag} years before the comic` }),
      ], host);
    };
    hit.addEventListener("pointermove", show);
    hit.addEventListener("focus", show);
    hit.addEventListener("pointerleave", () => tip.hide());
    hit.addEventListener("blur", () => tip.hide());
    hit.addEventListener("click", () => go("#/work/" + p.work.id));
    g.appendChild(hit);
  }

  const lags = pts.map((p) => p.lag).sort((a, b) => a - b);
  const median = lags[Math.floor(lags.length / 2)];
  return chartFigure({
    title: "How long a comic waits to be adapted",
    sub: `${pts.length} source records that carry both a comic year and a release year. Vertical axis is the year the adaptation shipped.`,
    note: `Median wait: ${median} years. Points below the line are adaptations of stories published after the work came out — usually a later comic revisiting the same material.`,
    legend: legendBox(["movie", "tv_show", "game"].map((k) => ({ color: TYPE[k].color, label: TYPE[k].label }))),
    plot: { node: svg, tip },
    tableFn: () =>
      table(
        [
          { key: "c", label: "Comic", wrap: true, cell: (p) => p.src.comic },
          { key: "cy", label: "Published", num: true, cell: (p) => String(p.src.year) },
          { key: "w", label: "Adapted in", cell: (p) => workLink(p.work, false) },
          { key: "wy", label: "Released", num: true, cell: (p) => String(p.work.year) },
          { key: "l", label: "Wait (yrs)", num: true, cell: (p) => String(p.lag) },
        ],
        [...pts].sort((a, b) => b.lag - a.lag),
        { plain: true }
      ),
  });
}

/* Won vs nominated by awarding body — two shades of one hue, an ordinal pair. */
function awardsChart() {
  const bodies = [...awardBodies.values()].sort((a, b) => b.won + b.nominated - (a.won + a.nominated));
  const max = Math.max(...bodies.map((b) => b.won + b.nominated));
  const W = 540;
  const rowH = 30;
  const M = { t: 6, r: 34, b: 26, l: 190 };
  const ph = bodies.length * rowH;
  const H = ph + M.t + M.b;
  const pw = W - M.l - M.r;
  const x = (v) => (v / max) * pw;

  const svg = s("svg", { viewBox: `0 0 ${W} ${H}`, width: W, height: H, role: "img", style: { minWidth: "380px" } });
  const g = s("g", { transform: `translate(${M.l},${M.t})` });
  svg.appendChild(g);
  for (let v = 0; v <= max; v += 2) {
    g.appendChild(s("line", { x1: x(v), x2: x(v), y1: 0, y2: ph, class: v === 0 ? "baseline" : "gridline" }));
    g.appendChild(s("text", { x: x(v), y: ph + 17, "text-anchor": "middle", class: "tick-num", text: String(v) }));
  }

  const tip = makeTip();
  bodies.forEach((b, i) => {
    const yTop = i * rowH + 4;
    const barH = 16;
    if (b.won) g.appendChild(s("rect", { x: 0, y: yTop, width: Math.max(1, x(b.won)), height: barH, rx: 3, fill: "var(--series-1)" }));
    if (b.nominated) g.appendChild(s("rect", { x: x(b.won) + 2, y: yTop, width: Math.max(1, x(b.nominated) - 2), height: barH, rx: 3, fill: "var(--series-1-soft)" }));
    g.appendChild(s("text", { x: x(b.won + b.nominated) + 9, y: yTop + barH - 3, class: "dlabel", text: String(b.won + b.nominated) }));
    g.appendChild(s("text", { x: -10, y: yTop + barH - 3, "text-anchor": "end", class: "tick", fill: "var(--text-secondary)", text: b.name.length > 26 ? b.name.slice(0, 25) + "…" : b.name }));
    const hit = s("rect", { x: -M.l, y: i * rowH, width: W, height: rowH, fill: "transparent", tabindex: "0", role: "button", "aria-label": `${b.name}: ${b.won} won, ${b.nominated} nominated` });
    const show = (ev) => {
      const host = svg.parentNode;
      const r = host.getBoundingClientRect();
      tip.show((ev.clientX ?? r.left + 300) - r.left, (ev.clientY ?? r.top + i * rowH) - r.top, [
        tipTitle(b.name),
        tipRow("var(--series-1)", "Won", String(b.won)),
        tipRow("var(--series-1-soft)", "Nominated", String(b.nominated)),
      ], host);
    };
    hit.addEventListener("pointermove", show);
    hit.addEventListener("focus", show);
    hit.addEventListener("pointerleave", () => tip.hide());
    hit.addEventListener("blur", () => tip.hide());
    g.appendChild(hit);
  });

  return chartFigure({
    title: "Awards by body",
    sub: `${allAwards.length} award records across ${bodies.length} awarding bodies.`,
    legend: legendBox([
      { color: "var(--series-1)", label: "Won" },
      { color: "var(--series-1-soft)", label: "Nominated, did not win" },
    ]),
    plot: { node: svg, tip },
    tableFn: () =>
      table(
        [
          { key: "b", label: "Body", cell: (b) => b.name },
          { key: "w", label: "Won", num: true, cell: (b) => String(b.won) },
          { key: "n", label: "Nominated", num: true, cell: (b) => String(b.nominated) },
        ],
        bodies,
        { plain: true }
      ),
  });
}

function viewAnalysis() {
  const frag = document.createDocumentFragment();
  frag.appendChild(
    el(
      "div",
      { class: "page-head" },
      el("h1", { text: "Analysis" }),
      el("p", { text: "Cuts of the data that no single table holds: how outlets differ, how long comics wait to be adapted, which storylines get reused, and what the catalogue has won." })
    )
  );

  const pubs = [...publicationIndex.values()].filter((p) => p.n >= 4).sort((a, b) => b.avg_pct - a.avg_pct);
  frag.appendChild(
    el("div", { class: "grid" },
      hbarChart({
        title: "How the outlets differ",
        sub: "Mean normalized score per publication, for outlets with at least four scores on record.",
        note: "Every scale — 10-point, 5-star, percentage — is mapped onto 0–100 first, so these are comparable. An outlet's mean also reflects which works it happened to review.",
        items: pubs.map((p) => ({ label: p.name, value: Math.round(p.avg_pct), display: Math.round(p.avg_pct) + " / 100", key: p.name, sub: `${p.n} scores, range ${Math.round(p.lo)}–${Math.round(p.hi)}` })),
        labelWidth: 190,
        maxRows: 20,
        tableCols: [
          { key: "p", label: "Publication", cell: (d) => d.label },
          { key: "a", label: "Mean score", num: true, cell: (d) => String(d.value) },
          { key: "s", label: "Spread", cell: (d) => d.sub },
        ],
      }))
  );

  frag.appendChild(
    el("div", { class: "grid cols-2", style: { marginTop: "14px" } }, adaptationLagChart(), awardsChart())
  );

  const comics = [...comicIndex.values()].filter((c) => c.n > 1).sort((a, b) => b.n - a.n);
  frag.appendChild(
    el("div", { class: "grid", style: { marginTop: "14px" } },
      hbarChart({
        title: "Storylines the screen keeps going back to",
        sub: "Comic titles cited as a source by more than one work.",
        items: comics.map((c) => ({
          label: c.title,
          value: c.n,
          key: c.title,
          sub: [c.writer, c.year].filter(Boolean).join(" · ") || null,
        })),
        labelWidth: 260,
        maxRows: 18,
        tableCols: [
          { key: "c", label: "Comic", wrap: true, cell: (d) => d.label },
          { key: "n", label: "Adapted by", num: true, cell: (d) => String(d.value) },
          { key: "w", label: "Credited to", wrap: true, cell: (d) => d.sub || "—" },
        ],
      }))
  );

  frag.appendChild(
    section(
      "Every award on record",
      allAwards.length,
      table(
        [
          { key: "w", label: "Work", cell: (a) => workLink(a.work, false) },
          { key: "b", label: "Body", cell: (a) => a.body },
          { key: "y", label: "Year", num: true, cell: (a) => (a.year == null ? "—" : String(a.year)) },
          { key: "c", label: "Category", wrap: true, cell: (a) => a.category },
          { key: "r", label: "Result", cell: (a) => (a.result === "won" ? el("strong", { text: "Won" }) : el("span", { class: "muted", text: "Nominated" })) },
        ],
        [...allAwards].sort((a, b) => (a.year ?? 0) - (b.year ?? 0)),
        { plain: true }
      )
    )
  );

  frag.appendChild(
    section(
      "Every comic source",
      [...comicIndex.values()].length,
      table(
        [
          { key: "c", label: "Comic", wrap: true, cell: (c) => c.title },
          { key: "y", label: "Published", num: true, cell: (c) => (c.year ?? el("span", { class: "muted", text: "—" })) },
          { key: "w", label: "Credited to", wrap: true, cell: (c) => c.writer || el("span", { class: "muted", text: "—" }) },
          { key: "n", label: "Cited by", num: true, cell: (c) => String(c.n) },
          {
            key: "u",
            label: "Works",
            wrap: true,
            cell: (c) =>
              el("span", { class: "chip-list" }, c.uses.map((u) => el("button", { class: "chip", text: u.work.title, onclick: () => go("#/work/" + u.work.id) }))),
          },
        ],
        [...comicIndex.values()].sort((a, b) => b.n - a.n || (a.year ?? 9999) - (b.year ?? 9999)),
        { plain: true }
      )
    )
  );

  return frag;
}

/* ============================================================
   ABOUT
   ============================================================ */

function viewAbout() {
  const linkTo = (label, hash) => el("button", { class: "linkish", text: label, onclick: () => go(hash) });
  const p = (...kids) => el("p", { style: { color: "var(--text-secondary)", maxWidth: "78ch" } }, kids);

  const linkCounts = { movie: 0, tv_show: 0, game: 0 };
  const workCounts = { movie: 0, tv_show: 0, game: 0 };
  for (const w of works) {
    workCounts[w.type]++;
    linkCounts[w.type] += w.characters.length;
  }
  const totalLinks = Object.values(linkCounts).reduce((a, b) => a + b, 0);

  const frag = document.createDocumentFragment();
  frag.appendChild(
    el(
      "div",
      { class: "page-head" },
      el("h1", { text: "About this data" }),
      el("p", { text: "Where the numbers come from, and the four places where a naive count gives a confident wrong answer." })
    )
  );

  frag.appendChild(
    section(
      "Characters are identities, not credit strings",
      null,
      p(
        "The source research spells the same character differently in every file — ",
        el("code", { text: "Spider-Man / Peter Parker" }),
        " in the games data, ",
        el("code", { text: "Peter Parker / Spider-Man" }),
        " in the films, plain ",
        el("code", { text: "Peter Parker" }),
        " on television. 416 credit strings name ",
        String(characters.length),
        " distinct characters; 61 of them have more than one spelling. Every character page here lists the spellings it absorbed."
      ),
      p("Where spellings disagreed on alignment, the majority wins and the per-row values stay in the underlying table.")
    )
  );

  frag.appendChild(
    section(
      "Appearance counts are not comparable across media",
      null,
      el("div", { style: { maxWidth: "820px" } }, table(
        [
          { key: "m", label: "Medium", cell: (r) => typeBadge(r.type) },
          { key: "w", label: "Works", num: true, cell: (r) => String(r.works) },
          { key: "l", label: "Character links", num: true, cell: (r) => String(r.links) },
          { key: "p", label: "Per work", num: true, cell: (r) => (r.links / r.works).toFixed(1) },
          { key: "s", label: "Share of links", num: true, cell: (r) => Math.round((r.links / totalLinks) * 100) + "%" },
        ],
        ["game", "movie", "tv_show"].map((t) => ({ type: t, works: workCounts[t], links: linkCounts[t] })),
        { plain: true }
      )),
      p(
        "A television series counts as one work no matter how many episodes it ran — ",
        linkTo("Ultimate Spider-Man", "#/work/" + (works.find((w) => w.title === "Ultimate Spider-Man")?.id ?? 0)),
        "'s 104 episodes contribute the same single appearance as one game. Games also hold most of the character links simply because their rosters were catalogued more deeply. Compare within a medium."
      )
    )
  );

  frag.appendChild(
    section(
      "Box office is lifetime, not opening week",
      null,
      p(
        "Two different measurements share one table in the source database: 16 of the 17 films carry a single full-run total filed under week 1, and only ",
        linkTo("Venom: The Last Dance", "#/work/" + (works.find((w) => w.title === "Venom: The Last Dance")?.id ?? 0)),
        " has a genuine week-by-week series. Every figure shown in this explorer is the lifetime total; the weekly rows are not mixed in."
      )
    )
  );

  frag.appendChild(
    section(
      "Review scores are normalized",
      null,
      p(
        "Sources use 10-point scales, 5-star scales, letter grades and percentages. Each score is mapped onto 0–100 before averaging, so a work's mean is comparable to another's. The raw score and its original maximum are shown alongside on every work page."
      )
    )
  );

  frag.appendChild(
    section(
      "Related works read in one direction",
      null,
      p(
        "Every connection is shown from the perspective of the work you are looking at — “Sequel to”, “Followed by”, “Tie-in game of” — rather than as the raw directed edge, which reads backwards half the time."
      )
    )
  );

  frag.appendChild(
    section(
      "What this page derives, and what it only reads",
      null,
      p(
        "Works, characters, people, episodes, releases and awards are read straight out of the database. ",
        linkTo("Franchises", "#/franchises"),
        ", ",
        linkTo("studios", "#/studios"),
        " and ",
        linkTo("platforms", "#/platforms"),
        " are not tables you can browse in the source — they are grouped here from the join tables, so a studio page is every work that credits that name. Co-appearances, collaborators, adaptation lag and the outlet means on the ",
        linkTo("Analysis", "#/analysis"),
        " page are all computed in the browser from those same rows; none of them are stored figures."
      ),
      p(
        "Grouping is by name, not by an identifier: two studios spelled differently in the source stay two rows here, exactly as they are in the database."
      )
    )
  );

  frag.appendChild(
    section(
      "Provenance",
      null,
      p(
        "Wikipedia, Box Office Mojo, Rotten Tomatoes, Metacritic, IMDb and TMDB, assembled offline into a 24-table SQLite database. This page reads a single JSON file generated from that database by ",
        el("code", { text: "explorer/build_explorer_data.py" }),
        " — no server, no network calls. Data is licensed CC BY 4.0; the build code is MIT."
      )
    )
  );

  return frag;
}

/* ============================================================
   SEARCH
   ============================================================ */

const searchIndex = [
  ...works.map((w) => ({ kind: "Works", label: w.title, sub: `${yr(w)} · ${TYPE[w.type].one}`, hash: "#/work/" + w.id, key: w.title.toLowerCase(), rank: 0 })),
  ...characters.map((c) => ({ kind: "Characters", label: c.name, sub: `${c.n_works} work${c.n_works === 1 ? "" : "s"}`, hash: "#/character/" + c.id, key: (c.name + " " + c.variants.join(" ")).toLowerCase(), rank: 1 })),
  ...people.map((p) => ({ kind: "People", label: p.name, sub: `${p.credits.length} credit${p.credits.length === 1 ? "" : "s"}`, hash: "#/person/" + p.id, key: p.name.toLowerCase(), rank: 2 })),
  ...[...franchiseIndex.values()].map((g) => ({ kind: "Franchises", label: g.name, sub: `${g.n_works} work${g.n_works === 1 ? "" : "s"}`, hash: "#/franchise/" + encodeURIComponent(g.name), key: g.name.toLowerCase(), rank: 3 })),
  ...[...studioIndex.values()].map((g) => ({ kind: "Studios", label: g.name, sub: `${g.n_works} work${g.n_works === 1 ? "" : "s"}`, hash: "#/studio/" + encodeURIComponent(g.name), key: g.name.toLowerCase(), rank: 4 })),
  ...[...platformIndex.values()].map((g) => ({ kind: "Platforms", label: g.name, sub: `${g.n_works} game${g.n_works === 1 ? "" : "s"}`, hash: "#/platform/" + encodeURIComponent(g.name), key: g.name.toLowerCase(), rank: 5 })),
];

function setupSearch() {
  const input = document.getElementById("search");
  const box = document.getElementById("results");
  let items = [];
  let cursor = -1;

  const close = () => {
    box.classList.remove("open");
    box.replaceChildren();
    items = [];
    cursor = -1;
  };

  const run = () => {
    const q = input.value.trim().toLowerCase();
    if (q.length < 2) return close();
    const hits = searchIndex
      .filter((it) => it.key.includes(q))
      .sort((a, b) => {
        const sa = a.key.startsWith(q) ? 0 : 1;
        const sb = b.key.startsWith(q) ? 0 : 1;
        return sa - sb || a.rank - b.rank || a.label.length - b.label.length;
      })
      .slice(0, 24);
    box.replaceChildren();
    items = [];
    if (!hits.length) {
      box.appendChild(el("div", { class: "empty", text: "Nothing matches “" + input.value.trim() + "”." }));
      box.classList.add("open");
      return;
    }
    let lastKind = null;
    for (const hit of hits) {
      if (hit.kind !== lastKind) {
        box.appendChild(el("div", { class: "group", text: hit.kind }));
        lastKind = hit.kind;
      }
      const b = el(
        "button",
        {
          onclick: () => {
            input.value = "";
            close();
            input.blur();
            go(hit.hash);
          },
        },
        el("span", { text: hit.label }),
        el("span", { class: "sub", text: hit.sub })
      );
      items.push(b);
      box.appendChild(b);
    }
    cursor = -1;
    box.classList.add("open");
  };

  input.addEventListener("input", run);
  input.addEventListener("focus", () => input.value.trim().length >= 2 && run());
  input.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      input.value = "";
      close();
      input.blur();
    } else if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      if (!items.length) return;
      e.preventDefault();
      items[cursor]?.classList.remove("active");
      cursor = (cursor + (e.key === "ArrowDown" ? 1 : -1) + items.length) % items.length;
      items[cursor].classList.add("active");
      items[cursor].scrollIntoView({ block: "nearest" });
    } else if (e.key === "Enter") {
      (items[cursor] || items[0])?.click();
    }
  });
  document.addEventListener("click", (e) => {
    if (!e.target.closest(".search-wrap")) close();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "/" && document.activeElement.tagName !== "INPUT" && document.activeElement.tagName !== "SELECT") {
      e.preventDefault();
      input.focus();
      input.select();
    }
  });
}

/* ---------- theme ---------- */

function setupTheme() {
  const stored = localStorage.getItem("sm-theme");
  if (stored) document.documentElement.setAttribute("data-theme", stored);
  document.getElementById("theme-btn").addEventListener("click", () => {
    const cur =
      document.documentElement.getAttribute("data-theme") ||
      (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
    const next = cur === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    localStorage.setItem("sm-theme", next);
  });
}

/* ---------- boot ---------- */

function boot() {
  const mark = icon("spider", 22);
  mark.setAttribute("class", "mark");
  document.querySelector(".brand").prepend(mark);
  const magnifier = icon("search", 14);
  magnifier.setAttribute("class", "icon");
  document.querySelector(".search-wrap .icon-slot").replaceWith(magnifier);
  document.getElementById("theme-btn").appendChild(icon("theme", 15));
  const c = DATA.meta.counts;
  document.getElementById("foot-line").textContent =
    `${c.works} works · ${c.characters} characters · ${c.people} people · ${c.credits} credits, ` +
    `${DATA.meta.year_min}–${DATA.meta.year_max}. Generated from spiderman.db. Data CC BY 4.0, code MIT.`;
  // The header nav, the brand and the overview tiles are real anchors, for keyboard and
  // copy-link semantics. Some embedded viewers treat any anchor navigation — even a
  // same-document fragment one — as a request for a new tab, so intercept internal
  // links and route them through the same hash navigation every button already uses.
  // Modified clicks are left alone, so opening a new tab on purpose still works.
  document.addEventListener("click", (e) => {
    if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    const a = e.target.closest('a[href^="#"]');
    if (!a) return;
    e.preventDefault();
    go(a.getAttribute("href"));
  });

  setupSearch();
  setupTheme();
  window.addEventListener("hashchange", render);
  render();
}

boot();
