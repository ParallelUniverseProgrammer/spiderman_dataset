#!/usr/bin/env python3
"""fetch_reception.py — review scores for the works Wikidata does not carry.

Writes data_raw/v3/reception.json. v2 has review scores for 30 of 81 works and
only one of the 23 films; Wikidata's P444 covers about half the gap, mostly on
the films. This closes the rest from the English Wikipedia articles.

    python3 fetch_reception.py [--refresh] [--only 'Shattered']

Two shapes of source
--------------------
Games use `{{Video game reviews}}`, a template whose parameters are outlet codes
(`MC`, `IGN`, `GSpot`, ...), so those come out structured. Films and series state
their aggregate scores in Reception prose instead — "holds an approval rating of
90% based on 350 reviews" — which is matched with explicit patterns anchored on
the outlet name. Anything that does not match a pattern is skipped rather than
guessed at, and every score keeps the sentence it came from so a reader can
check it.
"""
import argparse
import json
import re
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import wdlib as W
from fetch_episodes import clean, find_templates, split_params, template_params

HERE = Path(__file__).resolve().parent
DB = HERE / "spiderman.db"
V3 = HERE / "data_raw" / "v3"
OUT = V3 / "reception.json"

# {{Video game reviews}} parameter -> (publication, max score). Max is the scale
# the outlet publishes on; a value that carries its own "/n" overrides it.
VG_OUTLETS = {
    "MC": ("Metacritic", 100), "GR": ("GameRankings", 100), "OC": ("OpenCritic", 100),
    "IGN": ("IGN", 10), "GSpot": ("GameSpot", 10), "GameSpot": ("GameSpot", 10),
    "EuroG": ("Eurogamer", 10), "Edge": ("Edge", 10), "EGM": ("Electronic Gaming Monthly", 10),
    "Fam": ("Famitsu", 40), "GI": ("Game Informer", 10), "GamePro": ("GamePro", 5),
    "GameSpy": ("GameSpy", 5), "GT": ("GameTrailers", 10), "Destruct": ("Destructoid", 10),
    "Poly": ("Polygon", 10), "GRadar": ("GamesRadar+", 5), "VG": ("VideoGamer.com", 10),
    "XPlay": ("X-Play", 5), "OPM": ("Official PlayStation Magazine", 10),
    "OXM": ("Official Xbox Magazine", 10), "ONM": ("Official Nintendo Magazine", 100),
    "NP": ("Nintendo Power", 10), "NGamer": ("NGamer", 100), "NWR": ("Nintendo World Report", 10),
    "PALGN": ("PALGN", 10), "TeamXbox": ("TeamXbox", 10), "GamesTM": ("GamesTM", 10),
    "PCGamer": ("PC Gamer", 100), "PCGUK": ("PC Gamer UK", 100), "PCGUS": ("PC Gamer US", 100),
    "CVG": ("Computer and Video Games", 10), "Hyper": ("Hyper", 100),
    "MEGA": ("MEGA", 100), "Allgame": ("Allgame", 5), "AV": ("The A.V. Club", 100),
    "Giantbomb": ("Giant Bomb", 5), "GamesMaster": ("GamesMaster", 100),
    "Jeuxvideo": ("Jeuxvideo.com", 20), "MeriStation": ("MeriStation", 10),
    "Gamekult": ("Gamekult", 10), "Vandal": ("Vandal", 10), "Multiplayerit": ("Multiplayer.it", 10),
    "Sushi": ("Spaziogames", 10), "3DJuegos": ("3DJuegos", 10),
}

# Aggregate-review prose. Each pattern must capture the score first.
FILM_PATTERNS = [
    ("Rotten Tomatoes", 100, re.compile(
        r"(?:approval rating|rating) of (\d{1,3})%[^.]{0,80}?based on (\d[\d,]*) (?:critic |professional )?reviews?",
        re.I)),
    ("Rotten Tomatoes", 100, re.compile(
        r"(\d{1,3})% (?:approval rating|of \d+ critics)[^.]{0,60}?based on (\d[\d,]*) reviews?", re.I)),
    ("Rotten Tomatoes", 100, re.compile(
        r"Rotten Tomatoes[^.]{0,120}?(\d{1,3})%[^.]{0,80}?(\d[\d,]*) reviews?", re.I)),
    ("Metacritic", 100, re.compile(
        r"Metacritic[^.]{0,160}?(\d{1,3}) out of 100[^.]{0,80}?(\d[\d,]*) critics?", re.I)),
    ("Metacritic", 100, re.compile(
        r"(?:weighted average |average )?score of (\d{1,3}) out of 100[^.]{0,80}?(\d[\d,]*) critics?",
        re.I)),
    ("Metacritic", 100, re.compile(
        r"Metacritic[^.]{0,160}?(\d{1,3})/100[^.]{0,80}?(\d[\d,]*) critics?", re.I)),
    ("CinemaScore", None, re.compile(
        r"CinemaScore[^.]{0,120}?grade of \"?([A-F][+-]?)\"?", re.I)),
]


def load_works():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    rows = [dict(r) for r in con.execute("""
        SELECT w.id, w.title, w.release_year, w.media_type,
               (SELECT COUNT(*) FROM review_scores r WHERE r.work_id = w.id) AS have
        FROM media_works w ORDER BY w.id""")]
    con.close()
    return rows


def wd_pages():
    p = V3 / "works_wikidata.json"
    if not p.exists():
        return {}
    with open(p, encoding="utf-8") as f:
        d = json.load(f)
    return {int(k): v.get("enwiki") for k, v in d.get("works", {}).items() if v.get("enwiki")}


# ---------------------------------------------------------------------------
def parse_vg_reviews(text):
    """Rows out of every {{Video game reviews}} in the article."""
    out = []
    for _, _, body in find_templates(text, "Video game reviews"):
        params = template_params(body)
        # Custom rows: rev1 = <outlet>, rev1Score = <score>
        customs = {}
        for k, v in params.items():
            m = re.fullmatch(r"rev(\d+)", k, re.I)
            if m:
                customs[m.group(1)] = clean(v)
        for k, raw in params.items():
            m = re.fullmatch(r"rev(\d+)Score", k, re.I)
            if m and customs.get(m.group(1)):
                for rec in split_scores(customs[m.group(1)], None, raw):
                    out.append(rec)
                continue
            base = re.sub(r"\d*$", "", k)
            if k in VG_OUTLETS or base in VG_OUTLETS:
                pub, mx = VG_OUTLETS.get(k) or VG_OUTLETS[base]
                out.extend(split_scores(pub, mx, raw))
    return out


SCORE_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:/|out of)\s*(\d+(?:\.\d+)?)")
PCT_RE = re.compile(r"(\d{1,3}(?:\.\d+)?)\s*%")
STAR_RE = re.compile(r"(\d(?:\.\d)?)\s*/\s*(\d)\s*stars?", re.I)
PLATFORM_RE = re.compile(r"\(([^()]{1,40})\)\s*$")


def split_scores(pub, default_max, raw):
    """One template value can hold several platform-tagged scores separated by
    <br/>: '84/100 (PS4)<br/>79/100 (XONE)'."""
    if not raw:
        return []
    out = []
    for chunk in re.split(r"<\s*br\s*/?\s*>|\n\*", raw):
        txt = clean(chunk)
        if not txt or txt.lower() in ("n/a", "-", "tbd", "tba"):
            continue
        scope = None
        mp = PLATFORM_RE.search(txt)
        if mp:
            scope = mp.group(1).strip()
            txt = txt[: mp.start()].strip()
        m = SCORE_RE.search(txt)
        if m:
            score, mx = float(m.group(1)), float(m.group(2))
        else:
            m = PCT_RE.search(txt)
            if m:
                score, mx = float(m.group(1)), 100.0
            else:
                m = re.fullmatch(r"([A-F][+-]?)", txt)
                if m:
                    out.append({"publication": pub, "platform_scope": scope,
                                "grade": m.group(1), "raw": txt})
                    continue
                m = re.fullmatch(r"(\d+(?:\.\d+)?)", txt)
                if not m or default_max is None:
                    continue
                score, mx = float(m.group(1)), float(default_max)
        if mx <= 0 or score > mx * 1.5:
            continue
        out.append({
            "publication": pub, "platform_scope": scope, "score": score,
            "max_score": mx, "score_pct": round(score * 100.0 / mx, 2), "raw": txt,
        })
    return out


# Since roughly 2020 most film articles state aggregates through a template
# rather than in the sentence, in either a named or a positional form:
#   {{Rotten Tomatoes prose|score=95|count=386|average=8.6|consensus=...}}
#   {{Rotten Tomatoes prose|15|4|158|<consensus>}}     score, average, count
#   {{Metacritic film prose|score=86|count=60}} / {{Metacritic film prose|35|41}}
AGG_TEMPLATES = {
    "Rotten Tomatoes prose": ("Rotten Tomatoes", 100, ("score", "average", "count")),
    "Metacritic film prose": ("Metacritic", 100, ("score", "count")),
    "Metacritic TV prose": ("Metacritic", 100, ("score", "count")),
}


def parse_aggregate_templates(text):
    out = []
    for tname, (pub, mx, positional) in AGG_TEMPLATES.items():
        for _, _, body in find_templates(text, tname):
            parts = split_params(body)[1:]
            named, pos = {}, []
            for p in parts:
                if "=" in p and not p.split("=", 1)[0].strip().isdigit():
                    k, v = p.split("=", 1)
                    named[k.strip().lower()] = v.strip()
                else:
                    pos.append(p.strip())
            vals = {}
            for i, key in enumerate(positional):
                if key in named:
                    vals[key] = named[key]
                elif i < len(pos):
                    vals[key] = pos[i]

            def num(key):
                m = re.search(r"\d+(?:\.\d+)?", (vals.get(key) or "").replace(",", ""))
                return float(m.group(0)) if m else None

            score, count = num("score"), num("count")
            if score is None or score > mx:
                continue
            rec = {
                "publication": pub, "score": score, "max_score": float(mx),
                "score_pct": round(score * 100.0 / mx, 2),
                "review_count": int(count) if count else None,
                "source_template": tname,
            }
            avg = num("average")
            if avg is not None:
                rec["average_rating"] = avg
            out.append(rec)
    return out


def parse_prose(text):
    """Aggregate scores stated in Reception prose."""
    flat = re.sub(r"<ref.*?</ref>", " ", text, flags=re.S)
    flat = re.sub(r"<ref[^>]*/>", " ", flat)
    flat = re.sub(r"\{\{[^{}]*\}\}", " ", flat)
    flat = re.sub(r"\[\[([^\]|]*\|)?([^\]]*)\]\]", r"\2", flat)
    flat = re.sub(r"\s+", " ", flat)
    out, seen = [], set()
    for pub, mx, pat in FILM_PATTERNS:
        m = pat.search(flat)
        if not m or pub in seen:
            continue
        seen.add(pub)
        if mx is None:
            out.append({"publication": pub, "grade": m.group(1),
                        "context": flat[max(0, m.start() - 60): m.end() + 60].strip()})
            continue
        score = float(m.group(1))
        cnt = int(m.group(2).replace(",", "")) if m.lastindex and m.lastindex >= 2 else None
        if score > mx:
            continue
        out.append({
            "publication": pub, "score": score, "max_score": float(mx),
            "score_pct": round(score * 100.0 / mx, 2), "review_count": cnt,
            "context": flat[max(0, m.start() - 60): m.end() + 60].strip(),
        })
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--only")
    args = ap.parse_args()

    works = load_works()
    if args.only:
        works = [w for w in works if args.only.lower() in w["title"].lower()]
    pages = wd_pages()

    def do(w):
        page = pages.get(w["id"]) or w["title"]
        try:
            text = W.wp_parse_wikitext(page, refresh=args.refresh)
        except RuntimeError:
            text = None
        if not text:
            return w, page, [], []
        prose = parse_aggregate_templates(text)
        seen = {r["publication"] for r in prose}
        prose += [r for r in parse_prose(text) if r["publication"] not in seen]
        return w, page, parse_vg_reviews(text), prose

    results = []
    with ThreadPoolExecutor(max_workers=5) as ex:
        for w, page, vg, prose in ex.map(do, works):
            n = len(vg) + len(prose)
            flag = "" if n or w["have"] else "   <- still none"
            W.log(f"  {w['title'][:44]:46} vg={len(vg):3} prose={len(prose)}  (v2 had {w['have']}){flag}")
            results.append({
                "work_id": w["id"], "title": w["title"], "media_type": w["media_type"],
                "page": page, "v2_rows": w["have"],
                "video_game_reviews": vg, "prose_scores": prose,
            })

    V3.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"works": results}, f, indent=1, sort_keys=True, ensure_ascii=False)
    tot = sum(len(r["video_game_reviews"]) + len(r["prose_scores"]) for r in results)
    covered = sum(1 for r in results if r["video_game_reviews"] or r["prose_scores"])
    W.log(f"wrote {OUT} — {tot} scores across {covered}/{len(results)} works")


if __name__ == "__main__":
    main()
