#!/usr/bin/env python3
"""fetch_summaries.py — a plain-text description for every work.

Writes data_raw/v3/summaries.json: the lead section of each work's English
Wikipedia article, plus the article URL and Commons category. The dataset has
never carried prose about what any of these 81 works actually *are*, which makes
it awkward to use for anything text-facing.

    python3 fetch_summaries.py [--refresh]
"""
import argparse
import json
import sqlite3
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import wdlib as W

HERE = Path(__file__).resolve().parent
DB = HERE / "spiderman.db"
V3 = HERE / "data_raw" / "v3"
OUT = V3 / "summaries.json"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()

    con = sqlite3.connect(DB)
    works = [(r[0], r[1]) for r in con.execute("SELECT id, title FROM media_works ORDER BY id")]
    con.close()

    pages = {}
    p = V3 / "works_wikidata.json"
    if p.exists():
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
        pages = {int(k): v.get("enwiki") for k, v in d.get("works", {}).items() if v.get("enwiki")}

    def do(item):
        wid, title = item
        page = pages.get(wid) or title
        try:
            text = W.wp_extract(page, refresh=args.refresh)
        except RuntimeError:
            text = None
        return wid, page, text

    out = {}
    with ThreadPoolExecutor(max_workers=5) as ex:
        for wid, page, text in ex.map(do, works):
            if not text:
                W.log(f"  no summary for work {wid} ({page})")
                continue
            # The lead can run long; keep the first two paragraphs.
            paras = [x.strip() for x in text.split("\n") if x.strip()]
            summary = " ".join(paras[:2])
            out[str(wid)] = {
                "wikipedia_title": page,
                "url": "https://en.wikipedia.org/wiki/" + urllib.parse.quote(page.replace(" ", "_")),
                "summary": summary,
                "chars": len(summary),
            }

    V3.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"summaries": out}, f, indent=1, sort_keys=True, ensure_ascii=False)
    W.log(f"wrote {OUT} — {len(out)} summaries")


if __name__ == "__main__":
    main()
