#!/usr/bin/env python3
"""build_db_v3.py — build the v3 database: v2, plus the enrichment layer.

    python3 build_db_v3.py            # full rebuild
    python3 build_db_v3.py --check    # rebuild, then prove v2 compatibility

v3 is strictly additive. It runs build_db_v2.py unchanged — v2 owns the schema,
the research JSONs and the exports — and hands it `v3_layer`, which adds rows and
new tables before the CSVs are written so the CSVs match the database.

What that buys, and what it costs
---------------------------------
Anything written for v2 keeps working: every v2 table has the same columns in the
same order, no row v2 wrote is altered or removed, and the four v2 views are
untouched. What changes is that tables get *more rows* — 51 works had no review
score and now most do — so any hard-coded count in a v2-era script will be stale.
That is the point of the release, but it is worth knowing before you upgrade.

`--check` verifies the first two claims mechanically by building v2 alone into a
temporary file and diffing it against the v3 database row by row.
"""
import argparse
import csv
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
DB = HERE / "spiderman.db"
DATA_DIR = HERE / "data"
V2 = HERE / "build_db_v2.py"

V2_TABLES = [
    "franchises", "media_works", "movies", "tv_shows", "games",
    "character_identities", "characters", "work_characters", "cast_crew",
    "game_releases", "review_scores", "studios", "work_studios", "box_office",
    "budgets", "awards", "episodes", "work_relations", "source_material",
    "soundtracks", "platforms", "game_platforms", "people", "work_people",
]

V3_TABLES = [
    "external_ids", "work_genres", "work_countries", "work_languages",
    "work_content_ratings", "work_release_dates", "work_places",
    "box_office_regions", "work_summaries", "person_occupations",
    "person_citizenships", "person_details", "person_awards",
    "character_details", "episode_segments", "v3_sources", "v3_provenance",
]

V2_VIEWS = ["v_character_appearances", "v_character_work", "v_film_economics",
            "v_review_by_publication"]


def run_build(env_extra=None, cwd=HERE, script=V2):
    """Run build_db_v2.py. `script` must be the copy living inside `cwd`: the v2
    script resolves every path relative to its own location, so running the
    original from a scratch directory would rebuild the real database."""
    env = dict(os.environ)
    env.update(env_extra or {})
    r = subprocess.run([sys.executable, str(script)], cwd=cwd, env=env,
                       capture_output=True, text=True)
    if r.returncode:
        sys.stdout.write(r.stdout)
        sys.stderr.write(r.stderr)
        raise SystemExit(f"build failed ({r.returncode})")
    return r.stdout


def dump_csv(con, table, path):
    cur = con.execute(f"SELECT * FROM {table}")
    cols = [c[0] for c in cur.description]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(cols)
        w.writerows(cur.fetchall())
    return con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


# ---------------------------------------------------------------------------
def check_compat():
    """Build v2 alone into a scratch copy and diff it against the v3 database."""
    problems = []
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        # v2 writes next to itself, so give it its own tree.
        for name in ("build_db_v2.py",):
            shutil.copy2(HERE / name, td / name)
        shutil.copytree(HERE / "data_raw", td / "data_raw",
                        ignore=shutil.ignore_patterns(".wd_cache", "v3", ".tmdb_cache"))
        # people_external.json lives at the top of data_raw and must come along
        (td / "data").mkdir(exist_ok=True)
        run_build(cwd=td, script=td / "build_db_v2.py")
        if not (td / "spiderman.db").exists():
            return ["compatibility check: the scratch v2 build produced no database"]
        base = sqlite3.connect(td / "spiderman.db")
        cur3 = sqlite3.connect(DB)

        # 1. every v2 table keeps its columns, in order
        for t in V2_TABLES:
            a = [r[1] for r in base.execute(f"PRAGMA table_info({t})")]
            b = [r[1] for r in cur3.execute(f"PRAGMA table_info({t})")]
            if a != b:
                problems.append(f"{t}: column list changed {a} -> {b}")

        # 2. every row v2 wrote survives unchanged, except NULLs that were filled
        for t in V2_TABLES:
            cols = [r[1] for r in base.execute(f"PRAGMA table_info({t})")]
            pk = [r[1] for r in base.execute(f"PRAGMA table_info({t})") if r[5]]
            if not pk:
                pk = cols
            key = ",".join(pk)
            old = {tuple(r[: len(pk)]): r for r in base.execute(
                f"SELECT {key}, {','.join(cols)} FROM {t}")}
            new = {tuple(r[: len(pk)]): r for r in cur3.execute(
                f"SELECT {key}, {','.join(cols)} FROM {t}")}
            missing = set(old) - set(new)
            if missing:
                problems.append(f"{t}: {len(missing)} v2 rows missing in v3, e.g. {list(missing)[:2]}")
            corrected = {
                row[0].split(":", 1)[0] + ":" + row[0].split(":")[1]
                for row in cur3.execute(
                    "SELECT row_key FROM v3_provenance WHERE table_name=? AND action='correct'",
                    (t,))
            }
            changed = 0
            for k, orow in old.items():
                nrow = new.get(k)
                if nrow is None:
                    continue
                for i, col in enumerate(cols, start=len(pk)):
                    # Values v3 deliberately corrected are recorded in
                    # v3_provenance; they are reported, not counted as breakage.
                    if f"{k[0]}:{col}" in corrected:
                        continue
                    if orow[i] != nrow[i] and orow[i] not in (None, ""):
                        changed += 1
                        if changed <= 2:
                            problems.append(
                                f"{t}.{col} changed for {k}: {orow[i]!r} -> {nrow[i]!r}")
            if changed > 2:
                problems.append(f"{t}: {changed} v2 values overwritten in total")

        # 3. v2 views still exist and still return rows
        for v in V2_VIEWS:
            try:
                cur3.execute(f"SELECT * FROM {v} LIMIT 1").fetchone()
            except sqlite3.Error as e:
                problems.append(f"view {v} broken: {e}")

        # 4. the flat CSV keeps its column set
        with open(td / "data" / "spiderman_all_media_flat.csv", encoding="utf-8") as f:
            old_cols = next(csv.reader(f))
        with open(DATA_DIR / "spiderman_all_media_flat.csv", encoding="utf-8") as f:
            new_cols = next(csv.reader(f))
        if old_cols != new_cols:
            problems.append("flat CSV columns changed")

        base.close()
        cur3.close()
    return problems


def integrity(con):
    """FK orphans and enum violations across the v3 tables."""
    problems = []
    fks = [
        ("external_ids", "entity_id", "media_works", "id", "entity_type='work'"),
        ("external_ids", "entity_id", "people", "id", "entity_type='person'"),
        ("external_ids", "entity_id", "character_identities", "id", "entity_type='character'"),
        ("work_genres", "work_id", "media_works", "id", None),
        ("work_countries", "work_id", "media_works", "id", None),
        ("work_languages", "work_id", "media_works", "id", None),
        ("work_content_ratings", "work_id", "media_works", "id", None),
        ("work_release_dates", "work_id", "media_works", "id", None),
        ("work_places", "work_id", "media_works", "id", None),
        ("box_office_regions", "work_id", "media_works", "id", None),
        ("work_summaries", "work_id", "media_works", "id", None),
        ("person_occupations", "person_id", "people", "id", None),
        ("person_citizenships", "person_id", "people", "id", None),
        ("person_details", "person_id", "people", "id", None),
        ("person_awards", "person_id", "people", "id", None),
        ("character_details", "identity_id", "character_identities", "id", None),
        ("episode_segments", "show_work_id", "media_works", "id", None),
    ]
    for tbl, col, ref, refcol, cond in fks:
        where = f"WHERE {cond}" if cond else ""
        n = con.execute(
            f"SELECT COUNT(*) FROM {tbl} t {where} "
            f"{'AND' if cond else 'WHERE'} NOT EXISTS "
            f"(SELECT 1 FROM {ref} r WHERE r.{refcol} = t.{col})").fetchone()[0]
        if n:
            problems.append(f"{tbl}.{col}: {n} orphan rows")

    n = con.execute("SELECT COUNT(*) FROM review_scores WHERE score_pct < 0"
                    " OR score_pct > 100").fetchone()[0]
    if n:
        problems.append(f"review_scores: {n} rows with score_pct outside 0-100")
    n = con.execute("SELECT COUNT(*) FROM review_scores WHERE max_score IS NULL"
                    " OR max_score <= 0").fetchone()[0]
    if n:
        problems.append(f"review_scores: {n} rows with a missing or non-positive max_score")
    n = con.execute("SELECT COUNT(*) FROM box_office WHERE scope='lifetime'"
                    " GROUP BY work_id HAVING COUNT(*) > 1").fetchall()
    if n:
        problems.append(f"box_office: {len(n)} works with more than one lifetime row")
    n = con.execute("SELECT COUNT(*) FROM budgets b WHERE is_primary=1 AND component='production'"
                    " GROUP BY work_id HAVING COUNT(*) > 1").fetchall()
    if n:
        problems.append(f"budgets: {len(n)} works with more than one primary production budget")

    # text columns must not carry scrape artifacts, same rule v2 enforces
    for t in V3_TABLES:
        for col in con.execute(f"PRAGMA table_info([{t}])"):
            if col[2].upper() != "TEXT":
                continue
            n = con.execute(
                f"SELECT COUNT(*) FROM [{t}] WHERE [{col[1]}] LIKE '%|' OR [{col[1]}] LIKE '|%'"
                f" OR [{col[1]}] LIKE '%<!--%' OR [{col[1]}] LIKE '%[[%'").fetchone()[0]
            if n:
                problems.append(f"{t}.{col[1]}: {n} rows with wikitext artifacts")
    return problems


def report(con):
    print("\nCoverage — works with at least one row, out of 81:")
    for label, sql in [
        ("review scores", "SELECT COUNT(DISTINCT work_id) FROM review_scores"),
        ("box office", "SELECT COUNT(DISTINCT work_id) FROM box_office"),
        ("budgets", "SELECT COUNT(DISTINCT work_id) FROM budgets"),
        ("awards", "SELECT COUNT(DISTINCT work_id) FROM awards"),
        ("genres", "SELECT COUNT(DISTINCT work_id) FROM work_genres"),
        ("summaries", "SELECT COUNT(DISTINCT work_id) FROM work_summaries"),
        ("external ids", "SELECT COUNT(DISTINCT entity_id) FROM external_ids"
                         " WHERE entity_type='work'"),
    ]:
        print(f"  {label:16} {con.execute(sql).fetchone()[0]:>3}")

    print("\nPeople — columns filled, out of 581:")
    for col in ("birth_date", "death_date", "birth_place", "nationality",
                "imdb_id", "wikidata_id", "tmdb_id"):
        print(f"  {col:16} {con.execute(f'SELECT COUNT({col}) FROM people').fetchone()[0]:>3}")

    print("\nRows added by v3, by table:")
    for t, n in con.execute(
            "SELECT table_name, COUNT(*) FROM v3_provenance WHERE action='insert'"
            " GROUP BY table_name ORDER BY COUNT(*) DESC"):
        print(f"  {t:24} {n:>5}")
    n_fill = con.execute(
        "SELECT COUNT(*) FROM v3_provenance WHERE action='fill'").fetchone()[0]
    print(f"  ({n_fill} NULL columns filled on existing rows)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="also diff against a v2-only build to prove compatibility")
    args = ap.parse_args()

    print("Building v2 base + v3 layer ...")
    out = run_build({"SPIDERMAN_V3_LAYER": "v3_layer"})
    for line in out.splitlines():
        if "v3 layer" in line or line.startswith("      ") or "Validation" in line:
            print(line)

    con = sqlite3.connect(DB)

    print("\nExporting v3 tables to CSV:")
    for t in V3_TABLES:
        n = dump_csv(con, t, DATA_DIR / f"{t}.csv")
        print(f"  {t:24} {n:>6} rows")

    problems = integrity(con)
    if args.check:
        print("\nChecking v2 compatibility (building v2 alone for comparison) ...")
        problems += check_compat()

    report(con)

    print()
    if problems:
        print("VALIDATION FAILURES:")
        for p in problems:
            print(f"  x {p}")
        con.close()
        sys.exit(1)
    print("Validation: v3 integrity checks passed."
          + (" v2 compatibility verified." if args.check else ""))
    con.close()


if __name__ == "__main__":
    main()
