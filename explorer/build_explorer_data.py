#!/usr/bin/env python3
"""Export spiderman.db into explorer/data.json (+ data.js for file:// use)."""
import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = Path(__file__).resolve().parent
DB = ROOT / "spiderman.db"


def rows(con, sql, params=()):
    cur = con.execute(sql, params)
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def prune(d):
    if isinstance(d, dict):
        return {k: prune(v) for k, v in d.items() if v not in (None, "", [], {})}
    if isinstance(d, list):
        return [prune(x) for x in d]
    return d


def main():
    con = sqlite3.connect(DB)

    franchises = {f["id"]: f for f in rows(con, "SELECT * FROM franchises")}
    studios = {s["id"]: s for s in rows(con, "SELECT * FROM studios")}
    platforms = {p["id"]: p["name"] for p in rows(con, "SELECT * FROM platforms")}
    char_rows = {c["id"]: c for c in rows(con, "SELECT * FROM characters")}

    works = {}
    for w in rows(con, "SELECT * FROM media_works ORDER BY release_year, id"):
        fr = franchises.get(w["franchise_id"])
        works[w["id"]] = {
            "id": w["id"],
            "title": w["title"],
            "year": w["release_year"],
            "date": w["release_date"],
            "type": w["media_type"],
            "franchise": fr["name"] if fr else None,
            "notes": w["notes"],
            "studios": [], "cast": [], "crew": [], "characters": [],
            "reviews": [], "awards": [], "soundtracks": [], "sources": [],
            "relations": [], "episodes": [], "game_releases": [], "platforms": [],
        }

    for m in rows(con, "SELECT * FROM movies"):
        works[m.pop("work_id")]["movie"] = m
    for t in rows(con, "SELECT * FROM tv_shows"):
        works[t.pop("work_id")]["tv"] = t
    for g in rows(con, "SELECT * FROM games"):
        works[g.pop("work_id")]["game"] = g

    for ws in rows(con, "SELECT * FROM work_studios"):
        s = studios[ws["studio_id"]]
        works[ws["work_id"]]["studios"].append(
            {"name": s["name"], "role": ws["role"], "country": s["country"],
             "parent": s["parent_company"]})

    for gp in rows(con, "SELECT * FROM game_platforms"):
        works[gp["game_id"]]["platforms"].append(platforms[gp["platform_id"]])
    for gr in rows(con, "SELECT * FROM game_releases ORDER BY release_date"):
        works[gr["game_work_id"]]["game_releases"].append({
            "platform": platforms.get(gr["platform_id"]),
            "date": gr["release_date"], "publisher": gr["publisher"],
            "developer": gr["developer"], "metacritic": gr["metacritic_score"],
            "esrb": gr["esrb_rating"]})

    for b in rows(con, "SELECT * FROM budgets ORDER BY is_primary DESC, amount_usd DESC"):
        w = works[b["work_id"]]
        w.setdefault("budgets", []).append({
            "amount": b["amount_usd"], "component": b["component"],
            "primary": bool(b["is_primary"]), "source_year": b["source_year"],
            "inflation_adj_2024": b["inflation_adj_2024"], "note": b["note"]})
        if b["is_primary"] and b["component"] == "production":
            w["budget_usd"] = b["amount_usd"]
    for bo in rows(con, "SELECT * FROM box_office WHERE scope='lifetime'"):
        works[bo["work_id"]]["box_office"] = {
            "domestic": bo["domestic_usd"], "international": bo["international_usd"],
            "worldwide": bo["worldwide_usd"]}
    # Weekly rows are a different measurement from the lifetime totals and are kept
    # separate — see "Reading box_office" in the README.
    for bo in rows(con, "SELECT * FROM box_office WHERE scope='week' ORDER BY week_number"):
        works[bo["work_id"]].setdefault("weekly", []).append({
            "week": bo["week_number"], "start": bo["week_start_date"],
            "domestic": bo["domestic_usd"], "international": bo["international_usd"],
            "worldwide": bo["worldwide_usd"]})

    for r in rows(con, "SELECT * FROM review_scores ORDER BY score_pct DESC"):
        works[r["work_id"]]["reviews"].append({
            "source": r["source"], "publication": r["publication"],
            "scope": r["platform_scope"], "score": r["score"],
            "max": r["max_score"], "pct": r["score_pct"], "count": r["review_count"]})

    for a in rows(con, "SELECT * FROM awards ORDER BY year"):
        works[a["work_id"]]["awards"].append({
            "body": a["award_body"], "year": a["year"], "category": a["category"],
            "result": a["result"], "person_id": a["recipient_person_id"]})

    for s in rows(con, "SELECT * FROM soundtracks"):
        works[s["work_id"]]["soundtracks"].append({
            "type": s["type"], "title": s["title"], "by": s["composer_or_performer"],
            "date": s["release_date"], "peak_us": s["chart_peak_us"],
            "peak_uk": s["chart_peak_uk"]})

    for s in rows(con, "SELECT * FROM source_material"):
        works[s["work_id"]]["sources"].append({
            "comic": s["comic_title"], "issues": s["issue_range"],
            "writer": s["comic_writer"], "year": s["comic_year"],
            "arc": s["storyline_arc"]})

    for e in rows(con, "SELECT * FROM episodes ORDER BY season_number, episode_number"):
        works[e["show_work_id"]]["episodes"].append({
            "season": e["season_number"], "episode": e["episode_number"],
            "title": e["title"], "air_date": e["air_date"],
            "runtime": e["runtime_minutes"], "director": e["director"],
            "writer": e["writer"], "viewers_m": e["us_viewers_millions"]})

    # (A, sequel, B) means B follows A; (A, prequel, B) means B precedes A.
    REL_LABELS = {
        "sequel": ("Followed by", "Sequel to"),
        "prequel": ("Sequel to", "Followed by"),
        "spin_off": ("Spin-off", "Spin-off of"),
        "tie_in_game_of": ("Tie-in game of", "Tie-in game"),
        "dlc_of": ("DLC of", "DLC"),
        "remaster_of": ("Remaster of", "Remaster"),
        "same_universe": ("Same universe", "Same universe"),
        "crossover": ("Crossover", "Crossover"),
        "tie_in": ("Tie-in", "Tie-in"),
        "inspired": ("Inspired", "Inspired"),
        "related": ("Related", "Related"),
    }
    seen_rel = set()
    for r in rows(con, "SELECT * FROM work_relations"):
        a, b = r["work_a_id"], r["work_b_id"]
        lab_a, lab_b = REL_LABELS[r["relation_type"]]
        for wid, other, label in ((a, b, lab_a), (b, a, lab_b)):
            key = (wid, other, label)
            if key not in seen_rel:
                seen_rel.add(key)
                works[wid]["relations"].append({"work_id": other, "label": label})

    people = {}
    for p in rows(con, "SELECT * FROM people ORDER BY name"):
        people[p["id"]] = {
            "id": p["id"], "name": p["name"], "birth": p["birth_date"],
            "death": p["death_date"], "place": p["birth_place"],
            "imdb": p["imdb_id"], "wikidata": p["wikidata_id"],
            "tmdb": p["tmdb_id"], "credits": []}

    for cc in rows(con, "SELECT * FROM cast_crew ORDER BY work_id, credit_order"):
        entry = {"person_id": cc["person_id"], "role": cc["role"],
                 "character": cc["character_name"], "order": cc["credit_order"]}
        w = works[cc["work_id"]]
        (w["cast"] if cc["role"] in ("actor", "voice actor") else w["crew"]).append(entry)
        people[cc["person_id"]]["credits"].append({
            "work_id": cc["work_id"], "role": cc["role"],
            "character": cc["character_name"]})

    identities = {}
    for i in rows(con, "SELECT * FROM character_identities ORDER BY canonical_name"):
        identities[i["id"]] = {
            "id": i["id"], "name": i["canonical_name"], "alignment": i["alignment"],
            "first_comic": i["first_comic_title"], "first_year": i["first_comic_year"],
            "variants": sorted({c["name"] for c in char_rows.values()
                                if c["identity_id"] == i["id"]}),
            "appearances": []}

    for wc in rows(con, "SELECT * FROM work_characters ORDER BY work_id, billing_order"):
        ch = char_rows[wc["character_id"]]
        ident = identities.get(ch["identity_id"])
        if ident is None:
            continue
        ident["appearances"].append({
            "work_id": wc["work_id"], "as": ch["name"],
            "actor_person_id": wc["actor_person_id"],
            "billing": wc["billing_order"], "notes": wc["notes"]})
        works[wc["work_id"]]["characters"].append({
            "identity_id": ident["id"], "name": ident["name"], "as": ch["name"],
            "alignment": ident["alignment"],
            "actor_person_id": wc["actor_person_id"], "billing": wc["billing_order"]})

    for ident in identities.values():
        seen_years = sorted({works[a["work_id"]]["year"] for a in ident["appearances"]
                             if works[a["work_id"]]["year"]})
        ident["n_works"] = len({a["work_id"] for a in ident["appearances"]})
        ident["first_media_year"] = seen_years[0] if seen_years else None

    data = {
        "meta": {
            "title": "Spider-Man Media Dataset",
            "counts": {
                "works": len(works),
                "movies": sum(1 for w in works.values() if w["type"] == "movie"),
                "tv_shows": sum(1 for w in works.values() if w["type"] == "tv_show"),
                "games": sum(1 for w in works.values() if w["type"] == "game"),
                "characters": len(identities),
                "people": len(people),
                "credits": sum(len(p["credits"]) for p in people.values()),
            },
            "year_min": min(w["year"] for w in works.values() if w["year"]),
            "year_max": max(w["year"] for w in works.values() if w["year"]),
        },
        "franchises": [
            {"name": f["name"], "description": f["description"]}
            for f in sorted(franchises.values(), key=lambda f: f["name"])
        ],
        "works": prune(sorted(works.values(), key=lambda w: (w["year"] or 9999, w["id"]))),
        "characters": prune(sorted(identities.values(),
                                   key=lambda i: -i["n_works"])),
        "people": prune(sorted(people.values(), key=lambda p: p["name"])),
    }

    js = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    (OUT_DIR / "data.json").write_text(js + "\n", encoding="utf-8")
    (OUT_DIR / "data.js").write_text("window.SPIDERMAN_DATA=" + js + ";\n",
                                     encoding="utf-8")
    print(f"data.json {len(js)/1024:.0f} KB · works={len(works)} "
          f"characters={len(identities)} people={len(people)}")


if __name__ == "__main__":
    main()
