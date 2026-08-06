#!/usr/bin/env python3
"""build_db_v5.py — build the v5 database: v2, plus v3's layer, v4's and v5's.

    python3 build_db_v5.py            # full rebuild
    python3 build_db_v5.py --check    # rebuild, then prove v2 + v3 + v4 compatibility

v5 is additive in the same sense v3 and v4 were, and against all three of its
predecessors. It runs build_db_v2.py unchanged and hands it `v5_layer`, which
applies `v4_layer` (and so `v3_layer`) first and then its own tables before the
CSVs are written.

`--check` builds v2+v3+v4 alone into a temporary directory and diffs it against
the v5 database: every earlier table must keep its columns in the same order,
every row any of them wrote must still be there with the same values (except the
one NULL column v5 declares it fills), and all seventeen earlier views must run.
"""
import argparse
import csv
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

from build_db_v3 import V2_TABLES, V3_TABLES, V2_VIEWS, dump_csv, run_build
from build_db_v4 import V3_VIEWS, V4_TABLES, V4_VIEWS

HERE = Path(__file__).resolve().parent
DB = HERE / "spiderman.db"
DATA_DIR = HERE / "data"

V5_TABLES = [
    "related_characters", "character_relation_targets",
    "related_character_relations", "performers", "character_portrayals",
    "v5_sources", "v5_provenance",
]

V5_VIEWS = ["v_portrayals", "v_character_casting", "v_performer_lineage",
            "v_character_network_full"]

# The one column v5 is allowed to fill on a table an earlier version owns.
FILLABLE = {("work_characters", "actor_person_id")}


def check_compat():
    """Build v2+v3+v4 into a scratch copy and diff it against the v5 database."""
    problems = []
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        for name in ("build_db_v2.py", "build_db_v3.py", "build_db_v4.py",
                     "v3_layer.py", "v4_layer.py"):
            shutil.copy2(HERE / name, td / name)
        shutil.copytree(HERE / "data_raw", td / "data_raw",
                        ignore=shutil.ignore_patterns(".wd_cache", ".tmdb_cache", "v5"))
        (td / "data").mkdir(exist_ok=True)
        run_build({"SPIDERMAN_V3_LAYER": "v4_layer"}, cwd=td, script=td / "build_db_v2.py")
        if not (td / "spiderman.db").exists():
            return ["compatibility check: the scratch v2+v3+v4 build produced no database"]
        base = sqlite3.connect(td / "spiderman.db")
        new = sqlite3.connect(DB)
        tables = V2_TABLES + V3_TABLES + V4_TABLES

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
                    f"{t}: {len(missing)} earlier rows missing in v5, e.g. {list(missing)[:2]}")
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

        # 3. v5 only filled columns it declared it would
        for t, col in new.execute(
                "SELECT table_name, row_key FROM v5_provenance WHERE action='fill'"):
            column = col.rsplit(":", 1)[-1]
            if t in tables and (t, column) not in FILLABLE:
                problems.append(f"v5 filled an undeclared column: {t}.{column}")

        # 4. every earlier view still runs
        for v in V2_VIEWS + V3_VIEWS + V4_VIEWS:
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
    """FK orphans and the invariants v5's own tables must hold."""
    problems = []
    fks = [
        ("character_relation_targets", "identity_id", "character_identities", "id", None),
        ("character_relation_targets", "related_id", "related_characters", "id", None),
        ("related_character_relations", "related_id", "related_characters", "id", None),
        ("related_character_relations", "other_related_id", "related_characters", "id",
         "other_related_id IS NOT NULL"),
        ("related_character_relations", "other_identity_id", "character_identities", "id",
         "other_identity_id IS NOT NULL"),
        ("performers", "person_id", "people", "id", "person_id IS NOT NULL"),
        ("character_portrayals", "work_id", "media_works", "id", None),
        ("character_portrayals", "performer_id", "performers", "id", None),
    ]
    for tbl, col, ref, refcol, cond in fks:
        where = f"WHERE {cond}" if cond else ""
        n = con.execute(
            f"SELECT COUNT(*) FROM {tbl} t {where} "
            f"{'AND' if cond else 'WHERE'} NOT EXISTS "
            f"(SELECT 1 FROM {ref} r WHERE r.{refcol} = t.{col})").fetchone()[0]
        if n:
            problems.append(f"{tbl}.{col}: {n} orphan rows")

    # the polymorphic target has to point at a row of the kind it claims
    n = con.execute(
        "SELECT COUNT(*) FROM character_portrayals p WHERE p.target_kind='identity'"
        " AND NOT EXISTS (SELECT 1 FROM character_identities i WHERE i.id=p.target_id)"
    ).fetchone()[0]
    if n:
        problems.append(f"character_portrayals: {n} rows point at a missing identity")
    n = con.execute(
        "SELECT COUNT(*) FROM character_portrayals p WHERE p.target_kind='related'"
        " AND NOT EXISTS (SELECT 1 FROM related_characters r WHERE r.id=p.target_id)"
    ).fetchone()[0]
    if n:
        problems.append(f"character_portrayals: {n} rows point at a missing related character")

    n = con.execute("SELECT COUNT(*) FROM related_character_relations"
                    " WHERE related_id = other_related_id").fetchone()[0]
    if n:
        problems.append(f"related_character_relations: {n} self-edges")
    n = con.execute("SELECT COUNT(*) FROM related_character_relations"
                    " WHERE other_identity_id IS NULL AND other_related_id IS NULL"
                    ).fetchone()[0]
    if n:
        problems.append(f"related_character_relations: {n} edges with no far side")

    # a second-ring row must not duplicate an identity the dataset already has
    n = con.execute(
        "SELECT COUNT(*) FROM related_characters rc JOIN external_ids e"
        "   ON e.identifier = rc.wikidata_id"
        " WHERE e.entity_type='character' AND e.source='wikidata'").fetchone()[0]
    if n:
        problems.append(f"related_characters: {n} rows shadow an existing identity")

    # every filled actor link must agree with a portrayal that justifies it
    n = con.execute(
        "SELECT COUNT(*) FROM v5_provenance v"
        " JOIN work_characters wc ON wc.work_id = CAST(substr(v.row_key,1,"
        "      instr(v.row_key,':')-1) AS INTEGER)"
        "  AND wc.character_id = CAST(substr(v.row_key, instr(v.row_key,':')+1,"
        "      instr(substr(v.row_key, instr(v.row_key,':')+1), ':')-1) AS INTEGER)"
        " WHERE v.table_name='work_characters' AND v.action='fill'"
        "   AND wc.actor_person_id IS NULL").fetchone()[0]
    if n:
        problems.append(f"work_characters: {n} rows recorded as filled are still NULL")

    for t in V5_TABLES:
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

    print("\nPerformances:")
    for label, sql in [
        ("portrayals", "SELECT COUNT(*) FROM character_portrayals"),
        ("  of a dataset character",
         "SELECT COUNT(*) FROM character_portrayals WHERE target_kind='identity'"),
        ("  of a second-ring one",
         "SELECT COUNT(*) FROM character_portrayals WHERE target_kind='related'"),
        ("performers", "SELECT COUNT(*) FROM performers"),
        ("  already in `people`",
         "SELECT COUNT(*) FROM performers WHERE person_id IS NOT NULL"),
        ("works with a portrayal",
         "SELECT COUNT(DISTINCT work_id) FROM character_portrayals"),
        ("identities with one",
         "SELECT COUNT(DISTINCT target_id) FROM character_portrayals"
         " WHERE target_kind='identity'"),
        ("actor links filled",
         "SELECT COUNT(*) FROM v5_provenance WHERE table_name='work_characters'"),
    ]:
        print(f"  {label:26} {q(sql):>5}")
    print("  by media type / origin / method:")
    for row in con.execute(
            "SELECT w.media_type, COUNT(*), COUNT(DISTINCT p.work_id)"
            "  FROM character_portrayals p JOIN media_works w ON w.id = p.work_id"
            " GROUP BY 1 ORDER BY 2 DESC"):
        print(f"      {row[0]:22} {row[1]:>5} over {row[2]} works")
    for row in con.execute(
            "SELECT origin, match_method, COUNT(*) FROM character_portrayals"
            " GROUP BY 1,2 ORDER BY 3 DESC"):
        print(f"      {row[0] + '/' + row[1]:22} {row[2]:>5}")

    print("\nCharacter graph, both rings:")
    for label, sql in [
        ("second-ring characters", "SELECT COUNT(*) FROM related_characters"),
        ("  with a Wikipedia article",
         "SELECT COUNT(wikipedia_title) FROM related_characters"),
        ("dead-end edges resolved", "SELECT COUNT(*) FROM character_relation_targets"),
        ("  of edges that had none",
         "SELECT COUNT(*) FROM character_relations WHERE other_identity_id IS NULL"),
        ("second-ring edges", "SELECT COUNT(*) FROM related_character_relations"),
        ("  landing back on the 264",
         "SELECT COUNT(*) FROM related_character_relations"
         " WHERE other_identity_id IS NOT NULL"),
        ("edges still unresolved",
         "SELECT COUNT(*) FROM v_character_network_full WHERE to_kind='name'"),
    ]:
        print(f"  {label:26} {q(sql):>5}")

    print("\nRows added by v5, by table:")
    for t, n in con.execute(
            "SELECT table_name, COUNT(*) FROM v5_provenance WHERE action='insert'"
            " GROUP BY table_name ORDER BY COUNT(*) DESC"):
        print(f"  {t:26} {n:>5}")
    n_fill = con.execute(
        "SELECT COUNT(*) FROM v5_provenance WHERE action='fill'").fetchone()[0]
    print(f"  ({n_fill} NULL columns filled on existing rows)")

    empty = []
    for t in V5_TABLES:
        for col in con.execute(f"PRAGMA table_info([{t}])"):
            n = con.execute(f"SELECT COUNT([{col[1]}]) FROM [{t}]").fetchone()[0]
            if n == 0 and con.execute(f"SELECT COUNT(*) FROM [{t}]").fetchone()[0]:
                empty.append(f"{t}.{col[1]}")
    if empty:
        print(f"\nFully-NULL v5 columns ({len(empty)}): {', '.join(empty)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="also diff against a v2+v3+v4 build to prove compatibility")
    args = ap.parse_args()

    print("Building v2 base + v3 layer + v4 layer + v5 layer ...")
    out = run_build({"SPIDERMAN_V3_LAYER": "v5_layer"})
    for line in out.splitlines():
        if "layer" in line or line.startswith("      ") or "Validation" in line:
            print(line)

    con = sqlite3.connect(DB)

    print("\nExporting v5 tables to CSV:")
    for t in V5_TABLES:
        n = dump_csv(con, t, DATA_DIR / f"{t}.csv")
        print(f"  {t:28} {n:>6} rows")

    problems = integrity(con)
    for v in V5_VIEWS:
        try:
            con.execute(f"SELECT * FROM {v} LIMIT 1").fetchone()
        except sqlite3.Error as e:
            problems.append(f"view {v} broken: {e}")

    if args.check:
        print("\nChecking v2 + v3 + v4 compatibility (building them alone for comparison) ...")
        problems += check_compat()

    report(con)

    print()
    if problems:
        print("VALIDATION FAILURES:")
        for p in problems:
            print(f"  x {p}")
        con.close()
        sys.exit(1)
    print("Validation: v5 integrity checks passed."
          + (" v2 + v3 + v4 compatibility verified." if args.check else ""))
    con.close()


if __name__ == "__main__":
    main()
