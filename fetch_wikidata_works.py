#!/usr/bin/env python3
"""fetch_wikidata_works.py — resolve every work in `media_works` to a Wikidata item.

Writes data_raw/v3/works_wikidata.json: the id map plus the enrichment pulled off
each item (review scores, box office, budget, awards, genres, ratings, external
ids, ...). build_db_v3.py reads that file offline, so the build stays reproducible
without a network connection.

    python3 fetch_wikidata_works.py [--refresh] [--only 'Venom']

Resolution
----------
A blind label search is not trustworthy — "Spider-Man" alone matches a comics
character, eight films and a 1969 series. So a candidate is only accepted when it
agrees with the row we already hold on *two* independent axes: its P31 must reduce
(through P279*) to the class implied by our media_type, and its release year must
land within a year of ours. Title similarity only breaks ties between survivors.
Anything that fails is left unresolved and reported, because a wrong item would
import a wrong film's box office.
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
OUT_DIR = HERE / "data_raw" / "v3"
OUT = OUT_DIR / "works_wikidata.json"

# Root classes per media_type; a candidate's P31 must be one of these or a
# subclass of one.
ROOTS = {
    "movie": ["Q11424", "Q2431196"],          # film, audiovisual work→film-ish
    "tv_show": ["Q5398426", "Q15416", "Q581714"],  # TV series, TV programme, animated series
    "game": ["Q7889"],                         # video game
}
# Classes that must never be accepted for a media_type even if P279* says yes.
BLOCK = {
    "movie": {"Q24856", "Q7889", "Q5398426", "Q1107"},   # film series, game, TV series, anime
    "tv_show": {"Q11424", "Q7889", "Q24856"},
    "game": {"Q11424", "Q5398426", "Q24856", "Q7058673"},
}

# Hand-checked ids for works whose title alone cannot resolve them. Each was
# confirmed against the item's own release date and franchise links.
OVERRIDES = {
    # (title, year, media_type): qid  — or None to declare "no Wikidata item".
    # Each was checked against the item's own P31, release dates and platforms.

    # Sony's announced spin-off, not the unrelated 2007 film of the same name.
    # Filed as a film project (Q18011172) because it has not been released.
    ("El Muerto", None, "movie"): "Q114429919",

    # The 1970s live-action films: their items are labelled for the TV pilots
    # they were cut from, so a title search lands on the wrong side.
    ("Spider-Man", 1977, "movie"): "Q1831060",
    ("Spider-Man (Toei)", 1978, "movie"): "Q28135875",

    # Insomniac's line. Without these, all four collapse onto the 2018 game.
    ("Marvel's Spider-Man 2", 2023, "game"): "Q108479502",
    ("Marvel's Spider-Man: The City That Never Sleeps", 2018, "game"): "Q65040551",
    ("Marvel's Spider-Man 3", None, "game"): None,   # announced only, no item yet

    # Two different 1990 games share a title. Q1751705 lists DOS/C64/ZX/Atari ST,
    # Q3280776 is the Game Boy release.
    ("The Amazing Spider-Man (1990 computer)", 1990, "game"): "Q1751705",
    ("The Amazing Spider-Man (1990 Game Boy)", 1990, "game"): "Q3280776",

    # Distinct from The Punisher (1991 NES), which the search prefers.
    ("The Punisher: The Ultimate Payback!", 1991, "game"): "Q28126678",
}

# Review outlets we know how to normalise, keyed by the P447 reviewer item.
REVIEWERS = {
    "Q105584": ("Rotten Tomatoes", "critic"),
    "Q150248": ("Metacritic", "critic"),
    "Q37312": ("IMDb", "user"),
    "Q844330": ("Allmovie", "critic"),
    "Q1149822": ("AlloCiné", "critic"),
    "Q2001305": ("Kinopoisk", "user"),
    "Q3392672": ("FilmAffinity", "user"),
    "Q6023698": ("IGN", "critic"),
    "Q1137616": ("GameRankings", "critic"),
    "Q1132059": ("GameSpot", "critic"),
    "Q4165246": ("Bechdel Test", "other"),
}

# External identifier properties worth carrying into the dataset.
EXT_ID_PROPS = {
    "P345": "imdb", "P1258": "rotten_tomatoes", "P1712": "metacritic",
    "P4947": "tmdb_movie", "P4983": "tmdb_tv", "P1874": "netflix",
    "P2603": "kinopoisk", "P3302": "douban", "P2508": "kinenote",
    "P480": "filmaffinity", "P1237": "box_office_mojo", "P2509": "movie_meter",
    "P905": "porthu", "P1265": "allocine", "P2334": "swedish_film",
    "P3138": "omdb_ofdb", "P6466": "hulu", "P5786": "vgmdb",
    "P1733": "steam", "P2725": "gog", "P4415": "igdb", "P5944": "giant_bomb",
    "P1651": "youtube_trailer", "P856": "official_website",
    "P373": "commons_category", "P646": "freebase", "P214": "viaf",
    "P2704": "eidr", "P7502": "giphy", "P12196": "letterboxd",
    "P9586": "apple_tv", "P3808": "the_numbers", "P3417": "quora",
    "P6839": "tv_tropes", "P1712_alt": "metacritic_alt",
}

# Scalar / list properties lifted onto the work.
LIST_PROPS = {
    "P136": "genre", "P495": "country", "P364": "original_language",
    "P462": "color", "P915": "filming_location", "P840": "narrative_location",
    "P400": "platform", "P404": "game_mode", "P437": "distribution_format",
    "P2635": "number_of_parts",
}


def norm(s):
    s = unicodedata.normalize("NFKD", (s or "").lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"\(.*?\)", " ", s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return " ".join(s.split())


def load_works():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    rows = [
        dict(r)
        for r in con.execute(
            "SELECT id, title, release_year, release_date, media_type FROM media_works ORDER BY id"
        )
    ]
    con.close()
    return rows


# ---------------------------------------------------------------------------
# candidate gathering + scoring
# ---------------------------------------------------------------------------
def search_terms(w):
    t = w["title"]
    terms = [t]
    bare = re.sub(r"\s*\(.*?\)\s*", " ", t).strip()
    if bare and bare != t:
        terms.append(bare)
    if w["media_type"] == "game" and "Spider" in bare:
        terms.append(f"{bare} video game")
    if w["release_year"]:
        terms.append(f"{bare} {w['release_year']}")
    seen, out = set(), []
    for x in terms:
        if x.lower() not in seen:
            seen.add(x.lower())
            out.append(x)
    return out


def subclass_closure(class_qids, roots):
    """{class_qid: set(root_qids it reduces to)} via one SPARQL round trip."""
    if not class_qids:
        return {}
    vals = " ".join(f"wd:{q}" for q in sorted(class_qids))
    root_vals = " ".join(f"wd:{q}" for q in sorted(roots))
    q = f"""SELECT ?c ?root WHERE {{
      VALUES ?c {{ {vals} }}
      VALUES ?root {{ {root_vals} }}
      ?c wdt:P279* ?root .
    }}"""
    out = defaultdict(set)
    for b in W.sparql(q):
        out[b["c"]["value"].rsplit("/", 1)[-1]].add(b["root"]["value"].rsplit("/", 1)[-1])
    return out


def score(work, ent, closure):
    """Return (score, reasons) — None if the candidate is disqualified."""
    if not ent:
        return None
    mt = work["media_type"]
    p31 = W.pvalues(ent, "P31")
    if any(c in BLOCK[mt] for c in p31):
        return None
    ok_class = any(closure.get(c) for c in p31)
    if not ok_class:
        return None

    years = sorted({W.wd_year(t) for t in W.pvalues(ent, "P577")} - {None})
    # Games also carry per-platform dates; TV uses start time.
    for p in ("P580", "P571"):
        years += [y for y in (W.wd_year(t) for t in W.pvalues(ent, p)) if y]
    ours = work["release_year"]
    year_ok = None
    if ours and years:
        best = min(abs(y - ours) for y in years)
        if best > 1:
            return None
        year_ok = best
    elif ours and not years:
        year_ok = None  # unknown, not disqualifying

    label = (ent.get("labels", {}).get("en", {}) or {}).get("value", "")
    aliases = [a.get("value", "") for a in ent.get("aliases", {}).get("en", [])]
    nt = norm(work["title"])
    names = [norm(label)] + [norm(a) for a in aliases]
    exact = nt in names
    partial = any(nt and (nt in n or n in nt) for n in names if n)

    s = 0.0
    s += 4.0 if exact else (1.5 if partial else 0.0)
    if year_ok is not None:
        s += 3.0 - year_ok
    # A Spider-Man item should sit in the franchise somehow.
    linked = set(W.pvalues(ent, "P179")) | set(W.pvalues(ent, "P8345")) | set(
        W.pvalues(ent, "P144")
    )
    if linked:
        s += 0.5
    s += min(len(ent.get("claims", {})) / 100.0, 1.5)  # richer item wins ties
    if ent.get("sitelinks", {}).get("enwiki"):
        s += 0.5
    reasons = f"class={'/'.join(p31[:2])} year_delta={year_ok} exact={exact}"
    return (s, reasons)


def resolve(works, refresh=False):
    # 1. gather candidates
    cand_by_work = {}

    def do_search(w):
        seen, out = set(), []

        def add(qid):
            if qid and qid not in seen:
                seen.add(qid)
                out.append(qid)

        # Our titles frequently *are* the Wikipedia article title, disambiguator
        # and all — "Spider-Man (1967 TV series)" resolves in one hop, where a
        # label search for "Spider-Man" drowns in the franchise.
        for term in search_terms(w):
            add(W.wp_qid(term, refresh=refresh))
        for term in search_terms(w):
            for hit in W.wbsearch(term, limit=25, refresh=refresh):
                add(hit["id"])
        if len(out) < 3:
            hint = {"movie": "film", "tv_show": "television series", "game": "video game"}[
                w["media_type"]
            ]
            year = w["release_year"] or ""
            for t in W.wp_search(f"{w['title']} {hint} {year}", refresh=refresh):
                add(W.wp_qid(t, refresh=refresh))
        return w["id"], out

    with ThreadPoolExecutor(max_workers=8) as ex:
        for wid, qids in ex.map(do_search, works):
            cand_by_work[wid] = qids

    all_qids = sorted({q for v in cand_by_work.values() for q in v})
    W.log(f"  {len(all_qids)} candidate items across {len(works)} works")

    # 2. bulk-fetch their claims
    ents = W.entities_bulk(all_qids, props="claims|labels|aliases|sitelinks", refresh=refresh)

    # 3. one closure query covering every P31 seen
    p31s = {c for e in ents.values() if isinstance(e, dict) for c in W.pvalues(e, "P31")}
    all_roots = sorted({r for v in ROOTS.values() for r in v})
    closure_all = subclass_closure(p31s, all_roots)

    resolved, unresolved = {}, []
    for w in works:
        key = (w["title"], w["release_year"], w["media_type"])
        if key in OVERRIDES:
            if OVERRIDES[key]:
                resolved[w["id"]] = {"qid": OVERRIDES[key], "method": "override", "score": 99}
            else:
                unresolved.append((w, "declared absent"))
            continue
        roots = set(ROOTS[w["media_type"]])
        closure = {c: (rs & roots) for c, rs in closure_all.items() if rs & roots}
        scored = []
        for q in cand_by_work[w["id"]]:
            r = score(w, ents.get(q), closure)
            if r:
                scored.append((r[0], q, r[1]))
        scored.sort(reverse=True)
        if not scored:
            unresolved.append((w, "no candidate passed class+year"))
            continue
        top = scored[0]
        method = "unique" if len(scored) == 1 else (
            "clear" if len(scored) == 1 or top[0] - scored[1][0] >= 1.0 else "close"
        )
        resolved[w["id"]] = {
            "qid": top[1], "method": method, "score": round(top[0], 2),
            "why": top[2],
            "runner_up": None if len(scored) == 1 else f"{scored[1][1]} ({scored[1][0]:.1f})",
        }

    # One item may back only one work. Sequels, DLC and same-title-different-year
    # games otherwise collapse onto whichever item the search liked best, and
    # that item's box office would then be copied onto every one of them. The
    # best-scoring claimant keeps it; the rest are reported, not guessed at.
    by_qid = defaultdict(list)
    for wid, r in resolved.items():
        by_qid[r["qid"]].append(wid)
    titles = {w["id"]: w for w in works}
    for qid, wids in by_qid.items():
        if len(wids) < 2:
            continue
        keep = max(wids, key=lambda i: (resolved[i]["method"] == "override", resolved[i]["score"]))
        for wid in wids:
            if wid != keep:
                other = titles[keep]["title"]
                unresolved.append(
                    (titles[wid], f"{qid} already claimed by {other!r}")
                )
                del resolved[wid]
    return resolved, unresolved


# ---------------------------------------------------------------------------
# enrichment extraction
# ---------------------------------------------------------------------------
def extract(ent, qid):
    """Pull everything v3 wants off one work item."""
    out = {"qid": qid}

    out["label"] = (ent.get("labels", {}).get("en", {}) or {}).get("value")
    out["enwiki"] = (ent.get("sitelinks", {}).get("enwiki", {}) or {}).get("title")

    # --- review scores: P444, qualified by reviewer (P447) -----------------
    reviews = []
    for st in W.claims(ent, "P444"):
        raw = W.snak_value(st.get("mainsnak"))
        if not isinstance(raw, str):
            continue
        rev = W.qual_first(st, "P447")
        reviews.append({
            # `reviewer` is only a hint from the known-outlet table; the build
            # falls back to the label of reviewer_qid so outlets outside the
            # table still come through named.
            "reviewer_qid": rev,
            "reviewer": REVIEWERS.get(rev, (None, None))[0],
            "kind": REVIEWERS.get(rev, (None, None))[1],
            "raw": raw.strip(),
            "n_reviews": W.quantity_amount(W.qual_first(st, "P7887"))
                         or W.quantity_amount(W.qual_first(st, "P5045")),
            "point_in_time": W.wd_time_to_iso(W.qual_first(st, "P585")),
            "method": W.qual_first(st, "P459"),
            "platform": W.qual_first(st, "P400"),
        })
    out["reviews"] = reviews

    # --- money --------------------------------------------------------------
    box = []
    for st in W.claims(ent, "P2142"):
        amt = W.quantity_amount(W.snak_value(st.get("mainsnak")))
        if amt is None:
            continue
        box.append({
            "amount": amt,
            "unit": (W.snak_value(st.get("mainsnak")) or {}).get("unit", "").rsplit("/", 1)[-1],
            "place": W.qual_first(st, "P3005"),
            "point_in_time": W.wd_time_to_iso(W.qual_first(st, "P585")),
            "determination": W.qual_first(st, "P459"),
        })
    out["box_office"] = box

    cost = []
    for st in W.claims(ent, "P2130"):
        amt = W.quantity_amount(W.snak_value(st.get("mainsnak")))
        if amt is None:
            continue
        cost.append({
            "amount": amt,
            "unit": (W.snak_value(st.get("mainsnak")) or {}).get("unit", "").rsplit("/", 1)[-1],
            "of": W.qual_first(st, "P642") or W.qual_first(st, "P518"),
            "point_in_time": W.wd_time_to_iso(W.qual_first(st, "P585")),
        })
    out["cost"] = cost

    # --- awards: won (P166) and nominated (P1411) ---------------------------
    awards = []
    for prop, result in (("P166", "won"), ("P1411", "nominated")):
        for st in W.claims(ent, prop):
            aq = W.snak_value(st.get("mainsnak"))
            if not aq:
                continue
            awards.append({
                "award_qid": aq,
                "result": result,
                "year": W.wd_year(W.qual_first(st, "P585")),
                "for_work": W.qual_first(st, "P1686"),
                "winner": W.qual_first(st, "P1346"),
                "statement_subject": W.qual_first(st, "P805"),
                "together_with": W.qualifiers(st, "P1706"),
                "recipients": W.qualifiers(st, "P2453") + W.qualifiers(st, "P1346"),
            })
    out["awards"] = awards

    # --- classification / breadth ------------------------------------------
    for prop, name in LIST_PROPS.items():
        vs = W.pvalues(ent, prop)
        if vs:
            out.setdefault("props", {})[name] = vs

    # content rating, per rating authority
    ratings = []
    for st in W.claims(ent, "P1657"):
        ratings.append({
            "rating_qid": W.snak_value(st.get("mainsnak")),
            "country": W.qual_first(st, "P17"),
            "reason": W.qual_first(st, "P2676"),
        })
    out["ratings"] = ratings

    # release dates, per place
    rel = []
    for st in W.claims(ent, "P577"):
        t = W.snak_value(st.get("mainsnak"))
        if not t:
            continue
        rel.append({
            "date": W.wd_time_to_iso(t),
            "place": W.qual_first(st, "P291") or W.qual_first(st, "P17"),
            "event": W.qual_first(st, "P1032"),
        })
    out["release_dates"] = rel

    # duration in minutes
    dur = W.quantity_amount(W.pfirst(ent, "P2047"))
    if dur:
        out["duration_min"] = dur

    # cast with the character they played, straight off the film item
    cast = []
    for st in W.claims(ent, "P161"):
        cast.append({
            "person_qid": W.snak_value(st.get("mainsnak")),
            "character_qid": W.qual_first(st, "P453"),
            "character_name": W.qual_first(st, "P4633"),
            "order": W.quantity_amount(W.qual_first(st, "P1545")),
        })
    out["cast"] = cast
    out["characters"] = W.pvalues(ent, "P674")

    # crew: property -> [person qids]
    crew = {}
    for prop, role in (
        ("P57", "director"), ("P58", "screenwriter"), ("P86", "composer"),
        ("P162", "producer"), ("P344", "director of photography"),
        ("P1040", "film editor"), ("P2515", "costume designer"),
        ("P3174", "art director"), ("P4805", "make-up artist"),
        ("P1431", "executive producer"), ("P5126", "assistant director"),
        ("P175", "performer"), ("P178", "developer"), ("P123", "publisher"),
        ("P272", "production company"), ("P750", "distributor"),
        ("P170", "creator"), ("P1476", "title"),
    ):
        vs = W.pvalues(ent, prop)
        if vs:
            crew[role] = vs
    out["crew"] = crew

    # series links: follows / followed by / part of
    out["series"] = {
        "part_of": W.pvalues(ent, "P179"),
        "follows": W.pvalues(ent, "P155"),
        "followed_by": W.pvalues(ent, "P156"),
        "based_on": W.pvalues(ent, "P144"),
        "derivative": W.pvalues(ent, "P4969"),
        "has_part": W.pvalues(ent, "P527"),
    }

    # external ids
    ext = {}
    for prop, name in EXT_ID_PROPS.items():
        v = W.pfirst(ent, prop)
        if v and isinstance(v, str):
            ext[name] = v
    out["external_ids"] = ext

    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--only", help="substring filter on title, for spot checks")
    args = ap.parse_args()

    works = load_works()
    if args.only:
        works = [w for w in works if args.only.lower() in w["title"].lower()]
    W.log(f"resolving {len(works)} works against Wikidata")

    resolved, unresolved = resolve(works, args.refresh)
    W.log(f"  resolved {len(resolved)}, unresolved {len(unresolved)}")

    # full entity per resolved work, in parallel
    qids = [r["qid"] for r in resolved.values()]
    ents = {}
    with ThreadPoolExecutor(max_workers=8) as ex:
        for q, e in zip(qids, ex.map(lambda q: W.entity(q, args.refresh), qids)):
            ents[q] = e

    by_work = {}
    for wid, r in resolved.items():
        e = ents.get(r["qid"])
        if not e:
            continue
        data = extract(e, r["qid"])
        data["match"] = {k: r[k] for k in ("method", "score", "why", "runner_up") if k in r}
        by_work[str(wid)] = data

    # Every QID the payload references needs an English label here, or the
    # offline build would have nothing to write into a text column.
    ref = set()

    def collect(obj):
        if isinstance(obj, str):
            if re.fullmatch(r"Q\d+", obj):
                ref.add(obj)
        elif isinstance(obj, dict):
            for v in obj.values():
                collect(v)
        elif isinstance(obj, list):
            for v in obj:
                collect(v)

    collect(by_work)
    W.log(f"  labelling {len(ref)} referenced items")
    labels = W.qid_labels(ref, args.refresh)

    titles = {str(w["id"]): w["title"] for w in works}
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "works": by_work,
        "labels": labels,
        "titles": titles,
        "unresolved": [
            {"id": w["id"], "title": w["title"], "year": w["release_year"],
             "media_type": w["media_type"], "reason": why}
            for w, why in unresolved
        ],
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=1, sort_keys=True, ensure_ascii=False)
    W.log(f"wrote {OUT}")

    # report
    nrev = sum(len(d["reviews"]) for d in by_work.values())
    nbox = sum(len(d["box_office"]) for d in by_work.values())
    naw = sum(len(d["awards"]) for d in by_work.values())
    W.log(f"  {nrev} review statements, {nbox} box-office statements, {naw} award statements")
    for u in payload["unresolved"]:
        W.log(f"  UNRESOLVED {u['title']} ({u['year']}, {u['media_type']}): {u['reason']}")
    close = [(titles[k], d["match"]) for k, d in by_work.items() if d["match"].get("method") == "close"]
    for t, m in close:
        W.log(f"  CLOSE CALL {t}: {m}")


if __name__ == "__main__":
    main()
