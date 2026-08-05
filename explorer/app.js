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
  // `noun` / `nounOne` are the forms that read correctly mid-sentence, which lower-casing
  // the label does not give you for "TV series".
  movie: { label: "Movies", one: "Movie", noun: "movies", nounOne: "movie", color: "var(--series-1)" },
  tv_show: { label: "TV series", one: "TV series", noun: "TV series", nounOne: "TV series", color: "var(--series-2)" },
  game: { label: "Games", one: "Game", noun: "games", nounOne: "game", color: "var(--series-3)" },
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
  w.genres = w.genres || [];
  w.countries = w.countries || [];
  w.languages = w.languages || [];
  w.content_ratings = w.content_ratings || [];
  w.release_dates = w.release_dates || [];
  w.places = w.places || [];
  w.box_office_regions = w.box_office_regions || [];
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
  c.external_ids = c.external_ids || [];
  c.relations = c.relations || [];
  c.traits = c.traits || {};
  c.n_works = c.n_works || 0;
  c.by_type = { movie: 0, tv_show: 0, game: 0 };
  for (const wid of new Set(c.appearances.map((a) => a.work_id))) c.by_type[workById.get(wid).type]++;
}

/* The comics the screen adapted, and the people who made them. The export holds
   each credit once, on the comic; the creator's side of it is built here. */
const comicRows = DATA.comics || [];
const comicCreators = DATA.comic_creators || [];
const comicById = new Map(comicRows.map((c) => [c.id, c]));
const creatorById = new Map(comicCreators.map((c) => [c.id, c]));

for (const c of comicRows) {
  c.credits = c.credits || [];
  c.characters = c.characters || [];
  c.series = c.series_id ? comicById.get(c.series_id) : null;
  c.works = [];
}
for (const cr of comicCreators) cr.credits = [];
for (const c of comicRows) {
  for (const x of c.credits) {
    const cr = creatorById.get(x.creator_id);
    if (!cr) continue;
    x.creator = cr;
    cr.credits.push({ comic: c, role: x.role });
  }
}
for (const w of works) {
  for (const src of w.sources) {
    for (const id of src.comic_ids || []) {
      const c = comicById.get(id);
      if (c && !c.works.includes(w)) c.works.push(w);
    }
  }
}
for (const cr of comicCreators) {
  cr.name_l = cr.name.toLowerCase();
  cr.roles = [...new Set(cr.credits.map((x) => x.role))].sort();
  cr.n_comics = new Set(cr.credits.map((x) => x.comic.id)).size;
  /* Two different spans, and conflating them would be a lie: when they worked in
     comics, and when the screen got round to those comics. `summarise` owns
     first_year/last_year (the screen side) for every dimension, so the comics
     side keeps its own names. */
  const yrs = cr.credits.map((x) => x.comic.year).filter(Boolean);
  cr.comic_first_year = yrs.length ? Math.min(...yrs) : null;
  cr.comic_last_year = yrs.length ? Math.max(...yrs) : null;
  cr.works = [...new Set(cr.credits.flatMap((x) => x.comic.works))];
}
for (const p of people) {
  p.credits = p.credits || [];
  p.occupations = p.occupations || [];
  p.citizenships = p.citizenships || [];
  p.awards = p.awards || [];
  p.external_ids = p.external_ids || [];
  p.n_works = new Set(p.credits.map((c) => c.work_id)).size;
  p.roles = [...new Set(p.credits.map((c) => c.role))];
  p.is_actor = p.roles.some((r) => r === "actor" || r === "voice actor");
  p.years = p.credits.map((c) => workById.get(c.work_id).year).filter(Boolean).sort();
}

const FRANCHISES = [...new Set(works.map((w) => w.franchise).filter(Boolean))].sort();
const GENRES = [...new Set(works.flatMap((w) => w.genres))].sort();
const COUNTRIES = [...new Set(works.flatMap((w) => w.countries))].sort();
const LANGUAGES = [...new Set(works.flatMap((w) => w.languages))].sort();
const NATIONALITIES = [...new Set(people.map((p) => p.nationality).filter(Boolean))].sort();

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

/* Works nearest to this one by overlap — the same faces, or the same characters. Neither
   relation is stored anywhere; both fall out of the join tables. */
function neighbourWorks(w, pick) {
  const mine = new Set(pick(w));
  if (!mine.size) return [];
  const counts = new Map();
  for (const other of works) {
    if (other === w) continue;
    let n = 0;
    for (const k of new Set(pick(other))) if (mine.has(k)) n++;
    if (n) counts.set(other, n);
  }
  return [...counts.entries()]
    .map(([work, n]) => ({ work, n }))
    .sort((a, b) => b.n - a.n || (a.work.year ?? 9999) - (b.work.year ?? 9999));
}

const castKeys = (w) => [...w.cast, ...w.crew].map((c) => c.person_id);
const charKeys = (w) => w.characters.map((c) => c.identity_id);

/* ---------- more derived dimensions ---------- */

/* Outlets, comic storylines, awarding bodies and credit roles are all things the source
   names over and over without ever giving any of them a row. Each is shaped exactly like a
   franchise or a studio here — a name, the works behind it, a span — so one list view, one
   set of tiles and one works table serve all of them. */

for (const g of publicationIndex.values()) {
  g.works = [...new Set(g.scores.map((r) => r.work))];
  summarise(g);
  /* An outlet's mean is the mean of the scores it filed — not, as `summarise` computes for
     every other dimension, the mean of the works' own overall means. Restore it, or the
     outlet pages and the "how the outlets differ" chart report how good the works were
     instead of how generously this outlet marked them. */
  g.avg_pct = g.scores.reduce((a, r) => a + r.pct, 0) / g.n;
}

for (const g of comicIndex.values()) {
  g.name = g.title;
  g.works = [...new Set(g.uses.map((u) => u.work))];
  /* v4 resolved the citations to actual issues. A citation naming a run — "Amazing
     Spider-Man #121-122" — resolves to several, so this is a list, not a value. */
  g.resolved = [...new Set(g.uses.flatMap((u) => (u.comic_ids || []).map((id) => comicById.get(id)).filter(Boolean)))];
  summarise(g);
}

/* Comic writers and artists as a dimension of their own — the same shape as a studio
   or an outlet, so the one list view and one detail page serve them too. */
const creatorIndex = new Map();
for (const cr of comicCreators) {
  creatorIndex.set(cr.name, cr);
  summarise(cr);
}

for (const g of awardBodies.values()) {
  g.works = [...new Set(g.rows.map((a) => a.work))];
  g.categories = [...new Set(g.rows.map((a) => a.category))].sort();
  summarise(g);
}

/* Every credit role in the catalogue — "actor", "composer", "programmer" — as a dimension
   you can stand on and look back out at the people and works holding it. */
const roleIndex = new Map();
for (const w of works) {
  for (const c of [...w.cast, ...w.crew]) {
    const g = groupInto(roleIndex, c.role, (n) => ({ name: n, works: [], credits: [], people: new Set() }));
    g.credits.push({ ...c, work: w });
    g.people.add(c.person_id);
    if (!g.works.includes(w)) g.works.push(w);
  }
}
for (const g of roleIndex.values()) {
  summarise(g);
  g.n_people = g.people.size;
  g.is_cast = g.name === "actor" || g.name === "voice actor";
}

/* One year, from every angle the catalogue can see it. */
const yearIndex = new Map();
const yearBucket = (y) =>
  y == null || !Number.isFinite(Number(y))
    ? null
    : groupInto(yearIndex, Number(y), (n) => ({ year: n, works: [], born: [], died: [], debuts: [], comics: [], awards: [], releases: [] }));
for (const w of works) {
  yearBucket(w.year)?.works.push(w);
  for (const a of w.awards) yearBucket(a.year)?.awards.push({ ...a, work: w });
  for (const src of w.sources) if (src.comic) yearBucket(src.year)?.comics.push({ ...src, work: w });
  for (const r of w.game_releases) if (r.date) yearBucket(String(r.date).slice(0, 4))?.releases.push({ ...r, work: w });
}
for (const c of characters) if (c.first_media_year) yearBucket(c.first_media_year)?.debuts.push(c);
for (const p of people) {
  if (p.birth) yearBucket(String(p.birth).slice(0, 4))?.born.push(p);
  if (p.death) yearBucket(String(p.death).slice(0, 4))?.died.push(p);
}
const yearHas = (y) => {
  const b = yearIndex.get(Number(y));
  return b && (b.works.length || b.born.length || b.died.length || b.debuts.length || b.comics.length || b.awards.length || b.releases.length);
};

/* ---------- name resolution ---------- */

const normName = (s) => String(s).toLowerCase().replace(/[.'’]/g, "").replace(/\s+/g, " ").trim();
const personByName = new Map();
for (const p of people) if (!personByName.has(normName(p.name))) personByName.set(normName(p.name), p);
const studioByName = new Map([...studioIndex.keys()].map((n) => [normName(n), n]));
const comicByTitle = new Map([...comicIndex.keys()].map((n) => [normName(n), n]));

/* Half the names in the source sit in free-text fields — a director column, a head-writer
   string, a "Beenox / Griptonite Games" developer credit. Each field may hold several names
   at once, so they are split apart and resolved one at a time. */
const NAME_SPLIT = /\s*(?:;|\/|&|\band\b)\s*|,\s+(?!(?:Jr|Sr|II|III|Inc|LLC|Ltd|Co)\b)/;

function splitNames(str) {
  return String(str)
    .split(NAME_SPLIT)
    .map((x) => x.trim())
    .filter(Boolean)
    .map((raw) => {
      const m = raw.match(/^(.*?)\s*\(([^)]*)\)$/);
      return m && m[1].trim() ? { name: m[1].trim(), note: m[2] } : { name: raw, note: null };
    });
}

/* A name we hold a record for goes to that record; a name we do not goes to the lookup,
   which is never empty — the string came out of this data in the first place. */
function nameLink(name, kind, note) {
  const p = personByName.get(normName(name));
  const st = studioByName.get(normName(name));
  const first = kind === "studio" ? st && "#/studio/" + encodeURIComponent(st) : p && "#/person/" + p.id;
  const second = kind === "studio" ? p && "#/person/" + p.id : st && "#/studio/" + encodeURIComponent(st);
  const hash = first || second || findHash(name);
  return softLink(name, hash, {
    note,
    title: first || second ? name : `Find “${name}” everywhere in the data`,
  });
}

function nameLinks(str, kind = "person") {
  if (!str) return dash();
  const parts = splitNames(str);
  if (!parts.length) return dash();
  const out = [];
  parts.forEach((part, i) => {
    if (i) out.push(el("span", { class: "sep", text: "·" }));
    out.push(nameLink(part.name, kind, part.note));
  });
  return el("span", { class: "names" }, out);
}

/* ---------- facets: attributes many works share, with no table of their own ---------- */

const FACETS = {
  rating: { label: "MPAA rating", title: (v) => `Films rated ${v}`, get: (w) => w.movie?.mpaa_rating },
  esrb: { label: "ESRB rating", title: (v) => `Games rated ${v}`, get: (w) => w.game_releases.map((r) => r.esrb) },
  genre: { label: "Genre", title: (v) => `${v} games`, get: (w) => w.game?.genre },
  universe: { label: "Game universe", title: (v) => v, get: (w) => w.game?.universe },
  engine: { label: "Engine", title: (v) => `Built on ${v}`, get: (w) => w.game?.engine },
  network: { label: "Network", title: (v) => `Aired on ${v}`, get: (w) => w.tv?.network },
  format: { label: "Format", title: (v) => v, get: (w) => w.tv?.format },
  status: { label: "Status", title: (v) => `Series marked ${v}`, get: (w) => w.tv?.status },
  kind: { label: "Kind", title: (v) => `${v} works`, get: (w) => w.movie?.sub_type || w.tv?.sub_type },
  "studio-role": { label: "Studio credit", title: (v) => `Works with a ${v.replace(/_/g, " ")} credit`, get: (w) => w.studios.map((st) => st.role) },
  relation: { label: "Work relation", title: (v) => `Works carrying a “${v}” link`, get: (w) => w.relations.map((r) => r.label) },
  "credited-as": { label: "Credit spelling", title: (v) => `Credited as “${v}”`, get: (w) => w.characters.map((c) => c.as) },
  "content-genre": { label: "Genre", title: (v) => `${v} works`, get: (w) => w.genres },
  country: { label: "Country", title: (v) => `Works made in ${v}`, get: (w) => w.countries },
  language: { label: "Language", title: (v) => `Works in ${v}`, get: (w) => w.languages },
};

const facetCache = new Map();
function facetIndex(key) {
  if (facetCache.has(key)) return facetCache.get(key);
  const map = new Map();
  const get = FACETS[key].get;
  for (const w of works) {
    const raw = get(w);
    for (const v of (Array.isArray(raw) ? raw : [raw]).filter(Boolean)) {
      if (!map.has(v)) map.set(v, []);
      if (!map.get(v).includes(w)) map.get(v).push(w);
    }
  }
  facetCache.set(key, map);
  return map;
}

const facetHash = (key, value) => "#/facet/" + key + "/" + encodeURIComponent(value);
const findHash = (text) => "#/find/" + encodeURIComponent(String(text).trim());

/* ---------- the lookup of last resort ---------- */

/* Anything that resolves to no record links here instead of sitting inert: every row in the
   dataset that mentions the string, whichever column it was hiding in. */
function findEverywhere(q) {
  const needle = q.toLowerCase().trim();
  if (!needle) return [];
  const has = (v) => v != null && String(v).toLowerCase().includes(needle);
  const groups = [];
  const add = (kind, hits) => hits.length && groups.push({ kind, hits });

  add("Works", works.filter((w) => has(w.title) || has(w.notes) || has(w.maker)).map((w) => ({ label: w.title, sub: `${yr(w)} · ${TYPE[w.type].one}`, hash: "#/work/" + w.id })));
  add("Characters", characters.filter((c) => has(c.name) || c.variants.some(has) || has(c.first_comic) || has(c.gender) || has(c.publisher) || has(c.universe) || has(c.creators) || Object.values(c.traits).some((vs) => vs.some(has)) || c.relations.some((r) => has(r.name))).map((c) => ({ label: c.name, sub: `${c.n_works} work${c.n_works === 1 ? "" : "s"}`, hash: "#/character/" + c.id })));
  add("People", people.filter((p) => has(p.name) || has(p.place) || has(p.gender) || has(p.nationality) || has(p.birth_country) || has(p.death_place) || has(p.birth_name) || p.occupations.some(has) || p.citizenships.some(has)).map((p) => ({ label: p.name, sub: p.roles.slice(0, 3).join(", "), hash: "#/person/" + p.id })));
  add("Franchises", [...franchiseIndex.values()].filter((g) => has(g.name) || has(g.description)).map((g) => ({ label: g.name, sub: `${g.n_works} works`, hash: "#/franchise/" + encodeURIComponent(g.name) })));
  add("Studios", [...studioIndex.values()].filter((g) => has(g.name)).map((g) => ({ label: g.name, sub: `${g.n_works} works`, hash: "#/studio/" + encodeURIComponent(g.name) })));
  add("Platforms", [...platformIndex.values()].filter((g) => has(g.name)).map((g) => ({ label: g.name, sub: `${g.n_works} games`, hash: "#/platform/" + encodeURIComponent(g.name) })));
  add("Outlets", [...publicationIndex.values()].filter((g) => has(g.name)).map((g) => ({ label: g.name, sub: `${g.n} scores`, hash: "#/publication/" + encodeURIComponent(g.name) })));
  add("Comics", [...comicIndex.values()].filter((g) => has(g.title) || has(g.writer)).map((g) => ({ label: g.title, sub: [g.writer, g.year].filter(Boolean).join(" · "), hash: "#/comic/" + encodeURIComponent(g.title) })));
  add("Comic issues", comicRows.filter((c) => has(c.title) || has(c.publisher)).map((c) => ({ label: c.title, sub: [c.publisher, c.year].filter(Boolean).join(" · "), hash: "#/comicrow/" + c.id })));
  add("Comic creators", comicCreators.filter((c) => has(c.name) || c.roles.some((r) => has(roleText(r)))).map((c) => ({ label: c.name, sub: `${c.n_comics} comic${c.n_comics === 1 ? "" : "s"}, ${c.roles.map(roleText).join(", ")}`, hash: "#/creator/" + c.id })));
  add("Awarding bodies", [...awardBodies.values()].filter((g) => has(g.name) || g.categories.some(has)).map((g) => ({ label: g.name, sub: `${g.won} won, ${g.nominated} nominated`, hash: "#/award/" + encodeURIComponent(g.name) })));
  add("Credit roles", [...roleIndex.values()].filter((g) => has(g.name)).map((g) => ({ label: g.name, sub: `${g.n_people} people`, hash: "#/role/" + encodeURIComponent(g.name) })));

  /* Rows that live inside a work, and are reachable only through it. */
  const inner = [];
  for (const w of works) {
    const at = (what) => ({ label: what, sub: `${w.title} (${yr(w)})`, hash: "#/work/" + w.id });
    for (const e of w.episodes) {
      if (has(e.title)) inner.push(at(`Episode “${e.title}”`));
      if (has(e.director)) inner.push(at(`Directed episode ${e.title ? "“" + e.title + "”" : "#" + e.episode}`));
      if (has(e.writer)) inner.push(at(`Wrote episode ${e.title ? "“" + e.title + "”" : "#" + e.episode}`));
    }
    for (const t of w.soundtracks) if (has(t.title) || has(t.by)) inner.push(at(`${t.type === "song" ? "Song" : "Score"} ${t.title ? "“" + t.title + "”" : ""} ${t.by ? "— " + t.by : ""}`.trim()));
    for (const a of w.awards) if (has(a.category) || has(a.body)) inner.push(at(`${a.result === "won" ? "Won" : "Nominated"}: ${a.category}`));
    for (const src of w.sources) if (has(src.writer) || has(src.arc) || has(src.issues)) inner.push(at(`Source: ${[src.comic, src.issues, src.arc].filter(Boolean).join(" · ")}`));
    for (const r of w.game_releases) if (has(r.publisher) || has(r.developer) || has(r.date)) inner.push(at(`${r.platform || "Release"}${r.date ? " " + r.date : ""} — ${[r.developer, r.publisher].filter(Boolean).join(" / ")}`));
    for (const c of [...w.cast, ...w.crew]) if (has(c.character)) inner.push(at(`Credited as “${c.character}”`));
    const strings = [w.movie?.director, w.movie?.producer, w.movie?.distributor, w.tv?.head_writer, w.tv?.voice_actor_spider_man, w.tv?.network, w.game?.engine, w.game?.universe].filter(has);
    for (const v of strings) inner.push(at(String(v)));
  }
  add("Mentioned inside a work", inner.slice(0, 60));
  return groups;
}

/* ---------- routing ---------- */

/* Every list view's filter defaults. Absent from the URL means "this value".
   `focus` is not a filter — it is the row a link asked us to point at. */
const DEFAULTS = {
  works: { type: "all", franchise: "all", era: "all", genre: "all", country: "all", language: "all", char: "all", sort: "year", dir: 1, q: "", focus: "" },
  characters: { align: "all", sort: "n_works", dir: -1, q: "", focus: "" },
  people: { kind: "all", nationality: "all", sort: "n_works", dir: -1, q: "", focus: "" },
  franchises: { sort: "n_works", dir: -1, q: "" },
  studios: { sort: "n_works", dir: -1, q: "" },
  platforms: { sort: "n_works", dir: -1, q: "" },
  publications: { sort: "avg_pct", dir: -1, q: "" },
  comics: { sort: "n_works", dir: -1, q: "" },
  creators: { sort: "n_comics", dir: -1, q: "" },
  awards: { sort: "n_awards", dir: -1, q: "" },
  roles: { sort: "n_people", dir: -1, q: "" },
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
const LIST_VIEWS = ["works", "characters", "people", "franchises", "studios", "platforms", "publications", "comics", "creators", "awards", "roles"];
const LAST_LIST = {};
const listHash = (view) => LAST_LIST[view] || "#/" + view;

function render() {
  const { view, id, query } = currentRoute();
  const TAB_OF = {
    work: "works", character: "characters", person: "people",
    franchise: "franchises", studio: "studios", platform: "platforms",
    // The four dimensions the Analysis page opens up keep that tab lit.
    publication: "analysis", publications: "analysis", comic: "analysis", comics: "analysis",
    creator: "analysis", creators: "analysis", comicrow: "analysis",
    award: "analysis", awards: "analysis", role: "analysis", roles: "analysis",
    facet: "works",
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
    publications: viewPublications,
    publication: viewPublication,
    comics: viewComics,
    comic: viewComic,
    creators: viewCreators,
    creator: viewCreator,
    comicrow: viewComicRow,
    awards: viewAwards,
    award: viewAward,
    roles: viewRoles,
    role: viewRole,
    year: viewYear,
    facet: viewFacet,
    find: viewFind,
    analysis: viewAnalysis,
    about: viewAbout,
  };
  const fn = map[view] || viewOverview;
  app.appendChild(fn(id, query));
  /* `?at=<id>` names a block on the page being rendered — the destination of a tile whose
     number is answered further down, or on one specific chart of another page. */
  const at = new URLSearchParams(query).get("at");
  const target = at ? app.querySelector("#" + CSS.escape(at)) : null;
  if (target) target.scrollIntoView({ block: "start" });
  else window.scrollTo(0, window.__keepScroll ? window.scrollY : 0);
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

function statTile(label, value, hash, note) {
  const inner = [
    el("div", { class: "label" }, label),
    el("div", { class: "value", text: value }),
    note ? el("div", { class: "kpi-note", text: note }) : null,
  ];
  return hash
    ? el("a", { class: "kpi", href: hash, title: note || null }, inner)
    : el("div", { class: "kpi" }, inner);
}

/* A tile is only worth a destination when the destination answers the number on it. Where
   that answer is a block on this page — or one named chart on another — the tile jumps to
   that block instead of dumping the reader into an unfiltered list of everything. */
function pathHash() {
  const { view, id } = currentRoute();
  return "#/" + view + (id ? "/" + encodeURIComponent(id) : "");
}

const atHash = (id, base) => (base ?? pathHash()) + "?at=" + id;

function anchor(id, node) {
  node.id = id;
  node.classList.add("jump-target");
  return node;
}

const jumpTile = (label, value, id, note, base) => statTile(label, value, atHash(id, base), note);

/* A detail page can carry more than one cut at a time — an awarding body's records filtered
   to wins *and* its works filtered to films. So a tile or chip that changes one of them
   rewrites only its own params and leaves the rest of the page's state alone. */
function pageHashWith(overrides) {
  const params = new URLSearchParams(currentRoute().query);
  for (const [k, v] of Object.entries(overrides)) {
    if (v == null || v === "") params.delete(k);
    else params.set(k, String(v));
  }
  const q = params.toString();
  return pathHash() + (q ? "?" + q : "");
}

const dash = () => el("span", { class: "muted", text: "—" });

/* A link at body weight, for a value sitting inside a sentence, a cell or a fact list. */
function softLink(text, hash, opts = {}) {
  return el(
    "button",
    { class: "row-link soft", title: opts.title || null, onclick: () => go(hash) },
    text,
    opts.note ? el("span", { class: "as", text: "(" + opts.note + ")" }) : null
  );
}

/* The small linkable atoms every table cell is built from. */
const yearLink = (y, label) =>
  y == null ? dash() : yearHas(y) ? softLink(label ?? String(y), "#/year/" + y) : el("span", { text: label ?? String(y) });

const dateLink = (d) => {
  if (!d) return dash();
  const y = String(d).slice(0, 4);
  return yearHas(y) ? softLink(String(d), "#/year/" + Number(y)) : el("span", { text: String(d) });
};

const facetLink = (key, value, label) => (value ? softLink(label ?? String(value), facetHash(key, value)) : dash());
const roleLink = (role) => (role ? softLink(role, "#/role/" + encodeURIComponent(role)) : dash());
const findLink = (text, label) => (text ? softLink(label ?? String(text), findHash(text), { title: `Find “${text}” everywhere in the data` }) : dash());
const comicLink = (title, label) => {
  if (!title) return dash();
  const hit = comicByTitle.get(normName(title));
  return hit ? softLink(label ?? title, "#/comic/" + encodeURIComponent(hit)) : findLink(title, label);
};
const publicationLink = (name, label) =>
  publicationIndex.has(name) ? softLink(label ?? name, "#/publication/" + encodeURIComponent(name)) : findLink(name, label);
/* `scope` keeps the medium marker in the context the reader clicked it from: inside a
   character's own table it means "this medium, for this character", not "every movie". */
const mediumLink = (type, scope) =>
  el("button", {
    class: "dot-label link-quiet",
    title: scope ? `${TYPE[type].label} in this list` : `Every ${TYPE[type].nounOne} in the catalogue`,
    onclick: () => go("#/works?type=" + type + (scope ? "&" + scope : "")),
  },
    el("span", { class: "dot", style: { background: TYPE[type].color } }), TYPE[type].one);
const alignLink = (alignment) => {
  const a = ALIGN[alignment] || ALIGN.neutral;
  return el("button", { class: "dot-label link-quiet", onclick: () => go("#/characters?align=" + (alignment || "neutral")) },
    el("span", { class: "dot", style: { background: a.color } }), a.label);
};

/* Character link that survives the two ways the data names a character: by identity, and by
   the exact string a work credited. */
function characterLink(identity_id, label) {
  const c = charById.get(identity_id);
  if (!c) return label ? findLink(label) : dash();
  return softLink(label ?? c.name, "#/character/" + c.id, { title: c.name });
}

function creditedAsLink(work, credited) {
  if (!credited) return dash();
  const match = work.characters.find((wc) => wc.as === credited);
  return match ? characterLink(match.identity_id, credited) : facetLink("credited-as", credited);
}

function dotLabel(color, label) {
  return el("span", { class: "dot-label" }, el("span", { class: "dot", style: { background: color } }), label);
}

/* The medium marker is the same everywhere, and everywhere it is a way into that medium. */
function typeBadge(type, scope) {
  return mediumLink(type, scope);
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
    class: "row-link soft",
    text: maxLen && name.length > maxLen ? name.slice(0, maxLen - 1) + "\u2026" : name,
    title: name,
    onclick: () => go("#/franchise/" + encodeURIComponent(name)),
  });
}

const SOURCE_LABELS = {
  wikidata: "Wikidata", imdb: "IMDb", tmdb_movie: "TMDB", tmdb_tv: "TMDB", tmdb_person: "TMDB",
  rotten_tomatoes: "Rotten Tomatoes", metacritic: "Metacritic", letterboxd: "Letterboxd",
  steam: "Steam", giant_bomb: "Giant Bomb", box_office_mojo: "Box Office Mojo",
  the_numbers: "The Numbers", official_website: "Official site", commons_category: "Wikimedia Commons",
  musicbrainz_artist: "MusicBrainz", comic_vine: "Comic Vine",
};

/* Real outbound links — a genuine <a href>, not a hash route, so they get the browser's
   native new-tab / copy-link handling instead of the app's internal router. */
function externalLinksRow(list) {
  if (!list || !list.length) return null;
  return el(
    "div",
    { class: "chip-list" },
    list.map((x) => el("a", { class: "chip", href: x.url, target: "_blank", rel: "noopener", text: SOURCE_LABELS[x.source] || x.source }))
  );
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
  let focused = null;
  const body = rows.map((r) => {
    const tr = el(
      "tr",
      null,
      cols.map((c) => {
        const v = c.cell(r);
        return el("td", { class: (c.num ? "num " : "") + (c.wrap ? "wrap " : "") + (c.cls || "") }, v);
      })
    );
    // A link can ask for one row to be pointed at — "here is where this sits in the ranking".
    if (opts.focus && opts.focus(r)) {
      tr.classList.add("row-focus");
      focused = tr;
    }
    return tr;
  });
  const wrap = el(
    "div",
    { class: "table-wrap" + (opts.plain ? " plain" : "") },
    el("table", null, el("thead", null, head), el("tbody", null, body))
  );
  if (focused) requestAnimationFrame(() => focused.scrollIntoView({ block: "center" }));
  return wrap;
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

/* Every dimension the catalogue can be entered through, in one place, so nothing is
   reachable only by stumbling onto the right cell. */
function browseSection(title = "Every way into the data") {
  const items = [
    { label: "Works", hash: "#/works", n: works.length },
    { label: "Characters", hash: "#/characters", n: characters.length },
    { label: "People", hash: "#/people", n: people.length },
    { label: "Franchises", hash: "#/franchises", n: franchiseIndex.size },
    { label: "Studios", hash: "#/studios", n: studioIndex.size },
    { label: "Platforms", hash: "#/platforms", n: platformIndex.size },
    { label: "Outlets", hash: "#/publications", n: publicationIndex.size },
    { label: "Comic sources", hash: "#/comics", n: comicIndex.size },
    comicCreators.length ? { label: "Comic creators", hash: "#/creators", n: comicCreators.length } : null,
    { label: "Awarding bodies", hash: "#/awards", n: awardBodies.size },
    { label: "Credit roles", hash: "#/roles", n: roleIndex.size },
    { label: "Years", hash: "#/year/" + DATA.meta.year_max, n: yearIndex.size },
  ].filter(Boolean);
  return section(
    title,
    null,
    el("div", { class: "chip-list" }, items.map((it) => dimChip(it.label, it.hash, String(it.n)))),
    el("div", { class: "sub", style: { marginTop: "8px" }, text: "Outlets, comic sources, awarding bodies, credit roles and years are not tables in the source — they are grouped here out of the columns that name them, so each becomes somewhere you can stand. Comic creators are a table of their own." })
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
        statTile("Credits", String(c.credits), "#/people?sort=credits&dir=-1"),
        statTile("Franchises", String(franchiseIndex.size), "#/franchises"),
        statTile("Studios", String(studioIndex.size), "#/studios"),
        statTile("Platforms", String(platformIndex.size), "#/platforms")
      )
    )
  );

  frag.appendChild(el("div", { class: "grid", style: { marginTop: "14px" } }, timelineChart()));
  frag.appendChild(
    el("div", { class: "grid cols-2", style: { marginTop: "14px" } }, anchor("economics", economicsChart()), receptionChart())
  );
  frag.appendChild(el("div", { class: "grid", style: { marginTop: "14px" } }, topCharactersChart()));

  frag.appendChild(browseSection());

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
    if (total) hit.addEventListener("click", () => go(`#/year/${y}`));
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
          { key: "year", label: "Year", num: true, cell: (r) => yearLink(r.year) },
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

  /* Everything except the medium chips, which need to count what each chip would give you
     under the filters already set — not the whole catalogue. */
  const passesRest = (w) => {
    if (f.franchise !== "all" && w.franchise !== f.franchise) return false;
    if (f.era !== "all") {
      const e = Number(f.era);
      if (exactYear) {
        if (w.year !== e) return false;
      } else if (!w.year || w.year < e || w.year >= e + 10) return false;
    }
    if (f.genre !== "all" && !w.genres.includes(f.genre)) return false;
    if (f.country !== "all" && !w.countries.includes(f.country)) return false;
    if (f.language !== "all" && !w.languages.includes(f.language)) return false;
    if (f.char !== "all" && !w.characters.some((wc) => String(wc.identity_id) === String(f.char))) return false;
    if (f.q) {
      const hay = (w.title + " " + (w.franchise || "") + " " + (w.maker || "")).toLowerCase();
      if (!hay.includes(f.q.toLowerCase())) return false;
    }
    return true;
  };
  const scoped = works.filter(passesRest);
  const rows0 = f.type === "all" ? scoped : scoped.filter((w) => w.type === f.type);

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
    runtime: (w) => w.movie?.runtime_minutes ?? -1,
  }[f.sort] || ((w) => w.year ?? 9999);
  const rows = sortRows(rows0, get, f.dir, (w) => w.title);

  const counts = { all: scoped.length };
  for (const k of Object.keys(TYPE)) counts[k] = scoped.filter((w) => w.type === k).length;

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
      GENRES.length
        ? selectBox(
            "Genre",
            [{ value: "all", label: "All genres" }, ...GENRES.map((x) => ({ value: x, label: x }))],
            f.genre,
            (v) => applyFilters("works", { ...f, genre: v })
          )
        : null,
      COUNTRIES.length
        ? selectBox(
            "Country",
            [{ value: "all", label: "All countries" }, ...COUNTRIES.map((x) => ({ value: x, label: x }))],
            f.country,
            (v) => applyFilters("works", { ...f, country: v })
          )
        : null,
      LANGUAGES.length
        ? selectBox(
            "Language",
            [{ value: "all", label: "All languages" }, ...LANGUAGES.map((x) => ({ value: x, label: x }))],
            f.language,
            (v) => applyFilters("works", { ...f, language: v })
          )
        : null,
      /* The one filter that comes in from elsewhere: a character page's medium tiles link
         here scoped to that character, so the count on the tile is the list you land on. */
      selectBox(
        "Character",
        [{ value: "all", label: "Any character" }, ...[...characters].sort((a, b) => a.name.localeCompare(b.name)).map((c) => ({ value: String(c.id), label: c.name }))],
        String(f.char),
        (v) => applyFilters("works", { ...f, char: v })
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
        { key: "year", label: "Year", num: true, cell: (w) => yearLink(w.year, yr(w)) },
        { key: "type", label: "Medium", cell: (w) => typeBadge(w.type) },
        { key: "franchise", label: "Franchise", cell: (w) => (w.franchise ? franchiseLink(w.franchise, 24) : dash()) },
        { key: "maker", label: "Made by", cell: (w) => (w.maker ? nameLinks(w.maker) : dash()) },
        { key: "score", label: "Score", num: true, cell: (w) => (w.avg_pct == null ? el("span", { class: "muted", text: "—" }) : pct(w.avg_pct)) },
        { key: "gross", label: "Gross", num: true, cell: (w) => (w.gross == null ? el("span", { class: "muted", text: "—" }) : money(w.gross)) },
        { key: "chars", label: "Chars", num: true, cell: (w) => String(w.characters.length) },
        { key: "credits", label: "Credits", num: true, cell: (w) => String(w.n_credits) },
        /* Two columns that would be mostly empty in the default list, so they appear only
           when the reader is looking at them — which is what the runtime and budget tiles
           on a work's page ask for when they send you here. */
        f.sort === "budget" && { key: "budget", label: "Budget", num: true, cell: (w) => (w.budget_usd ? money(w.budget_usd) : dash()) },
        (f.type === "movie" || f.sort === "runtime") && {
          key: "runtime",
          label: "Runtime",
          num: true,
          cell: (w) => (w.movie?.runtime_minutes ? w.movie.runtime_minutes + " min" : dash()),
        },
      ].filter(Boolean),
      rows,
      { onSort: sortHandler("works", f, ["title", "year", "type", "franchise", "maker"]), sortKey: f.sort, dir: f.dir, scroll: true, focus: (w) => String(w.id) === String(f.focus) }
    );
    frag.appendChild(tableNode);
    tableNode = tableNode.querySelector("table");
  } else {
    frag.appendChild(el("div", { class: "table-wrap" }, el("div", { class: "empty-state", text: "No works match these filters." })));
  }

  return frag;
}

/* ---------- work detail ---------- */

function viewWork(id) {
  const w = workById.get(Number(id));
  if (!w) return el("div", { class: "empty-state", text: "Unknown work." });
  const frag = document.createDocumentFragment();
  frag.appendChild(backLink("All works", listHash("works")));

  const sub = w.type === "movie" ? w.movie?.sub_type : w.type === "tv_show" ? w.tv?.sub_type : w.game?.genre;
  const subKey = w.type === "game" ? "genre" : "kind";
  frag.appendChild(
    el(
      "div",
      { class: "detail-head" },
      el("h1", { text: w.title }),
      el(
        "div",
        { class: "meta-line" },
        el("button", { class: "badge link-quiet", onclick: () => go("#/works?type=" + w.type) },
          el("span", { class: "dot", style: { background: TYPE[w.type].color } }), TYPE[w.type].one),
        w.date ? dateLink(w.date) : yearLink(w.year, yr(w)),
        sub ? facetLink(subKey, sub) : null,
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

  if (w.summary?.text) {
    frag.appendChild(
      el(
        "p",
        { style: { color: "var(--text-secondary)", maxWidth: "78ch", marginTop: "10px" } },
        w.summary.text,
        w.summary.url ? el("a", { href: w.summary.url, target: "_blank", rel: "noopener", style: { marginLeft: "6px" }, text: "Wikipedia ↗" }) : null
      )
    );
  }

  /* Stat tiles carry a destination wherever the catalogue can answer "compared with what?" —
     the ranked list, with this work pointed at. */
  const rank = (sort) => `#/works?sort=${sort}&dir=-1&focus=${w.id}`;
  const tiles = [];
  if (w.avg_pct != null) tiles.push(statTile("Mean review score", pct(w.avg_pct) + " / 100", rank("score"), "See it ranked against every scored work"));
  /* The budget→gross chart is on the overview and only plots works carrying both figures,
     so it belongs to the tile that needs both. A budget on its own ranks against the other
     budgets instead — the same move the score and gross tiles make. */
  if (w.budget_usd) tiles.push(statTile("Production budget", money(w.budget_usd), rank("budget"), "See it ranked against every budget on record"));
  if (w.gross) tiles.push(statTile("Worldwide gross", money(w.gross), rank("gross"), "See it ranked against every work on record"));
  if (w.budget_usd && w.gross)
    tiles.push(statTile("Return on budget", (w.gross / w.budget_usd).toFixed(2) + "×", atHash("economics", "#/overview"), "See it on the budget → gross chart"));
  if (w.movie?.runtime_minutes)
    tiles.push(statTile("Runtime", w.movie.runtime_minutes + " min", `#/works?type=movie&sort=runtime&dir=-1&focus=${w.id}`, "See it ranked against every film"));
  /* The episode guide answers both of these — but only for the series that have one, and
     only honestly when it is not a stub of two rows against a 65-episode run. */
  const guide = w.episodes.length >= 3 ? pageHashWith({ at: "episodes", season: null }) : null;
  if (w.tv?.episodes)
    tiles.push(statTile("Episodes", num(w.tv.episodes), guide, guide ? (w.episodes.length < w.tv.episodes ? w.episodes.length + " are itemised below" : "See the episode guide") : null));
  if (w.tv?.seasons) tiles.push(statTile("Seasons", String(w.tv.seasons), guide, guide ? "See the episode guide" : null));
  if (w.characters.length) tiles.push(statTile("Characters", String(w.characters.length), rank("chars")));
  if (w.n_credits) tiles.push(statTile("Credited people", String(w.n_credits), rank("credits")));
  if (tiles.length) frag.appendChild(el("div", { class: "kpis", style: { marginTop: "16px" } }, tiles));

  /* facts — every value here names something the catalogue holds elsewhere */
  const facts = [];
  const addFact = (k, v) => v && facts.push(el("div", null, el("div", { class: "k", text: k }), el("div", { class: "v" }, v)));
  if (w.type === "movie" && w.movie) {
    addFact("Director", w.movie.director && nameLinks(w.movie.director));
    addFact("Producer", w.movie.producer && nameLinks(w.movie.producer));
    addFact("Distributor", w.movie.distributor && nameLinks(w.movie.distributor, "studio"));
    addFact("Rating", w.movie.mpaa_rating && facetLink("rating", w.movie.mpaa_rating));
  }
  if (w.type === "tv_show" && w.tv) {
    addFact("Network", w.tv.network && facetLink("network", w.tv.network));
    addFact("Format", w.tv.format && facetLink("format", w.tv.format));
    addFact(
      "Ran",
      w.tv.start_year &&
        el("span", { class: "names" }, yearLink(w.tv.start_year), w.tv.end_year && w.tv.end_year !== w.tv.start_year ? el("span", { class: "sep", text: "–" }) : null, w.tv.end_year && w.tv.end_year !== w.tv.start_year ? yearLink(w.tv.end_year) : null)
    );
    addFact("Head writer", w.tv.head_writer && nameLinks(w.tv.head_writer));
    addFact("Spider-Man voice", w.tv.voice_actor_spider_man && nameLinks(w.tv.voice_actor_spider_man));
    addFact("Status", w.tv.status && facetLink("status", w.tv.status));
  }
  if (w.type === "game" && w.game) {
    addFact("Genre", w.game.genre && facetLink("genre", w.game.genre));
    addFact("Universe", w.game.universe && facetLink("universe", w.game.universe));
    addFact("Engine", w.game.engine && facetLink("engine", w.game.engine));
    addFact(
      "Platforms",
      w.platforms.length &&
        el("span", { class: "names" }, [...w.platforms].sort().flatMap((n, i) => [i ? el("span", { class: "sep", text: "·" }) : null, softLink(n, "#/platform/" + encodeURIComponent(n))]).filter(Boolean))
    );
  }
  // Both rows link to the same ranking, which is by worldwide gross — the title says which.
  const grossRank = { title: "Rank every work by worldwide gross" };
  if (w.box_office?.domestic) addFact("Domestic gross", softLink(money(w.box_office.domestic), rank("gross"), grossRank));
  if (w.box_office?.international) addFact("International gross", softLink(money(w.box_office.international), rank("gross"), grossRank));
  if (facts.length) frag.appendChild(section("Details", null, el("div", { class: "card deflist" }, facts)));

  /* genre / country / language — columns in the source, not tables of their own, so they
     ride the same facet mechanism as MPAA rating or network. */
  if (w.genres.length || w.countries.length || w.languages.length) {
    const row = (label, key, values) =>
      values.length
        ? el(
            "div",
            null,
            el("div", { class: "k", text: label }),
            el("div", { class: "chip-list", style: { marginTop: "4px" } }, values.map((v) => facetLink(key, v, v)))
          )
        : null;
    frag.appendChild(
      section(
        "Classification",
        null,
        el(
          "div",
          { class: "card", style: { display: "grid", gap: "10px" } },
          row("Genre", "content-genre", w.genres),
          row("Country", "country", w.countries),
          row("Language", "language", w.languages)
        )
      )
    );
  }

  if (w.content_ratings.length) {
    frag.appendChild(
      section(
        "Content ratings",
        w.content_ratings.length,
        table(
          [
            { key: "r", label: "Rating", cell: (r) => facetLink("rating", r.rating) },
            { key: "c", label: "Country", wrap: true, cell: (r) => (r.country ? findLink(r.country) : dash()) },
            { key: "n", label: "Reason", wrap: true, cell: (r) => r.reason || el("span", { class: "muted", text: "—" }) },
          ],
          w.content_ratings,
          { plain: true }
        )
      )
    );
  }

  if (w.release_dates.length > 1) {
    frag.appendChild(
      section(
        "Release dates",
        w.release_dates.length,
        table(
          [
            { key: "d", label: "Date", cell: (r) => dateLink(r.date) },
            { key: "p", label: "Place", wrap: true, cell: (r) => (r.place ? findLink(r.place) : dash()) },
            { key: "e", label: "Event", wrap: true, cell: (r) => r.event || el("span", { class: "muted", text: "—" }) },
          ],
          [...w.release_dates].sort((a, b) => (a.date || "").localeCompare(b.date || "")),
          { plain: true }
        )
      )
    );
  }

  if (w.places.length) {
    const byRole = { narrative: [], filming: [] };
    for (const p of w.places) (byRole[p.role] || (byRole[p.role] = [])).push(p.place);
    frag.appendChild(
      section(
        "Places",
        w.places.length,
        el(
          "div",
          { class: "card", style: { display: "grid", gap: "10px" } },
          byRole.narrative?.length ? el("div", null, el("div", { class: "k", text: "Set in" }), el("div", { class: "chip-list", style: { marginTop: "4px" } }, byRole.narrative.map((p) => findLink(p)))) : null,
          byRole.filming?.length ? el("div", null, el("div", { class: "k", text: "Filmed in" }), el("div", { class: "chip-list", style: { marginTop: "4px" } }, byRole.filming.map((p) => findLink(p)))) : null
        )
      )
    );
  }

  if (w.box_office_regions.length) {
    frag.appendChild(
      section(
        "Box office by territory",
        w.box_office_regions.length,
        table(
          [
            { key: "r", label: "Region", cell: (r) => findLink(r.region) },
            { key: "a", label: "Gross", num: true, cell: (r) => money(r.amount) },
            { key: "d", label: "As of", cell: (r) => dateLink(r.as_of) },
          ],
          w.box_office_regions,
          { plain: true }
        )
      )
    );
  }

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
            { key: "c", label: "Credited as", wrap: true, cell: (c) => creditedAsLink(w, c.character) },
            { key: "r", label: "Role", cell: (c) => roleLink(c.role) },
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
            { key: "r", label: "Role", cell: (c) => roleLink(c.role) },
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
            { key: "s", label: "Source", wrap: true, cell: (r) => publicationLink(r.publication, r.source) },
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
    const hasSegments = w.episodes.some((e) => e.segments?.length > 1);
    /* The Seasons tile lands here, so the guide has to show the seasons rather than just
       run 65 rows together — the chips are what that number counted. */
    const seasons = [...new Set(w.episodes.map((e) => e.season).filter((s) => s != null))].sort((a, b) => a - b);
    const asked = Number(paramOf("season", ""));
    const season = seasons.includes(asked) ? asked : null;
    const eps = season == null ? w.episodes : w.episodes.filter((e) => e.season === season);
    const toEpisodes = (s) => pageHashWith({ at: "episodes", season: s });
    frag.appendChild(
      anchor("episodes", section(
        "Episodes on record",
        eps.length,
        seasons.length > 1
          ? el("div", { class: "filters section-filters" },
              chips(
                [
                  { value: "", label: "All seasons", n: w.episodes.length },
                  ...seasons.map((s) => ({ value: String(s), label: "Season " + s, n: w.episodes.filter((e) => e.season === s).length })),
                ],
                season == null ? "" : String(season),
                (v) => go(toEpisodes(v === "" ? null : v))
              ))
          : null,
        table(
          [
            { key: "s", label: "S", num: true, cell: (e) => (e.season == null ? "—" : String(e.season)) },
            { key: "e", label: "E", num: true, cell: (e) => (e.episode == null ? "—" : String(e.episode)) },
            { key: "t", label: "Title", wrap: true, cell: (e) => (e.title ? findLink(e.title) : dash()) },
            hasSegments && {
              key: "seg",
              label: "Segments",
              wrap: true,
              cell: (e) =>
                e.segments?.length > 1
                  ? el("span", { class: "names" }, e.segments.flatMap((sg, i) => [i ? el("span", { class: "sep", text: "·" }) : null, sg.title ? findLink(sg.title) : dash()]).filter(Boolean))
                  : dash(),
            },
            { key: "a", label: "Air date", cell: (e) => dateLink(e.air_date) },
            { key: "d", label: "Director", wrap: true, cell: (e) => nameLinks(e.director) },
            { key: "wr", label: "Writer", wrap: true, cell: (e) => nameLinks(e.writer) },
            { key: "v", label: "US viewers", num: true, cell: (e) => (e.viewers_m == null ? dash() : e.viewers_m + "M") },
          ].filter(Boolean),
          eps,
          { plain: true }
        ),
        w.tv?.episodes && w.episodes.length < w.tv.episodes
          ? el("div", { class: "sub", style: { marginTop: "8px" }, text: `The series ran ${w.tv.episodes} episodes; ${w.episodes.length} are itemised here.` })
          : null
      ))
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
            { key: "p", label: "Platform", cell: (r) => (r.platform ? softLink(r.platform, "#/platform/" + encodeURIComponent(r.platform)) : dash()) },
            { key: "d", label: "Date", cell: (r) => dateLink(r.date) },
            { key: "pub", label: "Publisher", wrap: true, cell: (r) => nameLinks(r.publisher, "studio") },
            { key: "dev", label: "Developer", wrap: true, cell: (r) => nameLinks(r.developer, "studio") },
            { key: "m", label: "Metacritic", num: true, cell: (r) => (r.metacritic == null ? dash() : String(r.metacritic)) },
            { key: "e", label: "ESRB", cell: (r) => (r.esrb ? facetLink("esrb", r.esrb) : dash()) },
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
            { key: "c", label: "Component", cell: (b) => (b.component ? findLink(b.component) : dash()) },
            { key: "a", label: "Amount", num: true, cell: (b) => money(b.amount) },
            { key: "y", label: "Source year", num: true, cell: (b) => yearLink(b.source_year) },
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
            { key: "c", label: "Comic", wrap: true, cell: (r) => comicLink(r.comic) },
            { key: "i", label: "Issues", wrap: true, cell: (r) => (r.issues ? findLink(r.issues) : dash()) },
            { key: "w", label: "Writer", wrap: true, cell: (r) => nameLinks(r.writer) },
            { key: "y", label: "Year", num: true, cell: (r) => yearLink(r.year) },
            { key: "a", label: "Arc", wrap: true, cell: (r) => (r.arc ? findLink(r.arc) : dash()) },
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
            { key: "b", label: "Body", cell: (a) => softLink(a.body, "#/award/" + encodeURIComponent(a.body)) },
            { key: "y", label: "Year", num: true, cell: (a) => yearLink(a.year) },
            { key: "c", label: "Category", wrap: true, cell: (a) => findLink(a.category) },
            { key: "r", label: "Result", cell: (a) => (a.result === "won" ? el("strong", { text: "Won" }) : el("span", { class: "muted", text: "Nominated" })) },
            { key: "p", label: "Recipient", cell: (a) => (a.person_id ? personLink(a.person_id) : dash()) },
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
            { key: "t", label: "Type", cell: (t) => findLink(t.type) },
            { key: "n", label: "Title", wrap: true, cell: (t) => (t.title ? findLink(t.title) : dash()) },
            { key: "b", label: "By", wrap: true, cell: (t) => nameLinks(t.by) },
            { key: "us", label: "US peak", num: true, cell: (t) => t.peak_us || dash() },
            { key: "uk", label: "UK peak", num: true, cell: (t) => t.peak_uk || dash() },
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
              el("div", { class: "k", style: { fontSize: "12px", color: "var(--text-muted)", marginBottom: "5px" } }, facetLink("relation", label)),
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

  /* Nothing in the source links these works — the overlap does. */
  const byPeople = neighbourWorks(w, castKeys).slice(0, 12);
  const byChars = neighbourWorks(w, charKeys).slice(0, 12);
  if (byPeople.length || byChars.length) {
    const strand = (label, list, one, many) =>
      list.length
        ? el(
            "div",
            null,
            el("div", { class: "k", style: { fontSize: "12px", color: "var(--text-muted)", marginBottom: "5px" }, text: label }),
            el(
              "div",
              { class: "chip-list" },
              list.map((x) =>
                el(
                  "button",
                  { class: "chip", onclick: () => go("#/work/" + x.work.id) },
                  el("span", { class: "dot", style: { background: TYPE[x.work.type].color } }),
                  x.work.title,
                  el("span", { class: "as", text: `${x.n} ${x.n === 1 ? one : many}` })
                )
              )
            )
          )
        : null;
    frag.appendChild(
      section(
        "Overlaps with",
        byPeople.length + byChars.length,
        el(
          "div",
          { class: "card", style: { display: "grid", gap: "12px" } },
          strand("Shares credited people with", byPeople, "person", "people"),
          strand("Shares characters with", byChars, "character", "characters")
        ),
        el("div", { class: "sub", style: { marginTop: "8px" }, text: "Computed from the credit and character tables, not from any stored relation — these are works this one happens to have people or characters in common with." })
      )
    );
  }

  if (w.external_ids?.length) {
    frag.appendChild(section("Elsewhere", w.external_ids.length, externalLinksRow(w.external_ids)));
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
  const scoped = characters.filter((c) => {
    if (!f.q) return true;
    const hay = (c.name + " " + c.variants.join(" ")).toLowerCase();
    return hay.includes(f.q.toLowerCase());
  });
  const rows0 = f.align === "all" ? scoped : scoped.filter((c) => c.alignment === f.align);
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

  // A chip promises what clicking it gives you, so it counts inside the other filters.
  const counts = { all: scoped.length };
  for (const a of Object.keys(ALIGN)) counts[a] = scoped.filter((c) => c.alignment === a).length;

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
        { key: "align", label: "Alignment", cell: (c) => alignLink(c.alignment) },
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
        { key: "first_media_year", label: "First on screen", num: true, cell: (c) => yearLink(c.first_media_year) },
        { key: "first_year", label: "First in comics", num: true, cell: (c) => yearLink(c.first_year) },
        { key: "variants", label: "Spellings", num: true, cell: (c) => String(c.variants.length) },
      ],
      rows,
      { onSort: sortHandler("characters", f, ["name", "align", "first_year", "first_media_year"]), sortKey: f.sort, dir: f.dir, scroll: true, focus: (c) => String(c.id) === String(f.focus) }
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
        el("button", { class: "badge link-quiet", onclick: () => go("#/characters?align=" + (c.alignment || "neutral")) },
          el("span", { class: "dot", style: { background: a.color } }), a.label),
        c.first_comic ? el("span", { class: "names" }, "First appeared in ", comicLink(c.first_comic)) : null,
        // The comic string usually carries its own year; don't print it twice.
        c.first_year && !String(c.first_comic || "").includes(String(c.first_year)) ? yearLink(c.first_year) : null
      )
    )
  );

  const cFacts = [];
  const addCFact = (k, v) => v && cFacts.push(el("div", null, el("div", { class: "k", text: k }), el("div", { class: "v" }, v)));
  addCFact("Gender", c.gender && findLink(c.gender));
  addCFact("Publisher", c.publisher && findLink(c.publisher));
  addCFact("Narrative universe", c.universe && findLink(c.universe));
  addCFact("Creators", c.creators && nameLinks(c.creators));
  addCFact("First appearance", c.first_appearance_title && el("span", { class: "names" }, findLink(c.first_appearance_title), c.first_appearance_year ? el("span", { class: "as", text: String(c.first_appearance_year) }) : null));
  /* The debut as a comic row rather than a title string — v4's version of the
     line above, and the one you can click through to the credits. */
  const debut = c.debut_comic_id ? comicById.get(c.debut_comic_id) : null;
  addCFact("Debut comic", debut && el("span", { class: "names" }, comicRowLink(debut),
    debut.year ? el("span", { class: "as", text: String(debut.year) }) : null));
  for (const [trait, label] of [["character_type", "Character type"], ["occupation", "Occupation"],
                                ["ability", "Abilities"], ["team", "Teams"],
                                ["ethnic_group", "Ethnicity"], ["religion", "Religion"],
                                ["eye_color", "Eyes"], ["hair_color", "Hair"], ["height", "Height"]]) {
    const vals = c.traits[trait];
    if (vals && vals.length)
      addCFact(label, el("span", { class: "names" },
        vals.flatMap((v, i) => [i ? el("span", { class: "sep", text: "·" }) : null, findLink(v)])));
  }
  if (cFacts.length) frag.appendChild(section("Details", null, el("div", { class: "card deflist" }, cFacts)));

  const tiles = [statTile("Works", String(c.n_works), `#/characters?sort=n_works&dir=-1&focus=${c.id}`, "See it ranked against every character")];
  // Each medium tile opens the works list scoped to this character, so the list you land on
  // holds exactly the works the number counted.
  for (const t of ["movie", "tv_show", "game"])
    if (c.by_type[t]) tiles.push(statTile(TYPE[t].label, String(c.by_type[t]), `#/works?type=${t}&char=${c.id}`, `The ${TYPE[t].noun} ${c.name} is in`));
  if (c.first_media_year) tiles.push(statTile("First on screen", String(c.first_media_year), "#/year/" + c.first_media_year));
  if (c.first_year) tiles.push(statTile("First in comics", String(c.first_year), yearHas(c.first_year) ? "#/year/" + c.first_year : null));
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

  /* Who this character is to other characters — the one thing the catalogue could
     never say before v4. An edge whose other end is in the dataset is a link; one
     that is not is still worth naming, so it stays as text. */
  if (c.relations.length) {
    const REL_LABELS = {
      enemy: "Enemy of", ally: "Allied with", mother: "Mother", father: "Father",
      spouse: "Spouse", child: "Child", partner: "Partner", relative: "Relative",
      alternate_universe_counterpart: "Counterpart in another universe",
    };
    const order = ["enemy", "ally", "alternate_universe_counterpart", "spouse", "partner",
                   "father", "mother", "child", "relative"];
    const byRel = new Map();
    for (const r of c.relations) {
      if (!byRel.has(r.relation)) byRel.set(r.relation, []);
      byRel.get(r.relation).push(r);
    }
    const rank = (rel) => (order.indexOf(rel) < 0 ? order.length : order.indexOf(rel));
    const groups = [...byRel.entries()].sort((a, b) => rank(a[0]) - rank(b[0]));
    /* Each relation gets a full-width row of its own: an "enemy of" list can run to
       eighty names, and a two-column grid would file that beside a one-name "spouse"
       and leave a column of whitespace the height of the page. */
    frag.appendChild(
      section("Relationships", c.relations.length,
        el("div", { class: "card" },
          groups.map(([rel, list], i) =>
            el("div", { style: i ? { marginTop: "14px" } : null },
              el("div", { class: "k", style: { fontSize: "12px", color: "var(--text-muted)", marginBottom: "5px" },
                          text: (REL_LABELS[rel] || rel.replace(/_/g, " ")) + " · " + list.length }),
              el("div", { class: "chip-list" },
                [...list]
                  .sort((a, b) => (b.other_id ? 1 : 0) - (a.other_id ? 1 : 0) || a.name.localeCompare(b.name))
                  .map((r) =>
                    r.other_id
                      ? el("button", { class: "chip", text: r.name, onclick: () => go("#/character/" + r.other_id) })
                      : el("span", { class: "chip muted", title: "Not a character in this dataset", text: r.name })))))),
        el("div", { class: "sub", style: { marginTop: "8px" },
          text: "Greyed names are characters Wikidata links to that this catalogue has no row for — they have never been on screen in a Spider-Man work." }))
    );
  }

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
          { key: "y", label: "Year", num: true, cell: (r) => yearLink(r.w.year, yr(r.w)) },
          { key: "t", label: "Medium", cell: (r) => typeBadge(r.w.type, "char=" + c.id) },
          { key: "f", label: "Franchise", cell: (r) => (r.w.franchise ? franchiseLink(r.w.franchise, 22) : dash()) },
          { key: "as", label: "Credited as", wrap: true, cell: (r) => facetLink("credited-as", r.as) },
          { key: "a", label: "Played by", cell: (r) => (r.actor_person_id ? personLink(r.actor_person_id) : dash()) },
        ],
        rows,
        { plain: true }
      )
    )
  );

  /* Who has played this character, and when — the question the appearance table answers only
     one row at a time. */
  const byActor = new Map();
  for (const r of rows) {
    if (!r.actor_person_id) continue;
    const g = groupInto(byActor, r.actor_person_id, (pid) => ({ person: personById.get(pid), works: [] }));
    g.works.push(r.w);
  }
  const performers = [...byActor.values()].filter((g) => g.person);
  if (performers.length) {
    for (const g of performers) {
      const ys = g.works.map((w) => w.year).filter(Boolean).sort();
      g.from = ys[0] ?? null;
      g.to = ys[ys.length - 1] ?? null;
    }
    performers.sort((x, y) => (x.from ?? 9999) - (y.from ?? 9999));
    frag.appendChild(
      section(
        "Played by",
        performers.length,
        table(
          [
            { key: "p", label: "Performer", cell: (g) => personLink(g.person.id) },
            { key: "y", label: "When", cell: (g) => (g.from == null ? dash() : g.from === g.to ? yearLink(g.from) : el("span", { class: "names" }, yearLink(g.from), el("span", { class: "sep", text: "–" }), yearLink(g.to))) },
            { key: "n", label: "Works", num: true, cell: (g) => String(g.works.length) },
            { key: "w", label: "In", wrap: true, cell: (g) => el("span", { class: "chip-list" }, g.works.map((w) => el("button", { class: "chip", onclick: () => go("#/work/" + w.id) }, el("span", { class: "dot", style: { background: TYPE[w.type].color } }), w.title))) },
            { key: "r", label: "Also plays", wrap: true, cell: (g) => {
              const others = charactersPlayedBy(g.person).filter((x) => x.character.id !== c.id);
              return others.length
                ? el("span", { class: "chip-list" }, others.slice(0, 4).map((x) => el("button", { class: "chip", onclick: () => go("#/character/" + x.character.id) }, x.character.name)))
                : dash();
            } },
          ],
          performers,
          { plain: true }
        )
      )
    );
  }

  const franchises = [...new Set(uniqueWorks.map((w) => w.franchise).filter(Boolean))].sort();
  if (franchises.length) {
    frag.appendChild(
      section(
        "Franchises this character has crossed",
        franchises.length,
        el(
          "div",
          { class: "chip-list" },
          franchises.map((n) => {
            const n_here = uniqueWorks.filter((w) => w.franchise === n).length;
            return dimChip(n, "#/franchise/" + encodeURIComponent(n), `${n_here} work${n_here === 1 ? "" : "s"}`);
          })
        )
      )
    );
  }

  if (c.variants.length > 1) {
    frag.appendChild(
      section(
        "Credit spellings collapsed into this identity",
        c.variants.length,
        el("div", { class: "chip-list" }, c.variants.map((v) => dimChip(v, facetHash("credited-as", v)))),
        el("div", { class: "sub", style: { marginTop: "8px" }, text: "These are the exact strings the source research used, and each one opens the works that used it. Counting the raw credit table instead of this identity would split this character across every spelling above." })
      )
    );
  }

  if (c.external_ids?.length) {
    frag.appendChild(section("Elsewhere", c.external_ids.length, externalLinksRow(c.external_ids)));
  }

  return frag;
}

/* Every identity a person has been credited as, with the works behind each. */
function charactersPlayedBy(person) {
  const byChar = new Map();
  for (const cr of person.credits) {
    const w = workById.get(cr.work_id);
    for (const wc of w.characters) {
      const isMatch = wc.actor_person_id === person.id || (cr.character && wc.as === cr.character);
      if (!isMatch) continue;
      const g = groupInto(byChar, wc.identity_id, (id) => ({ character: charById.get(id), works: [], as: new Set() }));
      if (!g.works.includes(w)) g.works.push(w);
      if (wc.as) g.as.add(wc.as);
    }
  }
  return [...byChar.values()]
    .filter((g) => g.character)
    .map((g) => {
      const ys = g.works.map((w) => w.year).filter(Boolean).sort();
      return { ...g, from: ys[0] ?? null, to: ys[ys.length - 1] ?? null };
    })
    .sort((a, b) => (a.from ?? 9999) - (b.from ?? 9999) || a.character.name.localeCompare(b.character.name));
}

/* ============================================================
   PEOPLE
   ============================================================ */

function viewPeople(_id, query) {
  const f = readFilters(DEFAULTS.people, query);
  const scoped = people.filter((p) => {
    if (f.nationality !== "all" && p.nationality !== f.nationality) return false;
    if (f.q && !p.name.toLowerCase().includes(f.q.toLowerCase())) return false;
    return true;
  });
  const rows0 = scoped.filter((p) => (f.kind === "cast" ? p.is_actor : f.kind === "crew" ? !p.is_actor : true));
  const get = {
    name: (p) => p.name.toLowerCase(),
    roles: (p) => p.roles.join(", ").toLowerCase(),
    n_works: (p) => p.n_works,
    credits: (p) => p.credits.length,
    first: (p) => p.years[0] ?? 9999,
    last: (p) => p.years[p.years.length - 1] ?? -1,
    nationality: (p) => (p.nationality || "~").toLowerCase(),
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
          { value: "all", label: "Everyone", n: scoped.length },
          { value: "cast", label: "Performers", n: scoped.filter((p) => p.is_actor).length },
          { value: "crew", label: "Crew only", n: scoped.filter((p) => !p.is_actor).length },
        ],
        f.kind,
        (v) => applyFilters("people", { ...f, kind: v })
      ),
      NATIONALITIES.length
        ? selectBox(
            "Nationality",
            [{ value: "all", label: "All nationalities" }, ...NATIONALITIES.map((x) => ({ value: x, label: x }))],
            f.nationality,
            (v) => applyFilters("people", { ...f, nationality: v })
          )
        : null,
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
        {
          key: "roles",
          label: "Roles",
          wrap: true,
          cell: (p) =>
            el("span", { class: "names" }, [
              ...p.roles.slice(0, 4).flatMap((r, i) => [i ? el("span", { class: "sep", text: "·" }) : null, roleLink(r)]),
              p.roles.length > 4 ? el("span", { class: "muted", text: ` +${p.roles.length - 4}` }) : null,
            ].filter(Boolean)),
        },
        { key: "n_works", label: "Works", num: true, cell: (p) => String(p.n_works) },
        { key: "credits", label: "Credits", num: true, cell: (p) => String(p.credits.length) },
        { key: "first", label: "First", num: true, cell: (p) => yearLink(p.years[0]) },
        { key: "last", label: "Latest", num: true, cell: (p) => yearLink(p.years[p.years.length - 1]) },
        { key: "nationality", label: "Nationality", cell: (p) => (p.nationality ? findLink(p.nationality) : dash()) },
      ],
      rows,
      { onSort: sortHandler("people", f, ["name", "roles", "first", "last", "nationality"]), sortKey: f.sort, dir: f.dir, scroll: true, focus: (p) => String(p.id) === String(f.focus) }
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
        p.birth
          ? el("span", { class: "names" }, yearLink(Number(p.birth.slice(0, 4))), p.death ? el("span", { class: "sep", text: "–" }) : null, p.death ? yearLink(Number(p.death.slice(0, 4))) : null)
          : null,
        p.place ? findLink(p.place) : null,
        p.nationality ? findLink(p.nationality) : null,
        p.imdb ? el("a", { class: "badge", href: "https://www.imdb.com/name/" + p.imdb + "/", text: "IMDb" }) : null,
        p.wikidata ? el("a", { class: "badge", href: "https://www.wikidata.org/wiki/" + p.wikidata, text: "Wikidata" }) : null
      )
    )
  );

  const pFacts = [];
  const addPFact = (k, v) => v && pFacts.push(el("div", null, el("div", { class: "k", text: k }), el("div", { class: "v" }, v)));
  addPFact("Birth name", p.birth_name && p.birth_name !== p.name ? findLink(p.birth_name) : null);
  addPFact("Gender", p.gender && findLink(p.gender));
  addPFact("Birth country", p.birth_country && findLink(p.birth_country));
  addPFact("Death place", p.death_place && findLink(p.death_place));
  addPFact("Career span", p.work_start && el("span", { class: "names" }, String(p.work_start), p.work_end && p.work_end !== p.work_start ? el("span", { class: "sep", text: "–" }) : null, p.work_end && p.work_end !== p.work_start ? String(p.work_end) : null));
  if (pFacts.length) frag.appendChild(section("Details", null, el("div", { class: "card deflist" }, pFacts)));

  if (p.occupations.length) frag.appendChild(section("Occupations", p.occupations.length, el("div", { class: "chip-list" }, p.occupations.map((o) => findLink(o)))));
  if (p.citizenships.length) frag.appendChild(section("Citizenships", p.citizenships.length, el("div", { class: "chip-list" }, p.citizenships.map((c) => findLink(c)))));

  frag.appendChild(
    el(
      "div",
      { class: "kpis", style: { marginTop: "16px" } },
      statTile("Works", String(p.n_works), `#/people?sort=n_works&dir=-1&focus=${p.id}`, "See it ranked against everyone"),
      statTile("Credits", String(p.credits.length), `#/people?sort=credits&dir=-1&focus=${p.id}`),
      p.years.length
        ? statTile(
            "Active",
            p.years[0] === p.years[p.years.length - 1] ? String(p.years[0]) : p.years[0] + "–" + p.years[p.years.length - 1],
            "#/year/" + p.years[0],
            p.years.length > 1 ? "Opens " + p.years[0] + ", their first catalogued year" : null
          )
        : null
    )
  );

  const rows = p.credits
    .map((c) => ({ ...c, w: workById.get(c.work_id) }))
    .sort((a, b) => (a.w.year ?? 9999) - (b.w.year ?? 9999));

  const charFor = (r) => creditedAsLink(r.w, r.character);

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

  /* The characters this person has played, when, and who else has played them. */
  const played = charactersPlayedBy(p);
  if (played.length) {
    frag.appendChild(
      section(
        "Characters played",
        played.length,
        table(
          [
            { key: "c", label: "Character", cell: (g) => characterLink(g.character.id) },
            { key: "a", label: "Alignment", cell: (g) => alignLink(g.character.alignment) },
            { key: "y", label: "When", cell: (g) => (g.from == null ? dash() : g.from === g.to ? yearLink(g.from) : el("span", { class: "names" }, yearLink(g.from), el("span", { class: "sep", text: "\u2013" }), yearLink(g.to))) },
            { key: "w", label: "In", wrap: true, cell: (g) => el("span", { class: "chip-list" }, g.works.map((w) => el("button", { class: "chip", onclick: () => go("#/work/" + w.id) }, el("span", { class: "dot", style: { background: TYPE[w.type].color } }), w.title, el("span", { class: "as", text: String(yr(w)) })))) },
            {
              key: "o",
              label: "Also played by",
              wrap: true,
              cell: (g) => {
                const others = [...new Set(g.character.appearances.map((ap) => ap.actor_person_id).filter((id) => id && id !== p.id))];
                return others.length
                  ? el("span", { class: "chip-list" }, others.slice(0, 5).map((id) => el("button", { class: "chip", onclick: () => go("#/person/" + id), text: personById.get(id)?.name || "\u2014" })))
                  : dash();
              },
            },
          ],
          played,
          { plain: true }
        ),
        el("div", { class: "sub", style: { marginTop: "8px" }, text: "Matched from the character table by performer, and by the exact string the work credited \u2014 so a role credited under a spelling this catalogue collapses still lands on the right identity." })
      )
    );
  }

  if (p.roles.length) {
    const mix = new Map();
    for (const c of p.credits) mix.set(c.role, (mix.get(c.role) || 0) + 1);
    frag.appendChild(
      section(
        "Roles held",
        p.roles.length,
        el(
          "div",
          { class: "chip-list" },
          [...mix.entries()].sort((a, b) => b[1] - a[1]).map(([r, n]) => dimChip(r, "#/role/" + encodeURIComponent(r), "\u00d7" + n))
        )
      )
    );
  }

  /* Where this career sits in the rest of the catalogue's furniture. */
  const pStudios = new Map();
  const pFranchises = new Map();
  for (const w of careerWorks) {
    for (const st of w.studios) pStudios.set(st.name, (pStudios.get(st.name) || 0) + 1);
    if (w.franchise) pFranchises.set(w.franchise, (pFranchises.get(w.franchise) || 0) + 1);
  }
  const countChips = (map, hashFor) =>
    el(
      "div",
      { class: "chip-list" },
      [...map.entries()]
        .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
        .map(([n, k]) => dimChip(n, hashFor(n), `${k} work${k === 1 ? "" : "s"}`))
    );
  if (pFranchises.size) frag.appendChild(section("Franchises", pFranchises.size, countChips(pFranchises, (n) => "#/franchise/" + encodeURIComponent(n))));
  if (pStudios.size) frag.appendChild(section("Studios behind those works", pStudios.size, countChips(pStudios, (n) => "#/studio/" + encodeURIComponent(n))));

  frag.appendChild(
    section(
      "Credits",
      rows.length,
      table(
        [
          { key: "w", label: "Work", cell: (r) => workLink(r.w, false) },
          { key: "y", label: "Year", num: true, cell: (r) => yearLink(r.w.year, yr(r.w)) },
          { key: "t", label: "Medium", cell: (r) => typeBadge(r.w.type) },
          { key: "r", label: "Role", cell: (r) => roleLink(r.role) },
          { key: "c", label: "As", wrap: true, cell: charFor },
        ],
        rows,
        { plain: true }
      )
    )
  );

  if (p.awards.length) {
    const won = p.awards.filter((a) => a.result === "won").length;
    frag.appendChild(
      section(
        "Awards",
        p.awards.length,
        table(
          [
            { key: "a", label: "Award", wrap: true, cell: (a) => findLink(a.award) },
            { key: "r", label: "Result", cell: (a) => (a.result === "won" ? el("strong", { text: "Won" }) : el("span", { class: "muted", text: "Nominated" })) },
            { key: "y", label: "Year", num: true, cell: (a) => yearLink(a.year) },
            { key: "f", label: "For", wrap: true, cell: (a) => (a.for_work ? findLink(a.for_work) : dash()) },
          ],
          [...p.awards].sort((a, b) => (b.year ?? 0) - (a.year ?? 0)),
          { plain: true }
        ),
        el("div", { class: "sub", style: { marginTop: "8px" }, text: `${won} won of ${p.awards.length} listed — including recognition for work outside this catalogue.` })
      )
    );
  }

  if (p.external_ids.length) {
    frag.appendChild(section("Elsewhere", p.external_ids.length, externalLinksRow(p.external_ids)));
  }

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
          { key: "y", label: "Year", num: true, cell: (e) => yearLink(e.year) },
          { key: "t", label: "Work", cell: (e) => (e.work ? workLink(e.work, false) : findLink(e.title)) },
          { key: "m", label: "Medium", cell: (e) => (e.type ? typeBadge(e.type) : dash()) },
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
    {
      key: "roles",
      label: "Credited as",
      asc: true,
      value: (g) => [...g.roles].sort().join(", "),
      cell: (g) => el("span", { class: "names" }, [...g.roles].sort().flatMap((r, i) => [i ? el("span", { class: "sep", text: "·" }) : null, facetLink("studio-role", r, r.replace(/_/g, " "))]).filter(Boolean)),
    },
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
      { key: "y", label: "Year", num: true, cell: (w) => yearLink(w.year, yr(w)) },
      { key: "m", label: "Medium", cell: (w) => typeBadge(w.type) },
      showFranchise && { key: "f", label: "Franchise", cell: (w) => (w.franchise ? franchiseLink(w.franchise, 26) : dash()) },
      { key: "s", label: "Score", num: true, cell: (w) => (w.avg_pct == null ? el("span", { class: "muted", text: "—" }) : pct(w.avg_pct)) },
      { key: "g", label: "Gross", num: true, cell: (w) => (w.gross == null ? el("span", { class: "muted", text: "—" }) : money(w.gross)) },
      { key: "c", label: "Chars", num: true, cell: (w) => String(w.characters.length) },
    ].filter(Boolean),
    [...list].sort((a, b) => (a.year ?? 9999) - (b.year ?? 9999)),
    { plain: true }
  );
}

/* Reads one of the query params a detail page understands. Detail pages have no filter
   state of their own, so a param here only ever comes from a tile or a chip on the page. */
const paramOf = (key, fallback = "all") => new URLSearchParams(currentRoute().query).get(key) || fallback;

/* The block every dimension page ends on: the works behind its numbers.
   The medium tiles above it point *here* rather than at the catalogue-wide works list, so
   what a tile counted is exactly what the reader lands on — and the chips widen it back out
   without leaving the page. `?at=works` is what the tiles scroll to, `?type=` is the cut. */
function worksSection(title, rows, { workOf = (r) => r, render = worksOfTable, id = "works", note = null } = {}) {
  const kinds = ["movie", "tv_show", "game"].filter((k) => rows.some((r) => workOf(r).type === k));
  const asked = paramOf("type");
  const type = kinds.includes(asked) ? asked : "all";
  const shown = type === "all" ? rows : rows.filter((r) => workOf(r).type === type);
  const head =
    kinds.length > 1
      ? el("div", { class: "filters section-filters" },
          chips(
            [
              { value: "all", label: "All", n: rows.length },
              ...kinds.map((k) => ({ value: k, label: TYPE[k].label, n: rows.filter((r) => workOf(r).type === k).length, color: TYPE[k].color })),
            ],
            type,
            (v) => go(pageHashWith({ at: id, type: v === "all" ? null : v }))
          ))
      : null;
  return anchor(id, section(title, shown.length, head, render(shown), note));
}

/* "Who and what else is in these works" — the same tally, whatever the grouping was. */
function tallySection(title, list, extract, hashFor, { max = 30, unit = "work", label = (k) => k } = {}) {
  const counts = new Map();
  for (const w of list) for (const v of extract(w)) if (v != null) counts.set(v, (counts.get(v) || 0) + 1);
  // An empty fragment appends to nothing, so callers never have to test first.
  if (!counts.size) return document.createDocumentFragment();
  return section(
    title,
    counts.size,
    el(
      "div",
      { class: "chip-list" },
      [...counts.entries()]
        .sort((a, b) => b[1] - a[1] || String(label(a[0])).localeCompare(String(label(b[0]))))
        .slice(0, max)
        .map(([k, n]) => dimChip(label(k), hashFor(k), `${n} ${unit}${n === 1 ? "" : "s"}`))
    )
  );
}

const creditedPeople = (w) => [...new Set([...w.cast, ...w.crew].map((c) => c.person_id))];
const personName = (id) => personById.get(id)?.name || "—";

/* Every one of these numbers is answered by the works block further down the page, so each
   tile scrolls to it — the medium tiles with that medium already selected. `works` names the
   block; a page whose works block is called something else passes its own id. */
function dimensionTiles(g, extras = [], { at = "works", label = "works", score = null } = {}) {
  const kinds = ["movie", "tv_show", "game"].filter((k) => g.by_type[k]);
  const to = (type) => pageHashWith({ at, type: type || null });
  const tiles = [statTile("Works", String(g.n_works), to(), "See the " + label)];
  // Only break down by medium when there is actually more than one — otherwise the
  // breakdown tile just repeats the total.
  if (kinds.length > 1)
    for (const k of kinds) tiles.push(statTile(TYPE[k].label, String(g.by_type[k]), to(k), `Just the ${TYPE[k].noun}`));
  if (g.gross) tiles.push(statTile("Combined gross", money(g.gross), to(), "The works it adds up"));
  // An outlet's mean averages the scores it filed, not the works — so it lands on those.
  if (g.avg_pct != null)
    tiles.push(statTile("Mean score", pct(g.avg_pct) + " / 100", score?.hash || to(), score?.note || "The works it averages"));
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
  frag.appendChild(worksSection("Works", g.works, { render: (list) => worksOfTable(list, { showFranchise: false }) }));

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
            { key: "l", label: "Relation", cell: (r) => facetLink("relation", r.label) },
            { key: "b", label: "Other work", cell: (r) => workLink(r.to, false) },
          ],
          links.sort((a, b) => (a.from.year ?? 0) - (b.from.year ?? 0) || a.label.localeCompare(b.label)),
          { plain: true }
        )
      )
    );
  }

  frag.appendChild(
    tallySection("Characters across this franchise", g.works, (w) => w.characters.map((c) => c.identity_id), (id) => "#/character/" + id, {
      max: 40,
      unit: "work",
      label: (id) => charById.get(id)?.name || "—",
    })
  );
  frag.appendChild(
    tallySection("Most credited here", g.works, creditedPeople, (id) => "#/person/" + id, { max: 24, label: personName })
  );
  frag.appendChild(
    tallySection("Studios behind it", g.works, (w) => w.studios.map((st) => st.name), (n) => "#/studio/" + encodeURIComponent(n), { max: 24 })
  );
  return frag;
}

function viewStudio(name) {
  const g = studioIndex.get(name);
  if (!g) return el("div", { class: "empty-state", text: "Unknown studio." });
  const frag = document.createDocumentFragment();
  frag.append(...dimensionHead(g, "Studio", "studios", "All studios", el("span", { text: [...g.roles].sort().join(" · ") })));
  frag.appendChild(dimensionTiles(g));

  /* Who owns it and where it is — the two columns that were NULL for every studio
     until v4, plus what else Wikidata knows about it. */
  const sd = (DATA.studio_details || {})[name];
  const st = g.works.flatMap((w) => w.studios).find((x) => x.name === name) || {};
  const sFacts = [];
  const addSFact = (k, v) => v && sFacts.push(el("div", null, el("div", { class: "k", text: k }), el("div", { class: "v" }, v)));
  addSFact("Country", st.country && findLink(st.country));
  addSFact("Parent company", st.parent && (studioIndex.has(st.parent) ? softLink(st.parent, "#/studio/" + encodeURIComponent(st.parent)) : findLink(st.parent)));
  addSFact("Industry", sd?.industry && findLink(sd.industry));
  addSFact("Headquarters", sd?.headquarters && findLink(sd.headquarters));
  addSFact("Founded", sd?.inception && dateLink(sd.inception));
  addSFact("Dissolved", sd?.dissolved && dateLink(sd.dissolved));
  if (sFacts.length) frag.appendChild(section("Details", null, el("div", { class: "card deflist" }, sFacts)));

  frag.appendChild(worksSection("Works", g.works));

  frag.appendChild(
    tallySection("Frequent co-credits", g.works, (w) => w.studios.map((st) => st.name).filter((n) => n !== g.name), (n) => "#/studio/" + encodeURIComponent(n), { max: 24 })
  );
  frag.appendChild(
    tallySection("People credited on these works", g.works, creditedPeople, (id) => "#/person/" + id, { max: 24, label: personName })
  );
  frag.appendChild(
    tallySection("Characters it has put on screen", g.works, (w) => w.characters.map((c) => c.identity_id), (id) => "#/character/" + id, { max: 30, label: (id) => charById.get(id)?.name || "—" })
  );
  frag.appendChild(
    tallySection("Franchises worked in", g.works, (w) => (w.franchise ? [w.franchise] : []), (n) => "#/franchise/" + encodeURIComponent(n), { max: 20 })
  );
  return frag;
}

function viewPlatform(name) {
  const g = platformIndex.get(name);
  if (!g) return el("div", { class: "empty-state", text: "Unknown platform." });
  const frag = document.createDocumentFragment();
  frag.append(...dimensionHead(g, "Platform", "platforms", "All platforms"));
  /* A platform's works are all games, so the medium breakdown never applies and every tile
     is answered by one block: the release table, which carries the dates and the scores. */
  const toReleases = pageHashWith({ at: "releases" });
  const extras = [];
  const pd = (DATA.platform_details || {})[name];
  if (pd?.manufacturer) extras.push(statTile("Made by", pd.manufacturer, findHash(pd.manufacturer)));
  if (g.avg_metacritic != null) extras.push(statTile("Mean Metacritic", String(Math.round(g.avg_metacritic)), toReleases, "The scores it averages"));
  if (g.releases.length) extras.push(statTile("Release rows", String(g.releases.length), toReleases, "One row per dated release"));
  frag.appendChild(dimensionTiles(g, extras, { at: "releases", label: "games" }));

  /* The hardware's own lifespan. Not tiles: a tile is a number you can open, and
     these two open nothing — the catalogue has no page for a hardware launch. */
  if (pd?.released || pd?.discontinued || pd?.developer) {
    const pFacts = [];
    const addPFact = (k, v) => v && pFacts.push(el("div", null, el("div", { class: "k", text: k }), el("div", { class: "v" }, v)));
    addPFact("Released", pd.released && dateLink(pd.released));
    addPFact("Discontinued", pd.discontinued && dateLink(pd.discontinued));
    addPFact("Developed by", pd.developer && findLink(pd.developer));
    frag.appendChild(section("The hardware", null, el("div", { class: "card deflist" }, pFacts)));
  }

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

  const gamesOnly = g.works.filter((w) => !g.releases.some((r) => r.work === w));
  if (g.releases.length) {
    frag.appendChild(
      anchor("releases", section(
        "Releases",
        g.releases.length,
        table(
          [
            { key: "t", label: "Game", cell: (r) => workLink(r.work, false) },
            { key: "d", label: "Date", cell: (r) => dateLink(r.date) },
            { key: "p", label: "Publisher", wrap: true, cell: (r) => nameLinks(r.publisher, "studio") },
            { key: "v", label: "Developer", wrap: true, cell: (r) => nameLinks(r.developer, "studio") },
            { key: "m", label: "Metacritic", num: true, cell: (r) => (r.metacritic == null ? dash() : String(r.metacritic)) },
            { key: "e", label: "ESRB", cell: (r) => (r.esrb ? facetLink("esrb", r.esrb) : dash()) },
          ],
          [...g.releases].sort((a, b) => String(a.date || "9").localeCompare(String(b.date || "9"))),
          { plain: true }
        ),
        gamesOnly.length
          ? el("div", { class: "sub", style: { marginTop: "8px" }, text: `${gamesOnly.length} more game${gamesOnly.length === 1 ? " is" : "s are"} listed on this platform without a dated release row — they follow below.` })
          : null
      ))
    );
  }
  if (gamesOnly.length) {
    const more = section("Also listed on this platform", gamesOnly.length, worksOfTable(gamesOnly));
    // With no release table above it, this block is the one every tile is pointing at.
    frag.appendChild(g.releases.length ? more : anchor("releases", more));
  }

  const houses = new Map();
  for (const r of g.releases) {
    for (const field of [r.developer, r.publisher]) {
      if (!field) continue;
      for (const part of splitNames(field)) houses.set(part.name, (houses.get(part.name) || 0) + 1);
    }
  }
  if (houses.size) {
    frag.appendChild(
      section(
        "Who shipped them",
        houses.size,
        el(
          "div",
          { class: "chip-list" },
          [...houses.entries()]
            .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
            .map(([n, c]) => {
              const st = studioByName.get(normName(n));
              return dimChip(n, st ? "#/studio/" + encodeURIComponent(st) : findHash(n), `${c} release${c === 1 ? "" : "s"}`);
            })
        )
      )
    );
  }
  frag.appendChild(
    tallySection("Franchises on this platform", g.works, (w) => (w.franchise ? [w.franchise] : []), (n) => "#/franchise/" + encodeURIComponent(n), { max: 20, unit: "game" })
  );
  frag.appendChild(
    tallySection("Characters playable or present", g.works, (w) => w.characters.map((c) => c.identity_id), (id) => "#/character/" + id, { max: 30, unit: "game", label: (id) => charById.get(id)?.name || "—" })
  );
  return frag;
}

/* ============================================================
   OUTLETS · COMICS · AWARDS · ROLES
   The four dimensions the Analysis charts stand on, each browsable in its own right.
   ============================================================ */

const viewPublications = dimensionListView({
  view: "publications",
  title: "Outlets",
  blurb: "Every publication that scored something in this catalogue, with what it scored and how generously. Scores are normalized to 0–100 before anything is averaged.",
  index: publicationIndex,
  columns: [
    { key: "name", label: "Outlet", asc: true, value: (g) => g.name.toLowerCase(), cell: (g) => el("button", { class: "row-link", text: g.name, onclick: () => go("#/publication/" + encodeURIComponent(g.name)) }) },
    { key: "n", label: "Scores", num: true, value: (g) => g.n, cell: (g) => String(g.n) },
    { key: "n_works", label: "Works", num: true, value: (g) => g.n_works, cell: (g) => String(g.n_works) },
    { key: "avg_pct", label: "Mean", num: true, value: (g) => g.avg_pct, cell: (g) => pct(g.avg_pct) },
    { key: "range", label: "Range", num: true, value: (g) => g.hi - g.lo, cell: (g) => `${Math.round(g.lo)}–${Math.round(g.hi)}` },
    { key: "span", label: "Span", num: true, asc: true, value: (g) => g.first_year ?? 9999, cell: (g) => spanText(g) },
  ],
});

const viewComics = dimensionListView({
  view: "comics",
  title: "Comic sources",
  blurb: "The comics the screen has drawn on. A storyline listed here was cited as source material by at least one work in the catalogue.",
  index: comicIndex,
  columns: [
    { key: "name", label: "Comic", asc: true, wrap: true, value: (g) => g.title.toLowerCase(), cell: (g) => el("button", { class: "row-link", text: g.title, onclick: () => go("#/comic/" + encodeURIComponent(g.title)) }) },
    { key: "year", label: "Published", num: true, asc: true, value: (g) => g.year ?? 9999, cell: (g) => yearLink(g.year) },
    { key: "writer", label: "Credited to", wrap: true, asc: true, value: (g) => (g.writer || "~").toLowerCase(), cell: (g) => nameLinks(g.writer) },
    { key: "n_works", label: "Adapted by", num: true, value: (g) => g.n_works, cell: (g) => String(g.n_works) },
    { key: "span", label: "On screen", num: true, asc: true, value: (g) => g.first_year ?? 9999, cell: (g) => spanText(g) },
  ],
});

const ROLE_LABELS = {
  writer: "writer", author: "author", penciller: "penciller", inker: "inker",
  colorist: "colourist", letterer: "letterer", cover_artist: "cover artist",
  illustrator: "illustrator", editor: "editor", creator: "creator",
};
const roleText = (r) => ROLE_LABELS[r] || r.replace(/_/g, " ");

const comicSpan = (g) =>
  g.comic_first_year == null ? "—" : g.comic_first_year === g.comic_last_year ? String(g.comic_first_year) : `${g.comic_first_year}–${g.comic_last_year}`;

const viewCreators = dimensionListView({
  view: "creators",
  title: "Comic creators",
  blurb:
    "The writers and artists behind the comics this catalogue adapts — every credit Wikidata files on those issues, down to the letterer. “Adapted by” counts the screen works citing a comic this person worked on.",
  index: creatorIndex,
  columns: [
    { key: "name", label: "Creator", asc: true, value: (g) => g.name_l, cell: (g) => el("button", { class: "row-link", text: g.name, onclick: () => go("#/creator/" + g.id) }) },
    { key: "roles", label: "Credited as", wrap: true, asc: true, value: (g) => g.roles.join(" "), cell: (g) => el("span", { class: "names" }, g.roles.flatMap((r, i) => [i ? el("span", { class: "sep", text: "·" }) : null, findLink(roleText(r))])) },
    { key: "n_comics", label: "Comics", num: true, value: (g) => g.n_comics, cell: (g) => String(g.n_comics) },
    { key: "comic_span", label: "Working", num: true, asc: true, value: (g) => g.comic_first_year ?? 9999, cell: (g) => comicSpan(g) },
    { key: "n_works", label: "Adapted by", num: true, value: (g) => g.n_works, cell: (g) => String(g.n_works) },
    { key: "screen", label: "Screen credit", value: (g) => (g.person_id ? "1" : "0"), cell: (g) => (g.person_id ? personLink(g.person_id) : dash()) },
  ],
});

function comicRowLink(c) {
  return el("button", { class: "row-link", text: c.title, onclick: () => go("#/comicrow/" + c.id) });
}

/* One comic issue, series or storyline as v4 resolved it — distinct from the
   citation-string page at #/comic/<title>, which groups every work that cited it. */
function viewComicRow(id) {
  const c = comicById.get(Number(id));
  if (!c) return el("div", { class: "empty-state", text: "Unknown comic." });
  const frag = document.createDocumentFragment();
  frag.appendChild(backLink("All comic sources", listHash("comics")));
  frag.appendChild(
    el("div", { class: "detail-head" },
      el("h1", { text: c.title }),
      el("div", { class: "meta-line" },
        el("span", { class: "badge", text: c.kind === "series" ? "Comic series" : c.kind === "storyline" ? "Storyline" : "Comic issue" }),
        c.year ? yearLink(c.year) : null,
        c.publisher ? findLink(c.publisher) : null,
        c.series ? el("span", null, "in ", comicRowLink(c.series)) : null),
      c.origin === "parsed"
        ? el("div", { class: "note", style: { marginTop: "10px" },
            text: "Read out of the citation that names it — Wikidata has no item for this issue, so it carries a series and a number but no date, publisher or credits." })
        : null)
  );

  const tiles = [];
  if (c.date) tiles.push(statTile("Published", c.date, yearHas(c.year) ? "#/year/" + c.year : null));
  if (c.issue != null) tiles.push(statTile("Issue", "#" + c.issue));
  if (c.credits.length) tiles.push(statTile("Credits", String(c.credits.length), atHash("credits")));
  if (c.works.length) tiles.push(statTile("Adapted by", String(c.works.length), atHash("works")));
  if (tiles.length) frag.appendChild(el("div", { class: "kpis", style: { marginTop: "16px" } }, tiles));

  if (c.credits.length) {
    const byRole = new Map();
    for (const x of c.credits) {
      if (!byRole.has(x.role)) byRole.set(x.role, []);
      byRole.get(x.role).push(x.creator);
    }
    frag.appendChild(
      anchor("credits", section("Credits", c.credits.length,
        table(
          [
            { key: "r", label: "Role", cell: (row) => findLink(roleText(row.role)) },
            { key: "n", label: "Credited", wrap: true, cell: (row) => el("span", { class: "names" }, row.people.flatMap((p, i) => [i ? el("span", { class: "sep", text: "·" }) : null, el("button", { class: "row-link", text: p.name, onclick: () => go("#/creator/" + p.id) })])) },
          ],
          [...byRole.entries()].map(([role, people]) => ({ role, people })),
          { plain: true }
        )))
    );
  }

  if (c.characters.length) {
    const chars = c.characters.map((cid) => charById.get(cid)).filter(Boolean);
    if (chars.length)
      frag.appendChild(
        section("Characters in it", chars.length,
          el("div", { class: "chip-list" },
            chars.map((ch) => el("button", { class: "chip", text: ch.name, onclick: () => go("#/character/" + ch.id) }))))
      );
  }

  const debutants = characters.filter((ch) => ch.debut_comic_id === c.id);
  if (debutants.length)
    frag.appendChild(
      section("First appeared here", debutants.length,
        el("div", { class: "chip-list" },
          debutants.map((ch) => el("button", { class: "chip", text: ch.name, onclick: () => go("#/character/" + ch.id) }))))
    );

  if (c.works.length) frag.appendChild(worksSection("Adapted by", c.works));

  if (c.kind === "series") {
    const issues = comicRows.filter((x) => x.series_id === c.id).sort((a, b) => (a.issue ?? 0) - (b.issue ?? 0));
    if (issues.length)
      frag.appendChild(
        section("Issues in the dataset", issues.length,
          table(
            [
              { key: "i", label: "Issue", num: true, cell: (x) => (x.issue == null ? dash() : "#" + x.issue) },
              { key: "t", label: "Title", cell: (x) => comicRowLink(x) },
              { key: "d", label: "Published", num: true, cell: (x) => dateLink(x.date) },
              { key: "n", label: "Adapted by", num: true, cell: (x) => String(x.works.length) },
              { key: "o", label: "From", cell: (x) => el("span", { class: "muted", text: x.origin === "parsed" ? "citation" : "Wikidata" }) },
            ],
            issues,
            { plain: true, scroll: true }
          ))
      );
  }
  return frag;
}

function viewCreator(id) {
  const cr = creatorById.get(Number(id));
  if (!cr) return el("div", { class: "empty-state", text: "Unknown creator." });
  const frag = document.createDocumentFragment();
  /* `dimensionHead` prints the span of the *works* — for a creator that is when the
     screen got round to their comics, which sits confusingly next to the years they
     were drawing. Say which one it is. */
  frag.append(...dimensionHead(cr, "Comic creator", "creators", "All comic creators",
    el("span", null,
      cr.works.length ? el("span", { class: "muted", text: "adapted on screen" }) : null,
      cr.person_id ? el("span", null, " · also on screen: ", personLink(cr.person_id)) : null)));

  const extras = [];
  extras.push(statTile("Comics", String(cr.n_comics), atHash("comics")));
  if (cr.comic_first_year) extras.push(statTile("Working in comics", comicSpan(cr)));
  if (cr.birth) extras.push(statTile("Born", cr.birth.slice(0, 4)));
  /* `dimensionTiles` leads with a Works tile pointing at the works block. Plenty of
     creators have none — their comics are in the dataset but nothing on screen cites
     them — and that tile would link to a block this page never renders. */
  frag.appendChild(
    cr.works.length
      ? dimensionTiles(cr, extras, { label: "adaptations" })
      : el("div", { class: "kpis", style: { marginTop: "16px" } },
          extras,
          statTile("Adapted by", "none", null, "No work in the catalogue cites a comic they worked on"))
  );

  /* One row per comic, not per credit: Ditko pencilled, inked and drew the cover of
     the same issue, and three identical rows say less than one row naming all three. */
  const byComic = new Map();
  for (const x of cr.credits) {
    if (!byComic.has(x.comic.id)) byComic.set(x.comic.id, { comic: x.comic, roles: [] });
    byComic.get(x.comic.id).roles.push(x.role);
  }
  const comicRowsFor = [...byComic.values()].sort(
    (a, b) => (a.comic.year ?? 9999) - (b.comic.year ?? 9999) ||
              (a.comic.issue ?? 0) - (b.comic.issue ?? 0) ||
              a.comic.title.localeCompare(b.comic.title));
  frag.appendChild(
    anchor("comics", section("Comics credited on", cr.n_comics,
      table(
        [
          { key: "t", label: "Comic", cell: (x) => comicRowLink(x.comic) },
          { key: "y", label: "Published", num: true, cell: (x) => (x.comic.year ? yearLink(x.comic.year) : dash()) },
          { key: "r", label: "As", wrap: true, cell: (x) => el("span", { class: "names" }, x.roles.flatMap((r, i) => [i ? el("span", { class: "sep", text: "·" }) : null, findLink(roleText(r))])) },
          { key: "a", label: "Adapted by", num: true, cell: (x) => String(x.comic.works.length) },
        ],
        comicRowsFor,
        { plain: true, scroll: true }
      )))
  );

  if (cr.works.length) frag.appendChild(worksSection("Screen works drawing on their comics", cr.works));
  return frag;
}

const viewAwards = dimensionListView({
  view: "awards",
  title: "Awarding bodies",
  blurb: "Every body that has handed this catalogue a nomination, and how often it followed through.",
  index: awardBodies,
  columns: [
    { key: "name", label: "Body", asc: true, value: (g) => g.name.toLowerCase(), cell: (g) => el("button", { class: "row-link", text: g.name, onclick: () => go("#/award/" + encodeURIComponent(g.name)) }) },
    { key: "won", label: "Won", num: true, value: (g) => g.won, cell: (g) => String(g.won) },
    { key: "nominated", label: "Nominated", num: true, value: (g) => g.nominated, cell: (g) => String(g.nominated) },
    { key: "n_awards", label: "Records", num: true, value: (g) => g.rows.length, cell: (g) => String(g.rows.length) },
    { key: "n_works", label: "Works", num: true, value: (g) => g.n_works, cell: (g) => String(g.n_works) },
    { key: "span", label: "Span", num: true, asc: true, value: (g) => g.first_year ?? 9999, cell: (g) => spanText(g) },
  ],
});

const viewRoles = dimensionListView({
  view: "roles",
  title: "Credit roles",
  blurb: "Every job title the credit tables use — from “actor” to “theme lyricist” — and the people who held it.",
  index: roleIndex,
  columns: [
    { key: "name", label: "Role", asc: true, value: (g) => g.name.toLowerCase(), cell: (g) => el("button", { class: "row-link", text: g.name, onclick: () => go("#/role/" + encodeURIComponent(g.name)) }) },
    { key: "n_people", label: "People", num: true, value: (g) => g.n_people, cell: (g) => String(g.n_people) },
    { key: "n_credits", label: "Credits", num: true, value: (g) => g.credits.length, cell: (g) => String(g.credits.length) },
    { key: "n_works", label: "Works", num: true, value: (g) => g.n_works, cell: (g) => String(g.n_works) },
    { key: "span", label: "Span", num: true, asc: true, value: (g) => g.first_year ?? 9999, cell: (g) => spanText(g) },
  ],
});

function viewPublication(name) {
  const g = publicationIndex.get(name);
  if (!g) return el("div", { class: "empty-state", text: "Unknown outlet." });
  const frag = document.createDocumentFragment();
  frag.append(...dimensionHead(g, "Outlet", "publications", "All outlets"));
  /* Two blocks answer this page: the scores it filed, and the works those scores are on.
     "Mean score" and the medium breakdown come from `dimensionTiles`, so the extras here are
     only what is true of the scores themselves. */
  const toScores = pageHashWith({ at: "scores" });
  frag.appendChild(
    dimensionTiles(
      g,
      [
        statTile("Scores on record", String(g.n), toScores, "Every score it filed"),
        statTile("Range", `${Math.round(g.lo)}–${Math.round(g.hi)}`, toScores, "Lowest and highest it gave"),
      ],
      { label: "works it scored", score: { hash: toScores, note: "The scores it averages" } }
    )
  );

  const scored = [...g.scores].sort((a, b) => b.pct - a.pct);
  if (scored.length >= 3) {
    frag.appendChild(
      el("div", { class: "grid", style: { marginTop: "16px" } },
        hbarChart({
          title: `What ${g.name} scored`,
          sub: "Every score this outlet filed, normalized to 0–100, highest first.",
          items: scored.map((r) => ({ label: r.work.title, value: Math.round(r.pct), display: Math.round(r.pct) + " / 100", key: r.work.id, sub: [r.scope, r.max ? `raw ${r.score}/${r.max}` : null].filter(Boolean).join(" · ") || null })),
          onPick: (d) => go("#/work/" + d.key),
          labelWidth: 240,
          maxRows: 24,
          valueLabel: "Score",
          tableCols: [
            { key: "w", label: "Work", cell: (d) => el("button", { class: "row-link", text: d.label, onclick: () => go("#/work/" + d.key) }) },
            { key: "s", label: "Normalized", num: true, cell: (d) => String(d.value) },
            { key: "n", label: "As filed", cell: (d) => d.sub || "—" },
          ],
        }))
    );
  }

  frag.appendChild(
    anchor("scores", section(
      "Scores",
      g.scores.length,
      table(
        [
          { key: "w", label: "Work", cell: (r) => workLink(r.work, false) },
          { key: "y", label: "Year", num: true, cell: (r) => yearLink(r.work.year, yr(r.work)) },
          { key: "m", label: "Medium", cell: (r) => typeBadge(r.work.type) },
          { key: "sc", label: "Scope", cell: (r) => (r.scope ? findLink(r.scope) : dash()) },
          { key: "raw", label: "Raw", num: true, cell: (r) => (r.max ? `${r.score} / ${r.max}` : String(r.score)) },
          { key: "n", label: "Normalized", num: true, cell: (r) => pct(r.pct) },
          { key: "d", label: "Against the mean", num: true, cell: (r) => (r.work.avg_pct == null ? dash() : (r.pct - r.work.avg_pct >= 0 ? "+" : "") + Math.round(r.pct - r.work.avg_pct)) },
        ],
        [...g.scores].sort((a, b) => (a.work.year ?? 9999) - (b.work.year ?? 9999)),
        { plain: true }
      ),
      el("div", { class: "sub", style: { marginTop: "8px" }, text: "“Against the mean” is this outlet's score minus the average of every normalized score the work carries — how far out of step this outlet was on that title." })
    ))
  );
  frag.appendChild(worksSection("Works scored", g.works));
  return frag;
}

function viewComic(title) {
  const g = comicIndex.get(title);
  if (!g) return el("div", { class: "empty-state", text: "Unknown comic." });
  const frag = document.createDocumentFragment();
  frag.append(...dimensionHead(g, "Comic source", "comics", "All comic sources", g.year ? yearLink(g.year) : null));
  const lags = g.uses.filter((u) => u.year && u.work.year).map((u) => u.work.year - u.year);
  frag.appendChild(
    dimensionTiles(g, [
      g.writer ? statTile("Credited to", g.writer.length > 24 ? g.writer.slice(0, 23) + "…" : g.writer, findHash(g.writer)) : null,
      lags.length ? statTile("First adapted after", Math.min(...lags) + " yrs", atHash("adaptation-lag", "#/analysis"), "See it on the comic-to-screen chart") : null,
      g.resolved.length ? statTile("Issues behind it", String(g.resolved.length), atHash("issues"), "The comics this citation resolves to") : null,
    ].filter(Boolean), { label: "adaptations" })
  );

  /* The citation is a string; these are the comics it turned out to name. */
  if (g.resolved.length) {
    const issues = [...g.resolved].sort(
      (a, b) => (a.year ?? 9999) - (b.year ?? 9999) || (a.issue ?? 0) - (b.issue ?? 0));
    frag.appendChild(
      anchor("issues", section("Issues behind this citation", issues.length,
        table(
          [
            { key: "t", label: "Comic", cell: (c) => comicRowLink(c) },
            { key: "d", label: "Published", num: true, cell: (c) => (c.date ? dateLink(c.date) : yearLink(c.year)) },
            { key: "p", label: "Publisher", cell: (c) => (c.publisher ? findLink(c.publisher) : dash()) },
            { key: "c", label: "Made by", wrap: true, cell: (c) => {
              const w = c.credits.filter((x) => x.role === "writer" || x.role === "author");
              return w.length
                ? el("span", { class: "names" }, w.flatMap((x, i) => [i ? el("span", { class: "sep", text: "·" }) : null, el("button", { class: "row-link", text: x.creator.name, onclick: () => go("#/creator/" + x.creator.id) })]))
                : dash();
            } },
            { key: "o", label: "From", cell: (c) => el("span", { class: "muted", text: c.origin === "parsed" ? "citation" : "Wikidata" }) },
          ],
          issues,
          { plain: true, scroll: true }
        ),
        el("div", { class: "sub", style: { marginTop: "8px" },
          text: "“Wikidata” rows carry a publication date and full credits. “citation” rows are issues named by the source material that Wikidata has no item for — the series and number are real, the rest is unknown." })))
    );
  }

  frag.appendChild(
    worksSection("Adapted by", g.uses, {
      workOf: (u) => u.work,
      render: (uses) =>
        table(
          [
            { key: "w", label: "Work", cell: (u) => workLink(u.work, false) },
            { key: "y", label: "Released", num: true, cell: (u) => yearLink(u.work.year, yr(u.work)) },
            { key: "m", label: "Medium", cell: (u) => typeBadge(u.work.type) },
            { key: "i", label: "Issues cited", wrap: true, cell: (u) => (u.issues ? findLink(u.issues) : dash()) },
            { key: "a", label: "Arc", wrap: true, cell: (u) => (u.arc ? findLink(u.arc) : dash()) },
            { key: "l", label: "Wait", num: true, cell: (u) => (u.year && u.work.year ? `${u.work.year - u.year} yrs` : dash()) },
          ],
          [...uses].sort((a, b) => (a.work.year ?? 9999) - (b.work.year ?? 9999)),
          { plain: true }
        ),
    })
  );

  /* Characters this storyline puts on screen — the readers' route from a comic to a face. */
  const chars = new Map();
  for (const u of g.uses) for (const wc of u.work.characters) chars.set(wc.identity_id, (chars.get(wc.identity_id) || 0) + 1);
  const charRows = [...chars.entries()].map(([id, n]) => ({ c: charById.get(id), n })).filter((x) => x.c).sort((a, b) => b.n - a.n || a.c.name.localeCompare(b.c.name));
  if (charRows.length) {
    frag.appendChild(
      section(
        "On screen in these adaptations",
        charRows.length,
        el("div", { class: "chip-list" }, charRows.slice(0, 40).map((x) => charChip({ identity_id: x.c.id, name: x.c.name, alignment: x.c.alignment })))
      )
    );
  }
  return frag;
}

function viewAward(name) {
  const g = awardBodies.get(name);
  if (!g) return el("div", { class: "empty-state", text: "Unknown awarding body." });
  const frag = document.createDocumentFragment();
  frag.append(...dimensionHead(g, "Awarding body", "awards", "All awarding bodies"));
  /* The two result tiles cut the record table rather than sitting inert: the number on the
     tile and the number of rows you land on are the same number. */
  const toRecords = (result) => pageHashWith({ at: "records", result: result || null });
  frag.appendChild(
    dimensionTiles(g, [
      statTile("Won", String(g.won), toRecords("won"), "Just the wins"),
      statTile("Nominated, did not win", String(g.nominated), toRecords("nominated"), "Just the nominations"),
    ], { label: "works it recognised" })
  );
  const result = ["won", "nominated"].includes(paramOf("result")) ? paramOf("result") : "all";
  const shownRows = result === "all" ? g.rows : g.rows.filter((a) => (result === "won" ? a.result === "won" : a.result !== "won"));
  frag.appendChild(
    anchor("records", section(
      "Every record",
      shownRows.length,
      el("div", { class: "filters section-filters" },
        chips(
          [
            { value: "all", label: "All", n: g.rows.length },
            { value: "won", label: "Won", n: g.won },
            { value: "nominated", label: "Nominated", n: g.nominated },
          ],
          result,
          (v) => go(toRecords(v === "all" ? null : v))
        )),
      table(
        [
          { key: "y", label: "Year", num: true, cell: (a) => yearLink(a.year) },
          { key: "w", label: "Work", cell: (a) => workLink(a.work, false) },
          { key: "c", label: "Category", wrap: true, cell: (a) => findLink(a.category) },
          { key: "r", label: "Result", cell: (a) => (a.result === "won" ? el("strong", { text: "Won" }) : el("span", { class: "muted", text: "Nominated" })) },
          { key: "p", label: "Recipient", cell: (a) => (a.person_id ? personLink(a.person_id) : dash()) },
        ],
        [...shownRows].sort((a, b) => (a.year ?? 0) - (b.year ?? 0)),
        { plain: true }
      )
    ))
  );
  frag.appendChild(section("Categories", g.categories.length, el("div", { class: "chip-list" }, g.categories.map((c) => dimChip(c, findHash(c))))));
  frag.appendChild(worksSection("Works recognised", g.works));
  return frag;
}

function viewRole(name) {
  const g = roleIndex.get(name);
  if (!g) return el("div", { class: "empty-state", text: "Unknown role." });
  const frag = document.createDocumentFragment();
  frag.append(...dimensionHead(g, "Credit role", "roles", "All credit roles"));
  const toHolders = pageHashWith({ at: "holders" });
  frag.appendChild(
    dimensionTiles(g, [
      statTile("People", String(g.n_people), toHolders, "Everyone who holds it"),
      statTile("Credits", String(g.credits.length), toHolders, "Counted once per person per work"),
    ], { label: "works with this credit" })
  );

  const byPerson = new Map();
  for (const c of g.credits) {
    const p = personById.get(c.person_id);
    if (!p) continue;
    const e = groupInto(byPerson, p.id, () => ({ person: p, works: [] }));
    if (!e.works.includes(c.work)) e.works.push(c.work);
  }
  const holders = [...byPerson.values()].sort((a, b) => b.works.length - a.works.length || a.person.name.localeCompare(b.person.name));

  if (holders.length >= 3) {
    frag.appendChild(
      el("div", { class: "grid", style: { marginTop: "16px" } },
        hbarChart({
          title: `Most credited as ${g.name}`,
          sub: "Works each person holds this credit on.",
          items: holders.map((h) => ({ label: h.person.name, value: h.works.length, key: h.person.id, sub: h.person.roles.filter((r) => r !== g.name).slice(0, 3).join(", ") || null })),
          onPick: (d) => go("#/person/" + d.key),
          labelWidth: 220,
          valueLabel: "Works",
          tableCols: [
            { key: "p", label: "Person", cell: (d) => el("button", { class: "row-link", text: d.label, onclick: () => go("#/person/" + d.key) }) },
            { key: "n", label: "Works", num: true, cell: (d) => String(d.value) },
            { key: "r", label: "Other roles", wrap: true, cell: (d) => d.sub || "—" },
          ],
        }))
    );
  }

  frag.appendChild(
    anchor("holders", section(
      "Everyone credited as " + g.name,
      holders.length,
      table(
        [
          { key: "p", label: "Person", cell: (h) => personLink(h.person.id) },
          { key: "n", label: "Works", num: true, cell: (h) => String(h.works.length) },
          { key: "w", label: "On", wrap: true, cell: (h) => el("span", { class: "chip-list" }, h.works.slice(0, 6).map((w) => el("button", { class: "chip", onclick: () => go("#/work/" + w.id) }, el("span", { class: "dot", style: { background: TYPE[w.type].color } }), w.title))) },
          { key: "o", label: "Other roles held", wrap: true, cell: (h) => el("span", { class: "names" }, h.person.roles.filter((r) => r !== g.name).slice(0, 4).flatMap((r, i) => [i ? el("span", { class: "sep", text: "·" }) : null, roleLink(r)]).filter(Boolean)) },
        ],
        holders,
        { plain: true }
      ),
      /* Both the People and the Credits tiles land here, and they are different numbers —
         say which is which rather than leaving the reader to reconcile them. */
      el("div", { class: "sub", style: { marginTop: "8px" },
        text: `${g.credits.length} credit row${g.credits.length === 1 ? "" : "s"} in the source name this role, held by ${g.n_people} ${g.n_people === 1 ? "person" : "people"} across ${g.n_works} work${g.n_works === 1 ? "" : "s"} — a person credited on three works accounts for three of them.` })
    ))
  );
  frag.appendChild(worksSection("Works with this credit", g.works));
  return frag;
}

/* ============================================================
   YEAR · FACET · FIND
   Three views that exist so no value in the catalogue is a dead end.
   ============================================================ */

function viewYear(raw) {
  const y = Number(raw);
  const b = yearIndex.get(y);
  if (!b) return el("div", { class: "empty-state", text: "Nothing in the catalogue is dated " + raw + "." });
  const frag = document.createDocumentFragment();
  frag.appendChild(backLink("All works", listHash("works")));
  const prev = [...yearIndex.keys()].filter((k) => k < y).sort((a, c) => c - a)[0];
  const next = [...yearIndex.keys()].filter((k) => k > y).sort((a, c) => a - c)[0];
  frag.appendChild(
    el(
      "div",
      { class: "detail-head" },
      el("h1", { text: String(y) }),
      el(
        "div",
        { class: "meta-line" },
        el("span", { class: "badge", text: "Year" }),
        prev ? softLink("← " + prev, "#/year/" + prev) : null,
        next ? softLink(next + " →", "#/year/" + next) : null,
        softLink("Filter the works list to " + y, `#/works?era=${y}`)
      )
    )
  );

  /* Every one of these numbers is listed in full further down this page, so the tiles jump
     there rather than to the catalogue-wide list of platforms, awards or comics. */
  const tiles = [];
  if (b.works.length) tiles.push(statTile("Released", String(b.works.length), `#/works?era=${y}`, "Filter the works list to " + y));
  if (b.debuts.length) tiles.push(jumpTile("Characters first seen", String(b.debuts.length), "y-debuts"));
  if (b.releases.length) tiles.push(jumpTile("Game releases", String(b.releases.length), "y-releases"));
  if (b.awards.length) tiles.push(jumpTile("Award records", String(b.awards.length), "y-awards"));
  if (b.comics.length) tiles.push(jumpTile("Comics later adapted", String(b.comics.length), "y-comics"));
  if (b.born.length) tiles.push(jumpTile("People born", String(b.born.length), "y-born"));
  if (tiles.length) frag.appendChild(el("div", { class: "kpis", style: { marginTop: "16px" } }, tiles));

  if (b.works.length) frag.appendChild(section("Released this year", b.works.length, worksOfTable(b.works)));

  if (b.debuts.length) {
    frag.appendChild(
      anchor("y-debuts", section(
        "First appeared on screen this year",
        b.debuts.length,
        el("div", { class: "chip-list" }, b.debuts.sort((a, c) => c.n_works - a.n_works).map((c) => charChip({ identity_id: c.id, name: c.name, alignment: c.alignment })))
      ))
    );
  }

  if (b.releases.length) {
    frag.appendChild(
      anchor("y-releases", section(
        "Game releases dated this year",
        b.releases.length,
        table(
          [
            { key: "w", label: "Game", cell: (r) => workLink(r.work, false) },
            { key: "p", label: "Platform", cell: (r) => (r.platform ? softLink(r.platform, "#/platform/" + encodeURIComponent(r.platform)) : dash()) },
            // Already on the year page, so the useful destination is the release table itself.
            { key: "d", label: "Date", cell: (r) => (r.date ? softLink(String(r.date), "#/work/" + r.work.id, { title: "All release rows for " + r.work.title }) : dash()) },
            { key: "pub", label: "Publisher", wrap: true, cell: (r) => nameLinks(r.publisher, "studio") },
            { key: "dev", label: "Developer", wrap: true, cell: (r) => nameLinks(r.developer, "studio") },
            { key: "m", label: "Metacritic", num: true, cell: (r) => (r.metacritic == null ? dash() : String(r.metacritic)) },
          ],
          [...b.releases].sort((a, c) => String(a.date).localeCompare(String(c.date))),
          { plain: true }
        )
      ))
    );
  }

  if (b.awards.length) {
    frag.appendChild(
      anchor("y-awards", section(
        "Awards decided this year",
        b.awards.length,
        table(
          [
            { key: "b", label: "Body", cell: (a) => softLink(a.body, "#/award/" + encodeURIComponent(a.body)) },
            { key: "w", label: "Work", cell: (a) => workLink(a.work, false) },
            { key: "c", label: "Category", wrap: true, cell: (a) => findLink(a.category) },
            { key: "r", label: "Result", cell: (a) => (a.result === "won" ? el("strong", { text: "Won" }) : el("span", { class: "muted", text: "Nominated" })) },
            { key: "p", label: "Recipient", cell: (a) => (a.person_id ? personLink(a.person_id) : dash()) },
          ],
          b.awards,
          { plain: true }
        )
      ))
    );
  }

  if (b.comics.length) {
    frag.appendChild(
      anchor("y-comics", section(
        "Comics published this year that the screen later used",
        b.comics.length,
        table(
          [
            { key: "c", label: "Comic", wrap: true, cell: (u) => comicLink(u.comic) },
            { key: "w", label: "Adapted in", cell: (u) => workLink(u.work, false) },
            { key: "y", label: "Released", num: true, cell: (u) => yearLink(u.work.year, yr(u.work)) },
            { key: "l", label: "Wait", num: true, cell: (u) => (u.work.year ? `${u.work.year - y} yrs` : dash()) },
          ],
          b.comics,
          { plain: true }
        )
      ))
    );
  }

  const peopleStrand = (label, list) =>
    list.length
      ? section(label, list.length, el("div", { class: "chip-list" }, list.map((p) => dimChip(p.name, "#/person/" + p.id, p.roles.slice(0, 2).join(", ") || null))))
      : null;
  const born = peopleStrand("People born this year", b.born);
  if (born) frag.appendChild(anchor("y-born", born));
  const died = peopleStrand("People who died this year", b.died);
  if (died) frag.appendChild(died);

  return frag;
}

function viewFacet(id) {
  const cut = String(id || "").indexOf("/");
  const key = cut < 0 ? id : id.slice(0, cut);
  const value = cut < 0 ? "" : id.slice(cut + 1);
  const facet = FACETS[key];
  if (!facet || !value) return el("div", { class: "empty-state", text: "Unknown attribute." });
  const index = facetIndex(key);
  const list = index.get(value) || [];
  if (!list.length) return el("div", { class: "empty-state", text: `Nothing in the catalogue has ${facet.label} “${value}”.` });

  const g = summarise({ name: value, works: list });
  const frag = document.createDocumentFragment();
  frag.appendChild(backLink("All works", listHash("works")));
  frag.appendChild(
    el(
      "div",
      { class: "detail-head" },
      el("h1", { text: facet.title(value) }),
      el("div", { class: "meta-line" }, el("span", { class: "badge", text: facet.label }), el("span", { text: spanText(g) })),
      el("div", { class: "note", style: { marginTop: "10px" }, text: `${facet.label} is a column in the source, not a table — this page is every work carrying the value “${value}”.` })
    )
  );
  frag.appendChild(dimensionTiles(g));

  /* Sideways: the other values this same column takes. */
  const siblings = [...index.entries()].filter(([v]) => v !== value).sort((a, b) => b[1].length - a[1].length || a[0].localeCompare(b[0]));
  frag.appendChild(worksSection("Works", list));
  if (siblings.length) {
    frag.appendChild(
      section(
        "Other " + facet.label.toLowerCase() + " values",
        siblings.length,
        el("div", { class: "chip-list" }, siblings.slice(0, 40).map(([v, ws]) => dimChip(v, facetHash(key, v), `${ws.length} work${ws.length === 1 ? "" : "s"}`)))
      )
    );
  }
  return frag;
}

function viewFind(q) {
  const query = String(q || "").trim();
  const groups = findEverywhere(query);
  const total = groups.reduce((a, g) => a + g.hits.length, 0);
  const frag = document.createDocumentFragment();
  frag.appendChild(backLink("Overview", "#/overview"));
  frag.appendChild(
    el(
      "div",
      { class: "page-head" },
      el("h1", { text: "“" + query + "”" }),
      el("p", {
        text: total
          ? `${total} place${total === 1 ? "" : "s"} in the catalogue mention this, across ${groups.length} kind${groups.length === 1 ? "" : "s"} of record. Free-text values in the source — a comic artist, an episode title, a rating — have no page of their own, so this is where they lead.`
          : "Nothing in the catalogue mentions this.",
      })
    )
  );
  if (!total) {
    frag.appendChild(el("div", { class: "table-wrap" }, el("div", { class: "empty-state", text: "No match." })));
    return frag;
  }
  for (const g of groups) {
    frag.appendChild(
      section(
        g.kind,
        g.hits.length,
        el(
          "div",
          { class: "chip-list" },
          g.hits.slice(0, 60).map((h) => dimChip(h.label, h.hash, h.sub || null))
        )
      )
    );
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
          { key: "c", label: "Comic", wrap: true, cell: (p) => comicLink(p.src.comic) },
          { key: "cy", label: "Published", num: true, cell: (p) => yearLink(p.src.year) },
          { key: "w", label: "Adapted in", cell: (p) => workLink(p.work, false) },
          { key: "wy", label: "Released", num: true, cell: (p) => yearLink(p.work.year) },
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
    const lbl = s("text", { x: -10, y: yTop + barH - 3, "text-anchor": "end", class: "tick", fill: "var(--text-secondary)", style: "cursor:pointer", text: b.name.length > 26 ? b.name.slice(0, 25) + "…" : b.name });
    lbl.addEventListener("click", () => go("#/award/" + encodeURIComponent(b.name)));
    g.appendChild(lbl);
    const hit = s("rect", { x: -M.l, y: i * rowH, width: W, height: rowH, fill: "transparent", style: "cursor:pointer", tabindex: "0", role: "button", "aria-label": `${b.name}: ${b.won} won, ${b.nominated} nominated` });
    hit.addEventListener("click", () => go("#/award/" + encodeURIComponent(b.name)));
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
          { key: "b", label: "Body", cell: (b) => softLink(b.name, "#/award/" + encodeURIComponent(b.name)) },
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
        onPick: (d) => go("#/publication/" + encodeURIComponent(d.key)),
        tableCols: [
          { key: "p", label: "Publication", cell: (d) => publicationLink(d.key, d.label) },
          { key: "a", label: "Mean score", num: true, cell: (d) => String(d.value) },
          { key: "s", label: "Spread", cell: (d) => d.sub },
        ],
      }),
      el("p", { class: "sub", style: { margin: "8px 2px 0" } },
        "Every outlet has a page of its own — ",
        el("button", { class: "linkish", text: "browse all " + publicationIndex.size + " →", onclick: () => go("#/publications") }))
    )
  );

  frag.appendChild(
    el("div", { class: "grid cols-2", style: { marginTop: "14px" } }, anchor("adaptation-lag", adaptationLagChart()), anchor("awards-chart", awardsChart()))
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
        onPick: (d) => go("#/comic/" + encodeURIComponent(d.key)),
        tableCols: [
          { key: "c", label: "Comic", wrap: true, cell: (d) => comicLink(d.key, d.label) },
          { key: "n", label: "Adapted by", num: true, cell: (d) => String(d.value) },
          { key: "w", label: "Credited to", wrap: true, cell: (d) => d.sub || "—" },
        ],
      }),
      el("p", { class: "sub", style: { margin: "8px 2px 0" } },
        "Each storyline opens onto the works that used it — ",
        el("button", { class: "linkish", text: "browse all " + comicIndex.size + " comic sources →", onclick: () => go("#/comics") }),
        comicCreators.length ? el("span", null, " · ",
          el("button", { class: "linkish", text: "or the " + comicCreators.length + " writers and artists behind them →", onclick: () => go("#/creators") })) : null)
    )
  );

  frag.appendChild(
    section(
      "Every award on record",
      allAwards.length,
      table(
        [
          { key: "w", label: "Work", cell: (a) => workLink(a.work, false) },
          { key: "b", label: "Body", cell: (a) => softLink(a.body, "#/award/" + encodeURIComponent(a.body)) },
          { key: "y", label: "Year", num: true, cell: (a) => yearLink(a.year) },
          { key: "c", label: "Category", wrap: true, cell: (a) => findLink(a.category) },
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
          { key: "c", label: "Comic", wrap: true, cell: (c) => comicLink(c.title) },
          { key: "y", label: "Published", num: true, cell: (c) => yearLink(c.year) },
          { key: "w", label: "Credited to", wrap: true, cell: (c) => nameLinks(c.writer) },
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

  frag.appendChild(browseSection("Browse the dimensions behind these charts"));

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
        linkTo(String(characters.length) + " distinct characters", "#/characters"),
        "; 61 of them have more than one spelling. Every character page here lists the spellings it absorbed, and each spelling opens the works that used it."
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
        ", ",
        linkTo("platforms", "#/platforms"),
        ", ",
        linkTo("outlets", "#/publications"),
        ", ",
        linkTo("comic sources", "#/comics"),
        ", ",
        linkTo("awarding bodies", "#/awards"),
        ", ",
        linkTo("credit roles", "#/roles"),
        " and ",
        linkTo("years", "#/year/" + DATA.meta.year_max),
        " are not tables you can browse in the source — they are grouped here from the columns that name them, so a studio page is every work that credits that name and an outlet page is every score it filed. Co-appearances, collaborators, work overlaps, adaptation lag and the outlet means on the ",
        linkTo("Analysis", "#/analysis"),
        " page are all computed in the browser from those same rows; none of them are stored figures."
      ),
      p(
        "Values that name nothing the catalogue holds a record for — a comic artist, an episode title, an ESRB rating — are not left inert either. Each one leads either to the works that share it or to a cross-column lookup, so every string on screen can be followed somewhere. ",
        linkTo("Try it on “Stan Lee” →", findHash("Stan Lee"))
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
      ),
      DATA.meta.provenance?.length ? provenanceSection() : null
    )
  );

  return frag;
}

/* Every row a later enrichment pass touched, honestly: which table, which outside source,
   and whether the row was new or an existing one filled in or corrected. Aggregated in the
   exporter from the v3_provenance table — one row there per (table, key, action). */
function provenanceSection() {
  const bySource = new Map();
  for (const r of DATA.meta.provenance) {
    const g = groupInto(bySource, r.source, () => ({
      name: r.source_name, url: r.source_url, licence: r.licence, retrieved: r.retrieved,
      tables: new Set(), inserted: 0, filled: 0, corrected: 0,
    }));
    g.tables.add(r.table);
    g[r.action === "insert" ? "inserted" : r.action === "fill" ? "filled" : "corrected"] += r.n;
  }
  return el(
    "div",
    { style: { display: "grid", gap: "10px" } },
    el("div", { style: { maxWidth: "820px" } }, table(
      [
        { key: "s", label: "Source", cell: (g) => (g.url ? el("a", { href: g.url, target: "_blank", rel: "noopener", text: g.name }) : g.name) },
        { key: "l", label: "Licence", cell: (g) => (g.licence ? findLink(g.licence) : dash()) },
        { key: "t", label: "Tables touched", num: true, cell: (g) => String(g.tables.size) },
        { key: "i", label: "New rows", num: true, cell: (g) => num(g.inserted) },
        { key: "f", label: "Filled / corrected", num: true, cell: (g) => num(g.filled + g.corrected) },
        { key: "r", label: "Retrieved", cell: (g) => g.retrieved || dash() },
      ],
      [...bySource.values()],
      { plain: true }
    )),
    el("p", { style: { color: "var(--text-secondary)", maxWidth: "78ch", fontSize: "13.5px" } },
      "“New rows” created a record the database did not have before — an award, an episode segment, a whole new join table. “Filled / corrected” means the row already existed and this source added a missing value or overwrote one.")
  );
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
  ...[...publicationIndex.values()].map((g) => ({ kind: "Outlets", label: g.name, sub: `${g.n} score${g.n === 1 ? "" : "s"}`, hash: "#/publication/" + encodeURIComponent(g.name), key: g.name.toLowerCase(), rank: 6 })),
  ...[...comicIndex.values()].map((g) => ({ kind: "Comic sources", label: g.title, sub: [g.writer, g.year].filter(Boolean).join(" · ") || `${g.n_works} adaptation${g.n_works === 1 ? "" : "s"}`, hash: "#/comic/" + encodeURIComponent(g.title), key: (g.title + " " + (g.writer || "")).toLowerCase(), rank: 7 })),
  ...[...awardBodies.values()].map((g) => ({ kind: "Awarding bodies", label: g.name, sub: `${g.won} won · ${g.nominated} nominated`, hash: "#/award/" + encodeURIComponent(g.name), key: (g.name + " " + g.categories.join(" ")).toLowerCase(), rank: 8 })),
  ...[...roleIndex.values()].map((g) => ({ kind: "Credit roles", label: g.name, sub: `${g.n_people} person${g.n_people === 1 ? "" : "s"}`.replace("persons", "people"), hash: "#/role/" + encodeURIComponent(g.name), key: g.name.toLowerCase(), rank: 9 })),
  ...[...yearIndex.keys()].sort((a, b) => a - b).map((y) => ({ kind: "Years", label: String(y), sub: `${yearIndex.get(y).works.length} release${yearIndex.get(y).works.length === 1 ? "" : "s"}`, hash: "#/year/" + y, key: String(y), rank: 10 })),
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
    const raw = input.value.trim();
    /* Whatever the index does or does not hold, there is always somewhere to go: the
       cross-dataset lookup reads the free-text columns the index never sees. */
    const everywhere = {
      kind: hits.length ? "Everywhere else" : "Look deeper",
      label: "Search every column for “" + raw + "”",
      sub: "free text too",
      hash: findHash(raw),
    };
    if (!hits.length) {
      box.appendChild(el("div", { class: "empty", text: "Nothing in the index matches “" + raw + "”." }));
    }
    let lastKind = null;
    for (const hit of [...hits, everywhere]) {
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
  const footLink = (text, hash) => el("button", { class: "linkish", text, onclick: () => go(hash) });
  document.getElementById("foot-line").replaceChildren(
    footLink(`${c.works} works`, "#/works"), " · ",
    footLink(`${c.characters} characters`, "#/characters"), " · ",
    footLink(`${c.people} people`, "#/people"), " · ",
    footLink(`${c.credits} credits`, "#/roles"), ", ",
    footLink(String(DATA.meta.year_min), "#/year/" + DATA.meta.year_min), "–",
    footLink(String(DATA.meta.year_max), "#/year/" + DATA.meta.year_max),
    ". Generated from spiderman.db. Data CC BY 4.0, code MIT."
  );
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
  loadDetails();
}

/* Outbound links, prose summaries and award lists live in a second file so the first
   paint only pays for the works/characters/people tables every reader loads. It arrives
   moments later and merges into the same objects the app already indexed, then
   re-renders whatever is on screen. A <script> tag (not fetch) keeps this working from
   a plain file:// open, exactly like data.js does. */
function loadDetails() {
  const tag = document.createElement("script");
  tag.src = "data-details.js";
  tag.onload = () => {
    const d = window.SPIDERMAN_DETAILS;
    if (!d) return;
    const merge = (index, entries) => {
      for (const [id, extra] of Object.entries(entries || {})) {
        const target = index.get(Number(id));
        if (target) Object.assign(target, extra);
      }
    };
    merge(workById, d.works);
    merge(personById, d.people);
    merge(charById, d.characters);
    rerenderInPlace();
  };
  document.body.appendChild(tag);
}

boot();
