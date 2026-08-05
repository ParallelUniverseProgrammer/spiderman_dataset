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

    # v4 resolved each source_material row to comic rows; carry the ids so a
    # citation on a work page can open the issues behind it.
    comic_ids_by_source = {}
    for link in rows(con, "SELECT * FROM work_source_comics"):
        comic_ids_by_source.setdefault(link["source_material_id"], []).append(
            link["comic_id"])

    for s in rows(con, "SELECT * FROM source_material"):
        works[s["work_id"]]["sources"].append({
            "comic": s["comic_title"], "issues": s["issue_range"],
            "writer": s["comic_writer"], "year": s["comic_year"],
            "arc": s["storyline_arc"],
            "comic_ids": sorted(comic_ids_by_source.get(s["id"], []))})

    segments_by_ep = {}
    for sg in rows(con, "SELECT * FROM episode_segments ORDER BY show_work_id, season_number, episode_number, segment_index"):
        key = (sg["show_work_id"], sg["season_number"], sg["episode_number"])
        segments_by_ep.setdefault(key, []).append({
            "title": sg["title"], "writer": sg["writer"], "director": sg["director"]})

    # Only the credits v4 matched to a person are carried: the names themselves
    # are already in `director`/`writer`, and what the explorer cannot derive on
    # its own is which of them is somebody with a page.
    ep_credits = {}
    for c in rows(con, "SELECT * FROM episode_credits WHERE person_id IS NOT NULL"
                       " ORDER BY episode_id, role, credit_order"):
        ep_credits.setdefault(c["episode_id"], []).append(
            {"role": c["role"], "name": c["name"], "person_id": c["person_id"]})

    for e in rows(con, "SELECT * FROM episodes ORDER BY season_number, episode_number"):
        works[e["show_work_id"]]["episodes"].append({
            "season": e["season_number"], "episode": e["episode_number"],
            "title": e["title"], "air_date": e["air_date"],
            "runtime": e["runtime_minutes"], "director": e["director"],
            "writer": e["writer"], "viewers_m": e["us_viewers_millions"],
            "credits": ep_credits.get(e["id"], []),
            "segments": segments_by_ep.get((e["show_work_id"], e["season_number"], e["episode_number"]), [])})

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
            "nationality": p["nationality"],
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

    # --- v3: additive fields the exporter previously left on the table ---

    for ws_ in rows(con, "SELECT * FROM work_summaries"):
        w = works.get(ws_["work_id"])
        if w:
            w["summary"] = {"title": ws_["wikipedia_title"], "url": ws_["url"], "text": ws_["summary"]}

    for g in rows(con, "SELECT * FROM work_genres ORDER BY genre"):
        works[g["work_id"]].setdefault("genres", []).append(g["genre"])
    for c in rows(con, "SELECT * FROM work_countries ORDER BY country"):
        works[c["work_id"]].setdefault("countries", []).append(c["country"])
    for l in rows(con, "SELECT * FROM work_languages ORDER BY language"):
        works[l["work_id"]].setdefault("languages", []).append(l["language"])

    for r in rows(con, "SELECT * FROM work_content_ratings ORDER BY rating"):
        works[r["work_id"]].setdefault("content_ratings", []).append(
            {"rating": r["rating"], "country": r["country"], "reason": r["reason"]})

    for r in rows(con, "SELECT * FROM work_release_dates ORDER BY release_date"):
        works[r["work_id"]].setdefault("release_dates", []).append(
            {"date": r["release_date"], "place": r["place"], "event": r["event"]})

    for pl in rows(con, "SELECT * FROM work_places ORDER BY role, place"):
        works[pl["work_id"]].setdefault("places", []).append(
            {"place": pl["place"], "role": pl["role"]})

    for r in rows(con, "SELECT * FROM box_office_regions ORDER BY amount_usd DESC"):
        works[r["work_id"]].setdefault("box_office_regions", []).append(
            {"region": r["region"], "amount": r["amount_usd"], "as_of": r["as_of"]})

    for d in rows(con, "SELECT * FROM person_details"):
        p = people.get(d["person_id"])
        if p:
            p.update({
                "gender": d["gender"], "birth_name": d["birth_name"],
                "birth_country": d["birth_country"], "death_place": d["death_place"],
                "work_start": d["work_period_start"], "work_end": d["work_period_end"],
                "wikipedia": d["wikipedia_title"]})

    for o in rows(con, "SELECT * FROM person_occupations ORDER BY occupation"):
        people[o["person_id"]].setdefault("occupations", []).append(o["occupation"])
    for c in rows(con, "SELECT * FROM person_citizenships ORDER BY country"):
        people[c["person_id"]].setdefault("citizenships", []).append(c["country"])
    for a in rows(con, "SELECT * FROM person_awards ORDER BY year"):
        people[a["person_id"]].setdefault("awards", []).append(
            {"award": a["award"], "result": a["result"], "year": a["year"], "for_work": a["for_work"]})

    for d in rows(con, "SELECT * FROM character_details"):
        ident = identities.get(d["identity_id"])
        if ident:
            ident.update({
                "gender": d["gender"], "publisher": d["publisher"],
                "universe": d["narrative_universe"], "creators": d["creators"],
                "first_appearance_title": d["first_appearance_title"],
                "first_appearance_year": d["first_appearance_year"],
                "wikipedia": d["wikipedia_title"]})

    # --- v4: the comics, the people who drew them, and the character graph ---

    comics = {}
    for c in rows(con, "SELECT * FROM comics ORDER BY id"):
        comics[c["id"]] = {
            "id": c["id"], "title": c["title"], "kind": c["kind"],
            "series_id": c["series_id"], "issue": c["issue_number"],
            "publisher": c["publisher"], "date": c["publication_date"],
            "year": c["publication_year"], "origin": c["origin"],
            "wikidata": c["wikidata_id"], "wikipedia": c["wikipedia_title"],
            "credits": [], "characters": []}

    creators = {}
    for cr in rows(con, "SELECT * FROM comic_creators ORDER BY name"):
        creators[cr["id"]] = {
            "id": cr["id"], "name": cr["name"], "wikidata": cr["wikidata_id"],
            "person_id": cr["person_id"], "birth": cr["birth_date"],
            "death": cr["death_date"], "wikipedia": cr["wikipedia_title"]}

    # Held once, on the comic. The app walks these to build each creator's side
    # of the same relation — storing both directions doubled the payload for
    # nothing.
    for x in rows(con, "SELECT * FROM comic_credits ORDER BY comic_id, role"):
        if x["creator_id"] in creators:
            comics[x["comic_id"]]["credits"].append(
                {"creator_id": x["creator_id"], "role": x["role"]})

    for x in rows(con, "SELECT * FROM comic_characters ORDER BY comic_id"):
        comics[x["comic_id"]]["characters"].append(x["identity_id"])

    for d in rows(con, "SELECT * FROM character_debuts"):
        ident = identities.get(d["identity_id"])
        if ident:
            ident["debut_comic_id"] = d["comic_id"]
            ident["debut_method"] = d["method"]

    for r in rows(con, "SELECT * FROM character_relations"
                       " ORDER BY identity_id, relation, other_name"):
        ident = identities.get(r["identity_id"])
        if ident:
            ident.setdefault("relations", []).append(
                {"relation": r["relation"], "name": r["other_name"],
                 "other_id": r["other_identity_id"]})

    for t in rows(con, "SELECT * FROM character_traits ORDER BY identity_id, trait, value"):
        ident = identities.get(t["identity_id"])
        if ident:
            ident.setdefault("traits", {}).setdefault(t["trait"], []).append(t["value"])

    platform_detail = {}
    for d in rows(con, "SELECT p.name, d.* FROM platform_details d"
                       " JOIN platforms p ON p.id = d.platform_id ORDER BY p.name"):
        platform_detail[d["name"]] = {
            "manufacturer": d["manufacturer"], "developer": d["developer"],
            "released": d["released"], "discontinued": d["discontinued"],
            "wikipedia": d["wikipedia_title"]}

    studio_detail = {}
    for d in rows(con, "SELECT s.name, d.* FROM studio_details d"
                       " JOIN studios s ON s.id = d.studio_id ORDER BY s.name"):
        studio_detail[d["name"]] = {
            "industry": d["industry"], "headquarters": d["headquarters"],
            "inception": d["inception"], "dissolved": d["dissolved"],
            "wikipedia": d["wikipedia_title"]}

    # Outbound links only — most external_ids rows are authority-file identifiers
    # (VIAF, GND, LoC…) with no url to send a reader to.
    for x in rows(con, "SELECT * FROM external_ids WHERE url IS NOT NULL ORDER BY entity_type, entity_id, source"):
        entry = {"source": x["source"], "id": x["identifier"], "url": x["url"]}
        target = {"work": works, "person": people, "character": identities}[x["entity_type"]].get(x["entity_id"])
        if target is not None:
            target.setdefault("external_ids", []).append(entry)

    prov_sources = {}
    provenance = []
    for version in ("v3", "v4"):
        for r in rows(con, f"SELECT * FROM {version}_sources"):
            prov_sources.setdefault(r["source_key"], r)
        for r in rows(con, f"SELECT table_name, source_key, action, COUNT(*) n"
                           f"  FROM {version}_provenance GROUP BY table_name, source_key, action"
                           f"  ORDER BY table_name, source_key, action"):
            src = prov_sources.get(r["source_key"], {})
            provenance.append({
                "table": r["table_name"], "action": r["action"], "n": r["n"],
                "version": version,
                "source": r["source_key"], "source_name": src.get("name"),
                "source_url": src.get("url"), "licence": src.get("licence"),
                "retrieved": src.get("retrieved")})

    # The heaviest v3 additions — outbound links, prose summaries, award lists — are
    # furniture for a single detail page, never for a list or a filter. Splitting them
    # into a second file fetched after first paint keeps the page every reader gets
    # (the works/characters/people tables) at roughly its v2 weight.
    details = {"works": {}, "people": {}, "characters": {}}
    for wid, w in works.items():
        d = {k: w.pop(k) for k in ("summary", "external_ids") if k in w}
        if d:
            details["works"][wid] = d
    for pid, p in people.items():
        d = {k: p.pop(k) for k in ("awards", "external_ids") if k in p}
        if d:
            details["people"][pid] = d
    for cid, c in identities.items():
        d = {k: c.pop(k) for k in ("external_ids",) if k in c}
        if d:
            details["characters"][cid] = d

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
                "comics": len(comics),
                "comic_creators": len(creators),
            },
            "year_min": min(w["year"] for w in works.values() if w["year"]),
            "year_max": max(w["year"] for w in works.values() if w["year"]),
            "provenance": provenance,
            "sources": sorted(prov_sources.values(), key=lambda s: s["name"]),
        },
        "franchises": [
            {"name": f["name"], "description": f["description"]}
            for f in sorted(franchises.values(), key=lambda f: f["name"])
        ],
        "works": prune(sorted(works.values(), key=lambda w: (w["year"] or 9999, w["id"]))),
        "characters": prune(sorted(identities.values(),
                                   key=lambda i: -i["n_works"])),
        "people": prune(sorted(people.values(), key=lambda p: p["name"])),
        "comics": prune(sorted(comics.values(),
                               key=lambda c: (c["year"] or 9999, c["title"]))),
        "comic_creators": prune(sorted(creators.values(), key=lambda c: c["name"])),
        "platform_details": prune(platform_detail),
        "studio_details": prune(studio_detail),
    }

    js = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    (OUT_DIR / "data.json").write_text(js + "\n", encoding="utf-8")
    (OUT_DIR / "data.js").write_text("window.SPIDERMAN_DATA=" + js + ";\n",
                                     encoding="utf-8")

    details_js = json.dumps(prune(details), ensure_ascii=False, separators=(",", ":"))
    (OUT_DIR / "data-details.json").write_text(details_js + "\n", encoding="utf-8")
    (OUT_DIR / "data-details.js").write_text(
        "window.SPIDERMAN_DETAILS=" + details_js + ";\n", encoding="utf-8")

    print(f"data.json {len(js)/1024:.0f} KB + data-details.json {len(details_js)/1024:.0f} KB · "
          f"works={len(works)} characters={len(identities)} people={len(people)}")


if __name__ == "__main__":
    main()
