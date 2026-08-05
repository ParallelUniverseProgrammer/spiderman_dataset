#!/usr/bin/env python3
"""v4_layer.py — the additive v4 layer: the dataset's outer edges, resolved.

`apply(conn, cur)` runs v3's layer first and then its own, so build_db_v4.py can
hand build_db_v2.py a single module and get v2 + v3 + v4 in one pass. It reads
the JSON under data_raw/v4/ written by fetch_comics.py, fetch_character_graph.py
and fetch_orgs.py, so it is offline and deterministic.

It obeys the same two rules v3 does, and build_db_v4.py's `--check` enforces
them against *both* earlier versions: nothing v2 or v3 wrote is changed except
to fill a NULL, and no existing table changes shape.

What v4 is about
----------------
v3 filled in the dataset's holes. v4 goes after its *edges* — the columns that
name something the database has no row for:

* `source_material.comic_title` / `issue_range` named comics that were strings.
  Now they are rows in `comics`, with the writer, penciller, inker, colourist,
  letterer and cover artist behind each one in `comic_credits`.
* `character_details.first_appearance_title` named the same comics again, from
  the other direction. `character_debuts` joins them up: 76 identities now point
  at a comic row rather than repeating a title.
* `episodes.director` and `episodes.writer` were semicolon-joined name strings
  over 577 rows. `episode_credits` splits them and matches each name back to
  `people`, which is how an episode director becomes the same entity as a film
  director.
* `studios.country` and `studios.parent_company` were two of the twelve columns
  the README lists as never populated. They are populated now.
* Characters had attributes but no relationships. `character_relations` adds
  790 edges — enemies, family, partners, alternate-universe counterparts — and
  `character_traits` the abilities and team memberships behind them.

Where a comic could not be resolved
-----------------------------------
Wikidata itemises about ninety of the nine hundred Amazing Spider-Man issues.
A citation naming one of the rest still becomes a `comics` row, with
`origin='parsed'`: the series and the issue number are read out of the citation
itself, so the row is as sound as the citation, but it carries no publication
date, publisher or credits, and `wikidata_id` is NULL. Filter on
`origin='wikidata'` for the ones with real metadata behind them.
"""
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path

import v3_layer

HERE = Path(__file__).resolve().parent
V4 = HERE / "data_raw" / "v4"

RETRIEVED = "2026-08-04"

SOURCES = [
    ("wikidata", "Wikidata", "https://www.wikidata.org/", "CC0-1.0"),
    ("wikipedia", "English Wikipedia", "https://en.wikipedia.org/", "CC BY-SA 4.0"),
    ("derived", "Derived from this dataset",
     "https://github.com/spiderman-dataset", "CC BY 4.0"),
]

# Roles as they come out of Wikidata's comics properties. `author` and `creator`
# are kept apart from `writer` on purpose: on a 1963 issue Wikidata files Stan
# Lee under P58 (writer) and on a 1963 X-Men issue under P50 (author), and
# flattening them would hide which property the credit actually came from.
CREDIT_ROLES = ("writer", "author", "penciller", "inker", "colorist", "letterer",
                "cover_artist", "illustrator", "editor", "creator")

RELATIONS = ("enemy", "ally", "mother", "father", "spouse", "child", "partner",
             "relative", "alternate_universe_counterpart")

TRAITS = ("ability", "character_type", "team", "occupation", "ethnic_group",
          "religion", "eye_color", "hair_color", "height", "sport",
          "medical_condition")


SCHEMA = """
-- ---------------------------------------------------------------------------
-- v4 tables. All new; no v2 or v3 table changes shape.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS v4_sources (
    source_key  TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    url         TEXT,
    licence     TEXT,
    retrieved   TEXT
);

CREATE TABLE IF NOT EXISTS v4_provenance (
    table_name  TEXT NOT NULL,
    row_key     TEXT NOT NULL,
    action      TEXT NOT NULL CHECK (action IN ('insert','fill','correct')),
    source_key  TEXT NOT NULL REFERENCES v4_sources(source_key),
    PRIMARY KEY (table_name, row_key, action)
);

-- The comics behind the adaptations. `ref_key` is the resolver's stable handle
-- for a comic — its QID, or 'parsed:<series QID>:<issue>' for an issue that is
-- named by a citation but has no Wikidata item. It is what makes the ids here
-- reproducible from one build to the next.
CREATE TABLE IF NOT EXISTS comics (
    id               INTEGER PRIMARY KEY,
    ref_key          TEXT NOT NULL UNIQUE,
    title            TEXT NOT NULL,
    kind             TEXT NOT NULL CHECK (kind IN ('series','issue','storyline')),
    series_id        INTEGER REFERENCES comics(id),
    issue_number     INTEGER,
    publisher        TEXT,
    publication_date TEXT,
    publication_year INTEGER,
    cover_date       TEXT,
    wikidata_id      TEXT,
    wikipedia_title  TEXT,
    origin           TEXT NOT NULL CHECK (origin IN ('wikidata','parsed'))
);

-- Comic writers and artists. `person_id` is set when the same human also holds
-- a screen credit in this dataset — Stan Lee has 20 of them.
CREATE TABLE IF NOT EXISTS comic_creators (
    id              INTEGER PRIMARY KEY,
    name            TEXT NOT NULL UNIQUE,
    wikidata_id     TEXT,
    person_id       INTEGER REFERENCES people(id),
    birth_date      TEXT,
    death_date      TEXT,
    wikipedia_title TEXT
);

CREATE TABLE IF NOT EXISTS comic_credits (
    comic_id   INTEGER NOT NULL REFERENCES comics(id),
    creator_id INTEGER NOT NULL REFERENCES comic_creators(id),
    role       TEXT NOT NULL,
    PRIMARY KEY (comic_id, creator_id, role)
);

-- Characters a comic issue lists (Wikidata P674), restricted to the identities
-- this dataset already knows.
CREATE TABLE IF NOT EXISTS comic_characters (
    comic_id    INTEGER NOT NULL REFERENCES comics(id),
    identity_id INTEGER NOT NULL REFERENCES character_identities(id),
    PRIMARY KEY (comic_id, identity_id)
);

-- source_material, resolved. One source_material row can yield several comics:
-- "Amazing Spider-Man #121-122" is two issues.
CREATE TABLE IF NOT EXISTS work_source_comics (
    source_material_id INTEGER NOT NULL REFERENCES source_material(id),
    work_id            INTEGER NOT NULL REFERENCES media_works(id),
    comic_id           INTEGER NOT NULL REFERENCES comics(id),
    match_method       TEXT NOT NULL CHECK (match_method IN ('issue','title','parsed')),
    PRIMARY KEY (source_material_id, comic_id)
);

-- Where a character first appeared, as a row rather than a title string.
CREATE TABLE IF NOT EXISTS character_debuts (
    identity_id INTEGER PRIMARY KEY REFERENCES character_identities(id),
    comic_id    INTEGER NOT NULL REFERENCES comics(id),
    method      TEXT NOT NULL CHECK (method IN ('wikidata','reference'))
);

-- The character graph. `other_identity_id` is set when the other side is itself
-- one of the 264 identities; when it is not, the edge still records who by name.
CREATE TABLE IF NOT EXISTS character_relations (
    identity_id       INTEGER NOT NULL REFERENCES character_identities(id),
    relation          TEXT NOT NULL,
    other_name        TEXT NOT NULL,
    other_identity_id INTEGER REFERENCES character_identities(id),
    other_wikidata_id TEXT,
    PRIMARY KEY (identity_id, relation, other_name)
);

CREATE TABLE IF NOT EXISTS character_traits (
    identity_id INTEGER NOT NULL REFERENCES character_identities(id),
    trait       TEXT NOT NULL,
    value       TEXT NOT NULL,
    PRIMARY KEY (identity_id, trait, value)
);

CREATE TABLE IF NOT EXISTS studio_details (
    studio_id       INTEGER PRIMARY KEY REFERENCES studios(id),
    wikidata_id     TEXT,
    wikipedia_title TEXT,
    industry        TEXT,
    headquarters    TEXT,
    inception       TEXT,
    dissolved       TEXT
);

CREATE TABLE IF NOT EXISTS platform_details (
    platform_id     INTEGER PRIMARY KEY REFERENCES platforms(id),
    wikidata_id     TEXT,
    wikipedia_title TEXT,
    manufacturer    TEXT,
    developer       TEXT,
    released        TEXT,
    discontinued    TEXT
);

-- episodes.director and .writer hold '; '-joined names. Split, ordered, and
-- matched back to `people` where that name already has a screen credit.
CREATE TABLE IF NOT EXISTS episode_credits (
    episode_id   INTEGER NOT NULL REFERENCES episodes(id),
    role         TEXT NOT NULL CHECK (role IN ('director','writer')),
    name         TEXT NOT NULL,
    credit_order INTEGER NOT NULL,
    person_id    INTEGER REFERENCES people(id),
    PRIMARY KEY (episode_id, role, name)
);

CREATE INDEX IF NOT EXISTS idx_v4_prov_table ON v4_provenance(table_name);
CREATE INDEX IF NOT EXISTS idx_comics_series ON comics(series_id);
CREATE INDEX IF NOT EXISTS idx_comic_credits_creator ON comic_credits(creator_id);
CREATE INDEX IF NOT EXISTS idx_char_rel_other ON character_relations(other_identity_id);
CREATE INDEX IF NOT EXISTS idx_episode_credits_person ON episode_credits(person_id);
CREATE INDEX IF NOT EXISTS idx_wsc_work ON work_source_comics(work_id);
"""

VIEWS = """
-- Every adaptation next to the comic it adapts, one row per link.
CREATE VIEW IF NOT EXISTS v_work_comic_sources AS
SELECT w.id AS work_id, w.title AS work_title, w.release_year, w.media_type,
       c.id AS comic_id, c.title AS comic_title, c.kind, c.issue_number,
       c.publication_year AS comic_year, c.origin,
       s.title AS series_title,
       (SELECT GROUP_CONCAT(cc.name, '; ')
          FROM comic_credits x JOIN comic_creators cc ON cc.id = x.creator_id
         WHERE x.comic_id = c.id AND x.role IN ('writer','author')) AS writers,
       sm.storyline_arc, wsc.match_method
FROM work_source_comics wsc
JOIN media_works w ON w.id = wsc.work_id
JOIN comics c      ON c.id = wsc.comic_id
JOIN source_material sm ON sm.id = wsc.source_material_id
LEFT JOIN comics s ON s.id = c.series_id;

-- A comic creator's footprint: how many comics, in what roles, over what span,
-- and whether they also hold a screen credit in this dataset.
CREATE VIEW IF NOT EXISTS v_comic_creator_profile AS
SELECT cc.id AS creator_id, cc.name, cc.wikidata_id, cc.person_id,
       COUNT(DISTINCT x.comic_id)                       AS n_comics,
       GROUP_CONCAT(DISTINCT x.role)                    AS roles,
       MIN(c.publication_year)                          AS first_year,
       MAX(c.publication_year)                          AS last_year,
       (SELECT COUNT(DISTINCT wsc.work_id)
          FROM comic_credits x2
          JOIN work_source_comics wsc ON wsc.comic_id = x2.comic_id
         WHERE x2.creator_id = cc.id)                   AS n_works_adapted
FROM comic_creators cc
LEFT JOIN comic_credits x ON x.creator_id = cc.id
LEFT JOIN comics c        ON c.id = x.comic_id
GROUP BY cc.id;

-- The character graph with both ends named, internal edges only.
CREATE VIEW IF NOT EXISTS v_character_network AS
SELECT r.identity_id, a.canonical_name AS character_name, r.relation,
       r.other_identity_id, b.canonical_name AS other_character_name,
       a.alignment AS alignment, b.alignment AS other_alignment
FROM character_relations r
JOIN character_identities a ON a.id = r.identity_id
JOIN character_identities b ON b.id = r.other_identity_id;

-- One row per identity: what it is, what it can do, who it fights, and how
-- often it has been adapted.
CREATE VIEW IF NOT EXISTS v_character_dossier AS
SELECT i.id AS identity_id, i.canonical_name, i.alignment,
       d.first_appearance_title, d.first_appearance_year, d.creators,
       (SELECT c.title FROM character_debuts cd JOIN comics c ON c.id = cd.comic_id
         WHERE cd.identity_id = i.id)                              AS debut_comic,
       (SELECT GROUP_CONCAT(t.value, '; ') FROM character_traits t
         WHERE t.identity_id = i.id AND t.trait = 'ability')       AS abilities,
       (SELECT GROUP_CONCAT(t.value, '; ') FROM character_traits t
         WHERE t.identity_id = i.id AND t.trait = 'team')          AS teams,
       (SELECT COUNT(*) FROM character_relations r
         WHERE r.identity_id = i.id AND r.relation = 'enemy')      AS n_enemies,
       (SELECT COUNT(DISTINCT wc.work_id) FROM work_characters wc
          JOIN characters ch ON ch.id = wc.character_id
         WHERE ch.identity_id = i.id)                              AS n_works
FROM character_identities i
LEFT JOIN character_details d ON d.identity_id = i.id;

-- Episode credits with the series and episode they belong to.
CREATE VIEW IF NOT EXISTS v_episode_credits AS
SELECT ec.episode_id, w.title AS series, e.season_number, e.episode_number,
       e.title AS episode_title, e.air_date, ec.role, ec.name, ec.person_id,
       p.name AS matched_person
FROM episode_credits ec
JOIN episodes e     ON e.id = ec.episode_id
JOIN media_works w  ON w.id = e.show_work_id
LEFT JOIN people p  ON p.id = ec.person_id;
"""


def load(name):
    p = V4 / name
    if not p.exists():
        return {}
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def norm_name(s):
    """Match form for a personal name: no accents, no punctuation, no case."""
    s = unicodedata.normalize("NFKD", (s or "").lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"\(.*?\)", " ", s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return " ".join(s.split())


def year_of(iso):
    m = re.match(r"^(-?\d{4})", iso or "")
    return int(m.group(1)) if m else None


class Layer:
    def __init__(self, conn, cur):
        self.conn, self.cur = conn, cur
        self.counts = Counter()

        self.comics_src = load("comics.json")
        self.graph = load("character_graph.json")
        self.orgs = load("orgs.json")

        self.L = dict(self.comics_src.get("labels") or {})
        for extra in (self.graph.get("labels"), self.orgs.get("labels")):
            for k, v in (extra or {}).items():
                if v:
                    self.L.setdefault(k, v)

        self.comic_id = {}      # ref_key -> comics.id
        self.creator_id = {}    # creator qid or name -> comic_creators.id
        self._canonical = None  # wikidata qid -> the identity that speaks for it
        self.shared_qids = {}   # qid -> identities sharing it, when more than one

    # -- plumbing ----------------------------------------------------------
    def prov(self, table, key, action, source):
        self.cur.execute(
            "INSERT OR IGNORE INTO v4_provenance (table_name,row_key,action,source_key)"
            " VALUES (?,?,?,?)", (table, str(key), action, source))

    def ins(self, table, cols, values, key, source="wikidata"):
        ph = ",".join("?" * len(values))
        self.cur.execute(
            f"INSERT OR IGNORE INTO {table} ({','.join(cols)}) VALUES ({ph})", values)
        if self.cur.rowcount:
            self.counts[table] += 1
            self.prov(table, key, "insert", source)
            return True
        return False

    def fill(self, table, col, pk_col, pk, value, source="wikidata"):
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

    def label(self, qid, default=None):
        return self.L.get(qid) or default

    # -- sections ----------------------------------------------------------
    def schema(self):
        self.cur.executescript(SCHEMA)
        for key, name, url, lic in SOURCES:
            self.cur.execute(
                "INSERT OR REPLACE INTO v4_sources (source_key,name,url,licence,retrieved)"
                " VALUES (?,?,?,?,?)", (key, name, url, lic, RETRIEVED))

    # -- comics ------------------------------------------------------------
    def comics(self):
        src = self.comics_src.get("comics") or {}
        if not src:
            return
        # Deterministic ids: series before issues (so series_id is resolvable in
        # one pass), then by ref_key.
        order = sorted(src.items(),
                       key=lambda kv: (kv[1]["kind"] != "series", kv[0]))
        for n, (ref_key, c) in enumerate(order, start=1):
            self.comic_id[ref_key] = n

        for ref_key, c in order:
            cid = self.comic_id[ref_key]
            series_id = self.comic_id.get(c.get("series_qid") or "")
            if series_id == cid:
                series_id = None            # a series is not its own parent
            date = c.get("publication_date")
            self.ins("comics",
                     ["id", "ref_key", "title", "kind", "series_id", "issue_number",
                      "publisher", "publication_date", "publication_year",
                      "cover_date", "wikidata_id", "wikipedia_title", "origin"],
                     [cid, ref_key, c["title"], c["kind"], series_id,
                      c.get("issue_number"), self.label(c.get("publisher_qid")),
                      date, year_of(date), c.get("cover_date"), c.get("qid"),
                      c.get("enwiki"),
                      "parsed" if c.get("origin") == "parsed" else "wikidata"],
                     f"comic:{ref_key}",
                     source="derived" if c.get("origin") == "parsed" else "wikidata")

    def creators(self):
        src = self.comics_src.get("creators") or {}
        if not src:
            return
        # Comic creators who also hold a screen credit are the same human; link
        # them rather than duplicating the person.
        people_by_qid, people_by_name = {}, {}
        for pid, name, wd in self.cur.execute(
                "SELECT id, name, wikidata_id FROM people"):
            if wd:
                people_by_qid.setdefault(wd, pid)
            people_by_name.setdefault(norm_name(name), pid)

        for n, (qid, d) in enumerate(sorted(src.items()), start=1):
            name = d.get("name")
            if not name:
                continue
            pid = people_by_qid.get(qid) or people_by_name.get(norm_name(name))
            self.creator_id[qid] = n
            self.ins("comic_creators",
                     ["id", "name", "wikidata_id", "person_id", "birth_date",
                      "death_date", "wikipedia_title"],
                     [n, name, qid, pid, d.get("birth_date"), d.get("death_date"),
                      d.get("enwiki")],
                     f"creator:{qid}")

    def comic_credits(self):
        src = self.comics_src.get("comics") or {}
        qid_to_identity = self.identity_by_qid()
        for ref_key, c in sorted(src.items()):
            cid = self.comic_id.get(ref_key)
            if not cid:
                continue
            for role, qids in sorted((c.get("credits") or {}).items()):
                if role not in CREDIT_ROLES:
                    continue
                for q in qids:
                    crid = self.creator_id.get(q)
                    if not crid:
                        continue
                    self.ins("comic_credits", ["comic_id", "creator_id", "role"],
                             [cid, crid, role], f"{ref_key}:{q}:{role}")
            for q in c.get("characters") or []:
                iid = qid_to_identity.get(q)
                if iid:
                    self.ins("comic_characters", ["comic_id", "identity_id"],
                             [cid, iid], f"{ref_key}:{iid}")

    def identity_by_qid(self):
        """QID -> the one identity that speaks for it.

        v3's resolver lands several identities on the same Wikidata item: the
        four Spider-Men of the Spider-Verse films all reduce to Q79037, and a
        handful of near-misses collapse too (Kamala Khan onto Carol Danvers).
        Copying an item's whole relationship set onto each of them would state,
        as data, that Takuya Yamashiro has Peter Parker's seventy-eight enemies.
        The item's facts go to the identity the dataset itself treats as
        principal — the one with the most credited spellings behind it — and the
        others are left without a graph rather than given a borrowed one.
        """
        if getattr(self, "_canonical", None) is not None:
            return self._canonical
        variants = dict(self.cur.execute(
            "SELECT id, n_variants FROM character_identities"))
        by_qid = {}
        for iid, qid in self.cur.execute(
                "SELECT entity_id, identifier FROM external_ids"
                " WHERE entity_type='character' AND source='wikidata'"):
            by_qid.setdefault(qid, []).append(iid)
        self._canonical = {
            qid: sorted(iids, key=lambda i: (-variants.get(i, 0), i))[0]
            for qid, iids in by_qid.items()
        }
        self.shared_qids = {q: v for q, v in by_qid.items() if len(v) > 1}
        return self._canonical

    def source_links(self):
        """source_material -> comics, and the character debut links."""
        for m in self.comics_src.get("matches") or []:
            cid = self.comic_id.get(m.get("comic_key") or "")
            if not cid:
                continue
            if m["origin"] == "source_material":
                self.ins("work_source_comics",
                         ["source_material_id", "work_id", "comic_id", "match_method"],
                         [m["origin_id"], m["work_id"], cid, m["match"]],
                         f"sm:{m['origin_id']}:{cid}",
                         source="derived" if m["match"] == "parsed" else "wikidata")

        # Wikidata's own P4584 first appearance wins; a citation-derived match is
        # the fallback for identities it does not cover.
        debuts = self.comics_src.get("character_debuts") or {}
        for iid, qid in sorted(debuts.items(), key=lambda kv: int(kv[0])):
            cid = self.comic_id.get(qid)
            if cid:
                self.ins("character_debuts", ["identity_id", "comic_id", "method"],
                         [int(iid), cid, "wikidata"], f"debut:{iid}")
        for m in self.comics_src.get("matches") or []:
            if m["origin"] != "character_identities":
                continue
            cid = self.comic_id.get(m.get("comic_key") or "")
            if cid:
                self.ins("character_debuts", ["identity_id", "comic_id", "method"],
                         [m["origin_id"], cid, "reference"], f"debut:{m['origin_id']}",
                         source="derived")

    # -- the character graph -----------------------------------------------
    def character_graph(self):
        names = {i: n for i, n in self.cur.execute(
            "SELECT id, canonical_name FROM character_identities")}
        canonical = self.identity_by_qid()
        speaks_for = set(canonical.values())

        for e in self.graph.get("edges") or []:
            rel = e["relation"]
            if rel not in RELATIONS or e["from_id"] not in speaks_for:
                continue
            other_id = canonical.get(e.get("to_qid"))
            other = names.get(other_id) if other_id else self.label(e.get("to_qid"))
            if not other or other_id == e["from_id"]:
                continue
            self.ins("character_relations",
                     ["identity_id", "relation", "other_name", "other_identity_id",
                      "other_wikidata_id"],
                     [e["from_id"], rel, other, other_id, e.get("to_qid")],
                     f"{e['from_id']}:{rel}:{other}")

        for iid, traits in sorted((self.graph.get("traits") or {}).items(),
                                  key=lambda kv: int(kv[0])):
            if int(iid) not in speaks_for:
                continue
            for trait, vals in sorted(traits.items()):
                if trait not in TRAITS:
                    continue
                for v in vals:
                    if isinstance(v, dict):        # a quantity, e.g. height
                        amount = str(v.get("amount", "")).lstrip("+")
                        text = f"{amount} m" if amount else None
                    else:
                        text = self.label(v)
                    if not text:
                        continue
                    self.ins("character_traits", ["identity_id", "trait", "value"],
                             [int(iid), trait, text], f"{iid}:{trait}:{text}")

        # character_details.publisher was one of the fully-NULL columns; the
        # publisher of a character's debut issue is what it should have held.
        for iid, pub in self.cur.execute("""
                SELECT cd.identity_id, c.publisher
                  FROM character_debuts cd JOIN comics c ON c.id = cd.comic_id
                 WHERE c.publisher IS NOT NULL""").fetchall():
            self.fill("character_details", "publisher", "identity_id", iid, pub)

    # -- studios and platforms ---------------------------------------------
    def orgs_rows(self):
        studios = {r[1]: r[0] for r in self.cur.execute("SELECT id, name FROM studios")}
        for name, d in sorted((self.orgs.get("studios") or {}).items()):
            sid = studios.get(name)
            if not sid:
                continue
            self.fill("studios", "country", "id", sid, self.label(d.get("country_qid")))
            self.fill("studios", "parent_company", "id", sid,
                      self.label(d.get("parent_qid")))
            self.ins("studio_details",
                     ["studio_id", "wikidata_id", "wikipedia_title", "industry",
                      "headquarters", "inception", "dissolved"],
                     [sid, d.get("qid"), d.get("enwiki"),
                      self.label(d.get("industry_qid")), self.label(d.get("hq_qid")),
                      d.get("inception"), d.get("dissolved")],
                     f"studio:{sid}")

        platforms = {r[1]: r[0] for r in self.cur.execute("SELECT id, name FROM platforms")}
        for name, d in sorted((self.orgs.get("platforms") or {}).items()):
            pid = platforms.get(name)
            if not pid:
                continue
            self.ins("platform_details",
                     ["platform_id", "wikidata_id", "wikipedia_title", "manufacturer",
                      "developer", "released", "discontinued"],
                     [pid, d.get("qid"), d.get("enwiki"),
                      self.label(d.get("manufacturer_qid")),
                      self.label(d.get("developer_qid")),
                      d.get("released"), d.get("discontinued")],
                     f"platform:{pid}")

    # -- episode credits ---------------------------------------------------
    def episode_credit_rows(self):
        """Split the joined name strings on `episodes` and match them to people.

        Needs no network: the names are already in the database, they are just
        not addressable. Matching is on an exact normalised name — a director
        credited only on one 1981 episode and never resolved to a person stays
        unmatched rather than being attached to a similar name.
        """
        people_by_name = {}
        for pid, name in self.cur.execute("SELECT id, name FROM people"):
            people_by_name.setdefault(norm_name(name), pid)

        rows = self.cur.execute(
            "SELECT id, director, writer FROM episodes ORDER BY id").fetchall()
        for eid, director, writer in rows:
            for role, blob in (("director", director), ("writer", writer)):
                if not blob:
                    continue
                seen = set()
                order = 0
                for raw in re.split(r"\s*[;&]\s*|\s+and\s+", blob):
                    name = raw.strip(" ,")
                    if not name or len(name) < 3:
                        continue
                    key = norm_name(name)
                    if not key or key in seen:
                        continue
                    seen.add(key)
                    order += 1
                    self.ins("episode_credits",
                             ["episode_id", "role", "name", "credit_order", "person_id"],
                             [eid, role, name, order, people_by_name.get(key)],
                             f"{eid}:{role}:{name}", source="derived")

    def views(self):
        self.cur.executescript(VIEWS)

    def run(self):
        self.schema()
        self.comics()
        self.creators()
        self.comic_credits()
        self.source_links()
        self.character_graph()
        self.orgs_rows()
        self.episode_credit_rows()
        self.views()
        return self.counts


def apply(conn, cur):
    """v3's layer, then v4's. build_db_v2.py calls this once."""
    added = v3_layer.apply(conn, cur)
    total = Layer(conn, cur).run()
    print("  v4 layer:")
    for k, v in sorted(total.items()):
        print(f"      {k:38} {v}")
    return added + sum(total.values())
