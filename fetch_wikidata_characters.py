#!/usr/bin/env python3
"""fetch_wikidata_characters.py — resolve character identities to Wikidata.

Writes data_raw/v3/characters_wikidata.json: first comic appearance, creators,
narrative universe, gender, powers and external ids for each of the 264 merged
identities. v2 has a first-appearance title and year for only 139 of them.

    python3 fetch_wikidata_characters.py [--refresh]

Resolution
----------
Candidates come from a label/alias search plus, where available, the character
lists (P674) of the works the identity appears in — a character credited in a
film we have already resolved is very likely one of that film's own P674 values.
A candidate is accepted only if it is a fictional entity (P31 reducing to
fictional character / human) *and* is tied to Marvel: publisher Marvel Comics,
a Marvel narrative universe, or a creator who worked there. That last test is
what keeps "Electro" and "Mysterio" off unrelated fictional namesakes.
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
OUT = V3 / "characters_wikidata.json"

FICTIONAL_ROOTS = ["Q95074", "Q15632617", "Q15773347", "Q3658341"]  # character, fictional human, ...
MARVEL = {
    "Q173496",   # Marvel Comics
    "Q931597",   # Marvel Universe / Earth-616
    "Q1439104",  # Marvel Cinematic Universe
    "Q642878",   # Marvel Entertainment
    "Q11302326",
}

CHAR_LIST_PROPS = {
    "P106": "occupation", "P1080": "narrative_universe", "P170": "creator",
    "P1441": "present_in_work", "P361": "part_of", "P2650": "interested_in",
    "P27": "citizenship", "P172": "ethnic_group", "P140": "religion",
    "P462": "color", "P1552": "has_quality", "P8687": "followers",
    "P175": "performer", "P674": "characters",
}

CHAR_EXT_IDS = {
    "P6262": "fandom_article", "P5905": "comic_vine", "P1417": "britannica",
    "P4013": "giphy", "P646": "freebase", "P373": "commons_category",
    "P1712": "metacritic", "P345": "imdb", "P6839": "tv_tropes",
    "P11527": "marvel_id",
}


def norm(s):
    s = unicodedata.normalize("NFKD", (s or "").lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"\(.*?\)", " ", s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return " ".join(s.split())


def load_identities():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    idents = [dict(r) for r in con.execute(
        "SELECT * FROM character_identities ORDER BY id")]
    variants = defaultdict(list)
    for r in con.execute("SELECT identity_id, name, alias FROM characters"):
        if r["identity_id"]:
            variants[r["identity_id"]].append(r["name"])
            if r["alias"]:
                variants[r["identity_id"]].append(r["alias"])
    works = defaultdict(set)
    for r in con.execute("""
        SELECT c.identity_id AS iid, wc.work_id FROM work_characters wc
        JOIN characters c ON c.id = wc.character_id WHERE c.identity_id IS NOT NULL"""):
        works[r["iid"]].add(r["work_id"])
    con.close()
    return idents, variants, works


def work_character_qids():
    p = V3 / "works_wikidata.json"
    if not p.exists():
        return {}
    with open(p, encoding="utf-8") as f:
        d = json.load(f)
    out = {}
    for wid, w in d.get("works", {}).items():
        qs = set(w.get("characters") or [])
        qs.update(c["character_qid"] for c in w.get("cast", []) if c.get("character_qid"))
        out[int(wid)] = qs
    return out


MARVEL_WORDS = ("marvel", "spider-man", "spiderman", "earth-616", "x-men", "avengers")

# Creators whose presence on a comics character is itself a Marvel signal.
MARVEL_CREATORS = {
    "Q181900",   # Stan Lee
    "Q317228",   # Steve Ditko
    "Q179041",   # Jack Kirby
    "Q1699964",  # John Romita Sr.
    "Q1518816",  # Gerry Conway
    "Q1370870",  # Roy Thomas
    "Q3105955",  # Todd McFarlane
    "Q1339022",  # David Michelinie
}

MARVEL_LINK_PROPS = ("P1080", "P123", "P361", "P1441", "P179", "P170", "P31", "P8345")


def marvel_link_qids(ent):
    out = set()
    for p in MARVEL_LINK_PROPS:
        out.update(W.pvalues(ent, p))
    return out


def is_marvel(ent, link_labels, from_work):
    """Marvel-ness, established the cheapest reliable way available.

    Requiring publisher=Marvel Comics alone rejects most of these characters:
    the items often carry only a narrative universe, a creator, or nothing but a
    description. Any one of those is enough, and an item that a work we already
    resolved lists as one of *its* characters is Marvel by construction.
    """
    if from_work:
        return True
    linked = marvel_link_qids(ent)
    if linked & MARVEL:
        return True
    if linked & MARVEL_CREATORS:
        return True
    for q in linked:
        lab = (link_labels.get(q) or "").lower()
        if any(w in lab for w in MARVEL_WORDS):
            return True
    desc = (ent.get("descriptions", {}).get("en", {}) or {}).get("value", "").lower()
    return any(w in desc for w in MARVEL_WORDS)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--only")
    args = ap.parse_args()

    idents, variants, works = load_identities()
    if args.only:
        idents = [i for i in idents if args.only.lower() in i["canonical_name"].lower()]
    W.log(f"resolving {len(idents)} character identities")

    wcq = work_character_qids()

    def search(ident):
        names = [ident["canonical_name"]] + variants.get(ident["id"], [])
        seen, cands, from_work = set(), [], set()
        for n in list(dict.fromkeys(names))[:4]:
            for hit in W.wbsearch(n, limit=15, refresh=args.refresh):
                if hit["id"] not in seen:
                    seen.add(hit["id"])
                    cands.append(hit["id"])
        # characters attached to the works this identity appears in
        for w in works.get(ident["id"], ()):
            for q in wcq.get(w, ()):
                from_work.add(q)
                if q not in seen:
                    seen.add(q)
                    cands.append(q)
        return ident["id"], cands, from_work

    cand_map, from_work_map = {}, {}
    with ThreadPoolExecutor(max_workers=6) as ex:
        for iid, cands, fw in ex.map(search, idents):
            cand_map[iid] = cands
            from_work_map[iid] = fw

    all_q = sorted({q for v in cand_map.values() for q in v})
    W.log(f"  {len(all_q)} candidate items")
    ents = W.entities_bulk(all_q, props="claims|labels|aliases|sitelinks|descriptions",
                           refresh=args.refresh)

    # One label pass over everything the candidates link to, so the Marvel test
    # can read those labels instead of guessing from a fixed id list.
    link_qids = {q for e in ents.values() if isinstance(e, dict) for q in marvel_link_qids(e)}
    W.log(f"  labelling {len(link_qids)} linked items for the Marvel test")
    link_labels = W.qid_labels(link_qids, args.refresh)

    p31s = {c for e in ents.values() if isinstance(e, dict) for c in W.pvalues(e, "P31")}
    fict = set()
    if p31s:
        vals = " ".join(f"wd:{q}" for q in sorted(p31s))
        roots = " ".join(f"wd:{q}" for q in FICTIONAL_ROOTS)
        for b in W.sparql(f"""SELECT DISTINCT ?c WHERE {{
          VALUES ?c {{ {vals} }} VALUES ?r {{ {roots} }} ?c wdt:P279* ?r . }}""", args.refresh):
            fict.add(b["c"]["value"].rsplit("/", 1)[-1])

    resolved, unresolved = {}, []
    for ident in idents:
        want = norm(ident["canonical_name"])
        alt = {norm(v) for v in variants.get(ident["id"], [])}
        scored = []
        for q in cand_map[ident["id"]]:
            e = ents.get(q)
            if not isinstance(e, dict):
                continue
            if not (set(W.pvalues(e, "P31")) & fict):
                continue
            marvel = is_marvel(e, link_labels, q in from_work_map.get(ident["id"], ()))
            label = (e.get("labels", {}).get("en", {}) or {}).get("value", "")
            names = {norm(label)} | {
                norm(a.get("value")) for a in e.get("aliases", {}).get("en", [])}
            names.discard("")
            exact = want in names
            near = bool(names & alt) or any(want and want in n for n in names)
            if not (exact or near):
                continue
            if not marvel:
                continue
            s = (4 if exact else 1.5) + min(len(e.get("claims", {})) / 50.0, 2.0)
            if e.get("sitelinks", {}).get("enwiki"):
                s += 0.5
            scored.append((s, q))
        scored.sort(reverse=True)
        if not scored:
            unresolved.append(ident)
            continue
        resolved[ident["id"]] = scored[0][1]

    W.log(f"  resolved {len(resolved)}, unresolved {len(unresolved)}")

    out = {}
    ref = set()
    for iid, q in resolved.items():
        e = ents.get(q)
        d = {"qid": q,
             "label": (e.get("labels", {}).get("en", {}) or {}).get("value"),
             "enwiki": (e.get("sitelinks", {}).get("enwiki", {}) or {}).get("title"),
             "gender_qid": W.pfirst(e, "P21"),
             "first_appearance_qid": W.pfirst(e, "P4584"),
             "publisher_qid": W.pfirst(e, "P123"),
             "inception": W.wd_time_to_iso(W.pfirst(e, "P571")),
             }
        for prop, name in CHAR_LIST_PROPS.items():
            vs = W.pvalues(e, prop)
            if vs:
                d.setdefault("props", {})[name] = vs
        ext = {}
        for prop, name in CHAR_EXT_IDS.items():
            v = W.pfirst(e, prop)
            if isinstance(v, str):
                ext[name] = v
        d["external_ids"] = ext
        out[str(iid)] = d
        for k in ("gender_qid", "first_appearance_qid", "publisher_qid"):
            if d.get(k):
                ref.add(d[k])
        for vals in d.get("props", {}).values():
            ref.update(v for v in vals if isinstance(v, str) and v.startswith("Q"))

    # First appearances are comic issues: resolve their title and publication year.
    fa = sorted({d["first_appearance_qid"] for d in out.values() if d.get("first_appearance_qid")})
    fa_info = {}
    if fa:
        vals = " ".join(f"wd:{q}" for q in fa)
        rows = W.sparql(f"""SELECT ?i ?iLabel ?date ?seriesLabel WHERE {{
          VALUES ?i {{ {vals} }}
          OPTIONAL {{ ?i wdt:P577 ?date }}
          OPTIONAL {{ ?i wdt:P179 ?series }}
          SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
        }}""", args.refresh)
        for b in rows:
            q = b["i"]["value"].rsplit("/", 1)[-1]
            rec = fa_info.setdefault(q, {})
            if "iLabel" in b:
                rec["title"] = b["iLabel"]["value"]
            if "date" in b:
                rec["year"] = W.wd_year(b["date"]["value"].replace("Z", "Z"))
            if "seriesLabel" in b:
                rec["series"] = b["seriesLabel"]["value"]

    W.log(f"  labelling {len(ref)} referenced items")
    labels = W.qid_labels(ref, args.refresh)

    V3.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({
            "characters": out, "labels": labels, "first_appearances": fa_info,
            "unresolved": [{"id": i["id"], "name": i["canonical_name"]} for i in unresolved],
        }, f, indent=1, sort_keys=True, ensure_ascii=False)
    W.log(f"wrote {OUT}")
    W.log(f"  first appearance known for "
          f"{sum(1 for d in out.values() if d.get('first_appearance_qid'))} identities")


if __name__ == "__main__":
    main()
