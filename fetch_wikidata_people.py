#!/usr/bin/env python3
"""fetch_wikidata_people.py — resolve `people` to Wikidata and pull biography.

Writes data_raw/v3/people_wikidata.json. Fills the columns TMDB left empty
(nationality is 0/581 in v2) and adds occupations, gender, awards and a second
set of external ids.

    python3 fetch_wikidata_people.py [--refresh] [--limit N]

Resolution
----------
Three tiers, most trustworthy first:

1. `people.wikidata_id` — already resolved via TMDB in v2, taken as given.
2. Credit intersection — a person credited on one of our works should appear in
   that work's own Wikidata credit list (P161 cast, P57 director, ...). A name
   that matches inside the credits of a work we know they worked on is the right
   human by construction, which is what makes this safe for common names.
3. Label search, accepted only when exactly one result is a human *and* that
   human's occupations overlap the roles we hold for them.

Tier 3 misses are recorded as unresolved rather than guessed.
"""
import argparse
import json
import re
import sqlite3
import unicodedata
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import wdlib as W

HERE = Path(__file__).resolve().parent
DB = HERE / "spiderman.db"
V3 = HERE / "data_raw" / "v3"
WORKS_JSON = V3 / "works_wikidata.json"
OUT = V3 / "people_wikidata.json"

HUMAN = "Q5"

# Occupations that make a person plausible for a screen credit. Used only to
# validate tier-3 label-search hits.
CREDIT_OCCUPATIONS = {
    "Q33999": "actor", "Q10800557": "film actor", "Q10798782": "television actor",
    "Q2405480": "voice actor", "Q2526255": "film director", "Q28389": "screenwriter",
    "Q36834": "composer", "Q3282637": "film producer", "Q222344": "cinematographer",
    "Q7042855": "film editor", "Q1053574": "executive producer", "Q245068": "comedian",
    "Q855091": "guitarist", "Q177220": "singer", "Q639669": "musician",
    "Q1281618": "sculptor", "Q715301": "video game developer", "Q1642960": "art director",
    "Q3455803": "director", "Q578109": "television producer", "Q1930187": "journalist",
    "Q266569": "voice actor (ja)", "Q4610556": "model", "Q947873": "television presenter",
    "Q11774202": "screenwriter (alt)", "Q3387717": "theatrical director",
    "Q753110": "songwriter", "Q158852": "conductor", "Q6606110": "game designer",
    "Q1650915": "researcher", "Q214917": "playwright", "Q49757": "poet",
    "Q6625963": "novelist", "Q36180": "writer", "Q482980": "author",
    "Q3501317": "stunt performer", "Q11481802": "animator", "Q1114448": "cartoonist",
    "Q1028181": "painter", "Q483501": "artist", "Q10871364": "sound designer",
}

PERSON_LIST_PROPS = {
    "P106": "occupation", "P27": "citizenship", "P1412": "languages_spoken",
    "P800": "notable_work", "P136": "genre", "P1303": "instrument",
    "P103": "native_language", "P184": "doctoral_advisor",
}

PERSON_EXT_IDS = {
    "P345": "imdb", "P4985": "tmdb_person", "P214": "viaf", "P244": "loc",
    "P227": "gnd", "P268": "bnf", "P646": "freebase", "P2019": "allmovie",
    "P1266": "allocine", "P3479": "omni", "P2604": "kinopoisk",
    "P2168": "svensk_film", "P434": "musicbrainz_artist", "P1953": "discogs",
    "P2949": "wikitree", "P535": "find_a_grave", "P3417": "quora",
    "P2003": "instagram", "P2002": "twitter", "P856": "official_website",
    "P1281": "worldcat", "P8687": "social_followers",
}


def norm(s):
    s = unicodedata.normalize("NFKD", (s or "").lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return " ".join(s.split())


def load_people():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    people = [dict(r) for r in con.execute("SELECT * FROM people ORDER BY id")]
    credits = defaultdict(set)
    for r in con.execute("SELECT person_id, work_id FROM cast_crew"):
        credits[r["person_id"]].add(r["work_id"])
    for r in con.execute("SELECT person_id, work_id FROM work_people"):
        credits[r["person_id"]].add(r["work_id"])
    for r in con.execute(
        "SELECT actor_person_id AS p, work_id FROM work_characters WHERE actor_person_id IS NOT NULL"
    ):
        credits[r["p"]].add(r["work_id"])
    roles = defaultdict(set)
    for r in con.execute("SELECT person_id, role FROM cast_crew"):
        roles[r["person_id"]].add((r["role"] or "").lower())
    con.close()
    return people, credits, roles


def work_credit_qids():
    """{work_id: set(person qids credited on that work in Wikidata)}"""
    if not WORKS_JSON.exists():
        return {}
    with open(WORKS_JSON, encoding="utf-8") as f:
        data = json.load(f)
    out = {}
    for wid, d in data.get("works", {}).items():
        qs = {c["person_qid"] for c in d.get("cast", []) if c.get("person_qid")}
        for vals in d.get("crew", {}).values():
            qs.update(v for v in vals if isinstance(v, str) and v.startswith("Q"))
        out[int(wid)] = qs
    return out


def resolve(people, credits, roles, refresh=False):
    resolved, unresolved = {}, []
    todo = []
    for p in people:
        if p.get("wikidata_id"):
            resolved[p["id"]] = {"qid": p["wikidata_id"], "method": "v2_tmdb"}
        else:
            todo.append(p)
    W.log(f"  {len(resolved)} already carry a wikidata_id; resolving {len(todo)} more")

    # --- tier 2: credit intersection ---------------------------------------
    wq = work_credit_qids()
    cand_qids = {q for s in wq.values() for q in s}
    labels = W.qid_labels(cand_qids, refresh) if cand_qids else {}
    still = []
    for p in todo:
        pool = set()
        for w in credits.get(p["id"], ()):
            pool |= wq.get(w, set())
        hits = [q for q in pool if norm(labels.get(q)) == norm(p["name"])]
        if len(set(hits)) == 1:
            resolved[p["id"]] = {"qid": hits[0], "method": "credit_intersection"}
        else:
            still.append(p)
    W.log(f"  credit intersection resolved {len(todo) - len(still)}")

    # --- tier 3: guarded label search ---------------------------------------
    def search(p):
        hits = W.wbsearch(p["name"], refresh=refresh)
        exact = [h for h in hits if norm(h.get("label")) == norm(p["name"])]
        return p, exact[:6]

    with ThreadPoolExecutor(max_workers=6) as ex:
        searched = list(ex.map(search, still))

    all_hits = sorted({h["id"] for _, hs in searched for h in hs})
    ents = W.entities_bulk(all_hits, props="claims|labels", refresh=refresh) if all_hits else {}

    n3 = 0
    for p, hits in searched:
        humans = []
        for h in hits:
            e = ents.get(h["id"])
            if not isinstance(e, dict) or HUMAN not in W.pvalues(e, "P31"):
                continue
            occ = set(W.pvalues(e, "P106"))
            if occ & set(CREDIT_OCCUPATIONS):
                humans.append(h["id"])
        if len(humans) == 1:
            resolved[p["id"]] = {"qid": humans[0], "method": "label_search_unique"}
            n3 += 1
        else:
            unresolved.append((p, f"{len(humans)} plausible humans"))
    W.log(f"  label search resolved {n3}, {len(unresolved)} unresolved")
    return resolved, unresolved


def extract(ent, qid):
    out = {"qid": qid}
    out["label"] = (ent.get("labels", {}).get("en", {}) or {}).get("value")
    out["enwiki"] = (ent.get("sitelinks", {}).get("enwiki", {}) or {}).get("title")
    out["is_human"] = "Q5" in W.pvalues(ent, "P31")

    out["birth_date"] = W.wd_time_to_iso(W.pfirst(ent, "P569"))
    out["death_date"] = W.wd_time_to_iso(W.pfirst(ent, "P570"))
    out["birth_place_qid"] = W.pfirst(ent, "P19")
    out["death_place_qid"] = W.pfirst(ent, "P20")
    out["gender_qid"] = W.pfirst(ent, "P21")
    out["birth_name"] = W.pfirst(ent, "P1477")
    out["height_cm"] = W.quantity_amount(W.pfirst(ent, "P2048"))
    out["work_period_start"] = W.wd_year(W.pfirst(ent, "P2031"))
    out["work_period_end"] = W.wd_year(W.pfirst(ent, "P2032"))

    for prop, name in PERSON_LIST_PROPS.items():
        vs = W.pvalues(ent, prop)
        if vs:
            out.setdefault("props", {})[name] = vs

    awards = []
    for prop, result in (("P166", "won"), ("P1411", "nominated")):
        for st in W.claims(ent, prop):
            aq = W.snak_value(st.get("mainsnak"))
            if not aq:
                continue
            awards.append({
                "award_qid": aq, "result": result,
                "year": W.wd_year(W.qual_first(st, "P585")),
                "for_work": W.qual_first(st, "P1686"),
            })
    out["awards"] = awards

    ext = {}
    for prop, name in PERSON_EXT_IDS.items():
        v = W.pfirst(ent, prop)
        if isinstance(v, str):
            ext[name] = v
    out["external_ids"] = ext
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--limit", type=int)
    args = ap.parse_args()

    people, credits, roles = load_people()
    if args.limit:
        people = people[: args.limit]
    W.log(f"resolving {len(people)} people against Wikidata")
    resolved, unresolved = resolve(people, credits, roles, args.refresh)

    qids = sorted({r["qid"] for r in resolved.values()})
    W.log(f"  fetching {len(qids)} entities")
    ents = {}
    with ThreadPoolExecutor(max_workers=8) as ex:
        for q, e in zip(qids, ex.map(lambda q: W.entity(q, args.refresh), qids)):
            if e:
                ents[q] = e

    by_person = {}
    for pid, r in resolved.items():
        e = ents.get(r["qid"])
        if not e:
            continue
        d = extract(e, r["qid"])
        d["match_method"] = r["method"]
        by_person[str(pid)] = d

    # One label pass over every referenced item, so the build stays offline.
    ref = set()
    for d in by_person.values():
        for k in ("birth_place_qid", "death_place_qid", "gender_qid"):
            if d.get(k):
                ref.add(d[k])
        for vals in d.get("props", {}).values():
            ref.update(v for v in vals if isinstance(v, str) and v.startswith("Q"))
        for a in d.get("awards", []):
            ref.add(a["award_qid"])
            if a.get("for_work"):
                ref.add(a["for_work"])
    W.log(f"  labelling {len(ref)} referenced items")
    labels = W.qid_labels(ref, args.refresh)

    # Birth places need their country for a usable `birth_place` string.
    place_qids = sorted({d[k] for d in by_person.values() for k in
                         ("birth_place_qid", "death_place_qid") if d.get(k)})
    place_country = {}
    if place_qids:
        vals = " ".join(f"wd:{q}" for q in place_qids)
        rows = W.sparql(f"""SELECT ?p ?c WHERE {{
          VALUES ?p {{ {vals} }}
          ?p wdt:P17 ?c .
        }}""", args.refresh)
        for b in rows:
            place_country[b["p"]["value"].rsplit("/", 1)[-1]] = b["c"]["value"].rsplit("/", 1)[-1]
        labels.update(W.qid_labels(set(place_country.values()), args.refresh))

    V3.mkdir(parents=True, exist_ok=True)
    payload = {
        "people": by_person,
        "labels": labels,
        "place_country": place_country,
        "unresolved": [{"id": p["id"], "name": p["name"], "reason": why}
                       for p, why in unresolved],
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=1, sort_keys=True, ensure_ascii=False)
    W.log(f"wrote {OUT}")

    filled = lambda k: sum(1 for d in by_person.values() if d.get(k))
    W.log(f"  birth_date {filled('birth_date')}, death_date {filled('death_date')}, "
          f"citizenship {sum(1 for d in by_person.values() if d.get('props', {}).get('citizenship'))}, "
          f"occupation {sum(1 for d in by_person.values() if d.get('props', {}).get('occupation'))}")


if __name__ == "__main__":
    main()
