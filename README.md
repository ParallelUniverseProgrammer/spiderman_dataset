# Spider-Man Media Dataset (v4)

A normalized SQLite database of Spider-Man movies, TV shows, and video games,
with linked lookup/junction tables. CSV exports are also provided for every table.

Build with `python3 build_db_v2.py`. The script is idempotent: it drops and
rebuilds `spiderman.db` and every CSV from `data_raw/*.json`, then runs a
validation pass and exits non-zero if any integrity, enum or export check fails.

## Database Schema

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
      the unnormalized research string. See "Characters vs credit strings" below:
      416 credit strings name 264 distinct characters.
work_characters (work_id, character_id, actor_person_id, billing_order, notes) -- 801 rows
cast_crew (work_id, person_id, role, character_name, credit_order)             -- 826 rows
game_releases (id, game_work_id, platform_id, release_date, publisher,
               developer, metacritic_score, esrb_rating)                       -- 169 rows
review_scores (work_id, source, publication, platform_scope, score, max_score,
               score_pct, review_count)                                        -- 270 rows
      max_score is inferred from the publication's known scale when the research
      omits it; score_pct normalizes every score onto 0-100 for cross-source
      comparison. source is the raw research string and embeds the reviewed
      platform ("Metacritic (PS3)"), giving 128 distinct strings for 36 outlets;
      GROUP BY publication, not source.
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
      weekly series. See "Reading box_office" below.
budgets (id, work_id, amount_usd, currency, component, inflation_adj_2024,
         source_year, is_primary, note)                                        -- 18 rows
      UNIQUE (work_id, component, amount_usd). A component may carry rival
      published estimates; is_primary marks the one figure per (work, component)
      that rollups and ROI should use.
awards (work_id, award_body, year, category, result, recipient_person_id)      -- 21 rows
episodes (id, show_work_id, season_number, episode_number, title, air_date,
          runtime_minutes, director, writer, us_viewers_millions)              -- 50 rows
      Only rows carrying an episode number. The research also supplies 31
      "Season N summary" placeholders and the 1977 pilot TV movie (already its
      own media_works row); none are episodes and the build drops them.
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

--- Analysis views ---
v_character_appearances   work_characters resolved to character_identities
v_character_work          one row per (character, work), spellings collapsed
v_film_economics          lifetime gross vs primary production budget, + multiple
v_review_by_publication   review scores with the outlet split from the platform
```

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

Count characters with `v_character_work`, not `work_characters` — the latter
splits Spider-Man across 7 rows and Doctor Octopus across 4.

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
count is partly a measure of how thoroughly a work was catalogued, and totals are
**not comparable across media** — compare within a medium, or read the per-medium
split rather than the total. The build prints this table on every run.

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

### Reading `box_office`

Two different measurements share this table. 16 of the 17 films carry a single
**full-run total** that the research filed under `week_number = 1`; only
*Venom: The Last Dance* has a genuine week-by-week series. Reading every week-1
row as an opening week compares one film's lifetime gross against another film's
first seven days — the 2002 *Spider-Man* row alone would report a $403.7M
"opening week". `scope` disambiguates, and the build rejects any row without one.

### People enrichment

Birth/death dates and IMDb/Wikidata/TMDB ids come from TMDB, fetched by a separate
script so the build itself stays offline and deterministic:

```bash
export TMDB_TOKEN='<your TMDB v4 read access token>'
python3 fetch_tmdb_people.py          # writes data_raw/people_external.json
python3 build_db_v2.py                # reads that file, no network needed
```

`external_match_method` records how each person was identified:

- `work_credits` (351) — the name was found in the credit list of a film or series
  it is credited on in this dataset. Correct by construction.
- `search_verified` (16) — resolved by name search, then confirmed by checking that
  the person's TMDB credits actually include a franchise title.

A name search that returns exactly one person is *not* proof of identity: TMDB has
a 1885-born Edward J. Montagne (the father, not the 1977 producer) and one John
Digweed (the DJ). 90 such matches were rejected by the verification step rather
than stored. The 214 unresolved people are mostly game developers and composers,
whom TMDB does not index.

`nationality` is left NULL — TMDB has no nationality field, and birth place is not
a substitute for it.

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

## Files

| File | Description |
|------|-------------|
| `spiderman.db` | SQLite database (primary, normalized) |
| `build_db_v2.py` | Idempotent build script (rebuilds DB + CSVs, then validates) |
| `fetch_tmdb_people.py` | Optional network step: resolves `people` against TMDB |
| `build_db.py` | v1 legacy build script, superseded |
| `data_raw/people_external.json` | TMDB person data (367 people), consumed by the build |
| `data_raw/movies.json` | Researched movie data (23 films) |
| `data_raw/games.json` | Researched game data (43 games, per-platform releases) |
| `data_raw/tv.json` | Researched TV data (15 series, 82 episode rows) |
| `data/*.csv` | One CSV per table (24 CSVs) |
| `data/spiderman_all_media_flat.csv` | Denormalized single-row-per-work view (42 columns) |

Every research item in `data_raw/` resolves to exactly one work: 23/23 movies,
15/15 TV series, 43/43 games.

## Key Statistics

- **81 media works** across 13 franchises
- **23 movies** (live-action + animated, including SSU spin-offs)
- **15 TV shows** (4 live-action, 11 animated)
- **43 games** (from 1982 Atari 2600 to 2023's Marvel's Spider-Man 2)
- **264 distinct characters** across 416 credit strings, all with a normalized alignment
- **801 work-character links**, 203 of them carrying an actor
- **826 cast & crew entries** (actors, directors, writers, composers, designers)
- **286 studio work links** with role
- **270 review scores** across 30 works and 36 publications (128 raw source strings)
- **157 work-relation edges**
- **50 TV episodes** with air dates and metadata, over 5 of the 15 series
- **142 source material references** linking media to underlying comics
- **367 people** resolved to TMDB, with verified IMDb and Wikidata IDs

Coverage of works with at least one enrichment row:

| Table | Works covered |
|-------|---------------|
| `work_characters` | 81/81 (100%) |
| `work_studios` | 81/81 (100%) |
| `source_material` | 73/81 (90%) |
| `cast_crew` | 70/81 (86%) |
| `work_relations` | 68/81 (83%) |
| `review_scores` | 30/81 (37%) |

## Known Limitations

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
  because it is not an episode. (v3 loaded those 31 placeholders, which is why it
  reported 82 rows over 14 series.)
- **`review_scores`** — concentrated on games; most films and series have none.
- **Unreleased works** (*Beyond the Spider-Verse*, *Brand New Day*, *El Muerto*,
  *Spider-Noir*, *Marvel's Spider-Man 3*) carry announced credits only, and no
  review, budget or box office figures.

## Research Sources

Wikipedia (Spider-Man in film / television / video games articles),
Box Office Mojo, Rotten Tomatoes, Metacritic, IMDb.

Person records come from **The Movie Database (TMDB)**. This product uses the TMDB
API but is not endorsed or certified by TMDB.
