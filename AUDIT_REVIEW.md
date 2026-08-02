# Spider-Man Media Dataset — Audit & Review

**Date:** 2025-07-25  
**Database:** `spiderman.db` (v2)  
**Build Script:** `build_db_v2.py`  
**Research JSONs:** `data_raw/movies.json`, `data_raw/games.json`, `data_raw/tv.json`

---

## Executive Summary

The database builds and passes **all FK integrity checks** (0 orphans across 17 junction/detail tables).  
However, **62% of works (50/81) have ZERO enrichment data** due to a critical title-matching bug.  
Data quality varies widely — some tables are nearly complete, others are sparsely populated.

---

## Critical Bugs (Must Fix)

### 1. Title Collision in Combined Dictionary
**File:** `build_db_v2.py`, function `find_work_id_by_title_year` (line 529)  
**Impact:** 2 movies lost ALL enrichment:
- `Spider-Man` (1977) → overwritten by `Spider-Man (1982 video game)`
- `The Amazing Spider-Man` (2012) → overwritten by `The Amazing Spider-Man` (1977 TV series)

**Root Cause:** Combined dict ` {**movie_work_ids, **tv_work_ids, **game_work_ids} ` uses bare title as key. Cross-media collisions resolve to last-inserted (games win, then TV, then movies).

### 2. Fuzzy Match False Positives
**File:** `build_db_v2.py`, lines 535–544  
**Impact:** Games incorrectly match to movies/TV (e.g., `"Spider-Man: The Video Game (1991 Sega arcade)"` → `Spider-Man: The Video Game` movie)  
**Root Cause:** Fuzzy logic strips parens from BOTH sides before comparing, causing `"Spider-Man"` (movie) to match `"Spider-Man (1982 video game)"` (game).

### 3. Incomplete Research Coverage
| Media | DB Works | In Research JSON | Missing |
|-------|----------|------------------|---------|
| Movies | 23 | 20 | 3 (Beyond the Spider-Verse, Brand New Day, El Muerto) |
| TV Shows | 15 | 14 | 1 (Spider-Noir) |
| Games | 43 | 32 | 11 (all pre-2000 + some mid-era) |

---

## Data Quality Scorecard

| Table | Rows | Expected | Coverage | Key Issues |
|-------|------|----------|----------|------------|
| `cast_crew` | 566 | ~810 | 35% | 50 works (62%) have **zero** entries |
| `work_characters` | 738 | ~810 | 46% | 75% missing actor links; 22 works have **zero** characters |
| `review_scores` | 9 | ~400 | **2%** | Almost entirely empty |
| `box_office_weekly` | 20 | ~250 | 8% | Only 17 films; duplicates (Spider-Man 2002 has 2× week 1) |
| `budgets` | 18 | ~60 | 30% | Only 6 films have budgets |
| `awards` | 21 | ~120 | 18% | Sparse |
| `episodes` | 82 | ~400 | 20% | Only 6 series have per-episode data |
| `people` (birth_date) | 20 | 397 | **5%** | Only hardcoded 20 enriched |
| `people` (IMDB/Wikidata) | 20 | 397 | **5%** | Only hardcoded 20 enriched |
| `characters` | 410 | — | — | Alignment not normalized (42 distinct values) |
| `work_studios.role` | 238 | — | — | CHECK constraint violated (research uses `developer`, `publisher`, `port`) |

---

## Schema / Export Bugs

| Bug | Location | Fix |
|-----|----------|-----|
| Flat CSV only 28 columns vs 40 expected | `build_db_v2.py` lines 860–890 | Align column list to v2 schema |
| `work_studios.role` CHECK constraint violated | Schema line 159 | Add `developer`, `publisher`, `port`, `co_developer` |
| Character alignment not normalized | 42 distinct values | Map to enum: `hero/villain/neutral/antihero` |
| Duplicate box office rows | `box_office_weekly` | Deduplicate on `(work_id, week_number)` |

---

## What Works (Verified)

- ✅ All 81 media works present with correct base data
- ✅ FK integrity: **0 orphans** across all 17 junction/detail tables
- ✅ Schema creation: 24 tables created without errors
- ✅ Research JSONs: 66 items well-structured, detailed
- ✅ Character table: 410 distinct characters loaded
- ✅ Platform table: 65 platforms, 152 game-platform links
- ✅ Franchise table: 13 franchises

---

## Recommended Fix Plan (Priority Order)

### Phase 1 — Fix Enrichment Matching (Highest ROI)
1. **Refactor `find_work_id_by_title_year`** to use composite key `(media_type, title)` or disambiguate by release_year
2. **Add 15 missing works** to research JSONs (3 upcoming movies, Spider-Noir TV, 11 pre-2000 games)
3. **Re-run build** — expected enrichment coverage jumps from 31→66+ works

### Phase 2 — Schema & Export Fixes
4. **Fix flat CSV export** — expand to 40 columns matching v2 schema
5. **Update `work_studios.role` CHECK constraint** — add `developer`, `publisher`, `port`, `co_developer`
6. **Normalize character alignment** — map 42 values → 4 enum values
7. **Deduplicate `box_office_weekly`** — unique index on `(work_id, week_number)`

### Phase 3 — Data Enrichment (Medium Term)
8. **Complete weekly box office** for all 17 wide-release films (Box Office Mojo)
9. **Enrich `people` table** — join to TMDB/IMDb APIs for birth dates, external IDs
10. **Expand `review_scores`** — scrape Rotten Tomatoes, Metacritic, IMDb per work
11. **Expand `episodes`** — fetch missing per-episode data from TV episode lists

---

## File Inventory

```
/home/k/Projects/spiderman_dataset/
├── spiderman.db                 # 348 KB — primary normalized DB
├── build_db_v2.py               # 58 KB — v2 build script (has bugs above)
├── build_db.py                  # 40 KB — v1 legacy
├── README.md                    # 5 KB — schema docs
├── AUDIT_REVIEW.md              # This file
├── data_raw/
│   ├── movies.json              # 20 items, 145 KB
│   ├── games.json               # 32 items, 209 KB
│   └── tv.json                  # 14 items, 52 KB
├── data/
│   ├── 24 per-table CSVs        # 200 KB total
│   └── spiderman_all_media_flat.csv  # 20 KB (only 28 cols)
└── seed/                        # (empty directory)
```

---

## Quick Verification Commands

```bash
# Check FK integrity
python3 -c "
import sqlite3
c = sqlite3.connect('spiderman.db')
for t, col in [('movies','work_id'),('tv_shows','work_id'),('games','work_id'),
               ('work_characters','work_id'),('cast_crew','work_id'),
               ('game_releases','game_work_id'),('review_scores','work_id'),
               ('work_studios','work_id'),('box_office_weekly','work_id'),
               ('budgets','work_id'),('awards','work_id'),('episodes','show_work_id'),
               ('work_relations','work_a_id'),('source_material','work_id'),
               ('soundtracks','work_id'),('game_platforms','game_id'),
               ('work_people','work_id')]:
    n = c.execute(f'SELECT COUNT(*) FROM {t} WHERE {col} NOT IN (SELECT id FROM media_works)').fetchone()[0]
    print(f'{t:24s} ({col}) -> {n} orphans')
c.close()
"

# Check enrichment coverage
python3 -c "
import sqlite3
c = sqlite3.connect('spiderman.db')
enriched = set(r[0] for r in c.execute('SELECT DISTINCT work_id FROM cast_crew'))
all_works = set(r[0] for r in c.execute('SELECT id FROM media_works'))
missing = all_works - enriched
print(f'Total: {len(all_works)}, Enriched: {len(enriched)}, Missing: {len(missing)}')
for wid in sorted(missing):
    t, y, m = c.execute('SELECT title, release_year, media_type FROM media_works WHERE id=?', (wid,)).fetchone()
    print(f'  [{m:8s}] {y or \"----\"}  {t}')
c.close()
"
```

---

## Decision

> **Ready for v3 build** incorporating Phase 1–2 fixes.  
> Estimated effort: ~2–3 hours (mostly refactoring matching logic + adding missing JSON entries).

---
*Generated by automated audit on 2025-07-25*

---

# Resolution — v3 build (2026-07-25)

Phases 1 and 2 are implemented in `build_db_v2.py`; the build now self-validates and
exits non-zero on any integrity, enum or export failure. Phase 3 is not done — it
needs external API/scraping access this build does not have.

## Audit findings, resolved

| # | Finding | Status |
|---|---------|--------|
| 1 | Title collision in combined dictionary | Fixed — `WorkMatcher` scopes lookups to one `media_type` and disambiguates on `release_year` |
| 2 | Fuzzy match false positives | Fixed — every fuzzy tier requires the years to agree; containment is restricted to same-year candidates and must be unique |
| 3 | Incomplete research coverage (15 works) | Fixed — 3 movies, 1 TV series, 11 games added to `data_raw/` |
| 4 | Flat CSV 28 columns vs 40 | Fixed — 40 namespaced columns, rows built from one ordered list, width asserted at build time |
| 5 | `work_studios.role` CHECK | Added (the constraint did not previously exist — see corrections below) |
| 6 | Character alignment not normalized | Fixed — enum column plus `alignment_raw` |
| 7 | Duplicate box office rows | Fixed — cause was finding #1, plus the loader ignoring the research's own `week_number`; `UNIQUE (work_id, week_number)` now enforces it |

## Bugs the audit did not catch

### The hardcoded `people` data was fabricated

The scorecard graded `people (IMDB/Wikidata)` as a **coverage** problem — "20/397,
only hardcoded 20 enriched". The data was not merely sparse. **All 20 IMDb IDs and
all 20 Wikidata IDs identified the wrong person**, and 5 of the 20 birth dates were
wrong. Resolved through TMDB's `/find` endpoint:

| Hardcoded as | IMDb ID given | That ID actually is |
|--------------|---------------|---------------------|
| Stan Lee | `nm0503155` | František Josef Leopold |
| Tobey Maguire | `nm0001498` | John Mahoney |
| Neil Patrick Harris | `nm0006203` | Cyril J. Mockridge |

A coverage metric cannot catch this: the rows were populated, just wrong. The block
is gone, replaced by `fetch_tmdb_people.py`, which resolves names inside the credit
list of the work they are credited on and writes `data_raw/people_external.json`
for the build to read offline. 367 of 581 people now carry verified identifiers.

### Everything else

| Bug | Impact | Fix |
|-----|--------|-----|
| Loader read `key_crew`; `games.json` supplies `key_credits` | 210 credits dropped; **all 43 games had zero `cast_crew`** | Read both keys |
| `review_scores` required a non-null `max_score` | 271 of 281 scores discarded — the real cause of the "2% coverage" row | `max_score` nullable and inferred from the publication's scale; added `score_pct` |
| `work_studios` PK `(work_id, studio_id)` | 5 studios that both developed and published a game lost their second role | `role` added to the PK |
| `relation_type: "related"` not in the enum | 14 edges silently swallowed by `INSERT OR IGNORE` | Added to the enum; unmapped types now reported |
| `"tie_in"` mapped to `"tie_in_game_of"` | Asserted game tie-ins that do not exist (Venom → *Into the Spider-Verse*) | `tie_in` is now its own type |
| Related-work titles matched exactly only | ~40% of relations lost | Resolver reads the year/medium out of the title's own parenthetical |
| `parse_year_from_comic_appearance` regex | Returned **2099** for Spider-Man 2099 and issue numbers as years | Prefers the explicit `first_comic_year` field; parser prefers a parenthesised, plausible year |
| Character actor matched on first substring hit | Mis-assigned credits between similarly named characters | Exact credit first; substring only when unique |
| `add_character` used `INSERT OR IGNORE` | First sighting won; richer later data dropped | Later sightings top up NULL columns |
| `work_relations.work_b_id` never FK-checked | Orphans would have gone unnoticed | Added, along with 8 other unchecked FK columns and `PRAGMA foreign_key_check` |
| No unique constraint on work identity | Duplicate works possible | `UNIQUE (title, release_year, media_type)` |

## Corrections to the audit

- **`work_studios.role` CHECK was not "violated"** — no CHECK constraint existed on
  that column. The real defect was the primary key. A CHECK has now been added.
- **Character alignment had 34 distinct values, not 42.**
- **`budgets` covers 16 films, not 6.**
- **`episodes` covers 14 of 15 series, not 6** — though as a sample, not a full listing.
- **`review_scores` was not "almost entirely empty" at source.** The research holds
  281 entries; the loader was throwing 271 of them away.

## Result

| Metric | v2 | v3 |
|--------|----|----|
| Works with zero cast/crew/characters | 50 | **0** |
| Research items matched | 31/66 | **81/81** |
| `cast_crew` rows | 566 | 826 |
| `review_scores` rows | 9 | 270 |
| `work_relations` rows | 96 | 159 |
| `work_studios` rows | 238 | 286 |
| `characters` with normalized alignment | 0 | 416/416 |
| `people` with a *correct* IMDb ID | 0 | 365 |
| `people` with a birth date | 20 (5 wrong) | 318 |
| Flat CSV | 28-col header, 30–31-col rows | 40 columns, uniform |
| FK orphans | 0 | 0 |

## Still open (Phase 3)

Phase 3 item 9 (`people` enrichment) is **done** via TMDB. The rest are
data-availability gaps, not build defects; each is reported by the build and listed
in the README under Known Limitations:

- 214 people remain unresolved — mostly game developers, designers and composers,
  who are outside TMDB's coverage. A MobyGames or Wikidata join would be needed.
- `nationality` is unpopulated: TMDB has no such field, and birth place is not a
  substitute for it.
- Weekly box office beyond opening week, full per-episode listings, and review
  scores for films and series still require Box Office Mojo / RT / Metacritic
  scraping.
---

# Bug sweep — v5 (2026-08-02)

A read-through of `build_db_v2.py` and `fetch_tmdb_people.py` against the built
database. The v4 build reported no validation failures before or after these
fixes; every defect below sat in a blind spot of the checks that existed.

| # | Defect | Fix |
|---|--------|-----|
| 1 | Six characters split across two identities each | Spellings added to `CHARACTER_IDENTITIES`; nesting detector added |
| 2 | `cast_crew` PK and `box_office` UNIQUE not enforced on NULL-tailed rows | Unique indexes over `COALESCE(...)` |
| 3 | Ordering relations declared in both directions, both shipped | Contradicting half dropped by release order; residue fails the build |
| 4 | `resolve_work` accepted a same-year candidate with no title agreement | Title evidence made mandatory; ties resolved or refused |

## 1. Un-delimited spellings never merged

`character_tokens` splits a credit string on `/` and strips a trailing
parenthetical. A spelling containing neither is one token, so it merges only if
`CHARACTER_IDENTITIES` names it outright. Six characters were therefore counted
twice, three of them with contradictory alignments that never met the majority
vote because the rows sat in different identities:

| Spellings | Was | Now |
|-----------|-----|-----|
| `Aunt May Parker` / `Aunt May` (+4 more) | 2 identities | 1 |
| `Punisher` (hero) / `Frank Castle / The Punisher` (antihero) | 2 | 1, antihero |
| `MJ (Michelle Jones-Watson)` / `Michelle "MJ" Jones-Watson` | 2 | 1 |
| `Stan (Stan Lee cameo)` / `Stan Lee` | 2 | 1 |
| `Morbius` (hero) / `Michael Morbius / Living Vampire` (antihero) | 2 | 1, antihero |
| `Calypso` (villain) / `Calypso Ezili` (hero) | 2 | 1, villain |

`Lucien / Milo Morbius` is a different character and correctly stays separate:
the research spells him `Milo Morbius`, its own token, which never matches the
bare `morbius` mantle. Distinct characters: **270 → 264**.

Every bare token added was first checked to occur in exactly one credit string
across all three research files, so none can capture an unrelated character. A
coverage or FK check cannot see this class of bug — the rows are present and
well-formed, there are simply two of them — so the build now lists identity
pairs whose canonical names nest, minus an allowlist of the 13 pairs reviewed
and found genuinely distinct.

## 2. A key ending in a nullable column stops being a key

SQLite holds two NULLs to be distinct when testing uniqueness, so a composite key
whose last column is NULL is not enforced for exactly those rows:

- `cast_crew` PK `(work_id, person_id, role, character_name)` — `character_name`
  is NULL on every crew credit, roughly 500 of 826 rows. `INSERT OR IGNORE` never
  saw a conflict on any of them.
- `box_office` UNIQUE `(work_id, scope, week_number)` — `week_number` is NULL on
  all 16 `scope='lifetime'` rows, so `INSERT OR REPLACE` would have appended a
  second lifetime total rather than replacing the first.

Both tables were duplicate-free, so nothing was wrong in the data; the guard the
loaders lean on simply was not there. Unique indexes folding the NULL to a
sentinel restore it, with no change to stored values or to the CSV exports.

## 3. Reciprocal ordering relations

`sequel` and `spin_off` are antisymmetric, but the research states some relations
from both ends, and the loader inserted both. Two contradictory pairs shipped:

- `Spider-Man: The Animated Series (1994) --sequel--> Spider-Man Unlimited (1999)`
  plus its exact reverse
- `Spider-Man 3 (2007) --spin_off--> Venom (2018)` plus its exact reverse

The v4 chronology check flagged only the backwards-in-time half, as a printed
note, and left both edges live. The build now drops the half that disagrees with
release order and reports it; a pair release order cannot settle is a validation
failure. Edges: **159 → 157**. The one genuine single suspect edge (*Ultimate
Spider-Man* 2005 `prequel` *Battle for New York* 2006) is untouched.

## 4. `resolve_work` could match on the year alone

Title and year evidence were summed into one number tested against a threshold of
8. An exact-year match scored exactly 8, so **any same-year film cleared the bar
with no title agreement whatsoever**, while an exactly-titled film whose year was
off by more than one scored 10−4=6 and was rejected. The docstring described the
intended rule correctly; the arithmetic did not implement it.

The rule is now applied as a filter over candidates rather than a test on the
top scorer, because a same-year/wrong-title result outscores an exactly-titled
one and would shadow it before the test ran. Ties are resolved by which title
carries the least extra text, and a remaining tie returns None.

Replayed against the 808 cached TMDB responses, 37 of 38 works resolve
identically. The one change is a false positive removed: unreleased **El Muerto**
carries no year, and the search returns three unrelated Spanish-language films
titled exactly that — v4 took the first (a 1991 film), the sweep returns None.
That film's single credit matched none of our three El Muerto people, so no
person record was ever affected and `people_external.json` is unchanged.

## Not fixed

- **`awards` PK omits `recipient_person_id`.** Two people nominated in the same
  category for the same work would collapse to one row via `INSERT OR IGNORE`,
  silently and uncounted. All three research files were checked: no such
  collision exists today, so this is latent, not active.
- **`budgets.is_primary` picks the highest figure.** Mechanical rather than
  credibility-weighted; matters only if the ROI view is read as precise.
