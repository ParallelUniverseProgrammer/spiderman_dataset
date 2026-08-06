#!/usr/bin/env python3
"""v5_layer.py — the additive v5 layer: performances, and the second ring.

`apply(conn, cur)` runs v4's layer (which runs v3's) and then its own, so
build_db_v5.py can hand build_db_v2.py a single module and get v2 + v3 + v4 + v5
in one pass. It reads the JSON under data_raw/v5/ written by
fetch_related_characters.py and fetch_screen_cast.py, so it is offline and
deterministic.

It obeys the rule its two predecessors do, and build_db_v5.py's `--check`
enforces it against all three: nothing an earlier version wrote is changed
except to fill a NULL, and no existing table changes shape.

What v5 is about
----------------
v4 resolved the dataset's edges into rows. v5 goes after the two places where
those rows still could not be joined to each other:

* **Who performed whom.** `work_characters.actor_person_id` was filled for 149
  of 233 film rows, 54 of 81 television rows and 0 of 487 game rows, because
  TMDB — where v2 got its cast — does not credit games. `character_portrayals`
  is one row per (work, character, performer) from four sources at once: the
  links v2 already had, `cast_crew.character_name` resolved against the
  character table, Wikidata's P725/P161 with their character-role qualifier,
  and the cast sections of the English Wikipedia articles. That is what makes
  "every actor who has played Doctor Octopus, in order" a query rather than a
  research project.
* **The other side of the character graph.** 533 of v4's 790 relationship edges
  ended in a name with no row behind it — every one of them carrying a Wikidata
  id. `related_characters` gives those 446 second-ring characters a row,
  `character_relation_targets` points each dead-end edge at it, and
  `related_character_relations` adds the 816 edges *between* them. The graph
  closes on itself instead of fraying.

Matching, and what it refuses to do
-----------------------------------
A credited character string resolves to an identity by Wikidata id first, then
by Wikipedia page, then by normalised name — and a name is only accepted when
it is unambiguous. "Spider-Man" names eleven identities in this dataset, so it
is resolved only inside a work that already lists exactly one of them; where it
cannot be narrowed the credit is dropped rather than assigned to the most
famous candidate. `character_portrayals.match_method` records which of the
three routes each row took, so the name-matched rows can be filtered out by
anyone who wants only the ones an external id vouches for.
"""
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

import v4_layer
from v4_layer import norm_name

HERE = Path(__file__).resolve().parent
V5 = HERE / "data_raw" / "v5"

RETRIEVED = "2026-08-05"

SOURCES = [
    ("wikidata", "Wikidata", "https://www.wikidata.org/", "CC0-1.0"),
    ("wikipedia", "English Wikipedia", "https://en.wikipedia.org/", "CC BY-SA 4.0"),
    ("derived", "Derived from this dataset",
     "https://github.com/spiderman-dataset", "CC BY 4.0"),
]

# Titles and honorifics that are part of a credit but not part of a name.
HONORIFICS = {"dr", "mr", "mrs", "ms", "miss", "capt", "captain", "prof",
              "professor", "sgt", "sergeant", "det", "detective", "gen",
              "general", "major", "col", "colonel", "lt", "lieutenant",
              "the", "a", "young", "old", "teen", "kid", "baby"}

# A credit line for a character that is not a character.
NON_CHARACTERS = {"narrator", "himself", "herself", "themselves", "various",
                  "various characters", "additional voices", "supporting",
                  "uncredited", "cameo", "voice", "voices", "unknown"}


SCHEMA = """
-- ---------------------------------------------------------------------------
-- v5 tables. All new; no v2, v3 or v4 table changes shape.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS v5_sources (
    source_key  TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    url         TEXT,
    licence     TEXT,
    retrieved   TEXT
);

CREATE TABLE IF NOT EXISTS v5_provenance (
    table_name  TEXT NOT NULL,
    row_key     TEXT NOT NULL,
    action      TEXT NOT NULL CHECK (action IN ('insert','fill','correct')),
    source_key  TEXT NOT NULL REFERENCES v5_sources(source_key),
    PRIMARY KEY (table_name, row_key, action)
);

-- The second ring of the character graph: everyone a v4 relationship named
-- without the dataset having a row for them. Not restricted to Spider-Man
-- characters — Mephisto, the X-Men and Richard Fisk are all here — which is the
-- point: they are what the 264 are connected *to*.
CREATE TABLE IF NOT EXISTS related_characters (
    id                 INTEGER PRIMARY KEY,
    wikidata_id        TEXT NOT NULL UNIQUE,
    name               TEXT NOT NULL,
    description        TEXT,
    wikipedia_title    TEXT,
    entity_type        TEXT,
    gender             TEXT,
    publisher          TEXT,
    narrative_universe TEXT,
    first_appearance   TEXT,
    creators           TEXT
);

-- Points a `character_relations` row whose far side was only a name at the
-- `related_characters` row it turned out to be. Its primary key is that
-- table's primary key, so the two join one to one.
CREATE TABLE IF NOT EXISTS character_relation_targets (
    identity_id INTEGER NOT NULL REFERENCES character_identities(id),
    relation    TEXT NOT NULL,
    other_name  TEXT NOT NULL,
    related_id  INTEGER NOT NULL REFERENCES related_characters(id),
    PRIMARY KEY (identity_id, relation, other_name)
);

-- Edges the second ring has among itself and back to the 264. Only edges whose
-- far side is in one of those two sets are kept, so this does not open a third
-- ring of new dead ends.
CREATE TABLE IF NOT EXISTS related_character_relations (
    related_id        INTEGER NOT NULL REFERENCES related_characters(id),
    relation          TEXT NOT NULL,
    other_name        TEXT NOT NULL,
    other_identity_id INTEGER REFERENCES character_identities(id),
    other_related_id  INTEGER REFERENCES related_characters(id),
    PRIMARY KEY (related_id, relation, other_name)
);

-- Everyone credited with performing a character. `person_id` is set when the
-- name is already a `people` row — the same arrangement `comic_creators` uses,
-- and for the same reason: a game voice actor with no film credit is a real
-- performer, but adding them to `people` would change a v2 table's contents.
CREATE TABLE IF NOT EXISTS performers (
    id              INTEGER PRIMARY KEY,
    name            TEXT NOT NULL UNIQUE,
    person_id       INTEGER REFERENCES people(id),
    wikidata_id     TEXT,
    wikipedia_title TEXT
);

-- One row per (work, character, performer). `target_kind` says which table
-- `target_id` points into: a character the dataset already had, or one of the
-- second-ring characters above — a 2017 episode credit for the Hulk is worth
-- keeping even though the Hulk is not a Spider-Man character.
CREATE TABLE IF NOT EXISTS character_portrayals (
    work_id        INTEGER NOT NULL REFERENCES media_works(id),
    target_kind    TEXT NOT NULL CHECK (target_kind IN ('identity','related')),
    target_id      INTEGER NOT NULL,
    performer_id   INTEGER NOT NULL REFERENCES performers(id),
    credited_as    TEXT,
    portrayal_type TEXT NOT NULL CHECK (portrayal_type IN ('voice','live_action')),
    origin         TEXT NOT NULL CHECK (origin IN
                       ('work_characters','cast_crew','wikidata','wikipedia')),
    match_method   TEXT NOT NULL CHECK (match_method IN
                       ('dataset','wikidata_id','wikipedia_page','name')),
    PRIMARY KEY (work_id, target_kind, target_id, performer_id)
);

CREATE INDEX IF NOT EXISTS idx_v5_prov_table ON v5_provenance(table_name);
CREATE INDEX IF NOT EXISTS idx_portrayal_performer ON character_portrayals(performer_id);
CREATE INDEX IF NOT EXISTS idx_portrayal_target ON character_portrayals(target_kind, target_id);
CREATE INDEX IF NOT EXISTS idx_rcr_other_identity ON related_character_relations(other_identity_id);
CREATE INDEX IF NOT EXISTS idx_performers_person ON performers(person_id);
"""

VIEWS = """
-- Every performance, with both ends named.
CREATE VIEW IF NOT EXISTS v_portrayals AS
SELECT p.work_id, w.title AS work_title, w.release_year, w.media_type,
       p.target_kind, p.target_id,
       COALESCE(i.canonical_name, rc.name)  AS character_name,
       i.alignment                          AS alignment,
       p.credited_as, p.portrayal_type,
       pf.id AS performer_id, pf.name AS performer, pf.person_id,
       p.origin, p.match_method
FROM character_portrayals p
JOIN media_works w  ON w.id = p.work_id
JOIN performers pf  ON pf.id = p.performer_id
LEFT JOIN character_identities i ON p.target_kind = 'identity' AND i.id = p.target_id
LEFT JOIN related_characters rc  ON p.target_kind = 'related'  AND rc.id = p.target_id;

-- Who has played this character, and over what span.
CREATE VIEW IF NOT EXISTS v_character_casting AS
SELECT i.id AS identity_id, i.canonical_name, i.alignment,
       COUNT(DISTINCT p.performer_id)      AS n_performers,
       COUNT(DISTINCT p.work_id)           AS n_works,
       MIN(w.release_year)                 AS first_year,
       MAX(w.release_year)                 AS last_year,
       SUM(p.portrayal_type = 'voice')     AS n_voice,
       SUM(p.portrayal_type = 'live_action') AS n_live_action,
       GROUP_CONCAT(DISTINCT pf.name)      AS performers
FROM character_identities i
JOIN character_portrayals p ON p.target_kind = 'identity' AND p.target_id = i.id
JOIN performers pf          ON pf.id = p.performer_id
JOIN media_works w          ON w.id = p.work_id
GROUP BY i.id;

-- The other direction: one performer's whole run through the franchise.
CREATE VIEW IF NOT EXISTS v_performer_lineage AS
SELECT pf.id AS performer_id, pf.name, pf.person_id,
       COUNT(DISTINCT p.work_id)                      AS n_works,
       COUNT(DISTINCT p.target_kind || ':' || p.target_id) AS n_characters,
       MIN(w.release_year)                            AS first_year,
       MAX(w.release_year)                            AS last_year,
       GROUP_CONCAT(DISTINCT w.media_type)            AS media_types,
       GROUP_CONCAT(DISTINCT COALESCE(i.canonical_name, rc.name)) AS characters
FROM performers pf
JOIN character_portrayals p ON p.performer_id = pf.id
JOIN media_works w          ON w.id = p.work_id
LEFT JOIN character_identities i ON p.target_kind = 'identity' AND i.id = p.target_id
LEFT JOIN related_characters rc  ON p.target_kind = 'related'  AND rc.id = p.target_id
GROUP BY pf.id;

-- Both rings of the character graph in one place. `to_kind='name'` is what is
-- left over: an edge whose far side resolved to neither table.
CREATE VIEW IF NOT EXISTS v_character_network_full AS
SELECT 'identity' AS from_kind, r.identity_id AS from_id,
       i.canonical_name AS from_name, r.relation,
       CASE WHEN r.other_identity_id IS NOT NULL THEN 'identity'
            WHEN t.related_id IS NOT NULL        THEN 'related'
            ELSE 'name' END                      AS to_kind,
       COALESCE(r.other_identity_id, t.related_id) AS to_id,
       r.other_name AS to_name
FROM character_relations r
JOIN character_identities i ON i.id = r.identity_id
LEFT JOIN character_relation_targets t
       ON t.identity_id = r.identity_id AND t.relation = r.relation
      AND t.other_name = r.other_name
UNION ALL
SELECT 'related', rr.related_id, rc.name, rr.relation,
       CASE WHEN rr.other_identity_id IS NOT NULL THEN 'identity' ELSE 'related' END,
       COALESCE(rr.other_identity_id, rr.other_related_id), rr.other_name
FROM related_character_relations rr
JOIN related_characters rc ON rc.id = rr.related_id;
"""


def load(name):
    p = V5 / name
    if not p.exists():
        return {}
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def norm_char(s):
    """Match form for a character name: no honorifics, no punctuation, no case."""
    toks = norm_name(s).split()
    while toks and toks[0] in HONORIFICS:
        toks = toks[1:]
    return " ".join(toks)


def char_keys(text):
    """The name forms one credited string should be looked up under.

    "Dr. Otto Octavius / Doctor Octopus" is one credit and three keys: the whole
    string, the civilian name and the alias, because different works credit the
    same character by each of them.
    """
    keys = []
    for part in [text] + re.split(r"\s*/\s*", text):
        k = norm_char(part)
        if k and k not in keys and k not in NON_CHARACTERS:
            keys.append(k)
    return keys


def page_key(title):
    return " ".join((title or "").replace("_", " ").split()).lower()


class Layer:
    def __init__(self, conn, cur):
        self.conn, self.cur = conn, cur
        self.counts = Counter()
        self.related_src = load("related_characters.json")
        self.cast_src = load("screen_cast.json")
        self.L = dict(self.related_src.get("labels") or {})
        for k, v in (self.cast_src.get("labels") or {}).items():
            if v:
                self.L.setdefault(k, v)
        self.related_id = {}      # qid -> related_characters.id
        self.performer_id = {}    # name -> performers.id
        self.performer_page = {}  # wikipedia page -> performers.id

    # -- plumbing ----------------------------------------------------------
    def prov(self, table, key, action, source):
        self.cur.execute(
            "INSERT OR IGNORE INTO v5_provenance (table_name,row_key,action,source_key)"
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

    def label(self, qid, default=None):
        return self.L.get(qid) or default

    def labels_of(self, qids):
        out = [self.label(q) for q in (qids or [])]
        return "; ".join(x for x in out if x) or None

    def schema(self):
        self.cur.executescript(SCHEMA)
        for key, name, url, lic in SOURCES:
            self.cur.execute(
                "INSERT OR REPLACE INTO v5_sources (source_key,name,url,licence,retrieved)"
                " VALUES (?,?,?,?,?)", (key, name, url, lic, RETRIEVED))

    # -- the second ring ---------------------------------------------------
    def identity_by_qid(self):
        """QID -> the identity that speaks for it.

        Same rule v4's graph uses: v3's resolver lands several identities on one
        Wikidata item, and the item's facts go to the one with the most credited
        spellings behind it rather than being copied onto all of them.
        """
        variants = dict(self.cur.execute(
            "SELECT id, n_variants FROM character_identities"))
        by_qid = defaultdict(list)
        for iid, qid in self.cur.execute(
                "SELECT entity_id, identifier FROM external_ids"
                " WHERE entity_type='character' AND source='wikidata'"):
            by_qid[qid].append(iid)
        return {q: sorted(ids, key=lambda i: (-variants.get(i, 0), i))[0]
                for q, ids in by_qid.items()}

    def related(self):
        src = self.related_src.get("characters") or {}
        if not src:
            return
        for n, qid in enumerate(sorted(src), start=1):
            self.related_id[qid] = n

        for qid in sorted(src):
            rec = src[qid]
            name = rec.get("name")
            if not name:
                continue
            self.ins("related_characters",
                     ["id", "wikidata_id", "name", "description", "wikipedia_title",
                      "entity_type", "gender", "publisher", "narrative_universe",
                      "first_appearance", "creators"],
                     [self.related_id[qid], qid, name, rec.get("description"),
                      rec.get("enwiki"), self.labels_of(rec.get("instance_of")),
                      self.label(rec.get("gender")), self.label(rec.get("publisher")),
                      self.labels_of(rec.get("narrative_universe")),
                      self.label(rec.get("first_appearance")),
                      self.labels_of(rec.get("creator"))],
                     f"related:{qid}")

        # Point v4's dead-end edges at the rows they turned out to name.
        written = {r[0] for r in self.cur.execute(
            "SELECT id FROM related_characters").fetchall()}
        for iid, rel, other, qid in self.cur.execute(
                "SELECT identity_id, relation, other_name, other_wikidata_id"
                " FROM character_relations WHERE other_identity_id IS NULL"
                " AND other_wikidata_id IS NOT NULL"
                " ORDER BY identity_id, relation, other_name").fetchall():
            rid = self.related_id.get(qid)
            if rid in written:
                self.ins("character_relation_targets",
                         ["identity_id", "relation", "other_name", "related_id"],
                         [iid, rel, other, rid], f"{iid}:{rel}:{other}",
                         source="derived")

        # …and the edges the second ring has of its own.
        canonical = self.identity_by_qid()
        names = dict(self.cur.execute(
            "SELECT id, canonical_name FROM character_identities"))
        for e in self.related_src.get("edges") or []:
            rid = self.related_id.get(e["from_qid"])
            if not rid:
                continue
            to_qid = e["to_qid"]
            other_iid = canonical.get(to_qid)
            other_rid = None if other_iid else self.related_id.get(to_qid)
            if other_iid:
                other = names.get(other_iid)
            elif other_rid:
                other = (src.get(to_qid) or {}).get("name") or self.label(to_qid)
            else:
                continue
            if not other or other_rid == rid:
                continue
            self.ins("related_character_relations",
                     ["related_id", "relation", "other_name", "other_identity_id",
                      "other_related_id"],
                     [rid, e["relation"], other, other_iid, other_rid],
                     f"{rid}:{e['relation']}:{other}")

    # -- performances ------------------------------------------------------
    def build_indexes(self):
        """Everything a credited string might be looked up by."""
        self.qid_to_identity = self.identity_by_qid()
        self.qid_to_related = {q: i for q, i in self.related_id.items()}

        self.page_to_identity = {}
        for iid, title in self.cur.execute(
                "SELECT identity_id, wikipedia_title FROM character_details"
                " WHERE wikipedia_title IS NOT NULL"):
            self.page_to_identity.setdefault(page_key(title), iid)
        self.page_to_related = {}
        for rid, title in self.cur.execute(
                "SELECT id, wikipedia_title FROM related_characters"
                " WHERE wikipedia_title IS NOT NULL"):
            self.page_to_related.setdefault(page_key(title), rid)

        # name key -> identities. A key claimed by more than one identity is
        # kept, and only used where a work narrows it to one.
        self.name_to_identities = defaultdict(set)
        for iid, name in self.cur.execute(
                "SELECT id, canonical_name FROM character_identities"):
            for k in char_keys(name):
                self.name_to_identities[k].add(iid)
        for iid, name, alias in self.cur.execute(
                "SELECT identity_id, name, alias FROM characters"
                " WHERE identity_id IS NOT NULL"):
            for k in char_keys(name) + char_keys(alias or ""):
                self.name_to_identities[k].add(iid)

        self.name_to_related = defaultdict(set)
        for rid, name in self.cur.execute("SELECT id, name FROM related_characters"):
            for k in char_keys(name):
                self.name_to_related[k].add(rid)

        # the identities a work is already known to feature
        self.work_identities = defaultdict(set)
        self.work_characters = defaultdict(dict)   # work -> identity -> [char ids]
        for wid, cid, iid in self.cur.execute(
                "SELECT wc.work_id, wc.character_id, c.identity_id"
                " FROM work_characters wc JOIN characters c ON c.id = wc.character_id"
                " WHERE c.identity_id IS NOT NULL"):
            self.work_identities[wid].add(iid)
            self.work_characters[wid].setdefault(iid, []).append(cid)

        self.people_by_name, self.people_by_qid, self.people_name = {}, {}, {}
        for pid, name, wd in self.cur.execute(
                "SELECT id, name, wikidata_id FROM people"):
            self.people_by_name.setdefault(norm_name(name), pid)
            self.people_name[pid] = name
            if wd:
                self.people_by_qid.setdefault(wd, pid)

        # works whose performances are voiced rather than acted
        self.voiced = {wid for (wid,) in self.cur.execute(
            "SELECT id FROM media_works WHERE media_type='game'")}
        self.voiced |= {wid for (wid,) in self.cur.execute(
            "SELECT DISTINCT work_id FROM work_genres WHERE genre LIKE '%anim%'")}

    def resolve_character(self, work_id, text, pages=(), qid=None):
        """(target_kind, target_id, match_method) or None. Never guesses.

        The dataset's own 264 identities are tried by all three routes before
        the second ring is tried by any of them. Otherwise Tom Hardy's Venom
        resolves to the second-ring item for the symbiote — Wikipedia links it
        there — rather than to the `Eddie Brock / Venom` identity the film is
        already recorded as featuring, and the same character would end up
        split across two tables.
        """
        keys = char_keys(text or "")
        scope = self.work_identities.get(work_id, set())

        if qid and qid in self.qid_to_identity:
            return "identity", self.qid_to_identity[qid], "wikidata_id"
        for page in pages or ():
            if page_key(page) in self.page_to_identity:
                return "identity", self.page_to_identity[page_key(page)], "wikipedia_page"
        for k in keys:                       # inside the work first
            hit = self.name_to_identities.get(k, set()) & scope
            if len(hit) == 1:
                return "identity", next(iter(hit)), "name"
        for k in keys:                       # then dataset-wide, if unambiguous
            hit = self.name_to_identities.get(k, set())
            if len(hit) == 1:
                return "identity", next(iter(hit)), "name"

        if qid and qid in self.qid_to_related:
            return "related", self.qid_to_related[qid], "wikidata_id"
        for page in pages or ():
            if page_key(page) in self.page_to_related:
                return "related", self.page_to_related[page_key(page)], "wikipedia_page"
        for k in keys:
            hit = self.name_to_related.get(k, set())
            if len(hit) == 1:
                return "related", next(iter(hit)), "name"
        return None

    def performer(self, name, qid=None, page=None):
        """performers.id for a credited name, inserting the row on first sight."""
        name = " ".join((name or "").split())
        if not name or len(name) < 3:
            return None
        pid = self.people_by_qid.get(qid) if qid else None
        if pid is None:
            pid = self.people_by_name.get(norm_name(name))
        if pid is not None:
            name = self.people_name[pid]     # the dataset's spelling wins
        if name in self.performer_id:
            return self.performer_id[name]
        # Two articles crediting "Ed Asner" and "Edward Asner" link the same
        # page, and that is the only thing that says they are one performer.
        if page and page_key(page) in self.performer_page:
            return self.performer_page[page_key(page)]
        new_id = len(self.performer_id) + 1
        self.performer_id[name] = new_id
        if page:
            self.performer_page.setdefault(page_key(page), new_id)
        self.ins("performers", ["id", "name", "person_id", "wikidata_id",
                                "wikipedia_title"],
                 [new_id, name, pid, qid, page], f"performer:{name}",
                 source="derived" if qid is None else "wikidata")
        return new_id

    def portrayal(self, work_id, target, performer_id, credited_as, origin,
                  source, voice=None):
        kind, tid, method = target
        if voice is None:
            voice = work_id in self.voiced
        self.ins("character_portrayals",
                 ["work_id", "target_kind", "target_id", "performer_id",
                  "credited_as", "portrayal_type", "origin", "match_method"],
                 [work_id, kind, tid, performer_id, credited_as,
                  "voice" if voice else "live_action", origin, method],
                 f"{work_id}:{kind}:{tid}:{performer_id}", source=source)

    def portrayals_from_dataset(self):
        """The links v2 already had, restated in the portrayal table."""
        for wid, cid, iid, cname, pid, pname in self.cur.execute(
                "SELECT wc.work_id, wc.character_id, c.identity_id, c.name,"
                "       wc.actor_person_id, p.name"
                "  FROM work_characters wc"
                "  JOIN characters c ON c.id = wc.character_id"
                "  JOIN people p     ON p.id = wc.actor_person_id"
                " WHERE c.identity_id IS NOT NULL"
                " ORDER BY wc.work_id, wc.character_id").fetchall():
            perf = self.performer(pname)
            if perf:
                self.portrayal(wid, ("identity", iid, "dataset"), perf, cname,
                               "work_characters", "derived")

    def portrayals_from_cast_crew(self):
        """`cast_crew.character_name` is a string; resolve it to a character."""
        for wid, pid, pname, cname in self.cur.execute(
                "SELECT cc.work_id, cc.person_id, p.name, cc.character_name"
                "  FROM cast_crew cc JOIN people p ON p.id = cc.person_id"
                " WHERE cc.character_name IS NOT NULL AND cc.role = 'actor'"
                " ORDER BY cc.work_id, cc.person_id").fetchall():
            perf = self.performer(pname)
            if not perf:
                continue
            # "Luke Cage / Power Man; Miles Morales" is two characters credited
            # to one actor; the slash inside each is one character's two names.
            for piece in re.split(r"\s*;\s*", cname):
                target = self.resolve_character(wid, piece)
                if target:
                    self.portrayal(wid, target, perf, piece.strip(),
                                   "cast_crew", "derived")

    def portrayals_from_wikidata(self):
        for wid, rows in sorted((self.cast_src.get("wikidata") or {}).items(),
                                key=lambda kv: int(kv[0])):
            wid = int(wid)
            for r in rows:
                qid = r.get("character_qid")
                if not qid:
                    continue
                target = self.resolve_character(wid, self.label(qid) or "", qid=qid)
                if not target:
                    continue
                perf = self.performer(self.label(r["person_qid"]), qid=r["person_qid"])
                if perf:
                    self.portrayal(wid, target, perf, self.label(qid), "wikidata",
                                   "wikidata",
                                   voice=True if r["kind"] == "voice" else None)

    def portrayals_from_wikipedia(self):
        for wid, rows in sorted((self.cast_src.get("wikipedia") or {}).items(),
                                key=lambda kv: int(kv[0])):
            wid = int(wid)
            for r in rows:
                target = self.resolve_character(wid, r["character"],
                                                pages=r.get("character_pages"))
                if not target:
                    continue
                perf = self.performer(r["performer"], page=r.get("performer_page"))
                if not perf:
                    continue
                section = (r.get("section") or "").lower()
                voice = True if "voice" in section else None
                self.portrayal(wid, target, perf, r["character"], "wikipedia",
                               "wikipedia", voice=voice)

    def fill_actor_links(self):
        """Fill work_characters.actor_person_id from the portrayals just built.

        Only where it is unambiguous: one performer with a `people` row for that
        work and identity, and one un-filled `work_characters` row to put them
        on. A character played by two actors in one film leaves the column NULL,
        the same way it was before — `character_portrayals` holds both.
        """
        by_pair = defaultdict(set)
        for wid, tid, pid in self.cur.execute(
                "SELECT p.work_id, p.target_id, pf.person_id"
                "  FROM character_portrayals p JOIN performers pf"
                "    ON pf.id = p.performer_id"
                " WHERE p.target_kind = 'identity' AND pf.person_id IS NOT NULL"):
            by_pair[(wid, tid)].add(pid)

        for (wid, iid), pids in sorted(by_pair.items()):
            if len(pids) != 1:
                continue
            person = next(iter(pids))
            rows = [cid for cid in self.work_characters.get(wid, {}).get(iid, [])]
            open_rows = [cid for cid in rows if self.cur.execute(
                "SELECT 1 FROM work_characters WHERE work_id=? AND character_id=?"
                " AND actor_person_id IS NULL", (wid, cid)).fetchone()]
            if len(open_rows) != 1:
                continue
            self.cur.execute(
                "UPDATE work_characters SET actor_person_id=?"
                " WHERE work_id=? AND character_id=? AND actor_person_id IS NULL",
                (person, wid, open_rows[0]))
            if self.cur.rowcount:
                self.counts["work_characters.actor_person_id"] += 1
                self.prov("work_characters", f"{wid}:{open_rows[0]}:actor_person_id",
                          "fill", "derived")

    def views(self):
        self.cur.executescript(VIEWS)

    def run(self):
        self.schema()
        self.related()
        self.build_indexes()
        self.portrayals_from_dataset()
        self.portrayals_from_cast_crew()
        self.portrayals_from_wikidata()
        self.portrayals_from_wikipedia()
        self.fill_actor_links()
        self.views()
        return self.counts


def apply(conn, cur):
    """v4's layer (and so v3's), then v5's. build_db_v2.py calls this once."""
    added = v4_layer.apply(conn, cur)
    total = Layer(conn, cur).run()
    print("  v5 layer:")
    for k, v in sorted(total.items()):
        print(f"      {k:38} {v}")
    return added + sum(total.values())
