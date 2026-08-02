#!/usr/bin/env python3
"""
build_db_v2.py — Build the enriched Spider-Man media database (v2).
Schema upgrades from v1:
  - Drops migrated denormalized columns from movies/games detail tables
    (rotten_tomatoes_score, metacritic_score, imdb_score from movies;
     metacritic_score/esrb_rating from games); canonical data moves to
     new normalized tables.
  - Adds 14 new tables (characters, work_characters, cast_crew,
    game_releases, review_scores, studios, work_studios, box_office_weekly,
    budgets, awards, episodes, work_relations, source_material, soundtracks).
  - Enriches people from data_raw/people_external.json (written by
    fetch_tmdb_people.py): birth/death date, birth place, IMDb, Wikidata, TMDB ids.
  - Reads movies.json and games.json from data_raw/ (agent research).
  - Embedded TV enrichment data for 14 series (from research agent).
  - Exports per-table CSVs + updated flat CSV + updated README.
"""

import collections
import csv
import json
import os
import re
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).parent
DATA_DIR = HERE / "data"
RAW_DIR = HERE / "data_raw"
DB_PATH = HERE / "spiderman.db"

DATA_DIR.mkdir(exist_ok=True)
RAW_DIR.mkdir(exist_ok=True)

# ---------------------------------------------------------------------------
# Wipe prior DB
# ---------------------------------------------------------------------------
if DB_PATH.exists():
    DB_PATH.unlink()

conn = sqlite3.connect(DB_PATH)
conn.execute("PRAGMA foreign_keys = ON")
cur = conn.cursor()

# ===========================================================================
# SCHEMA
# ===========================================================================
cur.executescript("""
CREATE TABLE franchises (
    id          INTEGER PRIMARY KEY,
    name        TEXT UNIQUE NOT NULL,
    description TEXT
);

CREATE TABLE media_works (
    id            INTEGER PRIMARY KEY,
    title         TEXT NOT NULL,
    release_year  INTEGER,
    release_date  TEXT,
    media_type    TEXT NOT NULL CHECK (media_type IN ('movie','tv_show','game')),
    franchise_id  INTEGER REFERENCES franchises(id),
    notes         TEXT
);

-- Movies detail (v2 drops v1 denormalized score/actor columns)
CREATE TABLE movies (
    work_id         INTEGER PRIMARY KEY REFERENCES media_works(id),
    sub_type        TEXT,
    studio          TEXT,
    distributor     TEXT,
    director        TEXT,
    producer        TEXT,
    runtime_minutes INTEGER,
    mpaa_rating     TEXT,
    notes           TEXT
);

-- TV shows detail
CREATE TABLE tv_shows (
    work_id                 INTEGER PRIMARY KEY REFERENCES media_works(id),
    sub_type                TEXT,
    format                  TEXT,
    network                 TEXT,
    start_year              INTEGER,
    end_year                INTEGER,
    seasons                 INTEGER,
    episodes                INTEGER,
    head_writer             TEXT,
    voice_actor_spider_man  TEXT,
    status                  TEXT
);

-- Games detail (v2 drops v1 denormalized score/rating columns)
CREATE TABLE games (
    work_id   INTEGER PRIMARY KEY REFERENCES media_works(id),
    genre     TEXT,
    engine    TEXT,
    universe  TEXT,
    notes     TEXT
);

-- NEW: character identities — the person, as opposed to the credit string.
-- Each source file names the same character its own way ("Spider-Man / Peter
-- Parker" in games.json, "Peter Parker / Spider-Man" in movies.json, "Peter
-- Parker" in tv.json), so a UNIQUE(name) on characters enforces string
-- uniqueness but not identity: 416 credit strings describe ~303 people.
-- characters rows stay verbatim; this table is what analysis should group by.
CREATE TABLE character_identities (
    id                  INTEGER PRIMARY KEY,
    canonical_name      TEXT NOT NULL UNIQUE,
    alignment           TEXT CHECK (alignment IN ('hero','villain','neutral','antihero')),
    first_comic_title   TEXT,
    first_comic_year    INTEGER,
    n_variants          INTEGER NOT NULL,
    merge_rule          TEXT NOT NULL CHECK (merge_rule IN ('singleton','token_set','alias_map'))
);

-- NEW: characters (one row per credit string as the research spells it)
-- alignment is normalized to a 4-value enum; alignment_raw keeps the research string.
-- identity_id resolves the row to the underlying person.
CREATE TABLE characters (
    id                  INTEGER PRIMARY KEY,
    name                TEXT NOT NULL UNIQUE,
    alias               TEXT,
    alignment           TEXT CHECK (alignment IN ('hero','villain','neutral','antihero')),
    alignment_raw       TEXT,
    first_comic_title   TEXT,
    first_comic_year    INTEGER,
    identity_id         INTEGER REFERENCES character_identities(id)
);

-- NEW: many:many work <-> character via actor/person
CREATE TABLE work_characters (
    work_id        INTEGER REFERENCES media_works(id),
    character_id   INTEGER REFERENCES characters(id),
    actor_person_id INTEGER REFERENCES people(id),
    billing_order  INTEGER,
    notes          TEXT,
    PRIMARY KEY (work_id, character_id)
);

-- NEW: cast & crew (unified people per work)
CREATE TABLE cast_crew (
    work_id        INTEGER REFERENCES media_works(id),
    person_id      INTEGER REFERENCES people(id),
    role           TEXT NOT NULL,
    character_name TEXT,
    credit_order   INTEGER,
    PRIMARY KEY (work_id, person_id, role, character_name)
);

-- NEW: game per-platform releases
CREATE TABLE game_releases (
    id               INTEGER PRIMARY KEY,
    game_work_id     INTEGER REFERENCES media_works(id),
    platform_id      INTEGER REFERENCES platforms(id),
    release_date     TEXT,
    publisher        TEXT,
    developer        TEXT,
    metacritic_score INTEGER,
    esrb_rating      TEXT
);

-- NEW: multi-source review scores
-- max_score is nullable: most research entries omit it, and it is inferred from
-- the publication's known scale rather than used as a reason to drop the score.
-- source is the raw research string and carries the reviewed platform inside it
-- ("Metacritic (PS3)"), which makes it useless as a GROUP BY key: 128 distinct
-- strings stand for 36 publications. publication and platform_scope split it.
CREATE TABLE review_scores (
    work_id        INTEGER REFERENCES media_works(id),
    source         TEXT NOT NULL,
    publication    TEXT NOT NULL,
    platform_scope TEXT,
    score          REAL NOT NULL,
    max_score      REAL,
    score_pct      REAL,
    review_count   INTEGER,
    PRIMARY KEY (work_id, source)
);

-- NEW: studios as entities
CREATE TABLE studios (
    id             INTEGER PRIMARY KEY,
    name           TEXT UNIQUE NOT NULL,
    country        TEXT,
    parent_company TEXT
);

-- NEW: many:many work <-> studio with role
-- role is part of the PK: a studio is frequently both developer and publisher of
-- the same game, and a (work_id, studio_id) PK silently discards the second role.
CREATE TABLE work_studios (
    work_id   INTEGER REFERENCES media_works(id),
    studio_id INTEGER REFERENCES studios(id),
    role      TEXT NOT NULL CHECK (role IN (
                    'production','co_production','distributor','financing',
                    'in_association_with','developer','co_developer','publisher','port')),
    PRIMARY KEY (work_id, studio_id, role)
);

-- NEW: box office. Two different measurements share this table, so scope says
-- which one a row is. 16 of the 17 films carry a single full-run total that the
-- research filed under week_number = 1; only Venom: The Last Dance has a real
-- week-by-week series. Reading every week-1 row as an opening week silently
-- compares a lifetime gross against one week of another film.
CREATE TABLE box_office (
    id                 INTEGER PRIMARY KEY,
    work_id            INTEGER REFERENCES media_works(id),
    scope              TEXT NOT NULL CHECK (scope IN ('week','lifetime')),
    week_number        INTEGER,          -- NULL when scope='lifetime'
    week_start_date    TEXT,
    domestic_usd       INTEGER,
    international_usd  INTEGER,
    worldwide_usd      INTEGER,
    UNIQUE (work_id, scope, week_number)
);

-- NEW: budget breakdowns.
-- A component can carry rival published estimates (Madame Web is reported at both
-- $80M and $100M). Both are kept; is_primary marks the one figure per
-- (work, component) that rollups and ROI should use, so a SUM cannot double-count.
CREATE TABLE budgets (
    id                    INTEGER PRIMARY KEY,
    work_id               INTEGER REFERENCES media_works(id),
    amount_usd            INTEGER NOT NULL,
    currency              TEXT DEFAULT 'USD',
    component             TEXT CHECK (component IN ('production','marketing','total')),
    inflation_adj_2024    INTEGER,
    source_year           INTEGER,
    is_primary            INTEGER NOT NULL DEFAULT 1 CHECK (is_primary IN (0,1)),
    note                  TEXT,
    UNIQUE (work_id, component, amount_usd)
);

-- NEW: awards & nominations
CREATE TABLE awards (
    work_id                INTEGER REFERENCES media_works(id),
    award_body             TEXT NOT NULL,
    year                   INTEGER,
    category               TEXT NOT NULL,
    result                 TEXT CHECK (result IN ('won','nominated')),
    recipient_person_id    INTEGER REFERENCES people(id),
    PRIMARY KEY (work_id, award_body, year, category, result)
);

-- NEW: TV episodes (granular)
CREATE TABLE episodes (
    id                     INTEGER PRIMARY KEY,
    show_work_id           INTEGER REFERENCES media_works(id),
    season_number          INTEGER,
    episode_number         INTEGER,
    title                  TEXT,
    air_date               TEXT,
    runtime_minutes        INTEGER,
    director               TEXT,
    writer                 TEXT,
    us_viewers_millions    REAL
);

-- NEW: work-to-work relations (graph edges)
CREATE TABLE work_relations (
    work_a_id      INTEGER REFERENCES media_works(id),
    work_b_id      INTEGER REFERENCES media_works(id),
    relation_type  TEXT NOT NULL CHECK (relation_type IN (
                        'sequel','prequel','spin_off','remake','same_universe',
                        'crossover','tie_in_game_of','adapted_from','dlc_of',
                        'inspired','prequel_in_lineage','related','remaster_of','tie_in')),
    PRIMARY KEY (work_a_id, work_b_id, relation_type)
);

-- NEW: source material (comic origins)
CREATE TABLE source_material (
    id              INTEGER PRIMARY KEY,
    work_id         INTEGER REFERENCES media_works(id),
    comic_title     TEXT,
    issue_range     TEXT,
    comic_writer    TEXT,
    comic_year      INTEGER,
    storyline_arc   TEXT
);

-- NEW: soundtracks / music
CREATE TABLE soundtracks (
    id                      INTEGER PRIMARY KEY,
    work_id                 INTEGER REFERENCES media_works(id),
    type                    TEXT CHECK (type IN ('score','song')) NOT NULL,
    title                   TEXT,
    composer_or_performer   TEXT,
    release_date            TEXT,
    chart_peak_us           TEXT,
    chart_peak_uk           TEXT
);

-- Platforms (unchanged from v1)
CREATE TABLE platforms (
    id   INTEGER PRIMARY KEY,
    name TEXT UNIQUE NOT NULL
);

-- Game platforms junction (replaces v1 game_platforms; now more detailed)
CREATE TABLE game_platforms (
    game_id     INTEGER REFERENCES media_works(id),
    platform_id INTEGER REFERENCES platforms(id),
    PRIMARY KEY (game_id, platform_id)
);

-- People (enriched from TMDB via fetch_tmdb_people.py -> data_raw/people_external.json)
-- nationality has no TMDB equivalent and stays NULL; birth_place is not a
-- substitute for it, so it is not derived from one.
CREATE TABLE people (
    id            INTEGER PRIMARY KEY,
    name          TEXT UNIQUE NOT NULL,
    birth_date    TEXT,
    death_date    TEXT,
    birth_place   TEXT,
    nationality   TEXT,
    imdb_id       TEXT,
    wikidata_id   TEXT,
    tmdb_id       INTEGER,
    external_match_method TEXT
);

-- Work people (v2 replaces v1 work_people with richer cast_crew table;
-- this table still used for non-character roles like director, producer, composer)
CREATE TABLE work_people (
    work_id   INTEGER REFERENCES media_works(id),
    person_id INTEGER REFERENCES people(id),
    role      TEXT NOT NULL,
    PRIMARY KEY (work_id, person_id, role)
);

-- A work is identified by (title, release_year, media_type). Unreleased works have a
-- NULL release_year, which SQLite treats as distinct, so they never collide here.
CREATE UNIQUE INDEX idx_media_works_identity
    ON media_works (title, release_year, media_type);

-- ---------------------------------------------------------------------------
-- Analysis views. Each one exists because the naive query over the base tables
-- is wrong in a way that is not obvious from the schema.
-- ---------------------------------------------------------------------------

-- Appearances per *character*, not per credit string. Counting work_characters
-- directly splits Spider-Man across 7 rows and Doctor Octopus across 4.
CREATE VIEW v_character_appearances AS
SELECT ci.id            AS identity_id,
       ci.canonical_name,
       ci.alignment,
       ci.first_comic_year,
       wc.work_id,
       w.media_type,
       w.release_year,
       wc.actor_person_id,
       wc.billing_order
FROM work_characters wc
JOIN characters c            ON c.id  = wc.character_id
JOIN character_identities ci ON ci.id = c.identity_id
JOIN media_works w           ON w.id  = wc.work_id;

-- One row per (character, work): the same person credited under two spellings in
-- one work collapses to a single appearance.
CREATE VIEW v_character_work AS
SELECT DISTINCT identity_id, canonical_name, alignment, first_comic_year,
       work_id, media_type, release_year
FROM v_character_appearances;

-- Film economics. Uses the lifetime gross and the primary budget estimate only.
CREATE VIEW v_film_economics AS
SELECT w.id AS work_id, w.title, w.release_year, f.name AS franchise,
       b.amount_usd            AS production_budget_usd,
       bo.worldwide_usd        AS lifetime_worldwide_usd,
       bo.domestic_usd         AS lifetime_domestic_usd,
       ROUND(bo.worldwide_usd * 1.0 / b.amount_usd, 2) AS gross_multiple
FROM media_works w
JOIN franchises f ON f.id = w.franchise_id
LEFT JOIN budgets b     ON b.work_id = w.id AND b.component = 'production' AND b.is_primary = 1
LEFT JOIN box_office bo ON bo.work_id = w.id AND bo.scope = 'lifetime'
WHERE w.media_type = 'movie';

-- Review scores grouped by publication rather than by the raw platform-tagged
-- source string.
CREATE VIEW v_review_by_publication AS
SELECT r.work_id, w.title, w.media_type, r.publication, r.platform_scope,
       r.score, r.max_score, r.score_pct
FROM review_scores r JOIN media_works w ON w.id = r.work_id;
""")

# ===========================================================================
# HELPER FUNCTIONS
# ===========================================================================
def add_person(name):
    cur.execute("INSERT OR IGNORE INTO people(name) VALUES (?)", (name,))
    return cur.execute("SELECT id FROM people WHERE name=?", (name,)).fetchone()[0]

def get_person_id(name):
    row = cur.execute("SELECT id FROM people WHERE name=?", (name,)).fetchone()
    return row[0] if row else None

def add_studio(name, country=None, parent_company=None):
    cur.execute("""INSERT OR IGNORE INTO studios(name, country, parent_company)
                   VALUES (?,?,?)""", (name, country, parent_company))
    return cur.execute("SELECT id FROM studios WHERE name=?", (name,)).fetchone()[0]

def add_platform(name):
    cur.execute("INSERT OR IGNORE INTO platforms(name) VALUES (?)", (name,))
    return cur.execute("SELECT id FROM platforms WHERE name=?", (name,)).fetchone()[0]

def add_character(name, alias=None, alignment=None, alignment_raw=None,
                  first_comic_title=None, first_comic_year=None):
    """Insert a character, or fill in fields a previously-seen record left NULL.

    The same character appears in many works with unevenly complete data, so later
    sightings top up missing columns instead of being discarded wholesale."""
    cur.execute("""INSERT OR IGNORE INTO characters(name, alias, alignment, alignment_raw,
                       first_comic_title, first_comic_year)
                   VALUES (?,?,?,?,?,?)""",
                (name, alias, alignment, alignment_raw, first_comic_title, first_comic_year))
    cur.execute("""UPDATE characters SET
                       alias             = COALESCE(alias, ?),
                       alignment         = COALESCE(alignment, ?),
                       alignment_raw     = COALESCE(alignment_raw, ?),
                       first_comic_title = COALESCE(first_comic_title, ?),
                       first_comic_year  = COALESCE(first_comic_year, ?)
                   WHERE name = ?""",
                (alias, alignment, alignment_raw, first_comic_title, first_comic_year, name))
    return cur.execute("SELECT id FROM characters WHERE name=?", (name,)).fetchone()[0]

def add_media_work(title, release_year, release_date, media_type, franchise_name, notes=""):
    fid = franchises[franchise_name]
    cur.execute("""INSERT INTO media_works(title, release_year, release_date, media_type, franchise_id, notes)
                   VALUES (?,?,?,?,?,?)""",
                (title, release_year, release_date, media_type, fid, notes))
    return cur.lastrowid

def parse_year_from_comic_appearance(text):
    """Extract a publication year from 'Amazing Fantasy #15 (1962)' or '1962'.

    Prefers a parenthesised year, because a bare 4-digit scan reads the '2099' out
    of 'Spider-Man 2099 #1 (1992)' and the issue number out of 'Amazing Spider-Man
    #1000'. Only years that could plausibly be a comic publication date count.
    """
    if not text:
        return None
    s = str(text)
    parenthesised = re.findall(r'\((\d{4})\)', s)
    for y in parenthesised:
        if 1930 <= int(y) <= 2100:
            return int(y)
    # No parenthesised year: accept a bare year, but never one glued to a '#' issue
    # number and never one that is part of the title (e.g. the 2099 imprint).
    for m in re.finditer(r'(?<!#)(?<!\d)(\d{4})(?!\d)', s):
        y = int(m.group(1))
        if 1930 <= y <= 2100 and not re.search(rf'#\s*\d*{y}', s):
            return y
    return None


# Research alignment strings carry parentheticals and plurals ("villain (Xbox only)",
# "heroes", "villain/antihero"). Collapse them onto the 4-value enum, keeping the
# original string in characters.alignment_raw.
ALIGNMENT_ENUM = ("hero", "villain", "neutral", "antihero")

def normalize_alignment(raw):
    """Map a free-text alignment onto hero/villain/neutral/antihero, or None."""
    if not raw:
        return None
    s = str(raw).lower()
    s = re.sub(r'\(.*?\)', ' ', s)          # drop "(cameo)", "(PS2/PSP)", ...
    s = s.replace('_', ' ').strip()
    # A slash means the source could not decide; the first term is the primary read.
    head = re.split(r'[/,;]', s)[0].strip()
    for token in (head, s):
        t = token.rstrip('s').strip()       # "villains" -> "villain"
        if t.startswith('antihero') or t.startswith('anti-hero'):
            return 'antihero'
        if t.startswith('hero'):
            return 'hero'
        if t.startswith('villain'):
            return 'villain'
        if t.startswith('neutral'):
            return 'neutral'
    # Narrators, groups and other one-offs are not aligned either way.
    if 'narrator' in s:
        return 'neutral'
    return None

# ===========================================================================
# CHARACTER IDENTITY RESOLUTION
# ===========================================================================
# movies.json, tv.json and games.json each spell the same character differently,
# and the loader keys characters on the raw string, so one person becomes many
# rows: "Spider-Man / Peter Parker" (26 works), "Peter Parker / Spider-Man" (14),
# "Spider-Man" (11), "Peter Parker" (7). Two rules resolve them.
#
# Rule 1 (token_set) — two credit strings naming the same set of identities in a
# different order, or differing only by a trailing parenthetical, are the same
# character. "Green Goblin / Norman Osborn" == "Norman Osborn / Green Goblin" ==
# "Green Goblin / Norman Osborn (DS)". This is purely mechanical and safe.
#
# Rule 2 (alias_map) — a codename and its civilian name are the same person, but
# only where that pairing is unambiguous. This cannot be inferred: several
# codenames are *shared mantles* held by different people ("Spider-Man" is Peter
# Parker, Miles Morales, Peter B. Parker, Takuya Yamashiro and Spider-Man Noir;
# "Doctor Octopus" is Otto and Olivia Octavius; "Venom" is Eddie Brock and Harry
# Osborn). Merging on those would fuse distinct characters, so the pairs are
# listed explicitly and shared mantles are deliberately absent.
# A credit string names a character in two different ways, and conflating them is
# what fragmented the catalogue:
#
#   names   — tokens that identify one specific person ("peter parker",
#             "eddie brock"). Unique to a single character.
#   mantles — codenames that a *succession* of people have worn ("spider-man" is
#             Peter, Miles, Peter B. Parker, Takuya Yamashiro and Spider-Man Noir;
#             "green goblin" is Norman and Harry). Shared, so a mantle alone
#             cannot identify anyone.
#
# The research only qualifies a mantle when the bearer is NOT the usual one — it
# writes "Miles Morales / Spider-Man" but plain "Spider-Man" for Peter — so an
# unqualified mantle resolves to its default bearer, recorded in MANTLE_DEFAULT.
# Every default below was checked against the underlying credits: all nine bare
# "Green Goblin" rows are Norman, all six bare "Venom" rows are Eddie Brock, and
# the bare "Spider-Man" rows carry the canonical Spider-Man voice actors.
CHARACTER_IDENTITIES = {
    "Peter Parker / Spider-Man": {"names": ["peter parker"],
                                  "mantles": ["spider-man", "amazing spider-man",
                                              "ultimate spider-man"]},
    "Miles Morales":      {"names": ["miles morales"],      "mantles": ["spider-man"]},
    "Spider-Man Noir":    {"names": ["spider-man noir"],    "mantles": []},
    "Green Goblin / Norman Osborn": {"names": ["norman osborn"], "mantles": ["green goblin"]},
    "Harry Osborn":       {"names": ["harry osborn"],       "mantles": ["green goblin", "new goblin"]},
    "Eddie Brock / Venom":{"names": ["eddie brock"],        "mantles": ["venom", "anti-venom"]},
    "Doctor Octopus":     {"names": ["otto octavius"],      "mantles": ["doctor octopus"]},
    "Gwen Stacy":         {"names": ["gwen stacy"],         "mantles": ["spider-gwen", "spider-woman"]},
    "Electro":            {"names": ["max dillon"],         "mantles": ["electro", "hyper-electro"]},
    "Sandman":            {"names": ["flint marko"],        "mantles": ["sandman"]},
    "Mysterio":           {"names": ["quentin beck"],       "mantles": ["mysterio"]},
    "Rhino":              {"names": ["aleksei sytsevich"],  "mantles": ["rhino"]},
    "Scorpion":           {"names": ["mac gargan"],         "mantles": ["scorpion"]},
    "Carnage":            {"names": ["cletus kasady"],      "mantles": ["carnage", "carnage killer"]},
    "Lizard":             {"names": ["curt connors"],       "mantles": ["lizard"]},
    "Black Cat":          {"names": ["felicia hardy"],      "mantles": ["black cat"]},
    "Aunt May":           {"names": ["may parker", "aunt may"], "mantles": []},
    "Uncle Ben":          {"names": ["ben parker", "uncle ben"], "mantles": []},
    "Vulture":            {"names": ["adrian toomes"],      "mantles": ["vulture"]},
    "Kingpin":            {"names": ["wilson fisk"],        "mantles": ["kingpin"]},
    "Tombstone":          {"names": ["lonnie lincoln"],     "mantles": ["tombstone"]},
    "Kraven the Hunter":  {"names": ["sergei kravinoff"],   "mantles": ["kraven the hunter"]},
    "Shocker":            {"names": ["herman schultz"],     "mantles": ["shocker"]},
    "Silk":               {"names": ["cindy moon"],         "mantles": ["silk"]},
    "Captain America":    {"names": ["steve rogers"],       "mantles": ["captain america"]},
    "Daredevil":          {"names": ["matt murdock"],       "mantles": ["daredevil"]},
    "Silver Sable":       {"names": ["silver sablinova"],   "mantles": ["silver sable"]},
    # Supporting cast and guest heroes, split the same way. Three of these are
    # plain spelling variants of one person: Johnathon/Jonathan Ohnn,
    # Phin/Phineas Mason, Hobie/Hobart Brown.
    "Hulk":               {"names": ["bruce banner"],       "mantles": ["hulk"]},
    "Doctor Doom":        {"names": ["victor von doom"],    "mantles": ["doctor doom"]},
    "Doctor Strange":     {"names": ["stephen strange"],    "mantles": ["doctor strange"]},
    "Wolverine":          {"names": ["logan"],              "mantles": ["wolverine"]},
    "Spider-Ham":         {"names": ["peter porker"],       "mantles": ["spider-ham"]},
    "Spider-Girl":        {"names": ["mayday parker"],      "mantles": ["spider-girl"]},
    "Spider-Punk":        {"names": ["hobart brown"],       "mantles": ["spider-punk"]},
    "Shriek":             {"names": ["frances barrison"],   "mantles": ["shriek"]},
    "The Spot":           {"names": ["jonathan ohnn", "johnathon ohnn"], "mantles": ["the spot"]},
    "Tinkerer":           {"names": ["phineas mason", "phin mason"],     "mantles": ["tinkerer"]},
    "Chameleon":          {"names": ["dmitri smerdyakov", "dmitri kravinoff"], "mantles": ["chameleon"]},
    "Yuri Watanabe":      {"names": ["yuri watanabe"],      "mantles": ["wraith"]},
    "Ben Reilly / Scarlet Spider": {"names": ["ben reilly"], "mantles": ["scarlet spider"]},
    # A distinct Spider-Man, so he claims the mantle rather than deferring to Peter.
    "Takuya Yamashiro / Spider-Man": {"names": ["takuya yamashiro"], "mantles": ["spider-man"]},
    # The research writes her civilian name with a nickname in quotes, which
    # character_tokens flattens to "cassandra cassie webb".
    "Madame Web":         {"names": ["cassandra webb", "cassandra cassie webb"],
                           "mantles": ["madame web"]},
}

# Who a bare, unqualified codename means. A mantle with no entry here identifies
# nobody on its own and is left as its own identity.
MANTLE_DEFAULT = {
    "spider-man":        "Peter Parker / Spider-Man",
    "amazing spider-man":"Peter Parker / Spider-Man",
    "ultimate spider-man":"Peter Parker / Spider-Man",
    "green goblin":      "Green Goblin / Norman Osborn",
    "new goblin":        "Harry Osborn",
    "venom":             "Eddie Brock / Venom",
    "anti-venom":        "Eddie Brock / Venom",
    "doctor octopus":    "Doctor Octopus",
    "electro":           "Electro",
    "hyper-electro":     "Electro",
    "sandman":           "Sandman",
    "mysterio":          "Mysterio",
    "rhino":             "Rhino",
    "scorpion":          "Scorpion",
    "carnage":           "Carnage",
    "carnage killer":    "Carnage",
    "lizard":            "Lizard",
    "black cat":         "Black Cat",
    "vulture":           "Vulture",
    "kingpin":           "Kingpin",
    "tombstone":         "Tombstone",
    "kraven the hunter": "Kraven the Hunter",
    "shocker":           "Shocker",
    "silk":              "Silk",
    "madame web":        "Madame Web",
    "captain america":   "Captain America",
    "daredevil":         "Daredevil",
    "silver sable":      "Silver Sable",
    "hulk":              "Hulk",
    "doctor doom":       "Doctor Doom",
    "doctor strange":    "Doctor Strange",
    "wolverine":         "Wolverine",
    "spider-ham":        "Spider-Ham",
    "spider-girl":       "Spider-Girl",
    "spider-punk":       "Spider-Punk",
    "shriek":            "Shriek",
    "the spot":          "The Spot",
    "tinkerer":          "Tinkerer",
    "chameleon":         "Chameleon",
    "scarlet spider":    "Ben Reilly / Scarlet Spider",
}

# Credits naming two characters' identifying tokens at once, where the model
# cannot pick a winner. Resolved by hand rather than by a rule that would
# misfire elsewhere.
CHARACTER_CREDIT_OVERRIDES = {
    # The Noir universe's Peter, distinct from the mainline one — they appear
    # side by side in Shattered Dimensions.
    "Spider-Man Noir / Peter Parker": "Spider-Man Noir",
    # Hobie Brown is the Prowler in the mainline continuity and Spider-Punk in
    # another; only the Spider-Punk credit spells him "Hobie".
    "Hobie Brown / Spider-Punk": "Spider-Punk",
}

# Deliberately absent, having been tried and rejected against the data:
#   Prowler   — worn by Aaron Davis, Hobie Brown and Miles G. Morales (Earth-42),
#               with no dominant bearer; merging fused three characters.
#   Hobgoblin — worn by Roderick Kingsley and Ned Leeds; merging made the MCU's
#               Ned Leeds a villain.
#   Spider-Woman — Gwen Stacy claims it here, but Jessica Drew also holds it, so
#               it has no default: a bare "Spider-Woman" stays its own identity.
_NAME_TO_CANON = {t: canon for canon, d in CHARACTER_IDENTITIES.items() for t in d["names"]}
_CANON_TOKENS = {canon: set(d["names"]) | set(d["mantles"])
                 for canon, d in CHARACTER_IDENTITIES.items()}

_TRAILING_PAREN = re.compile(r'\s*\([^)]*\)\s*$')

def character_tokens(name):
    """Identity tokens in a credit string: 'Lizard / Dr. Curt Connors' -> {lizard, curt connors}.

    The trailing parenthetical is a qualifier on the appearance ("(DS)", "(cameo)",
    "(Ultimate)", "(archival footage)"), never part of who the character is.
    Only the "Dr." abbreviation is stripped — "Doctor Octopus" is a codename whose
    first word is load-bearing.
    """
    base = _TRAILING_PAREN.sub('', name or '')
    out = set()
    for part in base.split('/'):
        part = re.sub(r'\s+', ' ', part.strip().lower())
        part = re.sub(r'^dr\.?\s+', '', part)
        part = part.replace('"', '').replace('“', '').replace('”', '')
        if part:
            out.add(part)
    return frozenset(out)


def resolve_character_identities(cursor):
    """Group characters rows into character_identities and set characters.identity_id.

    Returns (n_identities, n_merged_rows, conflicts) where conflicts lists the
    identities whose member rows disagreed about alignment.
    """
    rows = cursor.execute(
        "SELECT id, name, alignment, first_comic_title, first_comic_year FROM characters"
    ).fetchall()

    # Group key: an alias-map canonical name if any token matches one, else the
    # token set itself (rule 1).
    def group_key(name):
        stripped = _TRAILING_PAREN.sub('', (name or '').strip())
        if stripped in CHARACTER_CREDIT_OVERRIDES:
            return ('alias_map', CHARACTER_CREDIT_OVERRIDES[stripped])

        toks = character_tokens(name)
        named = {_NAME_TO_CANON[t] for t in toks if t in _NAME_TO_CANON}

        if len(named) == 1:
            canon = next(iter(named))
            # An identifying name decides the bearer — but only if every other
            # token is one this character actually claims. "Olivia Octavius /
            # Doctor Octopus" carries a name the Otto group does not claim, so
            # she stays separate.
            if not toks - _CANON_TOKENS[canon]:
                return ('alias_map', canon)
        elif not named and toks:
            # No identifying name: an unqualified codename. It resolves only if
            # every token is a mantle and they all point at the same bearer.
            defaults = {MANTLE_DEFAULT.get(t) for t in toks}
            if len(defaults) == 1 and None not in defaults:
                return ('alias_map', next(iter(defaults)))
        # Two different people named at once, or nothing recognised: fall back to
        # the mechanical token-set rule, which keeps them apart.
        return ('token_set', toks)

    groups = {}
    for cid, name, alignment, fct, fcy in rows:
        groups.setdefault(group_key(name), []).append((cid, name, alignment, fct, fcy))

    # Alignment is decided by majority of the member rows, ties broken by the
    # most specific label, so a character does not come out 'hero' in one query
    # and 'neutral' in another purely because of which spelling was joined on.
    ALIGN_PRIORITY = {'villain': 0, 'antihero': 1, 'hero': 2, 'neutral': 3}

    # Identity ids are assigned in this loop's order, so the sort key must not
    # depend on set iteration order: a token_set key is a frozenset, and
    # str(frozenset) varies with the process's string hash seed, which made every
    # rebuild renumber character_identities.id (and characters.identity_id with
    # it) even from identical inputs. Render the tokens in sorted order instead.
    def sort_key(item):
        rule, key = item[0]
        return (rule, key if isinstance(key, str) else ' | '.join(sorted(key)))

    n_merged, conflicts = 0, []
    for (rule, key), members in sorted(groups.items(), key=sort_key):
        aligns = [m[2] for m in members if m[2]]
        distinct = sorted(set(aligns))
        alignment = None
        if aligns:
            counts = collections.Counter(aligns)
            top = max(counts.values())
            alignment = sorted((a for a, n in counts.items() if n == top),
                               key=lambda a: ALIGN_PRIORITY[a])[0]

        # Canonical name: the alias-map label, or the shortest credit string, which
        # is the one without appearance qualifiers.
        if rule == 'alias_map':
            canonical = key
        else:
            canonical = sorted((m[1] for m in members), key=lambda s: (len(s), s))[0]

        first_title = next((m[3] for m in members if m[3]), None)
        years = [m[4] for m in members if m[4]]
        first_year = min(years) if years else None

        rule_out = 'singleton' if len(members) == 1 else rule
        cursor.execute("""INSERT INTO character_identities
                              (canonical_name, alignment, first_comic_title,
                               first_comic_year, n_variants, merge_rule)
                          VALUES (?,?,?,?,?,?)""",
                       (canonical, alignment, first_title, first_year,
                        len(members), rule_out))
        iid = cursor.lastrowid
        for m in members:
            cursor.execute("UPDATE characters SET identity_id=? WHERE id=?", (iid, m[0]))
        if len(members) > 1:
            n_merged += len(members) - 1
        if len(distinct) > 1:
            conflicts.append((canonical, distinct, alignment))

    return len(groups), n_merged, conflicts


# ===========================================================================
# FRANCHISES (must match v1 + new ones from research)
# ===========================================================================
franchise_data = [
    ("Early TV films", "1977-1981 CBS TV-movie compilations from The Amazing Spider-Man series"),
    ("Toei Japanese Spider-Man", "1978 Toei tokusatsu series & theatrical spin-off (Takuya Yamashiro)"),
    ("Sam Raimi trilogy", "Tobey Maguire films 2002-2007 directed by Sam Raimi"),
    ("Marc Webb duology", "Andrew Garfield films 2012-2014 directed by Marc Webb"),
    ("MCU", "Marvel Cinematic Universe - Tom Holland Spider-Man films"),
    ("Spider-Verse", "Sony Pictures Animation animated Spider-Verse films"),
    ("Sony Spider-Man Universe (SSU)", "Sony live-action spin-off films (Venom, Morbius, etc.)"),
    ("Insomniac Spider-Man universe", "PlayStation/PC Insomniac Games Marvel's Spider-Man series (Earth-1048)"),
    ("Standalone", "Standalone / non-franchise Spider-Man media"),
    ("LEGO Marvel crossover", "LEGO Marvel games featuring Spider-Man as a major character"),
    ("Movie tie-in", "Video games directly tieing in to a Spider-Man film release"),
    ("The Electric Company", "PBS children's show that featured Spidey Super Stories"),
    ("Spider-Man animated series lineage", "TV franchise connecting 1967/1981/1994/2008/2012/2017 animated series"),
]
for name, desc in franchise_data:
    cur.execute("INSERT INTO franchises(name, description) VALUES (?,?)", (name, desc))
franchises = {n: i for i, (n, _) in enumerate(franchise_data, start=1)}

# ===========================================================================
# LOAD RESEARCH JSONS
# ===========================================================================
with open(RAW_DIR / "movies.json", "r", encoding="utf-8") as f:
    MOVIES_RESEARCH = json.load(f)

with open(RAW_DIR / "games.json", "r", encoding="utf-8") as f:
    GAMES_RESEARCH = json.load(f)

with open(RAW_DIR / "tv.json", "r", encoding="utf-8") as f:
    TV_RESEARCH = json.load(f)

# ===========================================================================
# BUILD MEDIA WORKS + DETAIL TABLES FROM V1 BASE + RESEARCH
# ===========================================================================
# We'll re-create the base 81 works from v1 data, then enrich from research.

# --- MOVIES (23 from v1, 20 in research) ---
movie_base = [
    # (title, year, date, franchise, notes, sub_type, studio, distributor, director, producer, runtime, rating, notes_v1)
    ("Spider-Man", 1977, "1977-09-14", "Early TV films", "TV movie pilot for The Amazing Spider-Man series", "TV film",
     "Danchuck Productions; Marvel Productions", "CBS", "E. W. Swackhamer", "Danchuck Productions", 98, None, ""),
    ("Spider-Man Strikes Back", 1978, "1978-05-04", "Early TV films", "Composite of two TV episodes; later theatrically released in Europe", "TV film",
     "Danchuck Productions; Marvel Productions", "CBS", "Ron Satlof", "Danchuck Productions", 90, None, ""),
    ("Spider-Man: The Dragon's Challenge", 1981, "1981-09-09", "Early TV films", "Composite of TV episodes; theatrically released in Europe", "TV film",
     "Danchuck Productions; Marvel Productions", "CBS", "Don McDougall", "Danchuck Productions", 90, None, ""),
    ("Spider-Man (Toei)", 1978, "1978-07-22", "Toei Japanese Spider-Man", "Theatrical spin-off of the Toei tokusatsu TV series; non-Peter-Parker lead", "live-action",
     "Toei Company", "Toei Company", "Kōichi Takemoto", "Toei Company", 24, None, ""),
    ("Spider-Man", 2002, "2002-05-03", "Sam Raimi trilogy", "Nominated for Best Visual Effects and Best Sound at 75th Academy Awards", "live-action",
     "Columbia Pictures", "Sony Pictures Releasing", "Sam Raimi", "Laura Ziskin; Ian Bryce", 121, "PG-13", ""),
    ("Spider-Man 2", 2004, "2004-06-30", "Sam Raimi trilogy", "Won Best Visual Effects at 77th Academy Awards", "live-action",
     "Columbia Pictures", "Sony Pictures Releasing", "Sam Raimi", "Laura Ziskin; Ian Bryce", 127, "PG-13", ""),
    ("Spider-Man 3", 2007, "2007-05-04", "Sam Raimi trilogy", "Spider-Man 4 was cancelled in 2010", "live-action",
     "Columbia Pictures", "Sony Pictures Releasing", "Sam Raimi", "Laura Ziskin; Avi Arad; Grant Curtis", 139, "PG-13", ""),
    ("The Amazing Spider-Man", 2012, "2012-07-03", "Marc Webb duology", "Reboot of the franchise", "live-action",
     "Columbia Pictures; Marvel Entertainment", "Sony Pictures Releasing", "Marc Webb", "Avi Arad; Matt Tolmach; Laura Ziskin", 136, "PG-13", ""),
    ("The Amazing Spider-Man 2", 2014, "2014-05-02", "Marc Webb duology", "Sequels and Sinister Six spin-off were cancelled", "live-action",
     "Columbia Pictures; Marvel Entertainment", "Sony Pictures Releasing", "Marc Webb", "Avi Arad; Matt Tolmach", 142, "PG-13", ""),
    ("Spider-Man: Homecoming", 2017, "2017-07-07", "MCU", "First MCU Spider-Man solo film; co-production with Marvel Studios", "live-action",
     "Columbia Pictures; Marvel Studios; Pascal Pictures", "Sony Pictures Releasing", "Jon Watts", "Kevin Feige; Amy Pascal", 133, "PG-13", ""),
    ("Spider-Man: Into the Spider-Verse", 2018, "2018-12-14", "Spider-Verse", "Won Best Animated Feature at 91st Academy Awards", "animated",
     "Sony Pictures Animation", "Sony Pictures Releasing", "Bob Persichetti; Peter Ramsey; Rodney Rothman", "Phil Lord; Christopher Miller; Amy Pascal; Avi Arad; Christina Steinberg", 117, "PG", ""),
    ("Spider-Man: Far From Home", 2019, "2019-07-02", "MCU", "First Spider-Man film to gross over $1 billion", "live-action",
     "Columbia Pictures; Marvel Studios; Pascal Pictures", "Sony Pictures Releasing", "Jon Watts", "Kevin Feige; Amy Pascal", 129, "PG-13", ""),
    ("Spider-Man: No Way Home", 2021, "2021-12-17", "MCU", "Features Tobey Maguire and Andrew Garfield multiverse cameos", "live-action",
     "Columbia Pictures; Marvel Studios; Pascal Pictures", "Sony Pictures Releasing", "Jon Watts", "Kevin Feige; Amy Pascal", 148, "PG-13", ""),
    ("Spider-Man: Across the Spider-Verse", 2023, "2023-06-02", "Spider-Verse", "First part of a two-part sequel", "animated",
     "Sony Pictures Animation", "Sony Pictures Releasing", "Joaquim Dos Santos; Kemp Powers; Justin K. Thompson", "Phil Lord; Christopher Miller; Amy Pascal; Christina Steinberg", 140, "PG", ""),
    ("Spider-Man: Beyond the Spider-Verse", None, None, "Spider-Verse", "Upcoming; release delayed, year unconfirmed", "animated",
     "Sony Pictures Animation", "Sony Pictures Releasing", "Bob Persichetti", "Phil Lord; Christopher Miller; Amy Pascal", None, None, ""),
    ("Spider-Man: Brand New Day", 2026, "2026-07-31", "MCU", "Announced; release date set for July 2026", "live-action",
     "Columbia Pictures; Marvel Studios; Pascal Pictures", "Sony Pictures Releasing", "Destin Daniel Cretton", "Kevin Feige; Amy Pascal", None, None, ""),
    ("Venom", 2018, "2018-10-05", "Sony Spider-Man Universe (SSU)", "First SSU film", "SSU spin-off",
     "Columbia Pictures; Marvel; Tencent", "Sony Pictures Releasing", "Ruben Fleischer", "Avi Arad; Matt Tolmach; Amy Pascal", 112, "PG-13", ""),
    ("Venom: Let There Be Carnage", 2021, "2021-10-01", "Sony Spider-Man Universe (SSU)", "", "SSU spin-off",
     "Columbia Pictures; Marvel", "Sony Pictures Releasing", "Andy Serkis", "Avi Arad; Matt Tolmach; Amy Pascal; Tom Hardy", 97, "PG-13", ""),
    ("Morbius", 2022, "2022-04-01", "Sony Spider-Man Universe (SSU)", "", "SSU spin-off",
     "Columbia Pictures; Marvel", "Sony Pictures Releasing", "Daniel Espinosa", "Avi Arad; Matt Tolmach", 104, "PG-13", ""),
    ("Madame Web", 2024, "2024-02-14", "Sony Spider-Man Universe (SSU)", "", "SSU spin-off",
     "Columbia Pictures; Marvel", "Sony Pictures Releasing", "S.J. Clarkson", "Avi Arad; Lorenzo di Bonaventura", 116, "PG-13", ""),
    ("Kraven the Hunter", 2024, "2024-12-13", "Sony Spider-Man Universe (SSU)", "Final film in the SSU", "SSU spin-off",
     "Columbia Pictures; Marvel", "Sony Pictures Releasing", "J.C. Chandor", "Avi Arad; Matt Tolmach", 127, "R", ""),
    ("Venom: The Last Dance", 2024, "2024-10-25", "Sony Spider-Man Universe (SSU)", "", "SSU spin-off",
     "Columbia Pictures; Marvel", "Sony Pictures Releasing", "Kelly Marcel", "Avi Arad; Matt Tolmach; Amy Pascal; Tom Hardy", 109, "PG-13", ""),
    ("El Muerto", None, None, "Sony Spider-Man Universe (SSU)", "In development; indefinitely delayed; release date TBD", "SSU spin-off",
     "Columbia Pictures", "Sony Pictures Releasing", None, None, None, None, ""),
]

# --- TV SHOWS (15 from v1) ---
tv_base = [
    ("Spidey Super Stories", 1974, None, "The Electric Company", "Segment on The Electric Company; first live-action Spider-Man portrayal", "live-action", "sketch segment", "PBS (The Electric Company)", 1974, 1977, None, None, None, None, "Danny Seagren", "ended"),
    ("The Amazing Spider-Man", 1977, None, "Early TV films", "Live-action CBS series starring Nicholas Hammond; canceled after two seasons", "live-action", "live-action series", "CBS", 1977, 1979, 2, 13, None, None, "Nicholas Hammond", "ended"),
    ("Spider-Man (Japanese TV series)", 1978, None, "Toei Japanese Spider-Man", "Toei tokusatsu series; Spider-Man is Takuya Yamashiro, not Peter Parker; introduced giant-robot tradition carried into Super Sentai", "live-action", "tokusatsu series", "Tokyo Channel 12 (TV Tokyo)", 1978, 1979, 1, 41, None, None, "Shinji Tōdō (Takuya Yamashiro)", "ended"),
    ("Spider-Noir", 2026, "2026-05-25", "Spider-Verse", "Live-action Spider-Man Noir series spinning out of the Spider-Verse films; premiered May 25 2026 on MGM+; 8 episodes", "live-action", "live-action series", "MGM+ / Prime Video", 2026, 2026, 1, 8, None, None, "Nicolas Cage", "current"),
    ("Spider-Man (1967 TV series)", 1967, "1967-09-09", "Standalone", "First Spider-Man animated series; theme song became iconic; first season Grantray-Lawrence, then Ralph Bakshi", "animated", "animated series", "ABC", 1967, 1970, 3, 52, "Grant Simmons; Clyde Geronimi; Sid Marcus (s1); Ralph Bakshi (s2+)", None, "Paul Soles", "ended"),
    ("Spider-Man (1981 TV series)", 1981, "1981-09-12", "Standalone", "First Marvel Productions Spider-Man series; syndicated", "animated", "animated series", "Syndication", 1981, 1982, 1, 26, None, None, "Ted Schwartz", "ended"),
    ("Spider-Man and His Amazing Friends", 1981, "1981-09-12", "Standalone", "Spider-Man, Iceman and Firestar team-up series on NBC", "animated", "animated series", "NBC", 1981, 1983, 3, 24, None, "Don Jurwich", "Dan Gilvezan", "ended"),
    ("Spider-Man: The Animated Series", 1994, "1994-11-19", "Standalone", "Longest Spider-Man series until Ultimate Spider-Man; one story arc per season; 65 episodes", "animated", "animated series", "Fox Kids", 1994, 1998, 5, 65, "John Semper Jr.", None, "Christopher Daniel Barnes", "ended"),
    ("Spider-Man Unlimited", 1999, "1999-10-02", "Standalone", "Spider-Man transported to Counter-Earth; canceled after one season", "animated", "animated series", "Fox Kids", 1999, 2001, 1, 13, "Michael Reaves (1-6); Robert Gregory Browne & Larry Brody (7-13)", "Patrick Archibald", "Rino Romano", "ended"),
    ("Spider-Man: The New Animated Series", 2003, "2003-07-11", "Movie tie-in", "CGI series on MTV continuing the 2002 film continuity", "animated", "CGI animated series", "MTV", 2003, 2003, 1, 13, None, None, "Neil Patrick Harris", "ended"),
    ("The Spectacular Spider-Man", 2008, "2008-03-08", "Standalone", "Acclaimed series based on Lee/Ditko/Romita and Ultimate comics; ended when Sony returned animation rights to Marvel", "animated", "animated series", "The CW / Disney XD", 2008, 2009, 2, 26, "Greg Weisman", None, "Josh Keaton", "ended"),
    ("Ultimate Spider-Man", 2012, "2012-04-01", "Standalone", "Spider-Man leads a S.H.I.E.L.D. trainee team; 104 episodes over 4 seasons", "animated", "animated series", "Disney XD", 2012, 2017, 4, 104, "Brian Michael Bendis; Paul Dini", None, "Drake Bell", "ended"),
    ("Spider-Man (2017 TV series)", 2017, "2017-08-19", "Standalone", "Peter teams with Miles Morales, Gwen Stacy and Anya Corazon", "animated", "animated series", "Disney XD", 2017, 2020, 3, 58, "Kevin Shinick", None, "Robbie Daymond", "ended"),
    ("Spidey and His Amazing Friends", 2021, "2021-08-06", "Standalone", "Preschool series on Disney Junior", "animated", "animated series (preschool)", "Disney Junior", 2021, None, 4, 103, "Becca Topol", "Darren Bachynski (s1-2); Mitch Stookey (s3+)", "Benjamin Valic (s1-2); Alkaio Thiele (s3+)", "current"),
    ("Your Friendly Neighborhood Spider-Man", 2025, "2025-01-29", "MCU", "MCU animated series on Disney+; alternate timeline where Norman Osborn mentors Peter instead of Tony Stark", "animated", "animated series", "Disney+", 2025, None, 1, 10, "Jeff Trammell", "Mel Zwyer; Liza Singer; Stu Livingston", "Hudson Thames", "current"),
]

# --- GAMES (43 from v1) ---
game_base = [
    ("Spider-Man (1982 video game)", 1982, None, "Standalone", "First Spider-Man video game; climb skyscraper, defuse Green Goblin bombs", "Parker Brothers", "Parker Brothers", "Atari 2600; Magnavox Odyssey 2", "action", None, None, None, None, None, "Standalone"),
    ("Questprobe featuring Spider-Man", 1984, None, "Standalone", "Part of the Questprobe text/graphic adventure series", "Adventure International", "Adventure International", "Amstrad CPC; Apple II; Commodore 64; Commodore 16; Atari 8-bit; ZX Spectrum; IBM PC", "graphic adventure", None, "Scott Adams", None, None, "Standalone"),
    ("The Amazing Spider-Man and Captain America in Dr. Doom's Revenge!", 1989, None, "Standalone", "Comic-panel storytelling crossover", "Paragon Software Corporation", "Medallist (MicroProse)", "MS-DOS; Amiga; Atari ST; Amstrad CPC; ZX Spectrum; Commodore 64", "action/fighting", None, None, None, None, "Standalone"),
    ("The Amazing Spider-Man (1990 computer)", 1990, None, "Standalone", "Home computer release", "Oxford Digital Enterprises", "Paragon Software", "Amiga; MS-DOS; Commodore 64; Atari ST", "puzzle-action", None, None, None, None, "Standalone"),
    ("The Amazing Spider-Man (1990 Game Boy)", 1990, None, "Standalone", "First Game Boy Spider-Man; start of Game Boy trilogy", "Rare", "LJN/Nintendo", "Game Boy", "action platformer", None, None, None, None, "Standalone"),
    ("The Punisher: The Ultimate Payback!", 1991, None, "Standalone", "Spider-Man appears as supporting character", "Beam Software (Krome Studios Melbourne)", "Acclaim Entertainment", "Game Boy", "light gun/shooter", None, None, None, None, "Standalone"),
    ("Spider-Man vs. The Kingpin", 1991, "1991-01-01", "Standalone", "Released 1991 Genesis/Master System, 1992 Game Gear, 1993 Sega CD", "Technopop", "Sega", "Sega Genesis; Master System; Game Gear; Sega CD", "action platformer", None, None, None, None, "Standalone"),
    ("Spider-Man: The Video Game", 1991, None, "Standalone", "4-player arcade cabinet", "Sega", "Sega", "Arcade (Sega System 32)", "beat 'em up/platformer", None, None, None, None, "Standalone"),
    ("The Amazing Spider-Man 2 (1992)", 1992, None, "Standalone", "Game Boy trilogy part 2", "Bits Studios", "LJN", "Game Boy", "side-scrolling beat 'em up", None, None, None, None, "Standalone"),
    ("Spider-Man: Return of the Sinister Six", 1992, None, "Standalone", "First NES Spider-Man", "Bits Studios", "LJN/Flying Edge", "NES; Master System; Game Gear", "action platformer", None, None, None, None, "Standalone"),
    ("Spider-Man and the X-Men in Arcade's Revenge", 1992, None, "Standalone", "Crossover with the X-Men", "Software Creations", "LJN", "Super NES; Genesis; Game Gear; Game Boy", "action platformer", None, None, None, None, "Standalone"),
    ("The Amazing Spider-Man 3: Invasion of the Spider-Slayers", 1993, None, "Standalone", "Game Boy trilogy part 3", "Bits Studios", "LJN", "Game Boy", "action platformer", None, None, None, None, "Standalone"),
    ("Spider-Man and Venom: Maximum Carnage", 1994, None, "Standalone", "Based on the Maximum Carnage comic arc", "Software Creations", "LJN", "Super NES; Genesis", "beat 'em up", None, None, None, None, "Standalone"),
    ("The Amazing Spider-Man: Lethal Foes", 1995, None, "Standalone", "Japan-only Super Famicom release", "Argent; Epoch Co.", "Epoch", "Super Famicom", "action platformer", None, None, None, None, "Standalone"),
    ("Venom/Spider-Man: Separation Anxiety", 1995, None, "Standalone", "Sequel to Maximum Carnage", "Software Creations", "Acclaim Entertainment", "Super NES; Genesis", "beat 'em up", None, None, None, None, "Standalone"),
    ("Spider-Man (1995 video game)", 1995, None, "Standalone", "Based on the 1994 animated series", "Western Technologies", "LJN/Acclaim Entertainment", "Sega Genesis/Mega Drive; SNES", "action platformer", None, None, None, None, "Standalone"),
    ("The Amazing Spider-Man: Web of Fire", 1996, None, "Standalone", "One of the last 32X releases", "BlueSky Software", "Sega", "Sega 32X", "action platformer", None, None, None, None, "Standalone"),
    ("Spider-Man: The Sinister Six", 1996, None, "Standalone", "PC CD-ROM point-and-click", "Brooklyn Multimedia", "Byron Preiss Multimedia", "MS-DOS", "point-and-click adventure", None, None, None, None, "Standalone"),
    ("Spider-Man (2000 video game)", 2000, "2000-08-30", "Standalone", "First Activision-era Spider-Man", "Neversoft (PS); Vicarious Visions (GBC); Edge of Reality (N64); Treyarch (DC); LTI Gray Matter (Win)", "Activision", "PlayStation; Game Boy Color; Nintendo 64; Dreamcast; Microsoft Windows", "action-adventure/platformer", None, None, "87 (PS)", "T", "Standalone"),
    ("Spider-Man 2: The Sinister Six", 2001, None, "Standalone", "Handheld sequel", "Torus Games", "Activision", "Game Boy Color", "action platformer", None, None, None, None, "Standalone"),
    ("Spider-Man 2: Enter: Electro", 2001, "2001-10-18", "Standalone", "Sequel to the 2000 game; delayed from September 2001 to remove World Trade Center content", "Vicarious Visions", "Activision", "PlayStation", "action-adventure/platformer", None, None, None, "E", "Standalone"),
    ("Spider-Man: Mysterio's Menace", 2001, "2001-09-19", "Standalone", "", "Vicarious Visions", "Activision", "Game Boy Advance", "action platformer", None, None, None, "E", "Standalone"),
    ("Spider-Man (2002 video game)", 2002, "2002-04-16", "Movie tie-in", "Tie-in to Spider-Man (2002 film)", "Treyarch; LTI Gray Matter (Win); Digital Eclipse (GBA)", "Activision", "GameCube; PlayStation 2; Xbox; Microsoft Windows; Game Boy Advance", "action-adventure", None, None, "77 (PS2)", "T", "Movie tie-in"),
    ("Spider-Man 2 (2004 video game)", 2004, "2004-06-29", "Movie tie-in", "Tie-in to Spider-Man 2 (2004 film); first open-world web-swinging", "Treyarch; Digital Eclipse (GBA/N-Gage); Foundation 9 (Win); Aspyr (Mac); Vicarious Visions (DS/PSP)", "Activision", "GameCube; PlayStation 2; Xbox; Windows; N-Gage; Mac OS X; Nintendo DS; PSP; Game Boy Advance", "open world action-adventure", None, None, "83 (PS2); 80 (GC); 82 (Xbox)", "T", "Movie tie-in"),
    ("Ultimate Spider-Man (2005 video game)", 2005, "2005-09-22", "Standalone", "Based on Ultimate Spider-Man comic; cel-shaded art", "Treyarch; Beenox (Win); Vicarious Visions (DS/GBA)", "Activision", "GameCube; PlayStation 2; Xbox; Windows; Nintendo DS; Game Boy Advance", "open world action-adventure", None, None, "76 (PS2); 75 (GC); 79 (Xbox)", "T", "Standalone"),
    ("Spider-Man: Battle for New York", 2006, "2006-11-07", "Standalone", "", "Torus Games", "Activision", "Nintendo DS; Game Boy Advance; Mobile", "action beat 'em up", None, None, None, "E10+", "Standalone"),
    ("Spider-Man 3 (2007 video game)", 2007, "2007-05-04", "Movie tie-in", "Tie-in to Spider-Man 3 (2007 film)", "Vicarious Visions; Treyarch (X360/PS3); Beenox (Win)", "Activision", "Game Boy Advance; Windows; Nintendo DS; PlayStation 2; Wii; Xbox 360; PlayStation 3; PSP", "open world action-adventure", None, None, "57 (PS3); 54 (X360); 69 (Wii)", "T", "Movie tie-in"),
    ("Spider-Man: Friend or Foe", 2007, "2007-10-02", "Movie tie-in", "Loosely ties to the film trilogy", "Next Level Games; Beenox (Win); Behaviour Interactive (DS/PSP)", "Activision", "Windows; Nintendo DS; PlayStation 2; Wii; Xbox 360; PSP", "action beat 'em up", None, None, "61 (X360)", "E10+", "Movie tie-in"),
    ("Spider-Man: Web of Shadows", 2008, "2008-10-21", "Standalone", "Multiple endings based on red/black suit choices", "Shaba Games; Treyarch; Griptonite (DS); Amaze (PS2/PSP)", "Activision", "Windows; Nintendo DS; PlayStation 2; PlayStation 3; PSP; Wii; Xbox 360", "open world action-adventure", None, None, "78 (X360); 77 (PS3)", "T", "Standalone"),
    ("Ultimate Spider-Man: Total Mayhem", 2010, "2010-09-22", "Standalone", "Mobile title", "Gameloft", "Gameloft", "iOS; Android", "action beat 'em up", None, None, None, None, "Standalone"),
    ("Spider-Man: Shattered Dimensions", 2010, "2010-09-07", "Standalone", "Four Spider-Men across dimensions (Amazing, Noir, 2099, Ultimate)", "Beenox; Griptonite (DS)", "Activision", "Nintendo DS; PlayStation 3; Wii; Xbox 360; Windows", "action-adventure", None, None, "76 (X360); 76 (PS3)", "T", "Standalone"),
    ("Spider-Man: Edge of Time", 2011, "2011-10-04", "Standalone", "Amazing and 2099 Spider-Men", "Beenox; Other Ocean (DS)", "Activision", "Nintendo 3DS; Nintendo DS; PlayStation 3; Wii; Xbox 360", "action-adventure", None, None, "64 (X360); 65 (PS3)", "T", "Standalone"),
    ("The Amazing Spider-Man (2012 video game)", 2012, "2012-06-26", "Movie tie-in", "Tie-in to The Amazing Spider-Man (2012 film)", "Beenox; Other Ocean (DS); Gameloft (mobile); Mercenary Technology (Vita)", "Activision", "Nintendo 3DS; Nintendo DS; PlayStation 3; Wii; Xbox 360; Android; iOS; Windows; Wii U; Windows Phone; PlayStation Vita", "open world action-adventure", None, None, "64 (X360); 64 (PS3)", "T", "Movie tie-in"),
    ("The Amazing Spider-Man 2 (2014 video game)", 2014, "2014-04-29", "Movie tie-in", "Tie-in to The Amazing Spider-Man 2 (2014 film); last Activision Spider-Man game", "Beenox; Gameloft (mobile); High Voltage (3DS)", "Activision", "Android; iOS; Windows; Nintendo 3DS; PlayStation 3; PlayStation 4; Wii U; Xbox 360; Xbox One", "open world action-adventure", None, None, "50 (PS4); 50 (XOne)", "T", "Movie tie-in"),
    ("Spider-Man Unlimited (2014 video game)", 2014, "2014-09-10", "Standalone", "Mobile endless runner; shut down 2019", "Gameloft", "Gameloft", "iOS; Android; Windows Phone", "endless runner", None, None, None, None, "Standalone"),
    ("LEGO Marvel Super Heroes", 2013, "2013-10-22", "LEGO Marvel crossover", "Spider-Man as major playable character", "TT Games", "Warner Bros. Interactive Entertainment", "PlayStation 3; PlayStation 4; Xbox 360; Xbox One; Wii U; Windows; Nintendo DS; Nintendo 3DS; PlayStation Vita; OS X", "action-adventure", None, None, "85 (X360)", "E10+", "LEGO Marvel crossover"),
    ("LEGO Marvel Super Heroes 2", 2017, "2017-11-14", "LEGO Marvel crossover", "Spider-Man as major playable character", "TT Games", "Warner Bros. Interactive Entertainment", "PlayStation 4; Xbox One; Nintendo Switch; Windows", "action-adventure", None, None, "80 (PS4); 80 (XOne)", "E10+", "LEGO Marvel crossover"),
    ("Marvel's Spider-Man", 2018, "2018-09-07", "Insomniac Spider-Man universe", "Earth-1048; Remastered on PS5 Nov 12 2020 and Windows Aug 12 2022", "Insomniac Games", "Sony Interactive Entertainment", "PlayStation 4; PlayStation 5; Microsoft Windows", "action-adventure/open world", "Insomniac engine", "Ryan Smith; Brian Horton; Bryan Intihar; Marcus Smith", "87 (PS4)", "T", "Insomniac Spider-Man universe"),
    ("Marvel's Spider-Man: The City That Never Sleeps", 2018, "2018-10-23", "Insomniac Spider-Man universe", "3-episode DLC for Marvel's Spider-Man", "Insomniac Games", "Sony Interactive Entertainment", "PlayStation 4 (DLC)", "action-adventure (DLC)", None, None, None, "T", "Insomniac Spider-Man universe"),
    ("Marvel's Spider-Man Remastered", 2020, "2020-11-12", "Insomniac Spider-Man universe", "Remaster with ray tracing, new Peter model", "Insomniac Games; Nixxes Software (PC)", "Sony Interactive Entertainment", "PlayStation 5; Microsoft Windows", "action-adventure/open world", None, None, "87 (base)", "T", "Insomniac Spider-Man universe"),
    ("Marvel's Spider-Man: Miles Morales", 2020, "2020-11-12", "Insomniac Spider-Man universe", "Spin-off; PC release Nov 18 2022", "Insomniac Games; Nixxes Software (PC)", "Sony Interactive Entertainment", "PlayStation 4; PlayStation 5; Microsoft Windows", "action-adventure/open world", None, "Brian Horton; Cameron Christian", "85 (PS5)", "T", "Insomniac Spider-Man universe"),
    ("Marvel's Spider-Man 2", 2023, "2023-10-20", "Insomniac Spider-Man universe", "PC release Jan 30 2025; features Venom symbiote", "Insomniac Games; Nixxes Software (PC)", "Sony Interactive Entertainment", "PlayStation 5; Microsoft Windows", "action-adventure/open world", None, "Bryan Intihar; Ryan Smith", "90 (PS5)", "T", "Insomniac Spider-Man universe"),
    ("Marvel's Spider-Man 3", None, None, "Insomniac Spider-Man universe", "In development; internal target 2028 (per leaked roadmap); not officially released", "Insomniac Games", "Sony Interactive Entertainment", "PlayStation 5", "action-adventure/open world", None, None, None, "T", "Insomniac Spider-Man universe"),
]

# ---------------------------------------------------------------------------
# INSERT BASE MEDIA WORKS + DETAIL TABLES
# ---------------------------------------------------------------------------
# work_catalog is the authority for matching research back to works. A plain
# title->id dict cannot represent this catalog: "Spider-Man" is a 1977 TV film, a
# 2002 feature, a 1967 series and a 1982 game, so every entry carries its year and
# media_type and lookups are always scoped by both.
work_catalog = []   # list of {"id", "title", "year", "media_type"}

def register_work(wid, title, year, media_type):
    work_catalog.append({"id": wid, "title": title, "year": year, "media_type": media_type})

for row in movie_base:
    (title, year, date, franch, notes, sub_type, studio, distr, director, producer,
     runtime, rating, notes_v1) = row
    wid = add_media_work(title, year, date, "movie", franch, notes)
    register_work(wid, title, year, "movie")
    cur.execute("""INSERT INTO movies(work_id, sub_type, studio, distributor, director, producer,
                     runtime_minutes, mpaa_rating, notes)
                     VALUES (?,?,?,?,?,?,?,?,?)""",
                (wid, sub_type, studio, distr, director, producer, runtime, rating, notes))

for row in tv_base:
    (title, year, date, franch, notes, sub_type, fmt, network, start, end, seasons, eps,
     head_writer, director, voice, status) = row
    wid = add_media_work(title, year, date, "tv_show", franch, notes)
    register_work(wid, title, year, "tv_show")
    cur.execute("""INSERT INTO tv_shows(work_id, sub_type, format, network, start_year, end_year,
                     seasons, episodes, head_writer, voice_actor_spider_man, status)
                     VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (wid, sub_type, fmt, network, start, end, seasons, eps, head_writer, voice, status))

for row in game_base:
    title = row[0]
    year = row[1]
    date = row[2]
    franch = row[3]
    notes = row[4]
    genre = row[8]
    engine = row[9]
    universe = row[13]
    wid = add_media_work(title, year, date, "game", franch, notes)
    register_work(wid, title, year, "game")
    cur.execute("""INSERT INTO games(work_id, genre, engine, universe, notes)
                     VALUES (?,?,?,?,?)""",
                (wid, genre, engine, universe, notes))

conn.commit()

# ===========================================================================
# ENRICH FROM RESEARCH DATA
# ===========================================================================

# ---------------------------------------------------------------------------
# Matching research items back to catalog works
#
# The v2 matcher took a merged {**movies, **tv, **games} dict keyed on bare title
# and fell back to substring containment. Both halves were wrong: the merge let a
# game clobber a same-titled film, and containment matched "Spider-Man" (2002) to
# "Spider-Man (1982 video game)". Matching here is scoped to one media_type and
# every fuzzy tier requires the release years to agree.
# ---------------------------------------------------------------------------
def _norm_title(title):
    """Casefold, drop disambiguating parentheticals, and flatten punctuation."""
    s = re.sub(r'\s*\(.*?\)\s*', ' ', str(title or ''))
    s = s.replace('&', 'and')
    s = re.sub(r'[^a-z0-9]+', ' ', s.lower())
    return ' '.join(s.split())


class WorkMatcher:
    """Resolve a research item to exactly one work_id within a single media_type."""

    def __init__(self, catalog, media_type):
        self.media_type = media_type
        self.works = [w for w in catalog if w["media_type"] == media_type]
        self.unmatched = []
        self.by_exact = defaultdict(list)
        self.by_norm = defaultdict(list)
        for w in self.works:
            self.by_exact[w["title"]].append(w)
            self.by_norm[_norm_title(w["title"])].append(w)

    @staticmethod
    def _only(candidates):
        """A match counts only when it is unambiguous."""
        return candidates[0]["id"] if len(candidates) == 1 else None

    def find(self, research_item):
        title = research_item.get("title", "")
        year = research_item.get("release_year")
        norm = _norm_title(title)

        # Tier 1: exact title, and the year agrees (or the item carries no year).
        exact = self.by_exact.get(title, [])
        hit = self._only([w for w in exact if year is None or w["year"] == year])
        if hit:
            return hit
        # Tier 2: exact title, unique within this media type regardless of year.
        hit = self._only(exact)
        if hit:
            return hit
        # Tier 3: normalized title + matching year. Catches "Ultimate Spider-Man
        # (video game)" -> "Ultimate Spider-Man (2005 video game)" and
        # "Spider-Man" (1978) -> "Spider-Man (Toei)".
        norm_hits = self.by_norm.get(norm, [])
        hit = self._only([w for w in norm_hits if year is None or w["year"] == year])
        if hit:
            return hit
        # Tier 4: normalized title, unique within this media type.
        hit = self._only(norm_hits)
        if hit:
            return hit
        # Tier 5: containment, but only among works released the same year and only
        # when exactly one candidate survives. Catches "Spider-Man: Web of Fire"
        # (1996) -> "The Amazing Spider-Man: Web of Fire" (1996).
        if year is not None and norm:
            same_year = [w for w in self.works if w["year"] == year]
            contained = [w for w in same_year
                         if norm in _norm_title(w["title"]) or _norm_title(w["title"]) in norm]
            hit = self._only(contained)
            if hit:
                return hit

        self.unmatched.append((title, year))
        return None


movie_matcher = WorkMatcher(work_catalog, "movie")
tv_matcher = WorkMatcher(work_catalog, "tv_show")
game_matcher = WorkMatcher(work_catalog, "game")

# Every research item is resolved once, against the matcher for its own media type,
# so a cross-media title clash can never resolve to the wrong medium. Later loaders
# iterate these (item, work_id) pairs instead of re-running the match.
RESOLVED_MOVIES = [(item, movie_matcher.find(item)) for item in MOVIES_RESEARCH]
RESOLVED_TV = [(item, tv_matcher.find(item)) for item in TV_RESEARCH]
RESOLVED_GAMES = [(item, game_matcher.find(item)) for item in GAMES_RESEARCH]
RESOLVED_ALL = RESOLVED_MOVIES + RESOLVED_TV + RESOLVED_GAMES

# A research item that matches nothing is a silent data loss in v2; surface it.
for _m in (movie_matcher, tv_matcher, game_matcher):
    for _t, _y in _m.unmatched:
        print(f"  WARNING: unmatched {_m.media_type} research item: {_t!r} ({_y})")

# ---- 1. CHARACTERS + WORK_CHARACTERS ----
char_name_to_id = {}
alignment_dropped = set()
for research in (*MOVIES_RESEARCH, *TV_RESEARCH, *GAMES_RESEARCH):
    for ch in research.get("characters", []):
        raw_alignment = ch.get("alignment")
        alignment = normalize_alignment(raw_alignment)
        if raw_alignment and not alignment:
            alignment_dropped.add(raw_alignment)
        # The research carries an explicit first_comic_year; trust it over parsing
        # the appearance string, which cannot tell an imprint year ("Spider-Man
        # 2099") or an issue number from a publication date.
        year = ch.get("first_comic_year")
        if year is None:
            year = parse_year_from_comic_appearance(ch.get("first_comic_appearance"))
        cid = add_character(
            ch.get("name"),
            ch.get("alias"),
            alignment,
            raw_alignment,
            ch.get("first_comic_appearance"),
            year,
        )
        char_name_to_id[ch.get("name")] = cid

# Resolve the credit strings into the people they name. Runs once, after every
# research file has contributed its spellings.
n_identities, n_merged_chars, alignment_conflicts = resolve_character_identities(cur)


def find_actor_for_character(research, character_name):
    """Pick the billed actor for a character, preferring an exact credit match.

    v2 accepted the first substring hit, so "Spider-Man" claimed the credit for
    "Spider-Man Noir" whenever that appeared earlier in the cast list."""
    cast = research.get("principal_cast", []) or []
    for pc in cast:
        if pc.get("character") == character_name:
            return pc
    # Fall back to substring, but only when it identifies a single credit.
    partial = [pc for pc in cast
               if character_name and character_name in (pc.get("character") or "")]
    return partial[0] if len(partial) == 1 else None


# Link characters to works (principal cast provides actor-person links)
for research, wid in RESOLVED_ALL:
    if not wid:
        continue
    for ch in research.get("characters", []):
        cid = char_name_to_id.get(ch.get("name"))
        if not cid:
            continue
        pc = find_actor_for_character(research, ch.get("name"))
        actor_id = add_person(pc.get("actor")) if pc and pc.get("actor") else None
        billing = pc.get("billing_order") if pc else None
        cur.execute("""INSERT OR IGNORE INTO work_characters(work_id, character_id, actor_person_id, billing_order, notes)
                       VALUES (?,?,?,?,?)""",
                    (wid, cid, actor_id, billing, None))

# ---- 2. CAST_CREW (principal cast + key crew) ----
def crew_entries(research):
    """Crew credits, under either research key.

    movies.json/tv.json name this list `key_crew`; games.json names it
    `key_credits`. v2 only read `key_crew`, so all 210 game credits were dropped
    and every game ended up with an empty cast_crew."""
    return (research.get("key_crew") or []) + (research.get("key_credits") or [])


for research, wid in RESOLVED_ALL:
    if not wid:
        continue
    # Principal cast
    for pc in research.get("principal_cast", []):
        if not pc.get("actor"):
            continue
        pid = add_person(pc.get("actor"))
        cur.execute("""INSERT OR IGNORE INTO cast_crew(work_id, person_id, role, character_name, credit_order)
                       VALUES (?,?,?,?,?)""",
                    (wid, pid, "actor", pc.get("character"), pc.get("billing_order")))
    # Key crew / key credits
    for kc in crew_entries(research):
        if not kc.get("person") or not kc.get("role"):
            continue
        pid = add_person(kc.get("person"))
        cur.execute("""INSERT OR IGNORE INTO cast_crew(work_id, person_id, role, character_name, credit_order)
                       VALUES (?,?,?,?,?)""",
                    (wid, pid, kc.get("role"), None, None))
        # Also mirror into work_people for non-character roles (director, producer, ...)
        cur.execute("""INSERT OR IGNORE INTO work_people(work_id, person_id, role)
                       VALUES (?,?,?)""",
                    (wid, pid, kc.get("role")))

# ---- 3. STUDIOS + WORK_STUDIOS ----
studio_roles_seen = set()
for research, wid in RESOLVED_ALL:
    if not wid:
        continue
    for studio in research.get("studios", []):
        if not studio.get("name"):
            continue
        sid = add_studio(studio.get("name"), None, None)
        role = studio.get("role") or "production"
        studio_roles_seen.add(role)
        cur.execute("""INSERT OR IGNORE INTO work_studios(work_id, studio_id, role)
                       VALUES (?,?,?)""", (wid, sid, role))

# ---- 4. GAME RELEASES (per-platform) ----
def clean_company(name):
    """Strip the trailing table-cell '|' that the source scrape left on 47 of the
    169 developer strings. Left in place it forks one studio into two entities:
    "Traveller's Tales" (8 releases) and "Traveller's Tales |" (5)."""
    if not isinstance(name, str):
        return name
    cleaned = re.sub(r'\s*\|\s*$', '', name).strip()
    return cleaned or None


for research, wid in RESOLVED_GAMES:
    if not wid:
        continue
    for rel in research.get("per_platform_releases", []):
        pid = add_platform(rel.get("platform"))
        cur.execute("""INSERT INTO game_releases(game_work_id, platform_id, release_date, publisher, developer,
                           metacritic_score, esrb_rating)
                       VALUES (?,?,?,?,?,?,?)""",
                    (wid, pid,
                     rel.get("release_date"),
                     clean_company(rel.get("publisher")),
                     clean_company(rel.get("developer")),
                     rel.get("metacritic_score"),
                     rel.get("esrb_rating")))
        # Also populate junction table
        cur.execute("""INSERT OR IGNORE INTO game_platforms(game_id, platform_id) VALUES (?,?)""",
                    (wid, pid))

# ---- 5. REVIEW SCORES ----
# 271 of the 281 research entries omit max_score. v2 required it and discarded
# them, which is why review_scores held only 9 rows. The scale is a property of the
# publication, so derive it rather than throwing the score away.
SOURCE_MAX_SCORE = {
    # Aggregators and percentage-scale outlets
    "Metacritic": 100, "GameRankings": 100, "OpenCritic": 100,
    "Rotten Tomatoes": 100, "PostTrak": 100, "Hyper": 100,
    "Game Players": 100, "PC Gamer": 100, "Manci Games": 100,
    # Japanese magazines score out of 40 (four reviewers, 10 each)
    "Famitsu": 40, "Famicom Tsūshin": 40,
    # Ten-point outlets
    "IGN": 10, "GameSpot": 10, "Game Informer": 10, "Destructoid": 10,
    "Eurogamer": 10, "Electronic Gaming Monthly": 10, "GameTrailers": 10,
    "GameZone": 10, "Giant Bomb": 10, "Joystiq": 10, "Kotaku": 10,
    "Nintendo Life": 10, "Nintendo Power": 10, "Nintendo World Report": 10,
    "Official U.S. PlayStation Magazine": 10, "Official Xbox Magazine": 10,
    "Pocket Gamer": 10, "Polygon": 10, "Push Square": 10, "Shacknews": 10,
    "TouchArcade": 10, "1Up.com": 10, "Maxim": 10, "The Guardian": 10,
    # Five-point / star-scale outlets
    "Next Generation": 5, "GamePro": 5, "GamesRadar+": 5, "148Apps": 5,
}

def split_source(source):
    """'Metacritic (PS3)' -> ('Metacritic', 'PS3'); 'IGN' -> ('IGN', None).

    The research tags the reviewed platform onto the publication name, which makes
    `source` unusable for grouping — 128 distinct strings for 36 publications, 40+
    of them Metacritic. The platform is a property of the release, not the outlet.
    """
    s = (source or "").strip()
    m = re.match(r'^(.*?)\s*\(([^)]*)\)\s*$', s)
    if m:
        return m.group(1).strip(), m.group(2).strip() or None
    return s, None


def infer_max_score(source, score):
    """Best-known scale for a publication, falling back to the score's magnitude."""
    base = split_source(source)[0]
    if base in SOURCE_MAX_SCORE:
        return float(SOURCE_MAX_SCORE[base])
    # Unknown outlet (GameSpy used both /5 stars and /100 over its lifetime):
    # read the scale off the value itself.
    if score > 10:
        return 100.0
    if score > 5:
        return 10.0
    return 5.0


review_scores_skipped = 0
for research, wid in RESOLVED_ALL:
    if not wid:
        continue
    for rs in research.get("review_scores", []):
        source = rs.get("source")
        score = rs.get("score")
        count = rs.get("review_count")
        if score is None or not source:
            # e.g. CinemaScore letter grades, or entries carrying only a badge.
            review_scores_skipped += 1
            continue
        score = float(score)
        max_score = rs.get("max_score")
        max_score = float(max_score) if max_score is not None else infer_max_score(source, score)
        pct = round(100.0 * score / max_score, 2) if max_score else None
        publication, platform_scope = split_source(source)
        cur.execute("""INSERT OR REPLACE INTO review_scores(work_id, source, publication,
                           platform_scope, score, max_score, score_pct, review_count)
                       VALUES (?,?,?,?,?,?,?,?)""",
                    (wid, source, publication, platform_scope, score, max_score, pct, count))

# ---- 6. BOX OFFICE (movies only) ----
# v2 numbered weeks with an enumerate() counter and ignored the week_number the
# research supplies. Combined with the title collision that sent the 1977 TV film's
# row to the 2002 feature, that produced two "week 1" rows for one film.
#
# The deeper problem was semantic: 16 of the 17 films file a full-run total under
# week_number = 1, so "week 1 domestic" for Spider-Man (2002) was $403.7M — the
# entire domestic run, not an opening week. The research now tags each row with a
# scope and the loader refuses rows that do not carry one.
box_office_missing_scope = []
for research, wid in RESOLVED_MOVIES:
    if not wid:
        continue
    for i, bw in enumerate(research.get("box_office_weekly", []), start=1):
        scope = bw.get("scope")
        if scope not in ("week", "lifetime"):
            box_office_missing_scope.append((research.get("title"), i))
            continue
        week = bw.get("week_number", i) if scope == "week" else None
        cur.execute("""INSERT OR REPLACE INTO box_office(work_id, scope, week_number, week_start_date,
                           domestic_usd, international_usd, worldwide_usd)
                       VALUES (?,?,?,?,?,?,?)""",
                    (wid, scope, week,
                     bw.get("week_start_date"),
                     bw.get("domestic_usd"),
                     bw.get("international_usd"),
                     bw.get("worldwide_usd")))

# ---- 7. BUDGETS ----
# A film can carry rival published production figures (Madame Web: $80M and
# $100M). Both rows are kept, but exactly one per (work, component) is primary so
# that rollups and ROI cannot double-count a single film's budget.
for research, wid in RESOLVED_MOVIES:
    if not wid:
        continue
    by_component = defaultdict(list)
    for bd in research.get("budgets", []):
        by_component[bd.get("component")].append(bd)
    for component, entries in by_component.items():
        primary = max(entries, key=lambda e: e.get("amount_usd") or 0)
        for bd in entries:
            is_primary = 1 if bd is primary else 0
            note = bd.get("note")
            if len(entries) > 1 and not note:
                note = ("highest published estimate" if is_primary
                        else "competing published estimate")
            cur.execute("""INSERT OR IGNORE INTO budgets(work_id, amount_usd, currency, component,
                               inflation_adj_2024, source_year, is_primary, note)
                           VALUES (?,?,?,?,?,?,?,?)""",
                        (wid,
                         bd.get("amount_usd"),
                         bd.get("currency", "USD"),
                         component,
                         bd.get("inflation_adj_2024"),
                         bd.get("source_year"),
                         is_primary,
                         note))

# ---- 8. AWARDS ----
for research, wid in RESOLVED_ALL:
    if not wid:
        continue
    for aw in research.get("awards", []):
        recip_id = None
        if aw.get("recipient"):
            recip_id = add_person(aw.get("recipient"))
        cur.execute("""INSERT OR IGNORE INTO awards(work_id, award_body, year, category, result, recipient_person_id)
                       VALUES (?,?,?,?,?,?)""",
                    (wid,
                     aw.get("award_body"),
                     aw.get("year"),
                     aw.get("category"),
                     aw.get("result"),
                     recip_id))

# ---- 9. EPISODES (TV) ----
# Two research rows are not episodes and pushed a series past its own declared
# episode count: a "Season 2 summary" placeholder, and the 1977 pilot TV movie,
# which is already its own media_works row. Both lack an episode number, which is
# the thing that makes a row an episode.
episodes_skipped = []
for research, wid in RESOLVED_TV:
    if not wid:
        continue
    for ep in research.get("episodes", []):
        if ep.get("episode_number") is None:
            episodes_skipped.append((research.get("title"), ep.get("title")))
            continue
        cur.execute("""INSERT INTO episodes(show_work_id, season_number, episode_number, title,
                           air_date, runtime_minutes, director, writer, us_viewers_millions)
                       VALUES (?,?,?,?,?,?,?,?,?)""",
                    (wid,
                     ep.get("season_number"),
                     ep.get("episode_number"),
                     ep.get("title"),
                     ep.get("air_date"),
                     ep.get("runtime_minutes"),
                     ep.get("director"),
                     ep.get("writer"),
                     ep.get("us_viewers_millions")))

# ---- 10. WORK RELATIONS ----
rel_type_map = {
    "prequel": "prequel",
    "sequel": "sequel",
    "spin_off": "spin_off",
    "spin-off": "spin_off",
    "remake": "remake",
    "same_universe": "same_universe",
    "crossover": "crossover",
    "tie_in_game_of": "tie_in_game_of",
    # The research uses "tie_in" for loose associations (Venom -> Into the
    # Spider-Verse, the CBS series -> its TV-movie edits). v2 folded it into
    # "tie_in_game_of", asserting a game tie-in that does not exist.
    "tie_in": "tie_in",
    "adapted_from": "adapted_from",
    "dlc_of": "dlc_of",
    "inspired": "inspired",
    "prequel_in_lineage": "prequel_in_lineage",
    "bundle_with": "same_universe",
    "bundle_in": "same_universe",
    "successor": "sequel",
    "remaster": "remaster_of",
    "remaster_of": "remaster_of",
}
VALID_RELATION_TYPES = {
    'sequel', 'prequel', 'spin_off', 'remake', 'same_universe', 'crossover',
    'tie_in_game_of', 'adapted_from', 'dlc_of', 'inspired', 'prequel_in_lineage',
    'related', 'remaster_of', 'tie_in',
}

# Works the catalog itself identifies as add-on content. "dlc_of" is the one
# relation whose direction the source research states both ways ("Marvel's
# Spider-Man dlc_of The City That Never Sleeps" and the reverse), and it is also
# the one direction the dataset can settle on its own evidence.
DLC_WORK_IDS = {
    row[0] for row in cur.execute(
        """SELECT mw.id FROM media_works mw JOIN games g ON g.work_id = mw.id
           WHERE g.genre LIKE '%DLC%' OR mw.notes LIKE '%DLC%'""")
}

# Relations point across media types ("tie_in_game_of" a film), so the related-work
# lookup spans the whole catalog and cannot be scoped the way research titles are.
# Instead it mines the disambiguator the research already writes into the title —
# "Spider-Man (2002 film)", "Spider-Man 3 (video game)" — for a year and a medium.
related_by_exact = defaultdict(list)
related_by_norm = defaultdict(list)
for _w in work_catalog:
    related_by_exact[_w["title"]].append(_w)
    related_by_norm[_norm_title(_w["title"])].append(_w)

# A relation type can itself pin down the medium of its target.
RELATION_TARGET_MEDIA = {
    "tie_in_game_of": "movie",
    "dlc_of": "game",
    "remaster_of": "game",
}


def _parse_disambiguator(title):
    """Read (year, media_type, is_comic) out of a title's parentheticals."""
    inner = " ".join(re.findall(r'\((.*?)\)', str(title or ''))).lower()
    year_match = re.search(r'\b(19|20)\d{2}\b', inner)
    year = int(year_match.group(0)) if year_match else None
    if "comic" in inner or "miniseries" in inner or "storyline" in inner:
        return year, None, True
    # "film game" means the game of the film, so check for a game first.
    if "game" in inner:
        media = "game"
    elif "film" in inner or "movie" in inner:
        media = "movie"
    elif "tv" in inner or "series" in inner:
        media = "tv_show"
    else:
        media = None
    return year, media, False


def resolve_related_title(title, relation_type=None):
    hits = related_by_exact.get(title)
    if hits and len(hits) == 1:
        return hits[0]["id"]

    year, media, is_comic = _parse_disambiguator(title)
    if is_comic:
        return None     # comics and storylines are not works in this catalog

    candidates = related_by_norm.get(_norm_title(title), [])
    if not candidates:
        return None
    if year is not None:
        candidates = [w for w in candidates if w["year"] == year] or candidates
    media = media or RELATION_TARGET_MEDIA.get(relation_type)
    if media is not None:
        candidates = [w for w in candidates if w["media_type"] == media] or candidates
    return candidates[0]["id"] if len(candidates) == 1 else None


unknown_relation_types = set()
unresolved_relation_titles = set()
for research, wid in RESOLVED_ALL:
    if not wid:
        continue
    for rel in research.get("work_relations", []):
        rel_type = (rel.get("relation_type") or "").lower().replace(" ", "_").replace("-", "_")
        rel_type = rel_type_map.get(rel_type, rel_type)
        if rel_type not in VALID_RELATION_TYPES:
            # v2 let these hit the CHECK constraint and be swallowed by INSERT OR IGNORE.
            unknown_relation_types.add(rel_type)
            continue
        related_title = rel.get("related_work_title", "")
        rel_wid = resolve_related_title(related_title, rel_type)
        if rel_wid is None:
            unresolved_relation_titles.add(related_title)
            continue
        if rel_wid == wid:
            continue    # a work is not related to itself
        a, b = wid, rel_wid
        if rel_type == 'dlc_of' and b in DLC_WORK_IDS and a not in DLC_WORK_IDS:
            a, b = b, a     # the add-on is always the "dlc_of" side
        cur.execute("""INSERT OR IGNORE INTO work_relations(work_a_id, work_b_id, relation_type)
                       VALUES (?,?,?)""", (a, b, rel_type))

# ---- 11. SOURCE MATERIAL ----
# movies.json/tv.json use comic_* keys; games.json uses comic_or_film_title etc.
for research, wid in RESOLVED_ALL:
    if not wid:
        continue
    for src in research.get("source_material", []):
        cur.execute("""INSERT INTO source_material(work_id, comic_title, issue_range, comic_writer, comic_year, storyline_arc)
                       VALUES (?,?,?,?,?,?)""",
                    (wid,
                     src.get("comic_title") or src.get("comic_or_film_title"),
                     src.get("issue_range") or src.get("issue_range_or_film_year"),
                     src.get("comic_writer") or src.get("writer_or_director"),
                     src.get("comic_year") or src.get("year"),
                     src.get("storyline_arc")))

# ---- 12. SOUNDTRACKS ----
for research, wid in RESOLVED_ALL:
    if not wid:
        continue
    for st in research.get("soundtracks", []):
        cur.execute("""INSERT INTO soundtracks(work_id, type, title, composer_or_performer, release_date,
                           chart_peak_us, chart_peak_uk)
                       VALUES (?,?,?,?,?,?,?)""",
                    (wid,
                     st.get("type"),
                     st.get("title"),
                     st.get("composer_or_performer"),
                     st.get("release_date"),
                     st.get("chart_peak_us"),
                     st.get("chart_peak_uk")))

conn.commit()

# ===========================================================================
# PEOPLE ENRICHMENT
#
# v2 carried a hand-written dict of 20 people. Every one of its 20 IMDb IDs and 20
# Wikidata IDs pointed at an unrelated person (nm0503155 "Stan Lee" is Frantisek
# Josef Leopold; nm0001498 "Tobey Maguire" is John Mahoney), and five birth dates
# were wrong too. It has been replaced by fetch_tmdb_people.py, which resolves
# names inside the credit list of the work they are credited on and writes
# data_raw/people_external.json. That file is read here, so the build stays
# offline and reproducible.
# ===========================================================================
EXTERNAL_PEOPLE_PATH = RAW_DIR / "people_external.json"
people_enriched = 0
people_external = {}
if EXTERNAL_PEOPLE_PATH.exists():
    with open(EXTERNAL_PEOPLE_PATH, "r", encoding="utf-8") as f:
        people_external = json.load(f).get("people", {})
    for name, info in people_external.items():
        pid = get_person_id(name)
        if not pid:
            continue
        cur.execute("""UPDATE people SET birth_date=?, death_date=?, birth_place=?,
                              imdb_id=?, wikidata_id=?, tmdb_id=?, external_match_method=?
                       WHERE id=?""",
                    (info.get("birth_date"), info.get("death_date"), info.get("birth_place"),
                     info.get("imdb_id"), info.get("wikidata_id"), info.get("tmdb_id"),
                     info.get("matched_by"), pid))
        people_enriched += 1
else:
    print(f"  NOTE: {EXTERNAL_PEOPLE_PATH.name} not found; people external IDs left NULL.")
    print("        Run: export TMDB_TOKEN=... && python3 fetch_tmdb_people.py")

conn.commit()

# ===========================================================================
# CSV EXPORT
# ===========================================================================
def dump_table(table, path):
    cols = [r[1] for r in cur.execute(f"PRAGMA table_info({table})").fetchall()]
    rows = cur.execute(f"SELECT * FROM {table}").fetchall()
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(cols)
        w.writerows(rows)
    return len(rows)

csv_counts = {}
for t in ["franchises", "media_works", "movies", "tv_shows", "games",
          "character_identities", "characters", "work_characters", "cast_crew",
          "game_releases", "review_scores", "studios", "work_studios", "box_office",
          "budgets", "awards", "episodes", "work_relations", "source_material",
          "soundtracks", "platforms", "game_platforms", "people", "work_people"]:
    csv_counts[t] = dump_table(t, DATA_DIR / f"{t}.csv")

# ---------------------------------------------------------------------------
# Flat combined CSV — one row per work, 40 columns.
#
# The v2 writer declared a 28-column header but emitted 30-31 values per row: the
# movie and TV blocks both wrote a sub_type into a single shared slot, and each
# branch padded with a different number of blanks. Here every media-specific column
# is namespaced and every row is built from the same ordered column list, so the
# header and the rows cannot drift apart.
# ---------------------------------------------------------------------------
FLAT_COLUMNS = [
    # identity (7)
    "work_id", "title", "release_year", "release_date", "media_type", "franchise", "notes",
    # movie detail (8)
    "movie_sub_type", "movie_studio", "movie_distributor", "movie_director",
    "movie_producer", "movie_runtime_minutes", "movie_mpaa_rating", "movie_notes",
    # tv detail (10)
    "tv_sub_type", "tv_format", "tv_network", "tv_start_year", "tv_end_year",
    "tv_seasons", "tv_episodes", "tv_head_writer", "tv_voice_actor_spider_man", "tv_status",
    # game detail (4)
    "game_genre", "game_engine", "game_universe", "game_notes",
    # cross-table rollups (13)
    "studios", "platforms", "n_characters", "n_cast_crew", "top_billed_actor",
    "n_review_scores", "avg_review_pct", "n_awards", "n_awards_won",
    "production_budget_usd", "lifetime_worldwide_usd", "lifetime_domestic_usd",
    "opening_week_domestic_usd",
]
assert len(FLAT_COLUMNS) == 42, f"flat CSV must have 42 columns, got {len(FLAT_COLUMNS)}"

MOVIE_COLS = ["sub_type", "studio", "distributor", "director", "producer",
              "runtime_minutes", "mpaa_rating", "notes"]
TV_COLS = ["sub_type", "format", "network", "start_year", "end_year", "seasons",
           "episodes", "head_writer", "voice_actor_spider_man", "status"]
GAME_COLS = ["genre", "engine", "universe", "notes"]

flat_path = DATA_DIR / "spiderman_all_media_flat.csv"
with open(flat_path, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(FLAT_COLUMNS)
    works = cur.execute("""SELECT mw.id, mw.title, mw.release_year, mw.release_date,
                                  mw.media_type, f.name, mw.notes
                           FROM media_works mw LEFT JOIN franchises f ON f.id = mw.franchise_id
                           ORDER BY mw.media_type, mw.release_year, mw.title""").fetchall()
    for wid, title, year, date, mtype, franch, notes in works:
        row = dict.fromkeys(FLAT_COLUMNS, "")
        row.update(work_id=wid, title=title, release_year=year, release_date=date,
                   media_type=mtype, franchise=franch, notes=notes)

        detail_table, prefix, cols = {
            "movie": ("movies", "movie_", MOVIE_COLS),
            "tv_show": ("tv_shows", "tv_", TV_COLS),
            "game": ("games", "game_", GAME_COLS),
        }[mtype]
        detail = cur.execute(
            f"SELECT {', '.join(cols)} FROM {detail_table} WHERE work_id=?", (wid,)).fetchone()
        if detail:
            for col, value in zip(cols, detail):
                row[prefix + col] = value if value is not None else ""

        one = lambda sql: (cur.execute(sql, (wid,)).fetchone() or [None])[0]
        row["studios"] = one("""SELECT GROUP_CONCAT(name, '; ') FROM (
                                  SELECT DISTINCT s.name FROM work_studios ws
                                  JOIN studios s ON s.id = ws.studio_id
                                  WHERE ws.work_id = ? ORDER BY s.name)""") or ""
        row["platforms"] = one("""SELECT GROUP_CONCAT(name, '; ') FROM (
                                    SELECT DISTINCT p.name FROM game_platforms gp
                                    JOIN platforms p ON p.id = gp.platform_id
                                    WHERE gp.game_id = ? ORDER BY p.name)""") or ""
        # Distinct people, not distinct credit strings: a work that credits both
        # "Spider-Man" and "Spider-Man / Peter Parker" has one character, not two.
        row["n_characters"] = one("""SELECT COUNT(DISTINCT c.identity_id) FROM work_characters wc
                                     JOIN characters c ON c.id = wc.character_id
                                     WHERE wc.work_id = ?""")
        row["n_cast_crew"] = one("SELECT COUNT(*) FROM cast_crew WHERE work_id=?")
        row["top_billed_actor"] = one("""SELECT p.name FROM cast_crew cc JOIN people p ON p.id = cc.person_id
                                         WHERE cc.work_id=? AND cc.role='actor' AND cc.credit_order IS NOT NULL
                                         ORDER BY cc.credit_order LIMIT 1""") or ""
        row["n_review_scores"] = one("SELECT COUNT(*) FROM review_scores WHERE work_id=?")
        avg_pct = one("SELECT ROUND(AVG(score_pct), 1) FROM review_scores WHERE work_id=? AND score_pct IS NOT NULL")
        row["avg_review_pct"] = avg_pct if avg_pct is not None else ""
        row["n_awards"] = one("SELECT COUNT(*) FROM awards WHERE work_id=?")
        row["n_awards_won"] = one("SELECT COUNT(*) FROM awards WHERE work_id=? AND result='won'")
        row["production_budget_usd"] = one(
            """SELECT amount_usd FROM budgets
               WHERE work_id=? AND component='production' AND is_primary=1""") or ""
        row["lifetime_worldwide_usd"] = one(
            "SELECT worldwide_usd FROM box_office WHERE work_id=? AND scope='lifetime'") or ""
        row["lifetime_domestic_usd"] = one(
            "SELECT domestic_usd FROM box_office WHERE work_id=? AND scope='lifetime'") or ""
        # Only a genuine weekly row is an opening week. Reading this off any
        # week_number=1 row returned the full domestic run for 16 of 17 films.
        row["opening_week_domestic_usd"] = one(
            """SELECT domestic_usd FROM box_office
               WHERE work_id=? AND scope='week' AND week_number=1""") or ""

        w.writerow([row[c] for c in FLAT_COLUMNS])

# ===========================================================================
# VERIFICATION
# ===========================================================================
print("Database built at:", DB_PATH)
print("Table row counts:")
for t, n in csv_counts.items():
    print(f"  {t:24s} {n}")

# FK integrity
checks = [
    ("movies", "work_id"),
    ("tv_shows", "work_id"),
    ("games", "work_id"),
    ("work_characters", "work_id"),
    ("cast_crew", "work_id"),
    ("game_releases", "game_work_id"),
    ("review_scores", "work_id"),
    ("work_studios", "work_id"),
    ("box_office", "work_id"),
    ("budgets", "work_id"),
    ("awards", "work_id"),
    ("episodes", "show_work_id"),
    ("work_relations", "work_a_id"),
    ("source_material", "work_id"),
    ("soundtracks", "work_id"),
    ("game_platforms", "game_id"),
    ("work_people", "work_id"),
]
problems = []
for table, col in checks:
    orphans = cur.execute(f"SELECT COUNT(*) FROM {table} WHERE {col} NOT IN (SELECT id FROM media_works)").fetchone()[0]
    if orphans:
        problems.append(f"{table}.{col} has {orphans} orphan rows")

# work_relations.work_b_id and work_characters.character_id were never checked in v2.
for table, col, ref in [("work_relations", "work_b_id", "media_works"),
                        ("work_characters", "character_id", "characters"),
                        ("characters", "identity_id", "character_identities"),
                        ("work_characters", "actor_person_id", "people"),
                        ("cast_crew", "person_id", "people"),
                        ("game_releases", "platform_id", "platforms"),
                        ("game_platforms", "platform_id", "platforms"),
                        ("work_studios", "studio_id", "studios"),
                        ("work_people", "person_id", "people"),
                        ("awards", "recipient_person_id", "people")]:
    orphans = cur.execute(
        f"SELECT COUNT(*) FROM {table} WHERE {col} IS NOT NULL AND {col} NOT IN (SELECT id FROM {ref})"
    ).fetchone()[0]
    if orphans:
        problems.append(f"{table}.{col} -> {ref} has {orphans} orphan rows")

# SQLite only enforces declared FKs when the pragma is on; confirm it agrees.
fk_violations = cur.execute("PRAGMA foreign_key_check").fetchall()
if fk_violations:
    problems.append(f"PRAGMA foreign_key_check reports {len(fk_violations)} violations")

# ---------------------------------------------------------------------------
# ENRICHMENT COVERAGE
# The v2 build reported none of this, which is how 50 works sat empty unnoticed.
# ---------------------------------------------------------------------------
print()
print("Research match rate:")
for label, resolved in [("movies", RESOLVED_MOVIES), ("tv", RESOLVED_TV), ("games", RESOLVED_GAMES)]:
    matched = sum(1 for _, wid in resolved if wid)
    print(f"  {label:8s} {matched}/{len(resolved)} research items matched to a work")

total_works = cur.execute("SELECT COUNT(*) FROM media_works").fetchone()[0]
print()
print("Enrichment coverage (works with >=1 row):")
for table, col in [("cast_crew", "work_id"), ("work_characters", "work_id"),
                   ("work_studios", "work_id"), ("review_scores", "work_id"),
                   ("source_material", "work_id"), ("work_relations", "work_a_id")]:
    n = cur.execute(f"SELECT COUNT(DISTINCT {col}) FROM {table}").fetchone()[0]
    print(f"  {table:18s} {n:3d}/{total_works}  ({100 * n // total_works}%)")

total_people = cur.execute("SELECT COUNT(*) FROM people").fetchone()[0]
print(f"\nPeople enrichment ({people_enriched}/{total_people} matched externally):")
for col in ("birth_date", "birth_place", "imdb_id", "wikidata_id", "tmdb_id"):
    n = cur.execute(f"SELECT COUNT(*) FROM people WHERE {col} IS NOT NULL").fetchone()[0]
    print(f"  {col:14s} {n:3d}/{total_people}  ({100 * n // total_people}%)")
for method, n in cur.execute("""SELECT external_match_method, COUNT(*) FROM people
                                WHERE external_match_method IS NOT NULL
                                GROUP BY 1 ORDER BY 2 DESC"""):
    print(f"  matched by {method}: {n}")

bare = cur.execute("""SELECT media_type, release_year, title FROM media_works
                      WHERE id NOT IN (SELECT work_id FROM cast_crew)
                        AND id NOT IN (SELECT work_id FROM work_characters)
                      ORDER BY media_type, release_year""").fetchall()
print(f"\nWorks with no cast, crew or characters: {len(bare)}")
for mtype, yr, title in bare:
    print(f"  [{mtype:8s}] {yr or '----'}  {title}")

# ---------------------------------------------------------------------------
# DATA QUALITY ASSERTIONS
# ---------------------------------------------------------------------------
n_chars = cur.execute("SELECT COUNT(*) FROM characters").fetchone()[0]
print(f"\nCharacter identity resolution:")
print(f"  {n_chars} credit strings -> {n_identities} distinct characters "
      f"({n_merged_chars} redundant rows merged)")
for rule, n in cur.execute("""SELECT merge_rule, COUNT(*) FROM character_identities
                              GROUP BY 1 ORDER BY 2 DESC"""):
    print(f"    {rule:12s} {n}")
if alignment_conflicts:
    print(f"  identities whose spellings disagreed on alignment ({len(alignment_conflicts)}), "
          f"resolved by majority:")
    for canonical, distinct, chosen in alignment_conflicts:
        print(f"    {canonical:32s} {'/'.join(distinct)} -> {chosen}")
_dupe_app = cur.execute("""SELECT COUNT(*) FROM (
                             SELECT work_id, identity_id FROM v_character_appearances
                             GROUP BY 1,2 HAVING COUNT(*) > 1)""").fetchone()[0]
if _dupe_app:
    print(f"  NOTE: {_dupe_app} (work, character) pairs were credited under "
          f"more than one spelling; v_character_work deduplicates them.")

# work_characters records a cast list per *work*, and for a series a "work" is the
# whole run — Ultimate Spider-Man's 104 episodes contribute one appearance, the same
# weight as a single game. Nothing links a character to an episode. On top of that
# the rosters are not researched to equal depth per medium, so an appearance count
# partly measures how thoroughly a work was catalogued. Report the skew rather than
# let it be read as a finding about the franchise.
print("\nCharacter roster depth (appearance counts are NOT comparable across media):")
for mt, works, links, per, lo, hi in cur.execute("""
        SELECT w.media_type, COUNT(DISTINCT w.id), COUNT(*),
               ROUND(COUNT(*) * 1.0 / COUNT(DISTINCT w.id), 1),
               MIN(k.n), MAX(k.n)
        FROM media_works w
        JOIN work_characters wc ON wc.work_id = w.id
        JOIN (SELECT work_id, COUNT(*) n FROM work_characters GROUP BY 1) k ON k.work_id = w.id
        GROUP BY 1 ORDER BY 4 DESC"""):
    print(f"  {mt:8s} {works:>3} works, {links:>4} links, {per:>5} characters/work (range {lo}-{hi})")
print("  A TV work is an entire series; there is no character-to-episode link.")

if episodes_skipped:
    print(f"\nResearch rows skipped (no episode number, so not an episode): {len(episodes_skipped)}")
    for show, title in episodes_skipped:
        print(f"  [{show}] {title!r}")

# Columns nothing populates. The README documents these as known gaps; the build
# reports them so a column that quietly stops being filled cannot go unnoticed.
dead_columns = []
for (tbl,) in cur.execute("""SELECT name FROM sqlite_master WHERE type='table'
                             ORDER BY name""").fetchall():
    total = cur.execute(f"SELECT COUNT(*) FROM [{tbl}]").fetchone()[0]
    if not total:
        continue
    for col in cur.execute(f"PRAGMA table_info([{tbl}])").fetchall():
        filled = cur.execute(f"SELECT COUNT([{col[1]}]) FROM [{tbl}]").fetchone()[0]
        if filled == 0:
            dead_columns.append(f"{tbl}.{col[1]}")
if dead_columns:
    print(f"\nFully-NULL columns ({len(dead_columns)}) — no source populates these:")
    for c in dead_columns:
        print(f"  {c}")

if review_scores_skipped:
    print(f"\nReview entries skipped (no numeric score): {review_scores_skipped}")
if alignment_dropped:
    # Not a failure: the string is kept verbatim in characters.alignment_raw and the
    # enum column is left NULL. Some research values ("playable (PSP)") describe
    # playability rather than an allegiance and have no honest enum equivalent.
    print(f"\nAlignment strings with no enum equivalent (kept in alignment_raw): "
          f"{sorted(alignment_dropped)}")
if unknown_relation_types:
    problems.append(f"unmapped relation_type values: {sorted(unknown_relation_types)}")
if unresolved_relation_titles:
    print(f"\nRelated-work titles not in the catalog ({len(unresolved_relation_titles)}), "
          f"expected for comics/films outside the dataset:")
    for t in sorted(unresolved_relation_titles)[:10]:
        print(f"  {t}")

# work_relations edges read "work_b is the <relation_type> of work_a", the direction
# the source research uses in 57 of 60 year-orderable cases. The rest are listed
# rather than auto-flipped: a prequel can legitimately ship after the work it
# precedes (Battle for New York, 2006, is a narrative prequel to a 2005 game), so
# release order alone cannot decide which way an edge should point.
suspect_edges = cur.execute("""
    SELECT a.title, a.release_year, wr.relation_type, b.title, b.release_year
    FROM work_relations wr
    JOIN media_works a ON a.id = wr.work_a_id
    JOIN media_works b ON b.id = wr.work_b_id
    WHERE a.release_year IS NOT NULL AND b.release_year IS NOT NULL
      AND ((wr.relation_type = 'sequel'  AND b.release_year < a.release_year)
        OR (wr.relation_type = 'prequel' AND b.release_year > a.release_year))
""").fetchall()
if suspect_edges:
    print(f"\nRelation edges whose release order contradicts the declared direction "
          f"({len(suspect_edges)}) — review, not auto-corrected:")
    for at, ay, rt, bt, by in suspect_edges:
        print(f"  {at} ({ay}) --{rt}--> {bt} ({by})")

bad_roles = studio_roles_seen - {
    'production', 'co_production', 'distributor', 'financing', 'in_association_with',
    'developer', 'co_developer', 'publisher', 'port'}
if bad_roles:
    problems.append(f"work_studios.role values outside the CHECK constraint: {sorted(bad_roles)}")

dupe_weeks = cur.execute("""SELECT COUNT(*) FROM (SELECT work_id, scope, week_number FROM box_office
                            GROUP BY 1,2,3 HAVING COUNT(*) > 1)""").fetchone()[0]
if dupe_weeks:
    problems.append(f"box_office has {dupe_weeks} duplicated (work_id, scope, week_number) rows")

# ---------------------------------------------------------------------------
# Checks added in v4. Each one corresponds to a defect the v3 build shipped.
# ---------------------------------------------------------------------------
if box_office_missing_scope:
    problems.append(f"box_office rows with no scope in the research: {box_office_missing_scope}")

# A lifetime row has no week; a weekly row must have one.
bad_scope = cur.execute("""SELECT COUNT(*) FROM box_office
                           WHERE (scope='lifetime' AND week_number IS NOT NULL)
                              OR (scope='week'     AND week_number IS NULL)""").fetchone()[0]
if bad_scope:
    problems.append(f"box_office has {bad_scope} rows whose scope and week_number disagree")

# Exactly one primary figure per (work, component), or ROI silently doubles.
multi_primary = cur.execute("""SELECT COUNT(*) FROM (
                                 SELECT work_id, component FROM budgets WHERE is_primary=1
                                 GROUP BY 1,2 HAVING COUNT(*) > 1)""").fetchone()[0]
if multi_primary:
    problems.append(f"budgets has {multi_primary} (work, component) pairs with >1 primary row")

# Every credit string must resolve to exactly one person.
unresolved_chars = cur.execute("SELECT COUNT(*) FROM characters WHERE identity_id IS NULL").fetchone()[0]
if unresolved_chars:
    problems.append(f"{unresolved_chars} characters rows have no identity_id")

# A series cannot hold more episodes than it aired.
over_count = cur.execute("""SELECT w.title, t.episodes, COUNT(e.id)
                            FROM tv_shows t
                            JOIN media_works w ON w.id = t.work_id
                            LEFT JOIN episodes e ON e.show_work_id = t.work_id
                            WHERE t.episodes IS NOT NULL
                            GROUP BY 1,2 HAVING COUNT(e.id) > t.episodes""").fetchall()
if over_count:
    problems.append("episodes exceed the series' declared count: "
                    + "; ".join(f"{t} {n}>{c}" for t, c, n in over_count))

# The trailing '|' that forked studios into duplicate entities.
dirty = cur.execute("""SELECT COUNT(*) FROM game_releases
                       WHERE developer LIKE '%|' OR publisher LIKE '%|'""").fetchone()[0]
if dirty:
    problems.append(f"{dirty} game_releases rows still carry a trailing '|' in developer/publisher")

# Every score must be groupable by outlet.
no_pub = cur.execute("SELECT COUNT(*) FROM review_scores WHERE publication IS NULL OR publication=''").fetchone()[0]
if no_pub:
    problems.append(f"{no_pub} review_scores rows have no publication")

# No text column anywhere may carry a table-cell '|' artifact from the source
# scrape. The developer fix caught 47 of them; a later pass found 11 more in
# source_material, including comic years filed in storyline_arc as "1962 |".
pipe_hits = []
for (tbl,) in cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall():
    for col in cur.execute(f"PRAGMA table_info([{tbl}])").fetchall():
        if col[2].upper() != 'TEXT':
            continue
        n = cur.execute(f"""SELECT COUNT(*) FROM [{tbl}]
                            WHERE [{col[1]}] LIKE '%|' OR [{col[1]}] LIKE '|%'""").fetchone()[0]
        if n:
            pipe_hits.append(f"{tbl}.{col[1]} ({n})")
if pipe_hits:
    problems.append(f"pipe-artifact strings remain in: {', '.join(pipe_hits)}")

with open(flat_path, encoding="utf-8") as f:
    widths = {len(r) for r in csv.reader(f)}
if widths != {len(FLAT_COLUMNS)}:
    problems.append(f"flat CSV rows are ragged: widths {sorted(widths)}")

print()
if problems:
    print("VALIDATION FAILURES:")
    for p in problems:
        print(f"  ✗ {p}")
else:
    print("Validation: all integrity, enum and export checks passed.")

print("\nFlat CSV:", flat_path, f"({len(FLAT_COLUMNS)} columns)")
conn.close()
if problems:
    sys.exit(1)
