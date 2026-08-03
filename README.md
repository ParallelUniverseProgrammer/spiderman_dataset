# Spider-Man Media Dataset

[![Data licence: CC BY 4.0](https://img.shields.io/badge/data-CC%20BY%204.0-blue.svg)](LICENSE-DATA)
[![Code licence: MIT](https://img.shields.io/badge/code-MIT-green.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/)
[![Dependencies: none](https://img.shields.io/badge/dependencies-none-brightgreen.svg)](#reproducing-the-build)

**Every Spider-Man movie, TV series and video game ever released — 1967 to 2026 —
normalized into a 24-table SQLite database with cast, characters, studios, budgets,
box office, review scores and comic sources.**

Not a scraped CSV dump. Character names are resolved to *identities* (416 credit
strings → 264 real characters), review scores are normalized onto a common 0–100
scale, and every counting trap in the data is documented rather than left for you
to fall into. The build is offline, dependency-free and byte-for-byte reproducible.

```
81 works  ·  264 characters  ·  581 people  ·  826 cast & crew credits
24 tables  ·  4 analysis views  ·  25 CSV exports  ·  484 KB
```

| | |
|---|---|
| **Movies** | 23 — live-action and animated, 1977–2026, including the Sony spin-offs |
| **TV shows** | 15 — 4 live-action, 11 animated, 1967–2026 |
| **Games** | 43 — 1982 Atari 2600 through *Marvel's Spider-Man 2* (2023) |
| **Format** | SQLite (`spiderman.db`) + one CSV per table + a denormalized flat CSV |
| **Provenance** | Wikipedia, Box Office Mojo, Rotten Tomatoes, Metacritic, IMDb, TMDB |

**Contents** — [Quickstart](#quickstart) · [Browse it interactively](#browse-it-interactively) ·
[Example queries](#example-queries) ·
[Schema](#schema) · [Read this before you count](#read-this-before-you-count) ·
[Files](#files) · [Reproducing the build](#reproducing-the-build) ·
[Coverage & limitations](#coverage--limitations) · [Licence](#licence--attribution)

---

## Quickstart

```bash
git clone https://github.com/<your-user>/spiderman-dataset.git
cd spiderman-dataset
sqlite3 spiderman.db "SELECT title, release_year FROM media_works ORDER BY release_year LIMIT 5;"
```

No build step and nothing to install — `spiderman.db` and the CSVs are committed.

Or open `explorer/index.html` in a browser and click around instead — see
[Browse it interactively](#browse-it-interactively).

<details>
<summary><b>pandas</b></summary>

```python
import sqlite3, pandas as pd

con = sqlite3.connect("spiderman.db")
films = pd.read_sql("SELECT * FROM v_film_economics", con)

# or skip SQL entirely — one row per work, 42 columns
flat = pd.read_csv("data/spiderman_all_media_flat.csv")
```
</details>

<details>
<summary><b>Just the CSVs</b></summary>

`data/` holds one CSV per table plus `spiderman_all_media_flat.csv`, a
denormalized single-row-per-work view with studios, platforms, budget, gross and
review averages already joined. Good for a spreadsheet or a quick notebook; use
the database when you need the character and credit relationships.
</details>

---

## Browse it interactively

```bash
open explorer/index.html          # or just double-click it
```

A dependency-free static page — no server, no network calls, no build step. It
reads `explorer/data.json` (the whole database, ~440 KB) and gives you:

- **Overview** — releases per year by medium, budget → worldwide gross per film,
  review scores over time, and the most-adapted characters. Every mark is
  clickable and every chart has a table view.
- **Works / Characters / People** — sortable, filterable tables over all 81 works,
  264 characters and 581 people. Filters live in the URL, so any view is a link
  you can share, and any view downloads as CSV.
- **Franchises / Studios / Platforms** — three dimensions the database only holds
  implicitly, grouped out of the join tables: 13 franchises, 104 studios and
  66 platforms, each with its own page.
- **Analysis** — how the 13 review outlets differ on a common 0–100 scale, how
  long a comic waits before it is adapted (122 source records, median 28 years),
  which storylines the screen keeps going back to, and every award on record.
- **Detail pages** that cross-link in every direction: a film lists its cast,
  characters, studios, platforms, comic sources, awards, competing budget
  estimates and connected works; a character gets a release strip, the characters
  it most often shares a work with, and the credit spellings collapsed into it;
  a person gets a career strip, frequent collaborators and their role mix.
- **Search** (press `/`) across works, characters, people, franchises, studios
  and platforms at once.
- **About the data** — the counting traps below, restated where you'd hit them,
  plus which figures are read from the database and which are derived in the page.

To regenerate the JSON after rebuilding the database:

```bash
python3 explorer/build_explorer_data.py
```

`explorer/smoke-test.html` drives the page in an iframe and reports pass/fail for
every view, filter, sort and link; open it in a browser after changing the app.

---

## Example queries

Every query below is copy-pasteable and the output is real.

<details open>
<summary><b>Which films earned the most per dollar spent?</b></summary>

```sql
SELECT title, release_year, production_budget_usd, lifetime_worldwide_usd,
       ROUND(gross_multiple, 2) AS multiple
FROM v_film_economics
WHERE gross_multiple IS NOT NULL
ORDER BY gross_multiple DESC
LIMIT 5;
```

| title | release_year | production_budget_usd | lifetime_worldwide_usd | multiple |
|---|---|---|---|---|
| Spider-Man: No Way Home | 2021 | 200000000 | 1921000000 | 9.61 |
| Venom | 2018 | 100000000 | 856100000 | 8.56 |
| Spider-Man: Far From Home | 2019 | 160000000 | 1133000000 | 7.08 |
| Spider-Man: Across the Spider-Verse | 2023 | 100000000 | 690800000 | 6.91 |
| Spider-Man | 2002 | 139000000 | 826800000 | 5.95 |
</details>

<details>
<summary><b>Who are the most-adapted characters?</b></summary>

```sql
SELECT canonical_name, alignment, COUNT(*) AS works
FROM v_character_work          -- spellings already collapsed to one identity
GROUP BY identity_id
ORDER BY works DESC
LIMIT 8;
```

| canonical_name | alignment | works |
|---|---|---|
| Peter Parker / Spider-Man | hero | 70 |
| Green Goblin / Norman Osborn | villain | 27 |
| J. Jonah Jameson | neutral | 23 |
| Eddie Brock / Venom | villain | 23 |
| Doctor Octopus | villain | 23 |
| Mary Jane Watson | hero | 20 |
| Electro | villain | 18 |
| Aunt May | hero | 18 |

Query `v_character_work`, not `work_characters` — the raw table splits Spider-Man
across 7 credit spellings. See [Characters vs credit strings](#characters-vs-credit-strings).
</details>

<details>
<summary><b>How do outlets differ on the games?</b></summary>

```sql
SELECT publication, COUNT(*) AS scores, ROUND(AVG(score_pct), 1) AS avg_pct
FROM v_review_by_publication   -- outlet split out from the reviewed platform
GROUP BY publication
HAVING scores >= 8
ORDER BY avg_pct DESC;
```

| publication | scores | avg_pct |
|---|---|---|
| Game Informer | 14 | 76.8 |
| IGN | 35 | 74.6 |
| Destructoid | 8 | 73.1 |
| GameSpot | 36 | 69.9 |
| GameRankings | 28 | 68.7 |
| Metacritic | 87 | 68.5 |

`score_pct` normalizes every scale (10-point, 5-star, 100) onto 0–100 so outlets
are comparable at all.
</details>

<details>
<summary><b>How deeply is each medium catalogued?</b></summary>

```sql
SELECT media_type,
       COUNT(DISTINCT identity_id) AS distinct_characters,
       COUNT(*)                    AS appearances
FROM v_character_work
GROUP BY media_type;
```

| media_type | distinct_characters | appearances |
|---|---|---|
| game | 164 | 481 |
| movie | 135 | 230 |
| tv_show | 46 | 81 |

Read this one as a caveat, not a finding — see
[Counting appearances](#counting-appearances).
</details>

---

## Schema

24 tables, 4 views, 17 indexes. Row counts are current as of the committed build.

```
franchises (id, name, description)                              -- 13 rows
media_works (id, title, release_year, release_date, media_type,
             franchise_id, notes)                               -- 81 rows
      UNIQUE (title, release_year, media_type)

--- Detail tables (1:1 with media_works) ---
movies (work_id, sub_type, studio, distributor, director, producer,
        runtime_minutes, mpaa_rating, notes)                     -- 23 rows
tv_shows (work_id, sub_type, format, network, start_year, end_year,
          seasons, episodes, head_writer, voice_actor_spider_man, status) -- 15 rows
games (work_id, genre, engine, universe, notes)                 -- 43 rows

--- Enrichment tables ---
character_identities (id, canonical_name, alignment, first_comic_title,
                      first_comic_year, n_variants, merge_rule)  -- 264 rows
characters (id, name, alias, alignment, alignment_raw,
            first_comic_title, first_comic_year, identity_id)    -- 416 rows
      alignment CHECK IN (hero, villain, neutral, antihero); alignment_raw keeps
      the unnormalized research string.
work_characters (work_id, character_id, actor_person_id, billing_order, notes) -- 801 rows
cast_crew (work_id, person_id, role, character_name, credit_order)             -- 826 rows
game_releases (id, game_work_id, platform_id, release_date, publisher,
               developer, metacritic_score, esrb_rating)                       -- 169 rows
review_scores (work_id, source, publication, platform_scope, score, max_score,
               score_pct, review_count)                                        -- 270 rows
      max_score is inferred from the publication's known scale when the research
      omits it; score_pct normalizes every score onto 0-100. source is the raw
      research string and embeds the reviewed platform ("Metacritic (PS3)"),
      giving 128 distinct strings for 36 outlets; GROUP BY publication, not source.
studios (id, name, country, parent_company)                                    -- 104 rows
work_studios (work_id, studio_id, role)                                        -- 286 rows
      PRIMARY KEY (work_id, studio_id, role) — a studio is often both developer
      and publisher of the same game.
      role CHECK IN (production, co_production, distributor, financing,
                     in_association_with, developer, co_developer, publisher, port)
box_office (id, work_id, scope, week_number, week_start_date, domestic_usd,
            international_usd, worldwide_usd)                                  -- 20 rows
      UNIQUE (work_id, scope, week_number)
      scope CHECK IN (week, lifetime). 16 rows are full-run totals; 4 are a real
      weekly series.
budgets (id, work_id, amount_usd, currency, component, inflation_adj_2024,
         source_year, is_primary, note)                                        -- 18 rows
      UNIQUE (work_id, component, amount_usd). A component may carry rival
      published estimates; is_primary marks the one figure per (work, component)
      that rollups and ROI should use.
awards (work_id, award_body, year, category, result, recipient_person_id)      -- 21 rows
episodes (id, show_work_id, season_number, episode_number, title, air_date,
          runtime_minutes, director, writer, us_viewers_millions)              -- 50 rows
work_relations (work_a_id, work_b_id, relation_type)                           -- 157 rows
source_material (id, work_id, comic_title, issue_range, comic_writer,
                 comic_year, storyline_arc)                                    -- 142 rows
soundtracks (id, work_id, type, title, composer_or_performer, release_date,
             chart_peak_us, chart_peak_uk)                                     -- 32 rows

--- Shared lookup tables ---
platforms (id, name)                                                           -- 66 rows
game_platforms (game_id, platform_id)                                          -- 169 rows
people (id, name, birth_date, death_date, birth_place, nationality,
        imdb_id, wikidata_id, tmdb_id, external_match_method)                  -- 581 rows
work_people (work_id, person_id, role)                                         -- 517 rows
```

### Analysis views

Prefer these over the raw tables for anything you plan to aggregate.

| View | Rows | What it does |
|---|---|---|
| `v_character_work` | 792 | One row per (character, work) with spellings collapsed to one identity. **Use this to count characters.** |
| `v_character_appearances` | 801 | `work_characters` resolved to `character_identities`, keeping the actor and billing order. |
| `v_film_economics` | 23 | Lifetime gross vs primary production budget, plus `gross_multiple`. |
| `v_review_by_publication` | 270 | Review scores with the outlet split out from the reviewed platform. |

---

## Read this before you count

The dataset is normalized, but a few tables carry traps that produce
confident-looking wrong answers. Each one is described here and reported by the
build on every run.

### Characters vs credit strings

`characters` holds one row per credit string exactly as its source file spells it.
Each research file uses its own convention — `Spider-Man / Peter Parker` in
`games.json`, `Peter Parker / Spider-Man` in `movies.json`, `Peter Parker` in
`tv.json` — so `UNIQUE(name)` enforces string uniqueness, not identity. **416
credit strings name 264 distinct characters.** `identity_id` resolves each row to
the person; 61 identities have more than one spelling.

Two merge rules, recorded per identity in `merge_rule`:

- `token_set` — the same identities in a different order, or differing only by a
  trailing appearance qualifier: `Green Goblin / Norman Osborn` ==
  `Norman Osborn / Green Goblin` == `Green Goblin / Norman Osborn (DS)`. Mechanical.
- `alias_map` — resolved through `CHARACTER_IDENTITIES`, which splits the tokens in
  a credit string into two kinds:
  - **names** identify one specific person (`peter parker`, `eddie brock`);
  - **mantles** are codenames a succession of people have worn (`spider-man` is
    Peter, Miles, Peter B. Parker and Takuya Yamashiro; `green goblin` is Norman
    and Harry), so a mantle alone identifies nobody.

  The research only qualifies a mantle when the bearer is *not* the usual one — it
  writes `Miles Morales / Spider-Man` but plain `Spider-Man` for Peter — so an
  unqualified mantle resolves to its default bearer via `MANTLE_DEFAULT`. Every
  default was checked against the underlying credits: all nine bare `Green Goblin`
  rows are Norman, all six bare `Venom` rows are Eddie Brock, and the bare
  `Spider-Man` rows carry the canonical Spider-Man voice actors.

A credit naming two people at once resolves to neither and stays separate, which is
how `Olivia Octavius / Doctor Octopus` avoids being merged into Otto. Prowler
(Aaron Davis / Hobie Brown / Miles G. Morales) and Hobgoblin (Roderick Kingsley /
Ned Leeds) have no dominant bearer and so have no default at all.

> **Count characters with `v_character_work`, not `work_characters`** — the latter
> splits Spider-Man across 7 rows and Doctor Octopus across 4.

Where a character's spellings disagreed on alignment (21 identities, e.g.
`May Parker`=hero vs `Aunt May`=neutral), `character_identities.alignment` takes
the majority; the per-row research values stay in `characters`.

A spelling with no `/` and no parenthetical is a single indivisible token, so
neither merge rule can reach inside it and it becomes its own identity unless
`CHARACTER_IDENTITIES` lists it — this is what split `Aunt May Parker` from
`Aunt May`, and `Punisher`, `MJ`, `Stan`, `Morbius` and `Calypso` from their
fuller spellings. The build now reports any pair of identities whose canonical
names nest inside one another, against a list of pairs already reviewed and
judged genuinely distinct (`Doctor Octopus` vs `Olivia Octavius / Doctor
Octopus`, `Hulk` vs `She-Hulk`, …), so a new unmerged spelling shows up instead
of quietly inflating the character count.

### Counting appearances

`work_characters` records a cast list per **work**, and for television a work is the
entire series: *Ultimate Spider-Man*'s 104 episodes contribute one appearance, the
same weight as a single game. Nothing links a character to an episode, and the
`episodes` table has no character column.

The rosters are also not researched to equal depth per medium:

| Medium | Works | Character links | Characters per work |
|--------|-------|-----------------|---------------------|
| game | 43 | 487 | 11.3 |
| movie | 23 | 233 | 10.1 |
| tv_show | 15 | 81 | 5.4 |

Games hold **61%** of all character links, television **10%**. So an appearance
count is partly a measure of how thoroughly a work was catalogued.

> **Appearance totals are not comparable across media.** Compare within a medium,
> or read the per-medium split rather than the total.

### Reading `box_office`

Two different measurements share this table. 16 of the 17 films carry a single
**full-run total** that the research filed under `week_number = 1`; only
*Venom: The Last Dance* has a genuine week-by-week series. Reading every week-1
row as an opening week compares one film's lifetime gross against another film's
first seven days — the 2002 *Spider-Man* row alone would report a $403.7M
"opening week".

> **Filter on `scope`** (`lifetime` vs `week`). The build rejects any row without one.

### Reading `work_relations`

An edge `(work_a, relation_type, work_b)` reads **"work_b is the *relation_type*
of work_a"** for the ordering types (`sequel`, `prequel`, `spin_off`, …), which is
the direction the source research uses in 57 of 60 year-orderable cases. The two
types whose names already encode direction — `dlc_of` and `remaster_of` — read the
other way: work_a is the DLC/remaster of work_b, and `dlc_of` edges are reoriented
at build time from the catalog's own evidence.

The research declares some relations reciprocally and a few in the opposite
direction. For a symmetric type (`same_universe`, `crossover`, `related`,
`inspired`, `tie_in`) a reciprocal declaration is merely redundant and both edges
stand. For an ordering type it is a contradiction — both *The Animated Series*
and *Spider-Man Unlimited* named the other as their `sequel`, so the catalog
answered "what is the sequel of *Spider-Man Unlimited*" with the series that
preceded it — and the build now drops whichever half disagrees with release
order, reporting what it removed. A pair release order cannot settle (equal or
missing years) fails the build rather than being guessed at.

A *single* edge running against release order is still only reported, never
flipped, because a prequel can legitimately ship after the work it precedes
(*Battle for New York*, 2006, is a narrative prequel to a 2005 game).

### People and external IDs

`external_match_method` records how each person was identified:

- `work_credits` (351) — the name was found in the credit list of a film or series
  it is credited on in this dataset. Correct by construction.
- `search_verified` (16) — resolved by name search, then confirmed by checking that
  the person's TMDB credits actually include a franchise title.

A name search that returns exactly one person is *not* proof of identity: TMDB has
an 1885-born Edward J. Montagne (the father, not the 1977 producer) and one John
Digweed (the DJ). 90 such matches were rejected by the verification step rather
than stored — an unresolved person is preferable to a confidently wrong one.

---

## Files

| Path | Description |
|------|-------------|
| `spiderman.db` | SQLite database — the primary artifact |
| `data/*.csv` | One CSV per table (24) |
| `data/spiderman_all_media_flat.csv` | Denormalized one-row-per-work view (42 columns) |
| `data_raw/movies.json` | Source research: 23 films |
| `data_raw/games.json` | Source research: 43 games with per-platform releases |
| `data_raw/tv.json` | Source research: 15 series, 82 episode rows |
| `data_raw/people_external.json` | TMDB person data (367 people), consumed by the build |
| `build_db_v2.py` | The build: rebuilds the DB and every CSV, then validates |
| `fetch_tmdb_people.py` | Optional network step that regenerates `people_external.json` |
| `build_db.py` | v1 build script, superseded — kept for history |
| `AUDIT_REVIEW.md` | Historical QA audit of the v2 build; every issue listed is fixed |
| `explorer/` | Interactive browser explorer — open `explorer/index.html` |

Every research item in `data_raw/` resolves to exactly one work: 23/23 movies,
15/15 TV series, 43/43 games.

---

## Reproducing the build

```bash
python3 build_db_v2.py
```

Python 3.9+, **standard library only** — no pip install, no network. The script
drops and rebuilds `spiderman.db` and all 25 CSVs from `data_raw/*.json`, then runs
a validation pass over foreign keys, enum constraints and export integrity, exiting
non-zero if any check fails. It is deterministic: rebuilding from a clean checkout
reproduces the committed artifacts byte for byte.

The run also prints its own quality report — row counts, research match rate,
per-table coverage, fully-NULL columns, dropped rows and every contradiction it
found but chose not to silently correct.

<details>
<summary><b>Refreshing the TMDB person data (optional)</b></summary>

Person birth/death dates and IMDb/Wikidata/TMDB ids come from TMDB, fetched by a
separate script so the build itself stays offline and deterministic.

```bash
export TMDB_TOKEN='<your TMDB v4 read access token>'
python3 fetch_tmdb_people.py   # writes data_raw/people_external.json
python3 build_db_v2.py         # reads that file, no network needed
```
</details>

---

## Coverage & limitations

Works with at least one enrichment row:

| Table | Works covered |
|-------|---------------|
| `work_characters` | 81/81 (100%) |
| `work_studios` | 81/81 (100%) |
| `source_material` | 73/81 (90%) |
| `cast_crew` | 70/81 (86%) |
| `work_relations` | 68/81 (83%) |
| `review_scores` | 30/81 (37%) |

These are data-availability gaps, not build defects. The build reports each one.

- **`people` external IDs** — 367 of 581 people are resolved (318 with a birth
  date, 365 with an IMDb ID). The remaining 214 are chiefly game developers,
  designers and composers, who are outside TMDB's coverage; a MobyGames or
  Wikidata join would be needed for them.
- **Fully-NULL columns (8)** — nothing in the pipeline populates
  `box_office.week_start_date`, `budgets.inflation_adj_2024`, `people.nationality`,
  `soundtracks.release_date`, `soundtracks.chart_peak_uk`, `studios.country`,
  `studios.parent_company` or `work_characters.notes`. The build lists them on
  every run, so a column that quietly stops being filled cannot go unnoticed.
  `nationality` has no TMDB equivalent and birth place is not a substitute for it.
- **`box_office`** — 20 rows over 17 films: 16 lifetime totals and one genuine
  4-week run (*Venom: The Last Dance*). No film has both, so a film's opening
  week and its final gross are never both known.
- **`budgets`** — 18 rows over 16 films, production component only for most.
- **`awards`** — 21 rows, movies only.
- **`episodes`** — 50 episodes over 5 of the 15 series, and complete only for
  those five. The other ten series have no episode-level data at all: what the
  research supplies for them is a per-season summary row, which the build drops
  because it is not an episode.
- **`review_scores`** — concentrated on games; most films and series have none.
- **Unreleased works** (*Beyond the Spider-Verse*, *Brand New Day*, *El Muerto*,
  *Spider-Noir*, *Marvel's Spider-Man 3*) carry announced credits only, and no
  review, budget or box office figures.

---

## Licence & attribution

- **Data** (`spiderman.db`, `data/`, `data_raw/`) — [CC BY 4.0](LICENSE-DATA).
  Use it commercially, remix it, redistribute it; just credit the source.
- **Code** (`*.py`) — [MIT](LICENSE).

Suggested citation:

```
Spider-Man Media Dataset, https://github.com/<your-user>/spiderman-dataset,
CC BY 4.0.
```

### Sources

Factual records were compiled from Wikipedia (Spider-Man in film / television /
video games), Box Office Mojo, Rotten Tomatoes, Metacritic and IMDb.

Person records come from **The Movie Database (TMDB)**.
*This product uses the TMDB API but is not endorsed or certified by TMDB.*

Spider-Man and all related characters are trademarks of Marvel Characters, Inc.
This is an unaffiliated dataset of factual information about published works, and
contains no copyrighted media.
