#!/usr/bin/env python3
"""fetch_orgs.py — resolve studios and hardware platforms to Wikidata.

Writes data_raw/v4/orgs.json. Two of the twelve fully-NULL columns the README
lists — `studios.country` and `studios.parent_company` — get filled from here;
`platforms` gets three columns (manufacturer, released, discontinued) it never
had at all.

    python3 fetch_orgs.py [--refresh]

Coverage is uneven by construction. `studios` holds everything from Columbia
Pictures to three-person shovelware outfits from 1983, and most of the latter
have no Wikidata item; `platforms` runs from the Atari 2600 to iOS, and every
console-generation entry resolves cleanly while a handful of computer platforms
with ambiguous short names ("BBC Micro" vs. the broadcaster) do not. Both are
resolved by exact label/alias match only — no fuzzy acceptance — so a miss stays
a miss rather than becoming a wrong link.
"""
import argparse
import json
import sqlite3
import unicodedata
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import wdlib as W

HERE = Path(__file__).resolve().parent
DB = HERE / "spiderman.db"
V4 = HERE / "data_raw" / "v4"
OUT = V4 / "orgs.json"

# Wide on purpose: a "studio" in this dataset is anything credited with making a
# work, which spans public companies, one-room game developers and TV production
# arms. The exact-label test below is what keeps the net from catching anything.
STUDIO_ROOTS = [
    "Q4830453",   # business
    "Q891723",    # public company
    "Q1058914",   # software company
    "Q11033",     # mass media
    "Q1341478",   # media company
    "Q210167",    # video game developer
]
PLATFORM_ROOTS = [
    "Q27666158",  # video game platform
    "Q8076",      # video game console
    "Q56682555",  # video game console model
    "Q473708",    # home computer
    "Q9135",      # operating system
    "Q10929058",  # product model
    "Q55990535",  # computer model
    "Q60484681",  # computer model series
    "Q68",        # personal computer
]

STUDIO_PROPS = {
    "P17": "country_qid", "P749": "parent_qid", "P571": "inception",
    "P576": "dissolved", "P452": "industry_qid", "P159": "hq_qid",
}
PLATFORM_PROPS = {
    "P176": "manufacturer_qid", "P178": "developer_qid", "P577": "released",
    "P2669": "discontinued",
}

EXT_IDS = {"P646": "freebase", "P373": "commons_category", "P856": "official_website"}


def norm(s):
    s = unicodedata.normalize("NFKD", (s or "").lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return " ".join(s.split())


def load_names():
    con = sqlite3.connect(DB)
    studios = [r[0] for r in con.execute("SELECT name FROM studios ORDER BY name")]
    platforms = [r[0] for r in con.execute("SELECT name FROM platforms ORDER BY name")]
    con.close()
    return studios, platforms


def resolve(names, roots, refresh):
    """Exact label/alias match against a class-restricted candidate set."""
    def search(n):
        # A studio credit is often "X / Y" (co-developers) or "X, Inc." — try the
        # raw string first, then its parts.
        variants = [n]
        for sep in (" / ", ", "):
            if sep in n:
                variants += [p.strip() for p in n.split(sep)]
        variants = list(dict.fromkeys(v for v in variants if v))[:4]
        ids = []
        for v in variants:
            for h in W.wbsearch(v, limit=8, refresh=refresh):
                if h["id"] not in ids:
                    ids.append(h["id"])
        return n, ids

    cands = {}
    with ThreadPoolExecutor(max_workers=6) as ex:
        for n, ids in ex.map(search, names):
            cands[n] = ids
    all_q = sorted({q for v in cands.values() for q in v})
    ents = W.entities_bulk(all_q, props="claims|labels|aliases|sitelinks",
                           refresh=refresh, languages=W.LANGS)
    p31 = {c for e in ents.values() if isinstance(e, dict) for c in W.pvalues(e, "P31")}
    ok_types = set()
    if p31:
        vals = " ".join(f"wd:{q}" for q in sorted(p31))
        rts = " ".join(f"wd:{q}" for q in roots)
        for b in W.sparql(f"""SELECT DISTINCT ?c WHERE {{
          VALUES ?c {{ {vals} }} VALUES ?r {{ {rts} }} ?c wdt:P279* ?r . }}""", refresh):
            ok_types.add(b["c"]["value"].rsplit("/", 1)[-1])

    out = {}
    for n, ids in cands.items():
        want = norm(n)
        scored = []
        for q in ids:
            e = ents.get(q)
            if not isinstance(e, dict):
                continue
            if not set(W.pvalues(e, "P31")) & ok_types:
                continue
            names_ = {norm(W.en_label(e))} | {norm(a) for a in W.en_aliases(e)}
            names_.discard("")
            if want not in names_:
                continue
            s = 1.0
            if e.get("sitelinks", {}).get("enwiki"):
                s += 1.0
            s += min(len(e.get("claims", {})) / 40.0, 2.0)
            scored.append((s, q))
        if scored:
            scored.sort(reverse=True)
            out[n] = scored[0][1]
    return out, ents


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()

    studio_names, platform_names = load_names()
    W.log(f"resolving {len(studio_names)} studios, {len(platform_names)} platforms")

    studio_q, studio_ents = resolve(studio_names, STUDIO_ROOTS, args.refresh)
    W.log(f"  studios: {len(studio_q)}/{len(studio_names)} resolved")
    platform_q, platform_ents = resolve(platform_names, PLATFORM_ROOTS, args.refresh)
    W.log(f"  platforms: {len(platform_q)}/{len(platform_names)} resolved")

    ref = set()

    def build(names_q, ents, props, ext_props):
        out = {}
        for name, q in names_q.items():
            e = ents[q]
            d = {"qid": q,
                 "label": W.en_label(e),
                 "enwiki": (e.get("sitelinks", {}).get("enwiki", {}) or {}).get("title")}
            for prop, key in props.items():
                if key.endswith("_qid"):
                    v = W.pfirst(e, prop)
                    if v:
                        d[key] = v
                        ref.add(v)
                else:
                    v = W.wd_time_to_iso(W.pfirst(e, prop))
                    if v:
                        d[key] = v
            ext = {}
            for prop, src in ext_props.items():
                v = W.pfirst(e, prop)
                if isinstance(v, str):
                    ext[src] = v
            if ext:
                d["external_ids"] = ext
            out[name] = d
        return out

    studios_out = build(studio_q, studio_ents, STUDIO_PROPS, EXT_IDS)
    platforms_out = build(platform_q, platform_ents, PLATFORM_PROPS, EXT_IDS)

    W.log(f"labelling {len(ref)} referenced items")
    labels = W.qid_labels(ref, args.refresh, languages=W.LANGS)

    V4.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"studios": studios_out, "platforms": platforms_out, "labels": labels},
                  f, indent=1, sort_keys=True, ensure_ascii=False)
    W.log(f"wrote {OUT}")


if __name__ == "__main__":
    main()
