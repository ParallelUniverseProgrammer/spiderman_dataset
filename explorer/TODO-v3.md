# TODO: forward-port the explorer to v3

The explorer still reads the database through v2 eyes. Nothing is broken — v3 is
additive, `build_explorer_data.py` runs unchanged, and every view already shows
more than it did (56 works have review scores instead of 30, 15 series have
episode guides instead of 5). But the v3 tables are simply not read yet, so a
good deal of what is now in `spiderman.db` never reaches the page.

Do this at the earliest convenient time.

## What the exporter already picks up for free

`build_explorer_data.py` selects `*` from the v2 tables, so these arrived with no
work: the extra `review_scores`, `episodes` and `awards` rows, and the newly
filled `people.birth_date` / `birth_place` / `imdb_id` / `wikidata_id` /
`tmdb_id` and `character_identities.first_comic_title` / `first_comic_year`.

## What is in the database but not in `data.json`

| v3 table | rows | what the page could do with it |
|---|---|---|
| `work_summaries` | 79 | a paragraph of prose on every work detail page — the explorer has never had any |
| `external_ids` | 5,998 | outbound links (IMDb, Rotten Tomatoes, Metacritic, TMDB, Letterboxd, Steam) on work, person and character pages |
| `work_genres` / `work_countries` / `work_languages` | 308 | new filter facets on the Works table, and a genre dimension page alongside Franchises/Studios/Platforms |
| `person_occupations` / `person_citizenships` | 2,268 | a role mix and a nationality facet on People; `people.nationality` is now populated for 382 of 581, and the exporter does not currently emit that column at all |
| `person_details` | 421 | gender, birth name, active period on the person page |
| `person_awards` | 1,022 | an awards strip on the person page, including awards for work outside this dataset |
| `character_details` | 182 | creators, narrative universe and first appearance on the character page |
| `work_content_ratings` / `work_release_dates` / `work_places` | 327 | certificate badges, a territory-by-territory release timeline, a filming/narrative location map |
| `box_office_regions` | 9 | per-territory gross next to the existing domestic/worldwide split |
| `episode_segments` | 324 | both segment titles for the shows that air two shorts per slot (1967 series, *Spidey and His Amazing Friends*) |
| `v3_provenance` | 12,534 | an honest "where did this come from" affordance on About the data |

Four new views are also available and may be easier than joining by hand:
`v_work_reception`, `v_person_profile`, `v_episode_guide`, `v_work_identifiers`.

## Two things to be careful about

- **`data.json` size.** It is 537 KB today and the page loads all of it up front.
  The summaries and external ids alone would push it past a megabyte. Consider
  splitting the per-entity detail into a second file fetched on demand, or
  dropping `v3_provenance` from the export entirely — it is an audit trail, not
  something a reader needs in the browser.
- **`prune()` drops empty values**, so a v3 field that is absent for a given
  entity will be missing from the object rather than null. The existing views
  already handle this (three works have no `year` key), but new code reading v3
  fields must not assume the key is present.

## Also worth revisiting

`explorer/smoke-test.html` was not run against this build — the environment had
no browser. It should be opened and confirmed green before the next release, and
extended to cover whatever v3 views get added.
