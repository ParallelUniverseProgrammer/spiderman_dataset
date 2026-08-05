#!/usr/bin/env python3
"""build_db_v4.py — build the v4 database: v2, plus v3's layer, plus v4's.

    python3 build_db_v4.py            # full rebuild
    python3 build_db_v4.py --check    # rebuild, then prove v2 + v3 compatibility

v4 is additive in the same sense v3 was, and against both of its predecessors.
It runs build_db_v2.py unchanged and hands it `v4_layer`, which applies
`v3_layer` first and then its own tables before the CSVs are written.

`--check` builds v2+v3 alone into a temporary directory and diffs it against the
v4 database: every v2 and v3 table must keep its columns in the same order,
every row either of them wrote must still be there with the same values (except
NULLs v4 filled), and all eight earlier views must still run.
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

from build_db_v3 import V2_TABLES, V3_TABLES, V2_VIEWS, dump_csv, run_build

HERE = Path(__file__).resolve().parent
DB = HERE / "spiderman.db"
DATA_DIR = HERE / "data"

V3_VIEWS = ["v_work_reception", "v_person_profile", "v_episode_guide",
            "v_work_identifiers"]

V4_TABLES = [
    "comics", "comic_creators", "comic_credits", "comic_characters",
    "work_source_comics", "character_debuts", "character_relations",
    "character_traits", "studio_details", "platform_details", "episode_credits",
    "v4_sources", "v4_provenance",
]

V4_VIEWS = ["v_work_comic_sources", "v_comic_creator_profile",
            "v_character_network", "v_character_dossier", "v_episode_credits"]

# Columns v4 is allowed to fill on a table an earlier version owns.
FILLABLE = {("studios", "country"), ("studios", "parent_company"),
            ("character_details", "publisher")}


def check_compat():
    """Build v2+v3 into a scratch copy and diff it against the v4 database."""
    problems = []
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        for name in ("build_db_v2.py", "v3_layer.py"):
            shutil.copy2(HERE / name, td / name)
        shutil.copytree(HERE / "data_raw", td / "data_raw",
                        ignore=shutil.ignore_patterns(".wd_cache", ".tmdb_cache", "v4"))
        (td / "data").mkdir(exist_ok=True)
        run_build({"SPIDERMAN_V3_LAYER": "v3_layer"}, cwd=td, script=td / "build_db_v2.py")
        if not (td / "spiderman.db").exists():
            return ["compatibility check: the scratch v2+v3 build produced no database"]
        base = sqlite3.connect(td / "spiderman.db")
        new = sqlite3.connect(DB)
        tables = V2_TABLES + V3_TABLES

        # 1. every earlier table keeps its columns, in order
        for t in tables:
            a = [r[1] for r in base.execute(f"PRAGMA table_info({t})")]
            b = [r[1] for r in new.execute(f"PRAGMA table_info({t})")]
            if a != b:
                problems.append(f"{t}: column list changed {a} -> {b}")

        # 2. every row they wrote survives, with the same values
        for t in tables:
            cols = [r[1] for r in base.execute(f"PRAGMA table_info({t})")]
            pk = [r[1] for r in base.execute(f"PRAGMA table_info({t})") if r[5]] or cols
            key = ",".join(pk)
            old_rows = {tuple(r[: len(pk)]): r for r in base.execute(
                f"SELECT {key}, {','.join(cols)} FROM {t}")}
            new_rows = {tuple(r[: len(pk)]): r for r in new.execute(
                f"SELECT {key}, {','.join(cols)} FROM {t}")}
            missing = set(old_rows) - set(new_rows)
            if missing:
                problems.append(
                    f"{t}: {len(missing)} earlier rows missing in v4, e.g. {list(missing)[:2]}")
            changed = 0
            for k, orow in old_rows.items():
                nrow = new_rows.get(k)
                if nrow is None:
                    continue
                for i, col in enumerate(cols, start=len(pk)):
                    if orow[i] != nrow[i] and orow[i] not in (None, ""):
                        changed += 1
                        if changed <= 2:
                            problems.append(
                                f"{t}.{col} changed for {k}: {orow[i]!r} -> {nrow[i]!r}")
            if changed > 2:
                problems.append(f"{t}: {changed} earlier values overwritten in total")

        # 3. v4 only filled columns it declared it would
        for t, col in new.execute(
                "SELECT table_name, row_key FROM v4_provenance WHERE action='fill'"):
            column = col.rsplit(":", 1)[-1]
            if t in tables and (t, column) not in FILLABLE:
                problems.append(f"v4 filled an undeclared column: {t}.{column}")

        # 4. every earlier view still runs
        for v in V2_VIEWS + V3_VIEWS:
            try:
                new.execute(f"SELECT * FROM {v} LIMIT 1").fetchone()
            except sqlite3.Error as e:
                problems.append(f"view {v} broken: {e}")

        # 5. the flat CSV keeps its column set
        with open(td / "data" / "spiderman_all_media_flat.csv", encoding="utf-8") as f:
            old_cols = next(csv.reader(f))
        with open(DATA_DIR / "spiderman_all_media_flat.csv", encoding="utf-8") as f:
            new_cols = next(csv.reader(f))
        if old_cols != new_cols:
            problems.append("flat CSV columns changed")

        base.close()
        new.close()
    return problems


def integrity(con):
    """FK orphans, enum violations and the invariants v4's own tables must hold."""
    problems = []
    fks = [
        ("comics", "series_id", "comics", "id", "series_id IS NOT NULL"),
        ("comic_credits", "comic_id", "comics", "id", None),
        ("comic_credits", "creator_id", "comic_creators", "id", None),
        ("comic_characters", "comic_id", "comics", "id", None),
        ("comic_characters", "identity_id", "character_identities", "id", None),
        ("comic_creators", "person_id", "people", "id", "person_id IS NOT NULL"),
        ("work_source_comics", "work_id", "media_works", "id", None),
        ("work_source_comics", "comic_id", "comics", "id", None),
        ("work_source_comics", "source_material_id", "source_material", "id", None),
        ("character_debuts", "identity_id", "character_identities", "id", None),
        ("character_debuts", "comic_id", "comics", "id", None),
        ("character_relations", "identity_id", "character_identities", "id", None),
        ("character_relations", "other_identity_id", "character_identities", "id",
         "other_identity_id IS NOT NULL"),
        ("character_traits", "identity_id", "character_identities", "id", None),
        ("studio_details", "studio_id", "studios", "id", None),
        ("platform_details", "platform_id", "platforms", "id", None),
        ("episode_credits", "episode_id", "episodes", "id", None),
        ("episode_credits", "person_id", "people", "id", "person_id IS NOT NULL"),
    ]
    for tbl, col, ref, refcol, cond in fks:
        where = f"WHERE {cond}" if cond else ""
        n = con.execute(
            f"SELECT COUNT(*) FROM {tbl} t {where} "
            f"{'AND' if cond else 'WHERE'} NOT EXISTS "
            f"(SELECT 1 FROM {ref} r WHERE r.{refcol} = t.{col})").fetchone()[0]
        if n:
            problems.append(f"{tbl}.{col}: {n} orphan rows")

    n = con.execute("SELECT COUNT(*) FROM comics WHERE origin='wikidata'"
                    " AND wikidata_id IS NULL").fetchone()[0]
    if n:
        problems.append(f"comics: {n} rows claim a Wikidata origin with no id")
    n = con.execute("SELECT COUNT(*) FROM comics WHERE origin='parsed'"
                    " AND (series_id IS NULL OR issue_number IS NULL)").fetchone()[0]
    if n:
        problems.append(f"comics: {n} parsed rows without a series and issue number")
    n = con.execute("SELECT COUNT(*) FROM comics WHERE kind='issue'"
                    " AND series_id = id").fetchone()[0]
    if n:
        problems.append(f"comics: {n} rows are their own series")
    n = con.execute("SELECT COUNT(*) FROM character_relations"
                    " WHERE identity_id = other_identity_id").fetchone()[0]
    if n:
        problems.append(f"character_relations: {n} self-edges")
    n = con.execute("SELECT COUNT(*) FROM comics WHERE publication_year IS NOT NULL"
                    " AND (publication_year < 1930 OR publication_year > 2030)").fetchone()[0]
    if n:
        problems.append(f"comics: {n} rows with an implausible publication year")

    # text columns must not carry scrape artifacts, same rule v2 and v3 enforce
    for t in V4_TABLES:
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
    def q(sql, *args):
        return con.execute(sql, args).fetchone()[0]

    print("\nComics layer:")
    n_wd = q("SELECT COUNT(*) FROM comics WHERE origin=?", "wikidata")
    n_parsed = q("SELECT COUNT(*) FROM comics WHERE origin=?", "parsed")
    print(f"  {'comics':25} {q('SELECT COUNT(*) FROM comics'):>5}"
          f"   ({n_wd} from Wikidata, {n_parsed} parsed from a citation)")
    for label, sql in [
        ("creators", "SELECT COUNT(*) FROM comic_creators"),
        ("  also screen-credited", "SELECT COUNT(*) FROM comic_creators WHERE person_id IS NOT NULL"),
        ("credits", "SELECT COUNT(*) FROM comic_credits"),
        ("comic-character links", "SELECT COUNT(*) FROM comic_characters"),
        ("works with a comic source",
         "SELECT COUNT(DISTINCT work_id) FROM work_source_comics"),
        ("source_material resolved",
         "SELECT COUNT(DISTINCT source_material_id) FROM work_source_comics"),
        ("character debuts", "SELECT COUNT(*) FROM character_debuts"),
    ]:
        print(f"  {label:25} {q(sql):>5}")

    print("\nCharacter graph:")
    for label, sql in [
        ("relations", "SELECT COUNT(*) FROM character_relations"),
        ("  both ends in dataset",
         "SELECT COUNT(*) FROM character_relations WHERE other_identity_id IS NOT NULL"),
        ("identities with an edge",
         "SELECT COUNT(DISTINCT identity_id) FROM character_relations"),
        ("traits", "SELECT COUNT(*) FROM character_traits"),
        ("identities with a trait",
         "SELECT COUNT(DISTINCT identity_id) FROM character_traits"),
        ("items shared by 2+ identities",
         "SELECT COUNT(*) FROM (SELECT identifier FROM external_ids"
         " WHERE entity_type='character' AND source='wikidata'"
         " GROUP BY identifier HAVING COUNT(*) > 1)"),
    ]:
        print(f"  {label:25} {q(sql):>5}")

    print("\nDimensions filled:")
    for label, sql in [
        ("studios with a country", "SELECT COUNT(country) FROM studios"),
        ("studios with a parent", "SELECT COUNT(parent_company) FROM studios"),
        ("studio_details", "SELECT COUNT(*) FROM studio_details"),
        ("platform_details", "SELECT COUNT(*) FROM platform_details"),
        ("character publisher", "SELECT COUNT(publisher) FROM character_details"),
        ("episode credits", "SELECT COUNT(*) FROM episode_credits"),
        ("  matched to a person",
         "SELECT COUNT(*) FROM episode_credits WHERE person_id IS NOT NULL"),
        ("episodes with a credit",
         "SELECT COUNT(DISTINCT episode_id) FROM episode_credits"),
    ]:
        print(f"  {label:25} {q(sql):>5}")

    print("\nRows added by v4, by table:")
    for t, n in con.execute(
            "SELECT table_name, COUNT(*) FROM v4_provenance WHERE action='insert'"
            " GROUP BY table_name ORDER BY COUNT(*) DESC"):
        print(f"  {t:24} {n:>5}")
    n_fill = con.execute(
        "SELECT COUNT(*) FROM v4_provenance WHERE action='fill'").fetchone()[0]
    print(f"  ({n_fill} NULL columns filled on existing rows)")

    empty = []
    for t in V4_TABLES:
        for col in con.execute(f"PRAGMA table_info([{t}])"):
            n = con.execute(f"SELECT COUNT([{col[1]}]) FROM [{t}]").fetchone()[0]
            if n == 0 and con.execute(f"SELECT COUNT(*) FROM [{t}]").fetchone()[0]:
                empty.append(f"{t}.{col[1]}")
    if empty:
        print(f"\nFully-NULL v4 columns ({len(empty)}): {', '.join(empty)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="also diff against a v2+v3 build to prove compatibility")
    args = ap.parse_args()

    print("Building v2 base + v3 layer + v4 layer ...")
    out = run_build({"SPIDERMAN_V3_LAYER": "v4_layer"})
    for line in out.splitlines():
        if "layer" in line or line.startswith("      ") or "Validation" in line:
            print(line)

    con = sqlite3.connect(DB)

    print("\nExporting v4 tables to CSV:")
    for t in V4_TABLES:
        n = dump_csv(con, t, DATA_DIR / f"{t}.csv")
        print(f"  {t:24} {n:>6} rows")

    problems = integrity(con)
    for v in V4_VIEWS:
        try:
            con.execute(f"SELECT * FROM {v} LIMIT 1").fetchone()
        except sqlite3.Error as e:
            problems.append(f"view {v} broken: {e}")

    if args.check:
        print("\nChecking v2 + v3 compatibility (building them alone for comparison) ...")
        problems += check_compat()

    report(con)

    print()
    if problems:
        print("VALIDATION FAILURES:")
        for p in problems:
            print(f"  x {p}")
        con.close()
        sys.exit(1)
    print("Validation: v4 integrity checks passed."
          + (" v2 + v3 compatibility verified." if args.check else ""))
    con.close()


if __name__ == "__main__":
    main()
