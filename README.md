# Spider-Man Media Dataset

[![Data licence: CC BY 4.0](https://img.shields.io/badge/data-CC%20BY%204.0-blue.svg)](LICENSE-DATA)
[![Code licence: MIT](https://img.shields.io/badge/code-MIT-green.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/)
[![Dependencies: none](https://img.shields.io/badge/dependencies-none-brightgreen.svg)](#reproducing-the-build)

**Every Spider-Man movie, TV series and video game ever released — 1967 to 2026 —
normalized into a 54-table SQLite database with cast, characters, studios, budgets,
box office, review scores and the comics behind every adaptation.**

Not a scraped CSV dump. Character names are resolved to *identities* (416 credit
strings → 264 real characters), review scores are normalized onto a common 0–100
scale, comic citations are resolved to real issues with writers and artists
attached, and every counting trap in the data is documented rather than left for
you to fall into. The build is offline, dependency-free and byte-for-byte
reproducible.

```
81 works  ·  264 characters  ·  581 people  ·  826 cast & crew credits
257 comics  ·  318 comic creators  ·  790 character relationships
54 tables  ·  13 analysis views  ·  55 CSV exports  ·  4.7 MB
```

**v4** resolves the dataset's outer edges: the comic titles `source_material`
only ever named as strings are now 257 real comics with writers, artists and
publication dates attached, characters carry a relationship graph (enemies,
family, alternate-universe counterparts), and three of the twelve columns that
were NULL for every row in v3 — `studios.country`, `studios.parent_company`,
`character_details.publisher` — are now populated for some of them. See
[What v4 added](#what-v4-added).

<details>
<summary><b>What v3 added</b> — the 17-table enrichment release this builds on</summary>

Every v2 table kept its columns in the same order and no value v2 wrote was
overwritten — it just had a lot more in it: review scores went from 30 works
to 56, every series got an episode guide rather than five of them, and
`people.nationality` was populated for the first time. See
[What v3 added](#what-v3-added).
</details>

| | |
|---|---|
| **Movies** | 23 — live-action and animated, 1977–2026, including the Sony spin-offs |
| **TV shows** | 15 — 4 live-action, 11 animated, 1967–2026 |
| **Games** | 43 — 1982 Atari 2600 through *Marvel's Spider-Man 2* (2023) |
| **Format** | SQLite (`spiderman.db`) + one CSV per table + a denormalized flat CSV |
| **Provenance** | Wikipedia, Wikidata, Box Office Mojo, Rotten Tomatoes, Metacritic, IMDb, TMDB |

**Contents** — [Quickstart](#quickstart) · [What v4 added](#what-v4-added) ·
[What v3 added](#what-v3-added) · [Browse it interactively](#browse-it-interactively) ·
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

## What v4 added

v3 filled the dataset's holes. v4 goes after its *edges* — the columns that
named something the database had no row for. It adds **4,957 rows** from the
same two sources v3 used, plus what the database itself already knew but had
never cross-referenced (episode credits, comic debuts). Everything it touched
is in `v4_provenance`, on the same terms as v3: nothing v2 or v3 wrote was
changed except to fill a NULL, and `--check` proves it against both.

```sql
SELECT table_name, action, COUNT(*) FROM v4_provenance GROUP BY 1, 2 ORDER BY 3 DESC;
```

### Comics, resolved

`source_material.comic_title` and `character_details.first_appearance_title`
were free text — "Amazing Spider-Man #121-122", "The Amazing Spider-Man #3".
Neither was a row, so nothing could ask which adaptations draw on Ditko-era
issues, or who wrote the comic a character first appeared in. v4 resolves
these citations against Wikidata's comics data:

| | Before | v4 |
|---|---|---|
| Comics with their own row | 0 | **257** (150 from Wikidata, 107 read from a citation) |
| `source_material` rows resolved to a comic | 0 / 142 | **76 / 142** |
| Works with a resolved comic source | 0 / 81 | **36 / 81** |
| Comic creators on record | 0 | **318**, 21 of them also screen-credited in this dataset |
| Credits (writer, penciller, inker, colourist, letterer, cover artist…) | 0 | **889** |
| Character debuts pointing at a comic row | 0 / 264 | **131 / 264** |

Wikidata itemises roughly ninety of the nine hundred *Amazing Spider-Man*
issues. A citation naming one of the rest still becomes a `comics` row —
`origin='parsed'`, series and issue number read straight out of the citation —
rather than being dropped or forced onto the wrong issue; it just carries no
date, publisher or credits. Filter on `origin='wikidata'` for the ones with
real metadata behind them.

### The character graph

Characters had attributes (`character_details`) but no relationships to each
other. `character_relations` adds enemies, family, partners and
alternate-universe counterparts as edges; `character_traits` adds the
abilities, team memberships and physical description behind them.

| | |
|---|---|
| Relationship edges | **790** (257 between two identities this dataset has a row for; the rest name someone Wikidata links to that this dataset does not track) |
| Identities with at least one edge | **131 / 264** |
| Identities with at least one trait | **141 / 264** |

Where v3's identity resolver mapped several of this dataset's spellings onto
the same Wikidata item — the four Spider-Men of the Spider-Verse films all
reduce to one Q-id — the item's relationships are attached to whichever
identity has the most credited spellings behind it, not copied onto all of
them. Copying would have said, as data, that Takuya Yamashiro has Peter
Parker's seventy-eight enemies.

### The rest

- **`episodes.director` / `.writer`** needed no new source at all — just
  reading a column the database already had against another for the first
  time. They were `; `-joined name strings over 577 rows; `episode_credits`
  splits them and matches each name back to `people` by exact normalized
  match: **465 / 577** episodes now have at least one addressable credit,
  **238** of those names resolved to a person who also holds a screen credit
  elsewhere in the dataset.
- **`studios.country`** and **`studios.parent_company`** were two of the
  twelve columns the [coverage section](#coverage--limitations) listed as
  never populated. A new Wikidata resolution pass over all 104 studios and 66
  platforms fills them for **71 / 104** and **38 / 104** studios, and fills
  the new `studio_details` and `platform_details` tables (**74** and **51**
  rows) with industry, HQ, founding date and — for platforms — manufacturer
  and discontinuation date.
- **`character_details.publisher`** — also on that fully-NULL list — needed no
  network call of its own: it's filled for **106 / 264** identities from the
  publisher of the comic each one debuted in, once that comic had one.

### New tables

Thirteen, all new — no v2 or v3 table changes shape.

| Table | Rows | |
|---|---|---|
| `comics` | 257 | Series, issues and storylines resolved from citations |
| `comic_creators`, `comic_credits` | 318 / 889 | Writers and artists, and who did what on which issue |
| `comic_characters` | 460 | Which of this dataset's characters a comic issue lists |
| `work_source_comics` | 185 | `source_material` rows linked to the comics they resolved to |
| `character_debuts` | 131 | A character's first appearance as a comic row, not a title string |
| `character_relations`, `character_traits` | 790 / 712 | The character graph |
| `studio_details`, `platform_details` | 74 / 51 | Industry, HQ, founding/discontinuation dates |
| `episode_credits` | 875 | Director/writer names split out and matched to `people` |
| `v4_provenance`, `v4_sources` | 4,957 / 3 | What v4 touched, and where it came from |

Plus five views: `v_work_comic_sources`, `v_comic_creator_profile`,
`v_character_network`, `v_character_dossier`, `v_episode_credits`.

### Verifying the compatibility claim

```bash
python3 build_db_v4.py --check
```

Builds v2+v3 on their own into a temporary directory and diffs the result
against the v4 database: every v2 and v3 table must keep the same columns in
the same order, every row either of them wrote must still be there with the
same values (except NULLs v4 filled, and only on the three columns above), all
eight earlier views must still run, and the flat CSV must keep its 42 columns.

---

## What v3 added

v3 does one thing: it fills the holes v2 documented, from two sources that need no
API key — [Wikidata](https://www.wikidata.org/) and the English Wikipedia. It adds
**11,683 rows**, fills **845 columns that were NULL** on rows that already existed,
and corrects **2 stale values**. Everything it touched is listed row by row in the
new `v3_provenance` table, so the delta can be audited or filtered back out:

```sql
SELECT table_name, action, COUNT(*) FROM v3_provenance GROUP BY 1, 2 ORDER BY 3 DESC;
```

### Gaps closed

| | v2 | v3 |
|---|---|---|
| Works with a review score | 30 / 81 | **56 / 81** |
| Films with a review score | 1 / 23 | **17 / 23** |
| Series with an episode guide | 5 / 15 | **15 / 15** |
| Series with a review score | 1 / 15 | **4 / 15** |
| Episode rows | 50 | **577** |
| Works with an award on record | 7 | **17** |
| People with a nationality | 0 / 581 | **382 / 581** |
| People with a birth date | 318 / 581 | **394 / 581** |
| People with an IMDb ID | 365 / 581 | **416 / 581** |
| Characters with a first comic appearance | 139 / 264 | **157 / 264** |

### New tables

Seventeen, all new — no v2 table changed shape.

| Table | Rows | |
|---|---|---|
| `external_ids` | 5,998 | IMDb, Rotten Tomatoes, Metacritic, TMDB, Letterboxd, Steam, Wikidata … for works, people and characters |
| `person_occupations`, `person_citizenships` | 2,268 | what each person does, and where they are from |
| `person_awards` | 1,022 | awards a person holds in their own right, including for work outside this dataset |
| `person_details` | 421 | gender, birth name, active period |
| `episode_segments` | 324 | both titles for the shows that air two shorts per slot |
| `work_release_dates` | 196 | territory-by-territory release |
| `work_genres` | 186 | |
| `character_details` | 182 | creators, narrative universe, first appearance |
| `work_places` | 114 | narrative and filming locations |
| `work_countries`, `work_languages` | 122 | |
| `work_summaries` | 79 | a paragraph of prose per work — the dataset had none |
| `work_content_ratings` | 17 | MPAA / ESRB / BBFC certificates |
| `box_office_regions` | 9 | gross in territories the two-column `box_office` cannot express |
| `v3_provenance`, `v3_sources` | 12,536 | what came from where |

Plus four views: `v_work_reception`, `v_person_profile`, `v_episode_guide`,
`v_work_identifiers`.

### Two judgement calls worth knowing about

**Rotten Tomatoes publishes two numbers and Wikidata records both** against the
same reviewer — the Tomatometer (`90%`) and the mean of the rated reviews
(`7.6/10`). They are different measurements. Only the percentage is stored; taking
whichever statement came first would have reported *Spider-Man* (2002) as scoring
76 rather than 90. The two are told apart by the statement's determination method
(P459), which is also what identifies the outlet on the Metascores, none of which
carry a reviewer qualifier.

**Two `tv_shows` values were corrected rather than left alone.** *Spidey and His
Amazing Friends* declared 103 episodes over 4 seasons; it has since aired 113 over
5\. This is the only place v3 overwrites something v2 wrote, both changes are
recorded in `v3_provenance` with `action='correct'`, and `--check` reports them
instead of failing on them.

### Verifying the compatibility claim

```bash
python3 build_db_v3.py --check
```

This builds v2 on its own into a temporary directory and diffs it against the v3
database: every v2 table must have the same columns in the same order, every row
v2 wrote must still be there with the same values (except NULLs that were filled),
the four v2 views must still run, and the flat CSV must keep its 42 columns.

---

## Browse it interactively

```bash
open explorer/index.html          # or just double-click it
```

A dependency-free static page — no server, no network calls, no build step. It
reads `explorer/data.json` (the whole database, ~920 KB) and gives you:

- **Overview** — releases per year by medium, budget → worldwide gross per film,
  review scores over time, and the most-adapted characters. Every mark is
  clickable and every chart has a table view.
- **Works / Characters / People** — sortable, filterable tables over all 81 works,
  264 characters and 581 people. Filters live in the URL, so any view is a link
  you can share, and any view downloads as CSV.
- **Franchises / Studios / Platforms / Outlets / Comic sources / Comic creators /
  Awarding bodies / Credit roles / Years** — nine dimensions the database only
  holds implicitly, grouped out of the columns that name them, or — for comic
  creators — read straight from a v4 table: 13 franchises, 104 studios,
  66 platforms, 36 outlets, 102 comic sources, 318 comic creators, 8 awarding
  bodies, 62 credit roles and every year on the 1967–2026 span, each with its
  own page.
- **Analysis** — how the review outlets differ on a common 0–100 scale, how
  long a comic waits before it is adapted (122 source records, median 28 years),
  which storylines the screen keeps going back to, and every award on record.
- **Detail pages** that cross-link in every direction: a film lists its cast,
  characters, studios, platforms, comic sources, awards, competing budget
  estimates, connected works and the works it overlaps with by shared people or
  shared characters; a character gets a release strip, its co-appearances, its
  Wikidata-derived relationships (enemies, family, alternate-universe
  counterparts) with the ones this dataset also tracks as clickable links, every
  performer who has played it with the years they played it, and the credit
  spellings collapsed into it; a person gets a career strip, frequent
  collaborators, the characters they have played and when, and who else has
  played them; a comic issue page shows its writer, penciller, inker, colourist
  and letterer, the characters it puts on screen, and every adaptation that
  cites it; a comic creator page shows their full bibliography in this dataset
  and, where the same human also holds a screen credit, links to it.
- **Nothing is a dead end.** Every value on screen leads somewhere: names resolve
  to their person or studio page, years to a page for that year, attributes like
  an MPAA rating or a game engine to the works sharing them, and free text the
  catalogue holds no record for — a comic artist, an episode title — to a
  cross-column lookup that finds every row mentioning it.
- **And every number opens the rows behind it**, never an unfiltered list. A
  studio's "22 movies" cuts that studio's own works block to those 22; an
  awarding body's "2 won" cuts its record table to those two; a series' season
  count opens the episode guide split by season; a character's "3 games" opens
  the works list filtered to that character. Where the honest answer is a
  comparison rather than a list — a review score, a gross, a runtime, a budget —
  the tile opens the ranked table with that row highlighted and the column it
  ranked on in view. The smoke test asserts both halves — 140 checks across
  every page the v3 and v4 layers added, including the new comic and creator
  pages and the character graph — and fails on any cell of data that cannot be
  followed or any summary tile that is inert or lands somewhere that says
  nothing about the number on it.
- **Search** (press `/`) across works, characters, people, franchises, studios,
  platforms, outlets, comic sources, comic creators, awarding bodies, credit
  roles and years at once, with a "search every column" fallback — which now
  also reaches into character traits and relationships — for anything the
  index misses.
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

54 tables, 13 views. Row counts are current as of the committed build. The 24 v2
tables below are unchanged in shape; the 17 tables v3 adds are listed under
[What v3 added](#what-v3-added); the 13 tables v4 adds are listed under
[What v4 added](#what-v4-added).

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

The nine views v3 and v4 add are listed in their own sections:
[v3's four](#what-v3-added), [v4's five](#what-v4-added). `v_character_dossier`
and `v_work_comic_sources` are the ones most worth knowing about — one row per
character with its abilities, teams and enemy count; one row per adaptation
next to the specific comic it draws on.

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
| `data/*.csv` | One CSV per table (54) |
| `data/spiderman_all_media_flat.csv` | Denormalized one-row-per-work view (42 columns) |
| `data_raw/movies.json` | Source research: 23 films |
| `data_raw/games.json` | Source research: 43 games with per-platform releases |
| `data_raw/tv.json` | Source research: 15 series, 82 episode rows |
| `data_raw/people_external.json` | TMDB person data (367 people), consumed by the build |
| `data_raw/v3/*.json` | Wikidata and Wikipedia enrichment, consumed by the v3 layer |
| `data_raw/v4/*.json` | Comics, character graph and org data, consumed by the v4 layer |
| `build_db_v4.py` | **The build.** Runs v2, applies the v3 layer then the v4 layer, validates, exports |
| `v4_layer.py` | The additive v4 layer — comics, character graph, org detail, episode credits |
| `build_db_v3.py` | The v3 build; still produces exactly the v2+v3 database on its own |
| `v3_layer.py` | The additive v3 layer — every row it adds and why |
| `build_db_v2.py` | The v2 build; still produces exactly the v2 database on its own |
| `wdlib.py` | Cached, rate-limited Wikidata / Wikipedia / MusicBrainz access |
| `fetch_wikidata_*.py`, `fetch_episodes.py`, `fetch_reception.py`, `fetch_summaries.py` | Optional network steps that regenerate `data_raw/v3/` |
| `fetch_comics.py`, `fetch_character_graph.py`, `fetch_orgs.py` | Optional network steps that regenerate `data_raw/v4/` |
| `fetch_tmdb_people.py` | Optional network step that regenerates `people_external.json` |
| `build_db.py` | v1 build script, superseded — kept for history |
| `AUDIT_REVIEW.md` | Historical QA audit of the v2 build; every issue listed is fixed |
| `explorer/` | Interactive browser explorer — open `explorer/index.html` |

Every research item in `data_raw/` resolves to exactly one work: 23/23 movies,
15/15 TV series, 43/43 games.

---

## Reproducing the build

```bash
python3 build_db_v4.py           # v2 base + the v3 layer + the v4 layer
python3 build_db_v4.py --check   # ... and prove v2 + v3 compatibility
```

Python 3.9+, **standard library only** — no pip install, no network. `build_db_v4.py`
runs `build_db_v2.py` unchanged and hands it `v4_layer`, which applies `v3_layer`
and then its own rows before the CSVs are exported so the CSVs match the database
they came from. All three stages validate: v2 over foreign keys, enums and export
integrity; v3 over the same plus its own referential and scale checks; v4 over its
own FK and invariant checks (a comic can't be its own series, a parsed issue must
carry a series and number, no character is its own enemy). Either `--check` run
exiting non-zero fails the build.

`python3 build_db_v3.py` on its own still produces exactly the v2+v3 database it
always did, and `python3 build_db_v2.py` still produces exactly v2 — the layer
hook is inert unless `SPIDERMAN_V3_LAYER` is set, which `build_db_v3.py` points at
`v3_layer` and `build_db_v4.py` points at `v4_layer`.

All three are deterministic: the v3 and v4 layers read `data_raw/v3/*.json` and
`data_raw/v4/*.json` written by the fetch scripts below, so the build itself never
touches the network and rebuilding from a clean checkout reproduces the committed
artifacts byte for byte.

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

<details>
<summary><b>Refreshing the v3 data (optional)</b></summary>

The v3 fetchers write `data_raw/v3/*.json`, which the build then reads offline.
None of them needs an API key or an account — Wikidata's SPARQL endpoint and the
MediaWiki Action API are open. Responses are cached under `data_raw/.wd_cache/`,
so a re-run costs no requests, and every request passes a per-host rate limiter.

```bash
python3 fetch_wikidata_works.py       # resolve 81 works -> Wikidata; reviews, money, awards, ids
python3 fetch_wikidata_people.py      # biography, nationality, occupations, awards
python3 fetch_wikidata_characters.py  # first appearance, creators, universe
python3 fetch_episodes.py             # episode guides from the Wikipedia episode lists
python3 fetch_reception.py            # review scores Wikidata does not carry
python3 fetch_summaries.py            # a paragraph of prose per work
python3 build_db_v3.py --check
```

Each script reports what it could not resolve rather than guessing: one work
(*Marvel's Spider-Man 3*, announced but not made) has no Wikidata item, 160 people
and 82 character identities could not be resolved to one unambiguous entity, and
they are left alone rather than matched to a plausible-looking wrong one.
</details>

<details>
<summary><b>Refreshing the v4 data (optional)</b></summary>

The v4 fetchers reuse the QIDs `fetch_wikidata_characters.py` and
`fetch_wikidata_works.py` already resolved — no re-resolution, no extra
requests for those — and write `data_raw/v4/*.json`. Same rules as v3: no API
key, cached under `data_raw/.wd_cache/`, rate-limited per host.

```bash
python3 fetch_comics.py           # resolve source_material and first-appearance citations to comics
python3 fetch_character_graph.py  # enemies, family, alternate-universe counterparts, abilities
python3 fetch_orgs.py             # studios and platforms -> Wikidata; country, parent, manufacturer
python3 build_db_v4.py --check
```

`fetch_comics.py` reports its match rate by kind: of the citations that name a
comic at all, most resolve either to a specific Wikidata issue or, for the
issues Wikidata hasn't itemised, to a series-and-number pair read out of the
citation itself. The rest name something that turns out not to be a comic on
Wikidata — a character, a film with the same title, a band called Venom — and
are left unresolved rather than attached to the wrong item.
</details>

---

## Coverage & limitations

Works with at least one enrichment row:

| Table | Works covered | |
|-------|---------------|---|
| `work_characters` | 81/81 (100%) | |
| `work_studios` | 81/81 (100%) | |
| `external_ids` | 80/81 (99%) | v3 |
| `work_summaries` | 79/81 (98%) | v3 |
| `work_genres` | 76/81 (94%) | v3 |
| `source_material` | 73/81 (90%) | |
| `cast_crew` | 70/81 (86%) | |
| `work_relations` | 68/81 (83%) | |
| `review_scores` | 56/81 (69%) | was 30/81 in v2 |
| `work_source_comics` | 36/81 (44%) | v4 — only 73/81 have a `source_material` row to resolve in the first place |

These are data-availability gaps, not build defects. The build reports each one.

- **`comics` / `work_source_comics`** — 76 of 142 `source_material` citations
  resolved to a comic, over 36 of the 73 works that had a citation at all. A
  citation resolves either to a specific Wikidata issue or, for the ~90% of
  *Amazing Spider-Man* issues Wikidata hasn't itemised, to a series-and-number
  pair read out of the citation itself (`origin='parsed'`, no date or credits).
  What's left unresolved is mostly citations that don't actually name a comic —
  "Spider-Man comics", a film with the same title as a character, a storyline
  described in prose rather than by issue number.
- **`character_relations` / `character_traits`** — 131 of 264 identities have
  at least one relationship edge, 141 at least one trait. Coverage tracks
  `character_details` coverage almost exactly: a character with no Wikidata
  item to begin with has no relationships to read off it either.
- **`review_scores`** — 35 of 43 games, 17 of 23 films, 4 of 15 series. What is
  left is largely unreviewable rather than unresearched: the six films without a
  score are the three 1970s TV movies, the 1978 Toei film, and two that have not
  been released. The animated series are the real remaining gap — most were never
  covered by an aggregator.
- **`people` external IDs** — 421 of 581 people resolve to a Wikidata item, 394
  have a birth date and 416 an IMDb ID. The unresolved 160 are chiefly game
  developers, designers and composers with no Wikidata item, or names common
  enough that no single candidate could be confirmed. They are recorded as
  unresolved rather than matched to a likely-looking wrong person.
- **Characters** — 182 of 264 identities resolve to a Wikidata item, and 157 now
  have a first comic appearance. The remaining 82 are mostly one-off credit
  spellings and background parts that have no item anywhere.
- **Fully-NULL columns (9, down from 12)** — nothing populates
  `work_characters.notes`, `box_office.week_start_date`,
  `budgets.inflation_adj_2024`, `soundtracks.release_date`,
  `soundtracks.chart_peak_uk`, `work_content_ratings.country`,
  `work_content_ratings.reason`, `work_release_dates.event` or
  `box_office_regions.as_of`. The build lists them on every run, so a column
  that quietly stops being filled cannot go unnoticed. (`people.nationality`
  was on this list in v2 and is now filled for 382 of 581; v4 took
  `studios.country`, `studios.parent_company` and `character_details.publisher`
  off it — filled for 71/104, 38/104 and 106/264 respectively, still short of
  every row because not every studio or debut issue resolves to a Wikidata
  item with that fact on it.)
- **`box_office`** — 20 rows over 17 films: 16 lifetime totals and one genuine
  4-week run (*Venom: The Last Dance*). No film has both, so a film's opening week
  and its final gross are never both known. v3 adds nine per-territory figures in
  `box_office_regions` but found no film that was missing a total altogether — the
  six films without one are TV movies and unreleased titles that have no gross.
- **`budgets`** — 23 rows over 17 films; v3 added five, four of them competing
  estimates filed against a film that already had one (`is_primary = 0`).
- **`awards`** — 67 rows over 17 works (11 films and, new in v3, 6 games). A win
  and its matching nomination are one row, not two; see
  [What v3 added](#what-v3-added).
- **`episodes`** — 577 rows over all 15 series. Two caveats: shows that air two
  shorts per slot (the 1967 series, *Spidey and His Amazing Friends*) get one row
  per broadcast slot with the segment titles joined by `/`, and both segments
  separately in `episode_segments`; and *Ultimate Spider-Man* yields 86 rows
  against a declared 104, because its episode list does not itemise the rest.
- **Unreleased works** (*Beyond the Spider-Verse*, *El Muerto*, *Marvel's
  Spider-Man 3*) carry announced credits only, and no review, budget or box office
  figures. *Brand New Day* and *Spider-Noir* have since released and now carry
  review scores.

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

The v3 enrichment comes from **Wikidata** (CC0 1.0) and the **English Wikipedia**
(CC BY-SA 4.0), accessed through their public SPARQL and Action APIs. Which of the
two each v3 row came from is recorded in `v3_provenance`; `v3_sources` holds the
licence and the retrieval date. Text carried over verbatim — the work summaries in
`work_summaries` — is Wikipedia's and remains under CC BY-SA 4.0, which is more
restrictive than this dataset's CC BY 4.0; attribute accordingly if you reuse it.

Spider-Man and all related characters are trademarks of Marvel Characters, Inc.
This is an unaffiliated dataset of factual information about published works, and
contains no copyrighted media.
