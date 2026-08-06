#!/usr/bin/env python3
"""fetch_screen_cast.py — who performed which character, for the works that never said.

`work_characters.actor_person_id` is filled for 149 of 233 film rows, 54 of 81
television rows and **0 of 487 game rows**: TMDB, which v2 built the cast from,
does not credit video games. So the dataset can answer "who has played
Spider-Man" for film and not for anything else, which is the wrong shape for a
question that is mostly about the animated series and the Insomniac games.

This fills it from two open sources, and writes data_raw/v5/screen_cast.json:

* **Wikidata** — P725 (voice actor) and P161 (cast member), each with its P453
  "character role" qualifier. Precise and already identified on both sides, but
  it only exists for eleven of the games.
* **English Wikipedia** — the cast sections, parsed out of the wikitext. Nearly
  every article writes one credit per bullet in one of two forms:

      * [[Christopher Daniel Barnes]] – [[Spider-Man|Peter Parker / Spider-Man]]
      * [[Neil Patrick Harris]] as [[Spider-Man|Peter Parker / …]]<ref …>

  which is enough to recover the performer, the character, and the wiki page
  each of them points at. A bullet is only accepted when it has a separator and
  at least one wiki link, so the prose bullets in a "Characters and setting"
  section are skipped rather than half-parsed.

  Game articles mostly have no cast section at all — *Marvel's Spider-Man*
  writes its cast into prose — so a second, narrower pattern is read from the
  whole article: `[[Peter Parker]] (voiced by [[Yuri Lowenthal]])`. It says
  "voiced by" in so many words, which is what makes it safe to take out of
  running text where a bare parenthetical would not be.

    python3 fetch_screen_cast.py [--refresh] [--only SUBSTRING]

Nothing is matched to this dataset's rows here — that is v5_layer's job, and it
only accepts exact normalised matches. What comes out of this file is names and
the pages they link to, with the section they were credited under kept so a
voice credit stays distinguishable from a live-action one.
"""
import argparse
import html
import json
import re
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import wdlib as W

HERE = Path(__file__).resolve().parent
V3 = HERE / "data_raw" / "v3"
V5 = HERE / "data_raw" / "v5"
DB = HERE / "spiderman.db"
OUT = V5 / "screen_cast.json"

# Section headings that hold a credit list. "Casting" is excluded on purpose:
# it is a development-history section, all prose.
SECTION_RE = re.compile(r"(?i)\b(cast|voices?|starring|characters?)\b")
SECTION_SKIP_RE = re.compile(r"(?i)\bcasting\b|reception|development|release")

# " – ", " — ", " as ", " voiced by " — the separators a credit line uses.
SEP_RE = re.compile(r"\s*[–—]\s*|\s+as\s+|\s+voiced by\s+", re.I)
LINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]")
HEADING_RE = re.compile(r"^\s*(={2,6})\s*(.+?)\s*\1\s*$", re.M)

# "[[Peter Parker]] (voiced by [[Yuri Lowenthal]])" — the only parenthetical
# worth trusting outside a cast list, because it names the relationship.
VOICED_BY_RE = re.compile(
    r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\][^()\[\]]{0,40}?"
    r"\(\s*(?:voiced by|voice of|voiced)\s*\[\[([^\]|]+)(?:\|([^\]]+))?\]\]",
    re.I)

CAST_PROPS = {"P725": "voice", "P161": "cast"}


def strip_markup(s):
    """Drop refs, templates, comments and emphasis; keep link display text."""
    s = re.sub(r"<ref[^>]*/>", "", s)
    s = re.sub(r"<ref[^>]*>.*?</ref>", "", s, flags=re.S | re.I)
    s = re.sub(r"<!--.*?-->", "", s, flags=re.S)
    for _ in range(4):                       # templates nest a couple deep
        new = re.sub(r"\{\{[^{}]*\}\}", "", s)
        if new == s:
            break
        s = new
    s = re.sub(r"<[^>]+>", "", s)
    s = s.replace("'''", "").replace("''", "")
    return html.unescape(s)          # or '&nbsp;' becomes a performer called 'nbsp'


def links_and_text(s):
    """([(page, display), …], plain text) for a fragment of wikitext."""
    links = [(m.group(1).split("#")[0].strip(), (m.group(2) or m.group(1)).strip())
             for m in LINK_RE.finditer(s)]
    text = LINK_RE.sub(lambda m: (m.group(2) or m.group(1)), s)
    text = re.sub(r"\s*\([^)]*\)\s*", " ", text)      # (seasons 1–3), (voice)
    return links, " ".join(text.split()).strip(" ,;:.")


def parse_credit_line(line):
    """One '* actor – character, character' bullet -> credit dicts."""
    body = strip_markup(line.lstrip("*").strip())
    if not body or "[[" not in line:
        return []
    # Links go behind placeholders first: an en-dash inside "(seasons 1–3)" and
    # the brackets of "[[Lizard (character)]]" both look exactly like the things
    # being split on, and only masking tells them apart.
    held = []

    def mask(m):
        held.append(m.group(0))
        return f"\x00{len(held) - 1}\x00"

    def unmask(s):
        return re.sub(r"\x00(\d+)\x00", lambda m: held[int(m.group(1))], s)

    masked = re.sub(r"\([^()]*\)", " ", LINK_RE.sub(mask, body))
    parts = SEP_RE.split(masked, maxsplit=1)
    if len(parts) != 2:
        return []
    left, right = unmask(parts[0]), unmask(parts[1])
    if not left.strip() or not right.strip() or len(left) > 120:
        return []

    # One bullet can credit two performers ("Linda Gary & Julie Bennett").
    performers = []
    for chunk in re.split(r"\s*&\s*|\s+and\s+|\s*,\s*", left):
        plinks, ptext = links_and_text(chunk)
        name = plinks[0][1] if plinks else ptext
        page = plinks[0][0] if plinks else None
        if name and 2 < len(name) <= 60:
            performers.append((name, page))
    if not performers:
        return []

    # …and one performer can be credited with several characters, comma-listed.
    # Anything past a colon or a full stop is the description the article hangs
    # off the credit ("Jean Grey: a young mutant who…"), not another character.
    right = re.split(r"\s*:\s|\.\s", right)[0]
    characters = []
    for chunk in re.split(r"\s*,\s*(?![^\[]*\]\])", right):
        clinks, ctext = links_and_text(chunk)
        # A name, not a sentence: prose continuations start lower-case and run on.
        if (not ctext or len(ctext) > 60 or len(ctext.split()) > 7
                or not ctext[0].isupper()):
            continue
        characters.append({"text": ctext, "pages": [p for p, _ in clinks],
                           "displays": [d for _, d in clinks]})
    if not characters:
        return []

    return [{"performer": name, "performer_page": page, "character": c["text"],
             "character_pages": c["pages"], "character_displays": c["displays"]}
            for name, page in performers for c in characters]


def split_sections(wikitext):
    """[(heading, body), …] for one article; the lead comes back as ''."""
    parts, pos, heading = [], 0, ""
    for m in HEADING_RE.finditer(wikitext):
        parts.append((heading, wikitext[pos:m.start()]))
        heading, pos = m.group(2), m.end()
    parts.append((heading, wikitext[pos:]))
    return parts


def parse_article(title, refresh):
    """Every credit one article yields: cast-section bullets, then voiced-by prose."""
    wt = W.wp_parse_wikitext(title, None, refresh) or ""
    out, seen = [], set()
    for heading, body in split_sections(wt):
        if not SECTION_RE.search(heading) or SECTION_SKIP_RE.search(heading):
            continue
        for raw in body.splitlines():
            if not raw.startswith("*"):
                continue
            for credit in parse_credit_line(raw):
                credit["section"] = heading
                out.append(credit)
                seen.add((credit["performer"], credit["character"]))

    for m in VOICED_BY_RE.finditer(strip_markup(wt)):
        character = (m.group(2) or m.group(1)).strip()
        performer = (m.group(4) or m.group(3)).strip()
        if not character or not performer or len(character) > 90:
            continue
        if (performer, character) in seen:
            continue
        seen.add((performer, character))
        out.append({"performer": performer,
                    "performer_page": m.group(3).split("#")[0].strip(),
                    "character": character,
                    "character_pages": [m.group(1).split("#")[0].strip()],
                    "character_displays": [character],
                    "section": "(voiced by)"})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--only", help="restrict to works whose title contains this")
    args = ap.parse_args()

    con = sqlite3.connect(DB)
    works = {}
    for wid, title, mtype, wp in con.execute(
            "SELECT m.id, m.title, m.media_type, s.wikipedia_title"
            " FROM media_works m LEFT JOIN work_summaries s ON s.work_id = m.id"
            " ORDER BY m.id"):
        if args.only and args.only.lower() not in title.lower():
            continue
        works[wid] = {"title": title, "media_type": mtype, "wikipedia": wp}
    con.close()

    with open(V3 / "works_wikidata.json", encoding="utf-8") as f:
        wd_works = json.load(f)["works"]
    for wid, w in wd_works.items():
        if int(wid) in works and w.get("qid"):
            works[int(wid)]["qid"] = w["qid"]

    # -- Wikidata: P725 / P161 with their character-role qualifier -----------
    qids = sorted({w["qid"] for w in works.values() if w.get("qid")})
    W.log(f"{len(works)} works, {len(qids)} with a Wikidata item")
    ents = W.entities_bulk(qids, props="claims", refresh=args.refresh,
                           languages=W.LANGS)
    wd_credits, ref_qids = {}, set()
    for wid, w in works.items():
        e = ents.get(w.get("qid") or "")
        if not isinstance(e, dict):
            continue
        rows = []
        for prop, kind in CAST_PROPS.items():
            for st in W.claims(e, prop):
                person = W.snak_value(st.get("mainsnak"))
                if not isinstance(person, str) or not person.startswith("Q"):
                    continue
                char = W.qual_first(st, "P453")
                rows.append({"person_qid": person, "character_qid": char,
                             "kind": kind})
                ref_qids.add(person)
                if char:
                    ref_qids.add(char)
        if rows:
            wd_credits[wid] = rows
    W.log(f"  Wikidata: {sum(len(v) for v in wd_credits.values())} credits over "
          f"{len(wd_credits)} works "
          f"({sum(1 for v in wd_credits.values() for r in v if r['character_qid'])}"
          f" name a character)")

    # -- Wikipedia: the cast sections ---------------------------------------
    todo = [(wid, w["wikipedia"]) for wid, w in works.items() if w.get("wikipedia")]
    W.log(f"parsing cast sections in {len(todo)} articles")
    wp_credits = {}

    def one(item):
        wid, title = item
        try:
            return wid, parse_article(title, args.refresh)
        except Exception as exc:                       # a bad article is not fatal
            W.log(f"  ! {title}: {exc}")
            return wid, []

    with ThreadPoolExecutor(max_workers=5) as ex:
        for wid, credits in ex.map(one, todo):
            if credits:
                wp_credits[wid] = credits
                W.log(f"  {works[wid]['title'][:44]:46} {len(credits):>3} credits")
    W.log(f"  Wikipedia: {sum(len(v) for v in wp_credits.values())} credits over "
          f"{len(wp_credits)} works")

    W.log(f"labelling {len(ref_qids)} referenced items")
    labels = W.qid_labels(ref_qids, args.refresh, languages=W.LANGS)

    V5.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"wikidata": {str(k): v for k, v in sorted(wd_credits.items())},
                   "wikipedia": {str(k): v for k, v in sorted(wp_credits.items())},
                   "labels": labels}, f, indent=1, sort_keys=True, ensure_ascii=False)
    W.log(f"wrote {OUT}")

    by_type = {}
    for wid in set(wd_credits) | set(wp_credits):
        by_type[works[wid]["media_type"]] = by_type.get(works[wid]["media_type"], 0) + 1
    W.log("  works with a credit list: "
          + ", ".join(f"{k} {v}" for k, v in sorted(by_type.items())))


if __name__ == "__main__":
    main()
