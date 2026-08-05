#!/usr/bin/env python3
"""fetch_comics.py — turn the dataset's comic references into real comic items.

Writes data_raw/v4/comics.json: the series, issues and storylines that
`source_material` and the character first appearances point at, each with its
publisher, publication date, creator credits and cast.

    python3 fetch_comics.py [--refresh]

Why this exists
---------------
Up to v3 every comic in the dataset is a string. `source_material` says a film
adapts "Amazing Spider-Man #121-122" and `character_details` says Doctor Octopus
debuts in "The Amazing Spider-Man #3", but neither is an entity: you cannot ask
which adaptations draw on Ditko-era issues, or who wrote the comic a character
first appeared in. Those strings are the dataset's outer edge, and this resolves
them.

Resolution
----------
Three kinds of reference come out of the database:

* **issue** — anything with a `#NN` in it. The text before the `#` names a
  series; the series is resolved once, its issues are listed in one query each,
  and the number is looked up in that list. Ranges ("#121-122") expand.
* **series** — a bare series title with no issue number.
* **storyline** — a named arc ("The Night Gwen Stacy Died"), resolved by search
  and accepted only if the item is a comics item published by Marvel.

Two things make this harder than it sounds. Wikidata carries several items for
the same long-running title — "Amazing Spider-Man" exists three times over, and
only one of them has the issues hanging off it — so a name resolves to a *set* of
candidate series and the issue index is built across all of them. And its issue
coverage is partial: about ninety of the nine hundred Amazing Spider-Man issues
have items. A reference to one of the rest still yields a comic, marked
`origin='parsed'` with a null QID, because the series and the number are read
straight out of the citation; it simply has no publication date or credits.

A reference that matches nothing is kept in `unresolved` with the reason — and
the reason distinguishes "no such comic" from "this reference was never a comic
in the first place", which is what most of them turn out to be.
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
V4 = HERE / "data_raw" / "v4"
OUT = V4 / "comics.json"

MARVEL = "Q173496"

# Classes that make an item a comic of some kind. Checked by subclass closure,
# because Wikidata uses a long tail of these ("comic book issue", "one-shot",
# "limited series", "comic book story arc", ...).
COMIC_ROOTS = [
    "Q1004",      # comic
    "Q1760610",   # comic book
    "Q725377",    # graphic novel
    "Q14406742",  # comic book series
    "Q21198342",  # manga series
    "Q1667921",   # novel series (arcs are sometimes filed here)
    "Q20540385",  # comic book story arc
]

# Series-ish classes: an item of one of these is a container, not a single issue.
SERIES_ROOTS = ["Q14406742", "Q3464665", "Q21198342", "Q1667921"]

CREDIT_PROPS = {
    "P50": "author",
    "P58": "writer",
    "P10837": "penciller",
    "P10836": "inker",
    "P6338": "colorist",
    "P9191": "letterer",
    "P736": "cover_artist",
    "P110": "illustrator",
    "P98": "editor",
    "P170": "creator",
}

COMIC_EXT_IDS = {
    "P5905": "comic_vine", "P6262": "fandom_article", "P11308": "gcd_issue",
    "P8383": "goodreads_work", "P646": "freebase", "P373": "commons_category",
    "P1712": "metacritic",
}

# Reference text that names no comic at all. These appear in `issue_range` as
# prose ("general mythology") or as a bare year, and resolving them would mean
# inventing a link.
NON_TITLES = {
    "", "various", "general mythology", "ongoing comic", "n/a", "none",
    "original", "unknown", "various comics", "general", "original to mcu",
}


def norm(s):
    """Comparison form: no accents, no articles, no punctuation."""
    s = unicodedata.normalize("NFKD", (s or "").lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"\(.*?\)", " ", s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    s = " ".join(s.split())
    return re.sub(r"^the ", "", s)


ISSUE_RE = re.compile(r"#\s*(\d+)(?:\s*[-–—]\s*#?\s*(\d+))?")


def parse_ref(title, extra):
    """Split a reference into (kind, series_name, [issue numbers], display).

    The `#NN` can sit in either column — `source_material` puts the whole
    citation in `issue_range` for some rows and splits it across both for
    others — so both are searched, and the series name is whatever precedes it.
    """
    title = (title or "").strip()
    extra = (extra or "").strip()
    for field, other in ((extra, title), (title, extra)):
        m = ISSUE_RE.search(field)
        if not m:
            continue
        lo = int(m.group(1))
        hi = int(m.group(2)) if m.group(2) else lo
        if hi < lo or hi - lo > 60:      # a malformed range, not a run
            hi = lo
        series = field[: m.start()].strip(" ,;:-–—")
        if not series or norm(series) in NON_TITLES:
            series = other
        series = re.sub(r"\b(debut|first appearance|origin)\b", "", series,
                        flags=re.I).strip(" ,;:-–—")
        if not series:
            continue
        return "issue", series, list(range(lo, hi + 1)), f"{series} #{m.group(0)[1:].strip()}"
    if not title or norm(title) in NON_TITLES:
        return None, None, [], None
    # No issue number: a series title, or the name of a storyline.
    return "title", title, [], title


def load_refs():
    """Every comic reference the database holds, with where it came from."""
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    refs = []
    for r in con.execute("SELECT * FROM source_material ORDER BY id"):
        kind, series, issues, disp = parse_ref(r["comic_title"], r["issue_range"])
        if not kind:
            continue
        refs.append({"origin": "source_material", "origin_id": r["id"],
                     "work_id": r["work_id"], "kind": kind, "name": series,
                     "issues": issues, "display": disp, "year": r["comic_year"]})
    for r in con.execute("SELECT id, canonical_name, first_comic_title, first_comic_year"
                         " FROM character_identities WHERE first_comic_title IS NOT NULL"):
        kind, series, issues, disp = parse_ref(r["first_comic_title"], "")
        if not kind:
            continue
        refs.append({"origin": "character_identities", "origin_id": r["id"],
                     "work_id": None, "kind": kind, "name": series,
                     "issues": issues, "display": disp, "year": r["first_comic_year"]})
    con.close()
    return refs


def load_character_seeds():
    """First-appearance issues and comics-shaped `present in work` values from v3."""
    p = V3 / "characters_wikidata.json"
    if not p.exists():
        return {}, set()
    with open(p, encoding="utf-8") as f:
        d = json.load(f)
    debuts, piw = {}, set()
    for iid, c in (d.get("characters") or {}).items():
        if c.get("first_appearance_qid"):
            debuts[int(iid)] = c["first_appearance_qid"]
        for q in (c.get("props") or {}).get("present_in_work") or []:
            piw.add(q)
    return debuts, piw


def subclass_closure(qids, roots, refresh=False):
    """Which of `qids` reduce to one of `roots` through P279*."""
    qids = sorted(q for q in qids if q)
    if not qids:
        return set()
    keep = set()
    for i in range(0, len(qids), 200):
        chunk = qids[i:i + 200]
        vals = " ".join(f"wd:{q}" for q in chunk)
        rts = " ".join(f"wd:{q}" for q in roots)
        rows = W.sparql(f"""SELECT DISTINCT ?c WHERE {{
          VALUES ?c {{ {vals} }} VALUES ?r {{ {rts} }} ?c wdt:P279* ?r . }}""", refresh)
        keep.update(b["c"]["value"].rsplit("/", 1)[-1] for b in rows)
    return keep


def search_variants(name):
    """Query strings to try for one reference title.

    The citations are written for a reader, not a database: "Spider-Man comics",
    "Spider-Man (Marvel Comics)" and "The Amazing Spider-Man" all mean a series
    whose Wikidata label is none of those.
    """
    out, seen = [], set()
    base = name.strip()
    cands = [base,
             re.sub(r"\s*\(.*?\)\s*", " ", base).strip(),
             re.sub(r"\b(comics|comic|series|storyline|elements|general mythology)\b",
                    " ", base, flags=re.I).strip(" ,;:-"),
             ]
    for c in list(cands):
        if c and not c.lower().startswith("the "):
            cands.append("The " + c)
        if c.lower().startswith("the "):
            cands.append(c[4:])
    for c in cands:
        c = " ".join(c.split())
        if c and c.lower() not in seen and norm(c) not in NON_TITLES:
            seen.add(c.lower())
            out.append(c)
    return out[:5]


def backlink_counts(qids, refresh=False):
    """How many items name each candidate as their series (P179)."""
    counts = defaultdict(int)
    qids = sorted(qids)
    for i in range(0, len(qids), 120):
        vals = " ".join(f"wd:{q}" for q in qids[i:i + 120])
        rows = W.sparql(f"""SELECT ?s (COUNT(?i) AS ?n) WHERE {{
          VALUES ?s {{ {vals} }} ?i wdt:P179 ?s . }} GROUP BY ?s""", refresh)
        for b in rows:
            counts[b["s"]["value"].rsplit("/", 1)[-1]] = int(b["n"]["value"])
    return counts


def resolve_titles(names, refresh=False):
    """name -> candidate comic QIDs, best first, plus why the rest were rejected.

    A name resolves to a *list*: Wikidata files "Amazing Spider-Man" under three
    items and only one carries the issues, so the caller looks in all of them.
    """
    def search(n):
        ids = []
        for v in search_variants(n):
            for h in W.wbsearch(v, limit=15, refresh=refresh):
                if h["id"] not in ids:
                    ids.append(h["id"])
        return n, ids

    cands = {}
    with ThreadPoolExecutor(max_workers=6) as ex:
        for n, ids in ex.map(search, names):
            cands[n] = ids
    all_q = sorted({q for v in cands.values() for q in v})
    W.log(f"  {len(all_q)} candidate items for {len(names)} reference titles")
    ents = W.entities_bulk(all_q, props="claims|labels|aliases|sitelinks|descriptions",
                           refresh=refresh, languages=W.LANGS)
    p31 = {c for e in ents.values() if isinstance(e, dict) for c in W.pvalues(e, "P31")}
    comicish = subclass_closure(p31, COMIC_ROOTS, refresh)
    seriesish = subclass_closure(p31, SERIES_ROOTS, refresh)
    links = backlink_counts(
        {q for q, e in ents.items()
         if isinstance(e, dict) and set(W.pvalues(e, "P31")) & seriesish}, refresh)

    out, rejected = {}, {}
    for n, ids in cands.items():
        want = norm(n)
        scored, other = [], None
        for q in ids:
            e = ents.get(q)
            if not isinstance(e, dict):
                continue
            names_ = {norm(W.en_label(e))} | {norm(a) for a in W.en_aliases(e)}
            names_.discard("")
            if want not in names_:
                continue
            types = set(W.pvalues(e, "P31"))
            if not types & comicish:
                if other is None:
                    other = (e.get("descriptions", {}).get("en", {}) or {}).get("value")
                continue
            # The item that actually holds the issues is the one meant, by a
            # margin nothing else can outweigh.
            s = min(links.get(q, 0), 400) / 20.0
            if types & seriesish:
                s += 3.0
            if MARVEL in W.pvalues(e, "P123"):
                s += 2.0
            if e.get("sitelinks", {}).get("enwiki"):
                s += 0.5
            s += min(len(e.get("claims", {})) / 60.0, 1.0)
            scored.append((s, q))
        if scored:
            scored.sort(reverse=True)
            out[n] = [q for _, q in scored]
        elif other:
            rejected[n] = other
    return out, ents, seriesish, rejected


def series_issues(series_qids, refresh=False):
    """(series_qid, issue number) -> issue QID, for every listed issue."""
    index, members = {}, defaultdict(set)

    def one(sq):
        rows = W.sparql(f"""SELECT ?i ?iLabel ?num ?date WHERE {{
          ?i wdt:P179 wd:{sq} .
          OPTIONAL {{ ?i wdt:P433 ?num }}
          OPTIONAL {{ ?i wdt:P577 ?date }}
          SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
        }} LIMIT 3000""", refresh)
        return sq, rows

    with ThreadPoolExecutor(max_workers=4) as ex:
        for sq, rows in ex.map(one, sorted(series_qids)):
            for b in rows:
                q = b["i"]["value"].rsplit("/", 1)[-1]
                members[sq].add(q)
                num = None
                if "num" in b:
                    m = re.search(r"\d+", b["num"]["value"])
                    if m:
                        num = int(m.group(0))
                if num is None and "iLabel" in b:
                    m = ISSUE_RE.search(b["iLabel"]["value"])
                    if m:
                        num = int(m.group(1))
                if num is not None:
                    index.setdefault((sq, num), q)
    return index, members


def is_marvel_comic(e, comicish):
    if not isinstance(e, dict):
        return False
    if MARVEL in W.pvalues(e, "P123"):
        return True
    if set(W.pvalues(e, "P31")) & comicish:
        desc = (e.get("descriptions", {}).get("en", {}) or {}).get("value", "").lower()
        return "marvel" in desc or "spider-man" in desc
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()

    refs = load_refs()
    debuts, piw = load_character_seeds()
    W.log(f"{len(refs)} comic references, {len(debuts)} character debut items, "
          f"{len(piw)} 'present in work' items")

    # -- 1. titles -----------------------------------------------------------
    names = sorted({r["name"] for r in refs})
    W.log(f"resolving {len(names)} distinct reference titles")
    cand_qids, cand_ents, seriesish, rejected = resolve_titles(names, args.refresh)
    W.log(f"  {len(cand_qids)} resolved to a comics item, "
          f"{len(rejected)} matched something that is not a comic")

    # Every candidate that is a container gets its issues listed, not just the
    # best-scoring one: the duplicates are how Wikidata files a long run.
    series_qids = {q for qs in cand_qids.values() for q in qs
                   if set(W.pvalues(cand_ents.get(q, {}), "P31")) & seriesish}
    W.log(f"  {len(series_qids)} candidate series; listing their issues")
    index, members = series_issues(series_qids, args.refresh)
    W.log(f"  {sum(len(v) for v in members.values())} issue items, "
          f"{len(index)} with a usable number")

    # -- 2. match every reference -------------------------------------------
    matched, unresolved, parsed = [], [], {}
    for r in refs:
        qs = cand_qids.get(r["name"]) or []
        if not qs:
            why = ("names something that is not a comic: " + rejected[r["name"]]
                   if r["name"] in rejected else "no comics item matched the title")
            unresolved.append({**r, "reason": why})
            continue
        best = qs[0]
        if r["kind"] == "title":
            matched.append({**r, "comic_qid": best, "comic_key": best,
                            "match": "title"})
            continue
        # Prefer the series that carries the issue; fall back to the best-scoring.
        home = next((q for q in qs
                     if any((q, n) in index for n in r["issues"])), None)
        if home:
            for n in r["issues"]:
                q = index.get((home, n))
                if q:
                    matched.append({**r, "comic_qid": q, "comic_key": q,
                                    "series_qid": home, "issue_number": n,
                                    "match": "issue"})
                else:
                    parsed[(home, n)] = r["name"]
                    matched.append({**r, "comic_qid": None,
                                    "comic_key": f"parsed:{home}:{n}",
                                    "series_qid": home, "issue_number": n,
                                    "match": "parsed"})
            continue
        series_home = next((q for q in qs
                            if set(W.pvalues(cand_ents.get(q, {}), "P31")) & seriesish),
                           None)
        if series_home:
            # The series is known; Wikidata just has no item for these issues.
            for n in r["issues"]:
                parsed[(series_home, n)] = r["name"]
                matched.append({**r, "comic_qid": None,
                                "comic_key": f"parsed:{series_home}:{n}",
                                "series_qid": series_home, "issue_number": n,
                                "match": "parsed"})
            continue
        unresolved.append({**r, "reason": "title resolved to a single comic, not a series"})
    n_wd = sum(1 for m in matched if m["comic_qid"])
    W.log(f"  {len(matched)} references matched ({n_wd} to a Wikidata item, "
          f"{len(matched) - n_wd} parsed from the citation), "
          f"{len(unresolved)} unresolved")

    # -- 3. everything we now want a full record for -------------------------
    wanted = {m["comic_qid"] for m in matched if m["comic_qid"]}
    wanted |= {m["series_qid"] for m in matched if m.get("series_qid")}
    wanted |= set(debuts.values())
    wanted |= series_qids
    # 'present in work' is mostly films and games; keep only the comics.
    piw_ents = W.entities_bulk(sorted(piw - wanted), props="claims|labels",
                               refresh=args.refresh, languages=W.LANGS)
    piw_p31 = {c for e in piw_ents.values() if isinstance(e, dict) for c in W.pvalues(e, "P31")}
    piw_comic = subclass_closure(piw_p31, COMIC_ROOTS, args.refresh)
    wanted |= {q for q, e in piw_ents.items()
               if isinstance(e, dict) and set(W.pvalues(e, "P31")) & piw_comic}
    W.log(f"fetching {len(wanted)} comic items in full")
    ents = W.entities_bulk(sorted(wanted), props="claims|labels|sitelinks|descriptions",
                           refresh=args.refresh, languages=W.LANGS)

    all_p31 = {c for e in ents.values() if isinstance(e, dict) for c in W.pvalues(e, "P31")}
    comicish = subclass_closure(all_p31, COMIC_ROOTS, args.refresh)
    seriesish = subclass_closure(all_p31, SERIES_ROOTS, args.refresh)

    comics, creator_qids, ref_qids = {}, set(), set()
    for q, e in ents.items():
        if not isinstance(e, dict):
            continue
        types = set(W.pvalues(e, "P31"))
        label = W.en_label(e)
        if types & seriesish:
            kind = "series"
        elif types & comicish:
            kind = "issue"
        else:
            kind = "storyline"
        dates = [W.wd_time_to_iso(t) for t in W.pvalues(e, "P577")]
        dates = sorted(d for d in dates if d)
        num = None
        for raw in W.pvalues(e, "P433"):
            m = re.search(r"\d+", str(raw))
            if m:
                num = int(m.group(0))
                break
        if num is None and label:
            m = ISSUE_RE.search(label)
            if m:
                num = int(m.group(1))
        credits = {}
        for prop, role in CREDIT_PROPS.items():
            vs = W.pvalues(e, prop)
            if vs:
                credits[role] = vs
                creator_qids.update(vs)
        ext = {}
        for prop, name in COMIC_EXT_IDS.items():
            v = W.pfirst(e, prop)
            if isinstance(v, str):
                ext[name] = v
        rec = {
            "qid": q,
            "kind": kind,
            "title": label,
            "description": (e.get("descriptions", {}).get("en", {}) or {}).get("value"),
            "enwiki": (e.get("sitelinks", {}).get("enwiki", {}) or {}).get("title"),
            "series_qid": W.pfirst(e, "P179"),
            "issue_number": num,
            "publication_date": dates[0] if dates else None,
            "cover_date": dates[-1] if len(dates) > 1 else None,
            "publisher_qid": W.pfirst(e, "P123"),
            "country_qid": W.pfirst(e, "P495"),
            "language_qid": W.pfirst(e, "P407"),
            "follows_qid": W.pfirst(e, "P155"),
            "followed_by_qid": W.pfirst(e, "P156"),
            "characters": W.pvalues(e, "P674"),
            "credits": credits,
            "external_ids": ext,
        }
        comics[q] = rec
        ref_qids.update(x for x in (rec["series_qid"], rec["publisher_qid"],
                                    rec["country_qid"], rec["language_qid"]) if x)
        ref_qids.update(rec["characters"])

    # Issues the citations name that Wikidata has no item for. The series and the
    # number come straight out of the reference, so the row is real; everything
    # an item would have supplied — date, publisher, credits — stays null.
    for (sq, num), name in sorted(parsed.items(), key=lambda kv: (kv[1], kv[0][1])):
        stitle = (comics.get(sq) or {}).get("title") or name
        comics[f"parsed:{sq}:{num}"] = {
            "qid": None, "kind": "issue", "title": f"{stitle} #{num}",
            "description": None, "enwiki": None, "series_qid": sq,
            "issue_number": num, "publication_date": None, "cover_date": None,
            "publisher_qid": (comics.get(sq) or {}).get("publisher_qid"),
            "country_qid": None, "language_qid": None, "follows_qid": None,
            "followed_by_qid": None, "characters": [], "credits": {},
            "external_ids": {}, "origin": "parsed",
        }

    # -- 4. the creators -----------------------------------------------------
    W.log(f"fetching {len(creator_qids)} creators")
    cents = W.entities_bulk(sorted(creator_qids),
                            props="claims|labels|sitelinks|descriptions",
                            refresh=args.refresh, languages=W.LANGS)
    creators = {}
    for q, e in cents.items():
        if not isinstance(e, dict):
            continue
        creators[q] = {
            "qid": q,
            "name": W.en_label(e),
            "enwiki": (e.get("sitelinks", {}).get("enwiki", {}) or {}).get("title"),
            "birth_date": W.wd_time_to_iso(W.pfirst(e, "P569")),
            "death_date": W.wd_time_to_iso(W.pfirst(e, "P570")),
            "gender_qid": W.pfirst(e, "P21"),
            "citizenship_qids": W.pvalues(e, "P27"),
            "occupation_qids": W.pvalues(e, "P106"),
            "imdb": W.pfirst(e, "P345"),
            "comic_vine": W.pfirst(e, "P5905"),
        }
        ref_qids.update(creators[q]["citizenship_qids"])
        ref_qids.update(creators[q]["occupation_qids"])
        if creators[q]["gender_qid"]:
            ref_qids.add(creators[q]["gender_qid"])

    W.log(f"labelling {len(ref_qids)} referenced items")
    labels = W.qid_labels(ref_qids, args.refresh, languages=W.LANGS)

    V4.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"comics": comics, "creators": creators, "labels": labels,
                   "matches": matched, "unresolved": unresolved,
                   "character_debuts": {str(k): v for k, v in debuts.items()}},
                  f, indent=1, sort_keys=True, ensure_ascii=False)
    W.log(f"wrote {OUT}")
    by_kind = defaultdict(int)
    for c in comics.values():
        by_kind[c["kind"]] += 1
    W.log(f"  {len(comics)} comics ({dict(by_kind)}), {len(creators)} creators, "
          f"{sum(len(c['credits']) for c in comics.values())} credited roles")


if __name__ == "__main__":
    main()
