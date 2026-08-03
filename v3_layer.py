#!/usr/bin/env python3
"""v3_layer.py — the additive v3 enrichment layer.

`apply(conn, cur)` is called by build_db_v2.py (only when SPIDERMAN_V3_LAYER is
set, which build_db_v3.py does) after the v2 database is complete and before the
CSVs are exported. It reads the JSON files under data_raw/v3/ written by the
fetch_* scripts, so it is offline and deterministic.

Two rules govern everything here, and the validation in build_db_v3.py enforces
both:

1. **Nothing v2 wrote is changed.** Existing rows are never updated except to
   fill a column that is NULL, and no row is ever deleted. A v2 consumer sees the
   same values it always saw, plus rows it did not have.
2. **No v2 table changes shape.** New attributes live in new tables, so
   `SELECT *` against a v2 table returns the same columns in the same order.

Every row this module adds is recorded in `v3_provenance`, which makes the v3
delta auditable — and lets anyone still on v2 semantics filter it back out.
"""
import json
import re
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
V3 = HERE / "data_raw" / "v3"

RETRIEVED = "2026-08-03"

SOURCES = [
    ("wikidata", "Wikidata", "https://www.wikidata.org/", "CC0-1.0"),
    ("wikipedia", "English Wikipedia", "https://en.wikipedia.org/", "CC BY-SA 4.0"),
]


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def load(name):
    p = V3 / name
    if not p.exists():
        return {}
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def norm_key(s):
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


class Labels:
    """QID -> English label, across every payload, with a readable fallback."""

    def __init__(self, *maps):
        self.m = {}
        for m in maps:
            for k, v in (m or {}).items():
                if v:
                    self.m[k] = v

    def get(self, qid, default=None):
        if not qid:
            return default
        return self.m.get(qid, default)

    def many(self, qids):
        return [x for x in (self.get(q) for q in (qids or [])) if x]


SCHEMA = """
-- ---------------------------------------------------------------------------
-- v3 tables. All new; no v2 table changes shape.
-- ---------------------------------------------------------------------------

-- Which source each v3 row came from, and when it was retrieved.
CREATE TABLE IF NOT EXISTS v3_sources (
    source_key  TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    url         TEXT,
    licence     TEXT,
    retrieved   TEXT
);

-- One row per row v3 added or per column it filled. `row_key` is a readable
-- composite, not a foreign key, because it has to describe rows in tables whose
-- primary keys v3 must not alter.
CREATE TABLE IF NOT EXISTS v3_provenance (
    table_name  TEXT NOT NULL,
    row_key     TEXT NOT NULL,
    action      TEXT NOT NULL CHECK (action IN ('insert','fill','correct')),
    source_key  TEXT NOT NULL REFERENCES v3_sources(source_key),
    PRIMARY KEY (table_name, row_key, action)
);

-- Stable identifiers for works, people and characters on other sites.
CREATE TABLE IF NOT EXISTS external_ids (
    entity_type TEXT NOT NULL CHECK (entity_type IN ('work','person','character')),
    entity_id   INTEGER NOT NULL,
    source      TEXT NOT NULL,
    identifier  TEXT NOT NULL,
    url         TEXT,
    PRIMARY KEY (entity_type, entity_id, source)
);

CREATE TABLE IF NOT EXISTS work_genres (
    work_id INTEGER NOT NULL REFERENCES media_works(id),
    genre   TEXT NOT NULL,
    PRIMARY KEY (work_id, genre)
);

CREATE TABLE IF NOT EXISTS work_countries (
    work_id INTEGER NOT NULL REFERENCES media_works(id),
    country TEXT NOT NULL,
    PRIMARY KEY (work_id, country)
);

CREATE TABLE IF NOT EXISTS work_languages (
    work_id  INTEGER NOT NULL REFERENCES media_works(id),
    language TEXT NOT NULL,
    PRIMARY KEY (work_id, language)
);

-- Content ratings per rating authority (MPAA, ESRB, BBFC, PEGI, ...).
CREATE TABLE IF NOT EXISTS work_content_ratings (
    work_id INTEGER NOT NULL REFERENCES media_works(id),
    rating  TEXT NOT NULL,
    country TEXT,
    reason  TEXT,
    PRIMARY KEY (work_id, rating)
);

-- Territory-by-territory release, which media_works.release_date cannot hold.
CREATE TABLE IF NOT EXISTS work_release_dates (
    work_id      INTEGER NOT NULL REFERENCES media_works(id),
    release_date TEXT NOT NULL,
    place        TEXT,
    event        TEXT,
    PRIMARY KEY (work_id, release_date, place)
);

-- Narrative and filming locations.
CREATE TABLE IF NOT EXISTS work_places (
    work_id INTEGER NOT NULL REFERENCES media_works(id),
    place   TEXT NOT NULL,
    role    TEXT NOT NULL CHECK (role IN ('narrative','filming')),
    PRIMARY KEY (work_id, place, role)
);

-- Box office outside the domestic/worldwide split box_office can express.
CREATE TABLE IF NOT EXISTS box_office_regions (
    work_id    INTEGER NOT NULL REFERENCES media_works(id),
    region     TEXT NOT NULL,
    amount_usd INTEGER NOT NULL,
    as_of      TEXT,
    PRIMARY KEY (work_id, region)
);

CREATE TABLE IF NOT EXISTS work_summaries (
    work_id          INTEGER PRIMARY KEY REFERENCES media_works(id),
    wikipedia_title  TEXT,
    url              TEXT,
    summary          TEXT
);

CREATE TABLE IF NOT EXISTS person_occupations (
    person_id  INTEGER NOT NULL REFERENCES people(id),
    occupation TEXT NOT NULL,
    PRIMARY KEY (person_id, occupation)
);

CREATE TABLE IF NOT EXISTS person_citizenships (
    person_id INTEGER NOT NULL REFERENCES people(id),
    country   TEXT NOT NULL,
    PRIMARY KEY (person_id, country)
);

CREATE TABLE IF NOT EXISTS person_details (
    person_id         INTEGER PRIMARY KEY REFERENCES people(id),
    gender            TEXT,
    birth_name        TEXT,
    birth_country     TEXT,
    death_place       TEXT,
    work_period_start INTEGER,
    work_period_end   INTEGER,
    wikipedia_title   TEXT
);

-- Awards a person holds in their own right, including ones for other films.
CREATE TABLE IF NOT EXISTS person_awards (
    person_id  INTEGER NOT NULL REFERENCES people(id),
    award      TEXT NOT NULL,
    result     TEXT NOT NULL CHECK (result IN ('won','nominated')),
    year       INTEGER,
    for_work   TEXT,
    PRIMARY KEY (person_id, award, result, year, for_work)
);

CREATE TABLE IF NOT EXISTS character_details (
    identity_id            INTEGER PRIMARY KEY REFERENCES character_identities(id),
    gender                 TEXT,
    publisher              TEXT,
    narrative_universe     TEXT,
    creators               TEXT,
    first_appearance_title TEXT,
    first_appearance_year  INTEGER,
    wikipedia_title        TEXT
);

-- Shows that air two shorts per slot list both; `episodes` keeps one row per
-- broadcast slot, and the individual segments live here.
CREATE TABLE IF NOT EXISTS episode_segments (
    show_work_id   INTEGER NOT NULL REFERENCES media_works(id),
    season_number  INTEGER,
    episode_number INTEGER,
    segment_index  INTEGER NOT NULL,
    title          TEXT,
    writer         TEXT,
    director       TEXT,
    PRIMARY KEY (show_work_id, season_number, episode_number, segment_index)
);

CREATE INDEX IF NOT EXISTS idx_external_ids_entity ON external_ids(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_v3_prov_table ON v3_provenance(table_name);
CREATE INDEX IF NOT EXISTS idx_episode_segments_show ON episode_segments(show_work_id);
"""

VIEWS = """
-- One row per work with its aggregate critical standing, over whichever outlets
-- are on record. avg_pct is a mean of normalised percentages: outlets are not
-- weighted, so treat it as a summary, not a metascore.
CREATE VIEW IF NOT EXISTS v_work_reception AS
SELECT w.id AS work_id, w.title, w.release_year, w.media_type,
       COUNT(r.source)                                  AS n_scores,
       ROUND(AVG(r.score_pct), 1)                       AS avg_pct,
       MAX(CASE WHEN r.publication = 'Rotten Tomatoes' THEN r.score_pct END) AS rotten_tomatoes_pct,
       MAX(CASE WHEN r.publication = 'Metacritic'      THEN r.score_pct END) AS metacritic_pct
FROM media_works w
LEFT JOIN review_scores r ON r.work_id = w.id
GROUP BY w.id;

-- The people table plus everything v3 learned about them.
CREATE VIEW IF NOT EXISTS v_person_profile AS
SELECT p.id AS person_id, p.name, p.birth_date, p.death_date, p.birth_place,
       p.nationality, p.imdb_id, p.wikidata_id, p.tmdb_id,
       d.gender, d.birth_name, d.work_period_start, d.work_period_end,
       (SELECT GROUP_CONCAT(o.occupation, '; ')
          FROM person_occupations o WHERE o.person_id = p.id) AS occupations,
       (SELECT COUNT(*) FROM person_awards a
         WHERE a.person_id = p.id AND a.result = 'won')       AS awards_won,
       (SELECT COUNT(DISTINCT c.work_id) FROM cast_crew c
         WHERE c.person_id = p.id)                            AS works_credited
FROM people p LEFT JOIN person_details d ON d.person_id = p.id;

-- Every episode on record, with the series it belongs to.
CREATE VIEW IF NOT EXISTS v_episode_guide AS
SELECT e.show_work_id, w.title AS series, e.season_number, e.episode_number,
       e.title AS episode_title, e.air_date, e.director, e.writer,
       e.us_viewers_millions,
       (SELECT COUNT(*) FROM episode_segments s
         WHERE s.show_work_id = e.show_work_id
           AND s.season_number IS e.season_number
           AND s.episode_number IS e.episode_number) AS n_segments
FROM episodes e JOIN media_works w ON w.id = e.show_work_id;

-- Which of a work's identifiers are known, one row per work.
CREATE VIEW IF NOT EXISTS v_work_identifiers AS
SELECT w.id AS work_id, w.title,
       MAX(CASE WHEN x.source = 'wikidata'        THEN x.identifier END) AS wikidata_id,
       MAX(CASE WHEN x.source = 'imdb'            THEN x.identifier END) AS imdb_id,
       MAX(CASE WHEN x.source = 'rotten_tomatoes' THEN x.identifier END) AS rotten_tomatoes_id,
       MAX(CASE WHEN x.source = 'metacritic'      THEN x.identifier END) AS metacritic_id,
       MAX(CASE WHEN x.source = 'tmdb_movie'      THEN x.identifier END) AS tmdb_movie_id
FROM media_works w
LEFT JOIN external_ids x ON x.entity_type = 'work' AND x.entity_id = w.id
GROUP BY w.id;
"""

ID_URLS = {
    "wikidata": "https://www.wikidata.org/wiki/{}",
    "imdb": "https://www.imdb.com/title/{}/",
    "rotten_tomatoes": "https://www.rottentomatoes.com/{}",
    "metacritic": "https://www.metacritic.com/{}",
    "tmdb_movie": "https://www.themoviedb.org/movie/{}",
    "tmdb_tv": "https://www.themoviedb.org/tv/{}",
    "tmdb_person": "https://www.themoviedb.org/person/{}",
    "letterboxd": "https://letterboxd.com/film/{}/",
    "steam": "https://store.steampowered.com/app/{}/",
    "igdb": "https://www.igdb.com/games/{}",
    "giant_bomb": "https://www.giantbomb.com/{}/",
    "box_office_mojo": "https://www.boxofficemojo.com/title/{}/",
    "the_numbers": "https://www.the-numbers.com/movie/{}",
    "commons_category": "https://commons.wikimedia.org/wiki/Category:{}",
    "musicbrainz_artist": "https://musicbrainz.org/artist/{}",
    "official_website": "{}",
    "comic_vine": "https://comicvine.gamespot.com/{}/",
}


# ---------------------------------------------------------------------------
class Layer:
    def __init__(self, conn, cur):
        self.conn, self.cur = conn, cur
        self.counts = Counter()

        self.works = load("works_wikidata.json")
        self.people = load("people_wikidata.json")
        self.chars = load("characters_wikidata.json")
        self.episodes = load("episodes.json")
        self.reception = load("reception.json")
        self.summaries = load("summaries.json")

        self.L = Labels(
            self.works.get("labels"), self.people.get("labels"), self.chars.get("labels")
        )
        # wikidata person qid -> our person id, for award recipients and credits
        self.person_by_qid = {}
        for pid, d in (self.people.get("people") or {}).items():
            self.person_by_qid.setdefault(d["qid"], int(pid))
        for r in cur.execute(
                "SELECT id, wikidata_id FROM people WHERE wikidata_id IS NOT NULL"):
            self.person_by_qid.setdefault(r[1], r[0])

    # -- plumbing ----------------------------------------------------------
    def prov(self, table, key, action, source):
        self.cur.execute(
            "INSERT OR IGNORE INTO v3_provenance (table_name,row_key,action,source_key)"
            " VALUES (?,?,?,?)", (table, str(key), action, source))

    def ins(self, table, cols, values, key, source="wikidata"):
        """INSERT OR IGNORE + provenance; returns True when a row was added."""
        ph = ",".join("?" * len(values))
        self.cur.execute(
            f"INSERT OR IGNORE INTO {table} ({','.join(cols)}) VALUES ({ph})", values)
        if self.cur.rowcount:
            self.counts[table] += 1
            self.prov(table, key, "insert", source)
            return True
        return False

    def fill(self, table, col, pk_col, pk, value, source="wikidata"):
        """Set a column only where it is currently NULL."""
        if value in (None, ""):
            return False
        self.cur.execute(
            f"UPDATE {table} SET {col}=? WHERE {pk_col}=? AND ({col} IS NULL OR {col}='')",
            (value, pk))
        if self.cur.rowcount:
            self.counts[f"{table}.{col}"] += 1
            self.prov(table, f"{pk}:{col}", "fill", source)
            return True
        return False

    # -- sections ----------------------------------------------------------
    def schema(self):
        self.cur.executescript(SCHEMA)
        for key, name, url, lic in SOURCES:
            self.cur.execute(
                "INSERT OR REPLACE INTO v3_sources (source_key,name,url,licence,retrieved)"
                " VALUES (?,?,?,?,?)", (key, name, url, lic, RETRIEVED))

    def work_identity(self):
        """wikidata ids + external ids + Wikipedia summary for each work."""
        for wid, d in (self.works.get("works") or {}).items():
            wid = int(wid)
            self.ins("external_ids",
                     ["entity_type", "entity_id", "source", "identifier", "url"],
                     ["work", wid, "wikidata", d["qid"],
                      ID_URLS["wikidata"].format(d["qid"])],
                     f"work:{wid}:wikidata")
            for src, ident in (d.get("external_ids") or {}).items():
                if not ident:
                    continue
                url = ID_URLS.get(src)
                self.ins("external_ids",
                         ["entity_type", "entity_id", "source", "identifier", "url"],
                         ["work", wid, src, str(ident),
                          url.format(ident) if url else None],
                         f"work:{wid}:{src}")

        for wid, s in (self.summaries.get("summaries") or {}).items():
            self.ins("work_summaries",
                     ["work_id", "wikipedia_title", "url", "summary"],
                     [int(wid), s.get("wikipedia_title"), s.get("url"), s.get("summary")],
                     f"work:{wid}", source="wikipedia")

    def work_classification(self):
        for wid, d in (self.works.get("works") or {}).items():
            wid = int(wid)
            props = d.get("props") or {}
            for g in self.L.many(props.get("genre")):
                self.ins("work_genres", ["work_id", "genre"], [wid, g], f"{wid}:{g}")
            for c in self.L.many(props.get("country")):
                self.ins("work_countries", ["work_id", "country"], [wid, c], f"{wid}:{c}")
            for lang in self.L.many(props.get("original_language")):
                self.ins("work_languages", ["work_id", "language"], [wid, lang], f"{wid}:{lang}")
            for p in self.L.many(props.get("narrative_location")):
                self.ins("work_places", ["work_id", "place", "role"],
                         [wid, p, "narrative"], f"{wid}:{p}:narrative")
            for p in self.L.many(props.get("filming_location")):
                self.ins("work_places", ["work_id", "place", "role"],
                         [wid, p, "filming"], f"{wid}:{p}:filming")
            for r in d.get("ratings") or []:
                rating = self.L.get(r.get("rating_qid"))
                if not rating:
                    continue
                self.ins("work_content_ratings", ["work_id", "rating", "country", "reason"],
                         [wid, rating, self.L.get(r.get("country")),
                          self.L.get(r.get("reason"))], f"{wid}:{rating}")
            for rd in d.get("release_dates") or []:
                if not rd.get("date"):
                    continue
                self.ins("work_release_dates", ["work_id", "release_date", "place", "event"],
                         [wid, rd["date"], self.L.get(rd.get("place")),
                          self.L.get(rd.get("event"))],
                         f"{wid}:{rd['date']}:{rd.get('place')}")

    # -- review scores -----------------------------------------------------
    def _existing_reviews(self):
        seen = defaultdict(set)
        for wid, pub, scope in self.cur.execute(
                "SELECT work_id, publication, platform_scope FROM review_scores"):
            seen[wid].add((norm_key(pub), norm_key(scope)))
        return seen

    def reviews(self):
        seen = self._existing_reviews()

        def add(wid, pub, scope, score, mx, count, source_key):
            if not pub or score is None or not mx:
                return
            k = (norm_key(pub), norm_key(scope))
            if k in seen[wid]:
                return
            src = pub if not scope else f"{pub} ({scope})"
            pct = round(score * 100.0 / mx, 2)
            if not (0 <= pct <= 100):
                return
            if self.ins("review_scores",
                        ["work_id", "source", "publication", "platform_scope",
                         "score", "max_score", "score_pct", "review_count"],
                        [wid, src, pub, scope, float(score), float(mx), pct, count],
                        f"{wid}:{src}", source=source_key):
                seen[wid].add(k)

        # 1. Wikidata P444, read together with its P459 determination method.
        #
        #    Rotten Tomatoes publishes two different numbers and Wikidata records
        #    both against the same reviewer: the Tomatometer ("90%") and the mean
        #    of the rated reviews ("7.6/10"). They are not the same measurement,
        #    and storing the second as though it were the first would have said
        #    that Spider-Man (2002) scored 76. Only the aggregate percentage is
        #    kept. The method also names the outlet on statements that carry no
        #    P447 reviewer at all, which is most of the Metascores.
        for wid, d in (self.works.get("works") or {}).items():
            wid = int(wid)
            for r in d.get("reviews") or []:
                method = (self.L.get(r.get("method")) or "").lower()
                if any(s in method for s in SKIP_METHODS):
                    continue
                pub = self.L.get(r.get("reviewer_qid")) or r.get("reviewer")
                scope = self.L.get(r.get("platform"))
                for needle, (mpub, mscope) in METHOD_OUTLET.items():
                    if needle in method:
                        pub = pub or mpub
                        scope = scope or mscope
                        break
                if not pub:
                    continue
                score, mx = parse_score(r.get("raw"))
                if score is None:
                    continue
                # Both aggregators publish on a 0-100 scale; anything else from
                # them is a different statistic wearing the same reviewer.
                if pub in ("Rotten Tomatoes", "Metacritic") and mx != 100:
                    continue
                if not scope and pub in ("Rotten Tomatoes", "Metacritic"):
                    scope = "critic"
                add(wid, pub, scope, score, mx, r.get("n_reviews"), "wikidata")

        # 2. Wikipedia: {{Video game reviews}} and the film aggregate templates.
        for rec in self.reception.get("works") or []:
            wid = rec["work_id"]
            for r in rec.get("video_game_reviews") or []:
                if r.get("score") is None:
                    continue
                add(wid, r["publication"], r.get("platform_scope"),
                    r["score"], r.get("max_score"), None, "wikipedia")
            for r in rec.get("prose_scores") or []:
                if r.get("score") is None:
                    continue
                scope = "critic" if r["publication"] in ("Rotten Tomatoes", "Metacritic") else None
                add(wid, r["publication"], scope, r["score"], r.get("max_score"),
                    r.get("review_count"), "wikipedia")

    # -- money -------------------------------------------------------------
    def money(self):
        have_lifetime = {r[0] for r in self.cur.execute(
            "SELECT work_id FROM box_office WHERE scope='lifetime'")}
        for wid, d in (self.works.get("works") or {}).items():
            wid = int(wid)
            world = dom = None
            regions = {}
            for b in d.get("box_office") or []:
                if b.get("unit") != "Q4917":       # USD only; the column says usd
                    continue
                place = self.L.get(b.get("place"))
                if place in (None, "worldwide"):
                    world = max(world or 0, b["amount"])
                elif place in ("United States", "United States of America"):
                    dom = max(dom or 0, b["amount"])
                else:
                    regions[place] = max(regions.get(place, 0), b["amount"])
            for place, amt in regions.items():
                self.ins("box_office_regions", ["work_id", "region", "amount_usd"],
                         [wid, place, amt], f"{wid}:{place}")
            if world or dom:
                if wid in have_lifetime:
                    self.fill("box_office", "worldwide_usd", "work_id", wid, world) \
                        if world else None
                    # domestic sits on the same lifetime row
                    if dom:
                        self.cur.execute(
                            "UPDATE box_office SET domestic_usd=? WHERE work_id=? AND"
                            " scope='lifetime' AND domestic_usd IS NULL", (dom, wid))
                        if self.cur.rowcount:
                            self.counts["box_office.domestic_usd"] += 1
                            self.prov("box_office", f"{wid}:domestic_usd", "fill", "wikidata")
                else:
                    self.ins("box_office",
                             ["work_id", "scope", "week_number", "domestic_usd",
                              "international_usd", "worldwide_usd"],
                             [wid, "lifetime", None, dom, None, world],
                             f"{wid}:lifetime")
                    have_lifetime.add(wid)

            for c in d.get("cost") or []:
                if c.get("unit") != "Q4917":
                    continue
                primary = self.cur.execute(
                    "SELECT COUNT(*) FROM budgets WHERE work_id=? AND component='production'"
                    " AND is_primary=1", (wid,)).fetchone()[0]
                self.ins("budgets",
                         ["work_id", "amount_usd", "currency", "component",
                          "source_year", "is_primary", "note"],
                         [wid, c["amount"], "USD", "production",
                          int(c["point_in_time"][:4]) if c.get("point_in_time") else None,
                          0 if primary else 1,
                          "competing estimate (Wikidata)" if primary else "Wikidata"],
                         f"{wid}:production:{c['amount']}")

    # -- awards ------------------------------------------------------------
    def awards(self):
        existing = defaultdict(set)
        for wid, body, cat, res in self.cur.execute(
                "SELECT work_id, award_body, category, result FROM awards"):
            existing[wid].add((norm_key(cat), res))
        for wid, d in (self.works.get("works") or {}).items():
            wid = int(wid)
            # A film that won an award is also, on Wikidata, "nominated for" it.
            # Keeping both would report two Academy Award rows for one statuette,
            # so a win suppresses the matching nomination. Wins are also sorted
            # first so the one carrying a year survives.
            items = sorted(
                (a for a in (d.get("awards") or []) if self.L.get(a.get("award_qid"))),
                key=lambda a: (a["result"] != "won", a.get("year") is None))
            won = {norm_key(split_award(self.L.get(a["award_qid"]))[1])
                   for a in items if a["result"] == "won"}
            for a in items:
                label = self.L.get(a.get("award_qid"))
                body, category = split_award(label)
                if a["result"] == "nominated" and norm_key(category) in won:
                    continue
                if (norm_key(category), a["result"]) in existing[wid]:
                    continue
                recipient = None
                for q in a.get("recipients") or []:
                    if q in self.person_by_qid:
                        recipient = self.person_by_qid[q]
                        break
                if self.ins("awards",
                            ["work_id", "award_body", "year", "category", "result",
                             "recipient_person_id"],
                            [wid, body, a.get("year"), category, a["result"], recipient],
                            f"{wid}:{body}:{a.get('year')}:{category}:{a['result']}"):
                    existing[wid].add((norm_key(category), a["result"]))

    # -- people ------------------------------------------------------------
    def people_rows(self):
        for pid, d in (self.people.get("people") or {}).items():
            pid = int(pid)
            props = d.get("props") or {}
            self.fill("people", "birth_date", "id", pid, d.get("birth_date"))
            self.fill("people", "death_date", "id", pid, d.get("death_date"))
            self.fill("people", "wikidata_id", "id", pid, d.get("qid"))
            self.fill("people", "imdb_id", "id", pid, (d.get("external_ids") or {}).get("imdb"))
            tmdb = (d.get("external_ids") or {}).get("tmdb_person")
            if tmdb and str(tmdb).isdigit():
                self.fill("people", "tmdb_id", "id", pid, int(tmdb))

            # birth_place: "City, Country" where the country is known
            bp = self.L.get(d.get("birth_place_qid"))
            if bp:
                country = self.L.get((self.people.get("place_country") or {}).get(
                    d.get("birth_place_qid")))
                self.fill("people", "birth_place", "id", pid,
                          f"{bp}, {country}" if country and country != bp else bp)

            # nationality is empty for all 581 rows in v2
            cits = self.L.many(props.get("citizenship"))
            if cits:
                self.fill("people", "nationality", "id", pid, "; ".join(cits))
            for c in cits:
                self.ins("person_citizenships", ["person_id", "country"], [pid, c], f"{pid}:{c}")
            for o in self.L.many(props.get("occupation")):
                self.ins("person_occupations", ["person_id", "occupation"], [pid, o], f"{pid}:{o}")

            self.ins("person_details",
                     ["person_id", "gender", "birth_name", "birth_country", "death_place",
                      "work_period_start", "work_period_end", "wikipedia_title"],
                     [pid, self.L.get(d.get("gender_qid")), d.get("birth_name"),
                      self.L.get((self.people.get("place_country") or {}).get(
                          d.get("birth_place_qid"))),
                      self.L.get(d.get("death_place_qid")),
                      d.get("work_period_start"), d.get("work_period_end"), d.get("enwiki")],
                     f"person:{pid}")

            for a in d.get("awards") or []:
                label = self.L.get(a.get("award_qid"))
                if not label:
                    continue
                self.ins("person_awards", ["person_id", "award", "result", "year", "for_work"],
                         [pid, label, a["result"], a.get("year"),
                          self.L.get(a.get("for_work")) or ""],
                         f"{pid}:{label}:{a['result']}:{a.get('year')}")

            for src, ident in (d.get("external_ids") or {}).items():
                url = ID_URLS.get(src)
                self.ins("external_ids",
                         ["entity_type", "entity_id", "source", "identifier", "url"],
                         ["person", pid, src, str(ident), url.format(ident) if url else None],
                         f"person:{pid}:{src}")
            self.ins("external_ids",
                     ["entity_type", "entity_id", "source", "identifier", "url"],
                     ["person", pid, "wikidata", d["qid"], ID_URLS["wikidata"].format(d["qid"])],
                     f"person:{pid}:wikidata")

    # -- characters --------------------------------------------------------
    def characters(self):
        fa = self.chars.get("first_appearances") or {}
        for iid, d in (self.chars.get("characters") or {}).items():
            iid = int(iid)
            props = d.get("props") or {}
            first = fa.get(d.get("first_appearance_qid")) or {}
            title = first.get("title")
            year = first.get("year")

            self.ins("character_details",
                     ["identity_id", "gender", "publisher", "narrative_universe", "creators",
                      "first_appearance_title", "first_appearance_year", "wikipedia_title"],
                     [iid, self.L.get(d.get("gender_qid")),
                      self.L.get(d.get("publisher_qid")),
                      "; ".join(self.L.many(props.get("narrative_universe"))) or None,
                      "; ".join(self.L.many(props.get("creator"))) or None,
                      title, year, d.get("enwiki")],
                     f"identity:{iid}")

            self.fill("character_identities", "first_comic_title", "id", iid, title)
            self.fill("character_identities", "first_comic_year", "id", iid, year)
            # the per-spelling rows inherit their identity's first appearance
            for (cid,) in self.cur.execute(
                    "SELECT id FROM characters WHERE identity_id=?", (iid,)).fetchall():
                self.fill("characters", "first_comic_title", "id", cid, title)
                self.fill("characters", "first_comic_year", "id", cid, year)

            for src, ident in (d.get("external_ids") or {}).items():
                url = ID_URLS.get(src)
                self.ins("external_ids",
                         ["entity_type", "entity_id", "source", "identifier", "url"],
                         ["character", iid, src, str(ident), url.format(ident) if url else None],
                         f"character:{iid}:{src}")
            self.ins("external_ids",
                     ["entity_type", "entity_id", "source", "identifier", "url"],
                     ["character", iid, "wikidata", d["qid"],
                      ID_URLS["wikidata"].format(d["qid"])],
                     f"character:{iid}:wikidata")

    # -- episodes ----------------------------------------------------------
    def episodes_rows(self):
        for show in self.episodes.get("shows") or []:
            wid = show["work_id"]
            have_keys, have_titles = set(), set()
            for s, e, t in self.cur.execute(
                    "SELECT season_number, episode_number, title FROM episodes"
                    " WHERE show_work_id=?", (wid,)):
                have_keys.add((s, e))
                if t:
                    have_titles.add(norm_key(t))

            rows = show.get("episodes") or []
            # An unnumbered row in an episode list is the pilot TV movie, and
            # both of the series that have one already hold it as its own work.
            rows = [e for e in rows
                    if e.get("season_episode") is not None
                    or e.get("overall_number") is not None]
            # A season-less row in a list that otherwise has seasons is a shorts
            # or specials block — the 2017 series' six "Origin Shorts" reuse
            # episode numbers 1-6 and are not part of its 58 episodes.
            if any(e.get("season_hint") for e in rows):
                rows = [e for e in rows if e.get("season_hint")]

            # Two shorts in one slot share an episode number; they become one
            # `episodes` row plus one `episode_segments` row each.
            grouped = defaultdict(list)
            for ep in rows:
                season = ep.get("season_hint")
                number = ep.get("season_episode") or ep.get("overall_number")
                grouped[(season, number)].append(ep)

            for (season, number), eps in sorted(
                    grouped.items(), key=lambda kv: (kv[0][0] or 0, kv[0][1] or 0)):
                titles = [e["title"] for e in eps if e.get("title")]
                title = " / ".join(dict.fromkeys(titles)) or None
                if (season, number) in have_keys:
                    continue
                if title and norm_key(title) in have_titles:
                    continue
                first = eps[0]
                if self.ins("episodes",
                            ["show_work_id", "season_number", "episode_number", "title",
                             "air_date", "director", "writer", "us_viewers_millions"],
                            [wid, season, number, title, first.get("air_date"),
                             first.get("director"), first.get("writer"),
                             first.get("us_viewers_millions")],
                            f"{wid}:s{season}e{number}", source="wikipedia"):
                    have_keys.add((season, number))

                segs = []
                for e in eps:
                    segs.extend(e.get("segment_titles") or ([e["title"]] if e.get("title") else []))
                if len(segs) > 1:
                    for i, st in enumerate(segs, 1):
                        self.ins("episode_segments",
                                 ["show_work_id", "season_number", "episode_number",
                                  "segment_index", "title", "writer", "director"],
                                 [wid, season, number, i, st,
                                  eps[0].get("writer"), eps[0].get("director")],
                                 f"{wid}:s{season}e{number}:{i}", source="wikipedia")

    def reconcile_series_counts(self):
        """Bring `tv_shows.episodes`/`seasons` up to what is now on record.

        This is the one place v3 overwrites a value v2 wrote, and it does so only
        in one direction: when the episode rows outnumber the declared count, the
        declared count is stale — two of these series have aired further seasons
        since the v2 research was done. Anything else is left alone, and each
        change is recorded as action='correct' so it can be found and reversed.
        """
        rows = self.cur.execute("""
            SELECT t.work_id, w.title, t.episodes, t.seasons,
                   COUNT(e.id) AS observed, MAX(e.season_number) AS max_season
            FROM tv_shows t
            JOIN media_works w ON w.id = t.work_id
            LEFT JOIN episodes e ON e.show_work_id = t.work_id
            GROUP BY t.work_id""").fetchall()
        for wid, title, declared, seasons, observed, max_season in rows:
            if declared is not None and observed > declared:
                self.cur.execute("UPDATE tv_shows SET episodes=? WHERE work_id=?",
                                 (observed, wid))
                self.counts["tv_shows.episodes (corrected)"] += 1
                self.prov("tv_shows", f"{wid}:episodes:{declared}->{observed}",
                          "correct", "wikipedia")
            if max_season and seasons is not None and max_season > seasons:
                self.cur.execute("UPDATE tv_shows SET seasons=? WHERE work_id=?",
                                 (max_season, wid))
                self.counts["tv_shows.seasons (corrected)"] += 1
                self.prov("tv_shows", f"{wid}:seasons:{seasons}->{max_season}",
                          "correct", "wikipedia")

    def views(self):
        self.cur.executescript(VIEWS)

    def run(self):
        self.schema()
        self.work_identity()
        self.work_classification()
        self.reviews()
        self.money()
        self.awards()
        self.people_rows()
        self.characters()
        self.episodes_rows()
        self.reconcile_series_counts()
        self.views()
        return self.counts


# ---------------------------------------------------------------------------
# P459 determination-method labels that identify the outlet behind a review
# statement, and the ones that mark a statistic we do not store.
METHOD_OUTLET = {
    "tomatometer": ("Rotten Tomatoes", "critic"),
    "metascore": ("Metacritic", "critic"),
    "metacritic user score": ("Metacritic", "user"),
    "popcornmeter": ("Rotten Tomatoes", "audience"),
    "audience score": ("Rotten Tomatoes", "audience"),
}
SKIP_METHODS = ("average of rated reviews",)


def parse_score(raw):
    """'92%' / '7.7/10' / '73/100' / '4,0/5' -> (score, max)."""
    if not raw:
        return None, None
    s = raw.strip().replace(",", ".")
    m = re.match(r"^(\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)$", s)
    if m:
        return float(m.group(1)), float(m.group(2))
    m = re.match(r"^(\d+(?:\.\d+)?)\s*%$", s)
    if m:
        return float(m.group(1)), 100.0
    return None, None


AWARD_BODY_FIXES = {
    "Academy Award": "Academy Awards",
    "Annie Award": "Annie Awards",
    "BAFTA Award": "BAFTA Awards",
    "Golden Globe Award": "Golden Globe Awards",
    "Hugo Award": "Hugo Awards",
    "Saturn Award": "Saturn Awards",
    "Primetime Emmy Award": "Primetime Emmy Awards",
    "Daytime Emmy Award": "Daytime Emmy Awards",
    "Kids' Choice Award": "Kids' Choice Awards",
    "Critics' Choice Movie Award": "Critics' Choice Movie Awards",
    "Golden Raspberry Award": "Golden Raspberry Awards",
    "MTV Movie Award": "MTV Movie Awards",
    "Grammy Award": "Grammy Awards",
    "Empire Award": "Empire Awards",
}


def split_award(label):
    """'Academy Award for Best Animated Feature' -> ('Academy Awards', 'Best ...')."""
    body, category = label, label
    for sep in (" for ", " – ", " - ", ": "):
        if sep in label:
            body, category = label.split(sep, 1)
            break
    body = body.strip()
    body = AWARD_BODY_FIXES.get(body, body)
    if body.endswith("Award"):
        body += "s"
    return body, category.strip()


def apply(conn, cur):
    total = Layer(conn, cur).run()
    for k, v in sorted(total.items()):
        print(f"      {k:38} {v}")
    return sum(total.values())
