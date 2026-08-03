#!/usr/bin/env python3
"""fetch_episodes.py — per-episode data for the series v2 left empty.

Writes data_raw/v3/episodes.json. Ten of the fifteen series carry no episode rows
in v2; between them that is roughly 500 episodes of titles, air dates, directors,
writers and US viewer counts.

    python3 fetch_episodes.py [--refresh] [--only 'Spectacular']

Source
------
The English Wikipedia episode lists, read as wikitext through the Action API
rather than scraped from rendered HTML. Every one of these lists is built from
the `{{Episode list}}` template, so the fields come out named
(`EpisodeNumber`, `DirectedBy`, `OriginalAirDate`, ...) instead of having to be
recovered from table geometry. Season numbers come from the enclosing
`{{Episode table}}` / section heading, and an episode that cannot be placed in a
season keeps a NULL season rather than a guessed one.
"""
import argparse
import json
import re
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import wdlib as W

HERE = Path(__file__).resolve().parent
DB = HERE / "spiderman.db"
V3 = HERE / "data_raw" / "v3"
OUT = V3 / "episodes.json"

MONTHS = {m: i + 1 for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July",
     "August", "September", "October", "November", "December"])}


# ---------------------------------------------------------------------------
# wikitext helpers
# ---------------------------------------------------------------------------
def split_params(body):
    """Split a template body on top-level '|', respecting [[ ]] and {{ }}."""
    parts, buf, depth_t, depth_l = [], [], 0, 0
    i = 0
    while i < len(body):
        two = body[i:i + 2]
        if two == "{{":
            depth_t += 1; buf.append(two); i += 2; continue
        if two == "}}":
            depth_t -= 1; buf.append(two); i += 2; continue
        if two == "[[":
            depth_l += 1; buf.append(two); i += 2; continue
        if two == "]]":
            depth_l -= 1; buf.append(two); i += 2; continue
        ch = body[i]
        if ch == "|" and depth_t == 0 and depth_l == 0:
            parts.append("".join(buf)); buf = []
        else:
            buf.append(ch)
        i += 1
    parts.append("".join(buf))
    return parts


def find_templates(text, name):
    """Yield (start, end, body) for each {{name ...}} occurrence.

    `{{Episode list/sublist}}` is the same template with a different entry point
    and has to be matched too, or every series whose seasons live on subpages
    comes back empty.
    """
    pat = re.compile(
        r"\{\{\s*" + name.replace(" ", r"[ _]") + r"(?:/sublist)?\s*(\||\}\})", re.I)
    for m in pat.finditer(text):
        i = m.start()
        depth, j = 0, i
        while j < len(text):
            if text[j:j + 2] == "{{":
                depth += 1; j += 2; continue
            if text[j:j + 2] == "}}":
                depth -= 1; j += 2
                if depth == 0:
                    break
                continue
            j += 1
        yield i, j, text[i + 2:j - 2]


def template_params(body):
    out = {}
    parts = split_params(body)[1:]  # drop the template name
    for p in parts:
        if "=" not in p:
            continue
        k, v = p.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def clean(s):
    """Wikitext -> plain text."""
    if s is None:
        return None
    s = re.sub(r"<ref[^>]*?/>", "", s)
    s = re.sub(r"<ref.*?</ref>", "", s, flags=re.S)
    s = re.sub(r"<!--.*?-->", "", s, flags=re.S)
    # {{sortname|Bob|Smith}} / {{ill|X|..}} -> keep the readable arguments
    for _ in range(4):
        new = re.sub(
            r"\{\{\s*(?:sort ?name|sortname|ill|nowrap|nobold|small|lang)\s*\|([^{}]*?)\}\}",
            lambda m: " ".join(x for x in split_params("x|" + m.group(1))[1:3] if "=" not in x),
            s, flags=re.I)
        if new == s:
            break
        s = new
    s = re.sub(r"\{\{[^{}]*\}\}", "", s)          # remaining templates
    s = re.sub(r"\[\[([^\]|]*\|)?([^\]]*)\]\]", r"\2", s)  # links
    s = re.sub(r"</?[^>]+>", "", s)               # html
    s = s.replace("&nbsp;", " ").replace("&amp;", "&").replace("&ndash;", "-")
    s = s.replace("''", "").replace('"', "").strip(" \t\n'\"")
    return " ".join(s.split()) or None


def parse_date(s):
    """{{start date|1994|11|19}} or 'November 19, 1994' -> ISO."""
    if not s:
        return None
    m = re.search(r"\{\{\s*(?:start ?date|dts|date)\s*\|\s*(\d{4})\s*\|\s*(\d{1,2})\s*\|\s*(\d{1,2})",
                  s, re.I)
    if m:
        return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    t = clean(s) or ""
    m = re.search(r"([A-Z][a-z]+)\s+(\d{1,2}),?\s+(\d{4})", t)
    if m and m.group(1) in MONTHS:
        return f"{int(m.group(3)):04d}-{MONTHS[m.group(1)]:02d}-{int(m.group(2)):02d}"
    m = re.search(r"(\d{1,2})\s+([A-Z][a-z]+)\s+(\d{4})", t)
    if m and m.group(2) in MONTHS:
        return f"{int(m.group(3)):04d}-{MONTHS[m.group(2)]:02d}-{int(m.group(1)):02d}"
    m = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", t)
    if m:
        return m.group(0)
    return None


def parse_int(s):
    t = clean(s) or ""
    m = re.search(r"\d+", t.replace(",", ""))
    return int(m.group(0)) if m else None


def parse_float(s):
    t = clean(s) or ""
    m = re.search(r"\d+(?:\.\d+)?", t.replace(",", ""))
    return float(m.group(0)) if m else None


# ---------------------------------------------------------------------------
# season attribution
# ---------------------------------------------------------------------------
HEADING = re.compile(r"^\s*(={2,6})\s*(.+?)\s*\1\s*$", re.M)


def season_at(text, pos, default=None):
    """Season number implied by the nearest heading above `pos`."""
    best = default
    for m in HEADING.finditer(text):
        if m.start() > pos:
            break
        h = m.group(2)
        s = re.search(r"season\s+(\d+)", h, re.I) or re.search(r"^\s*Season\s+(\w+)", h, re.I)
        if s:
            try:
                best = int(s.group(1))
            except ValueError:
                words = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
                         "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
                best = words.get(s.group(1).lower(), best)
        elif re.search(r"\b(19|20)\d\d\b", h) and re.search(r"^series\s+(\d+)", h, re.I):
            pass
    return best


def numbered(p, base):
    """Segment-numbered params: Title_1 / Title_2 on shows that air two shorts
    per slot. Returns the list in order, or [] when the show is not segmented."""
    keys = sorted(
        (k for k in p if re.fullmatch(re.escape(base) + r"_(\d+)", k)),
        key=lambda k: int(k.rsplit("_", 1)[1]),
    )
    return [clean(p[k]) for k in keys if clean(p[k])]


def parse_article(text, page):
    """All {{Episode list}} rows in one article."""
    # Comments routinely open in one parameter and close in another; stripping
    # them per-field leaves '<!--' welded to a title and '-->' as the writer.
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    eps = []
    for start, end, body in find_templates(text, "Episode list"):
        p = template_params(body)
        if not p:
            continue
        seg_titles = numbered(p, "Title")
        title = clean(p.get("Title") or p.get("RTitle") or p.get("AltTitle"))
        if not title and seg_titles:
            title = " / ".join(seg_titles)
        num = parse_int(p.get("EpisodeNumber"))
        num2 = parse_int(p.get("EpisodeNumber2"))
        eps.append({
            "page": page,
            "overall_number": num,
            "season_episode": num2,
            "season_hint": season_at(text, start),
            "title": title,
            "segment_titles": seg_titles,
            "air_date": parse_date(p.get("OriginalAirDate") or p.get("OriginalAirDateR")),
            "director": clean(p.get("DirectedBy")) or " / ".join(numbered(p, "DirectedBy")) or None,
            "writer": clean(p.get("WrittenBy")) or " / ".join(numbered(p, "WrittenBy")) or None,
            "us_viewers_millions": parse_float(p.get("Viewers")),
            "prod_code": clean(p.get("ProdCode")),
            "summary": clean(p.get("ShortSummary")),
            "aux1": clean(p.get("Aux1")),
            "aux2": clean(p.get("Aux2")),
            "aux3": clean(p.get("Aux3")),
            "aux4": clean(p.get("Aux4")),
        })
    return eps


# ---------------------------------------------------------------------------
def load_shows():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    rows = [dict(r) for r in con.execute("""
        SELECT w.id, w.title, w.release_year, t.seasons, t.episodes,
               (SELECT COUNT(*) FROM episodes e WHERE e.show_work_id = w.id) AS have
        FROM media_works w JOIN tv_shows t ON t.work_id = w.id
        ORDER BY w.release_year""")]
    con.close()
    return rows


def candidate_pages(show, wd_title):
    base = re.sub(r"\s*\(.*?\)\s*$", "", show["title"]).strip()
    disamb = re.search(r"\((.*?)\)\s*$", show["title"])
    cands = []
    if wd_title:
        cands += [f"List of {wd_title} episodes", wd_title]
    cands += [f"List of {show['title']} episodes", f"List of {base} episodes"]
    if disamb:
        cands.append(f"List of {base} ({disamb.group(1)}) episodes")
    if show["release_year"]:
        cands.append(f"List of {base} ({show['release_year']} TV series) episodes")
    cands.append(show["title"])
    cands.append(base)
    seen, out = set(), []
    for c in cands:
        if c.lower() not in seen:
            seen.add(c.lower())
            out.append(c)
    return out


def wd_titles():
    p = V3 / "works_wikidata.json"
    if not p.exists():
        return {}
    with open(p, encoding="utf-8") as f:
        d = json.load(f)
    return {int(k): v.get("enwiki") for k, v in d.get("works", {}).items()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--only")
    args = ap.parse_args()

    shows = load_shows()
    if args.only:
        shows = [s for s in shows if args.only.lower() in s["title"].lower()]
    titles = wd_titles()

    def work(show):
        found = []
        pages_tried = []
        for page in candidate_pages(show, titles.get(show["id"])):
            pages_tried.append(page)
            try:
                text = W.wp_parse_wikitext(page, refresh=args.refresh)
            except RuntimeError:
                continue
            if not text:
                continue
            eps = parse_article(text, page)
            if eps:
                found = eps
                break
        return show, found, pages_tried

    results = []
    with ThreadPoolExecutor(max_workers=5) as ex:
        for show, eps, tried in ex.map(work, shows):
            W.log(f"  {show['title'][:46]:48} parsed={len(eps):4} "
                  f"(v2 had {show['have']}, expected {show['episodes']})")
            results.append({
                "work_id": show["id"], "title": show["title"],
                "expected": show["episodes"], "v2_rows": show["have"],
                "pages_tried": tried, "episodes": eps,
            })

    V3.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"shows": results}, f, indent=1, sort_keys=True, ensure_ascii=False)
    total = sum(len(r["episodes"]) for r in results)
    W.log(f"wrote {OUT} — {total} episode rows across {len(results)} series")


if __name__ == "__main__":
    main()
