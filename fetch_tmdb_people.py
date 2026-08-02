#!/usr/bin/env python3
"""fetch_tmdb_people.py — resolve the `people` table against TMDB.

Writes data_raw/people_external.json, which build_db_v2.py reads offline. Keeping
the network step in its own script means the build stays deterministic and
reproducible without an API key or a connection.

    export TMDB_TOKEN='<v4 read access token>'
    python3 fetch_tmdb_people.py [--limit N] [--refresh]

Matching strategy
-----------------
A blind /search/person on a name is unreliable — "Ryan Smith" and "Chris Miller"
match many people. So the primary path resolves each film and series to a TMDB id
and matches our names against *that title's own credit list*. A name that appears
in the credits of the same work is the right person by construction.

Only names left over after that fall back to /search/person, and a fallback hit is
accepted only when the search returns exactly one exact-name match. Everything
ambiguous is recorded as unresolved rather than guessed at, because a wrong
birth date is worse than a missing one.

Responses are cached under data_raw/.tmdb_cache/ so re-runs cost no requests.
"""
import argparse
import json
import os
import re
import sqlite3
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Lock

HERE = Path(__file__).parent
RAW_DIR = HERE / "data_raw"
CACHE_DIR = RAW_DIR / ".tmdb_cache"
DB_PATH = HERE / "spiderman.db"
OUT_PATH = RAW_DIR / "people_external.json"

API = "https://api.themoviedb.org/3"
TOKEN = os.environ.get("TMDB_TOKEN", "").strip()

CACHE_DIR.mkdir(parents=True, exist_ok=True)
_print_lock = Lock()


def log(msg):
    with _print_lock:
        print(msg, flush=True)


# ---------------------------------------------------------------------------
# HTTP with on-disk cache
# ---------------------------------------------------------------------------
def get(path, refresh=False, **params):
    """GET an API path, caching the parsed JSON by request signature."""
    qs = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    key = re.sub(r'[^A-Za-z0-9]+', '_', f"{path}?{qs}").strip('_')[:180]
    cache_file = CACHE_DIR / f"{key}.json"
    if cache_file.exists() and not refresh:
        return json.loads(cache_file.read_text(encoding="utf-8"))

    url = f"{API}{path}" + (f"?{qs}" if qs else "")
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {TOKEN}", "accept": "application/json"})
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            cache_file.write_text(json.dumps(data), encoding="utf-8")
            return data
        except urllib.error.HTTPError as e:
            if e.code == 429:                      # rate limited
                time.sleep(2 * (attempt + 1))
                continue
            if e.code == 404:
                return None
            raise
        except (urllib.error.URLError, TimeoutError):
            time.sleep(1.5 * (attempt + 1))
    log(f"  ! giving up on {url}")
    return None


# ---------------------------------------------------------------------------
# Name handling
# ---------------------------------------------------------------------------
def norm_name(name):
    """Casefold and strip accents/punctuation so 'Luna Lauren Vélez' == '... Velez'."""
    s = unicodedata.normalize("NFKD", str(name or ""))
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = re.sub(r'[^a-z0-9 ]+', ' ', s.lower())
    return " ".join(s.split())


def norm_title(title):
    s = re.sub(r'\s*\(.*?\)\s*', ' ', str(title or '')).replace('&', 'and')
    return " ".join(re.sub(r'[^a-z0-9]+', ' ', s.lower()).split())


# ---------------------------------------------------------------------------
# Resolve our works to TMDB ids
# ---------------------------------------------------------------------------
def resolve_work(title, year, media_type, refresh=False):
    """Find the TMDB id for one of our works, or None."""
    kind = "movie" if media_type == "movie" else "tv"
    # The Toei film and the CBS TV-movies are catalogued under names TMDB does not
    # use; strip our own disambiguators before searching.
    query = re.sub(r'\s*\((Toei|\d{4} TV series|Japanese TV series)\)\s*', ' ', title).strip()
    data = get(f"/search/{kind}", refresh=refresh, query=query,
               **({"year": year} if year and kind == "movie" else
                  {"first_air_date_year": year} if year else {}))
    if not data or not data.get("results"):
        data = get(f"/search/{kind}", refresh=refresh, query=query)
    if not data or not data.get("results"):
        return None

    # An exact title carries a work on its own, a partial title needs the year to
    # corroborate it, and no amount of year agreement substitutes for a title that
    # does not match at all. Summing the two into one score did not express that:
    # an exact-year match scored 8 against a threshold of 8, so any film sharing a
    # release year cleared the bar with no title agreement whatsoever, while an
    # exactly-titled film whose year was off by more than one scored 10-4=6 and was
    # rejected. Every work_credits match is only as sound as the work resolved here,
    # so a wrong pick quietly attributes a stranger's birth date and IMDb id to one
    # of our people. The rule is applied as a filter over candidates rather than a
    # test on the top scorer, because a same-year/wrong-title result outscores an
    # exactly-titled one and would shadow it before the test ran.
    want = norm_title(query)
    ranked = []
    for r in data["results"]:
        name = r.get("title") or r.get("name") or ""
        date = r.get("release_date") or r.get("first_air_date") or ""
        ryear = int(date[:4]) if date[:4].isdigit() else None
        if norm_title(name) == want:
            title_score = 10
        elif want in norm_title(name) or norm_title(name) in want:
            title_score = 4
        else:
            continue                # no title agreement: never a match
        if not year or not ryear:
            year_score = 0
        elif ryear == year:
            year_score = 8
        elif abs(ryear - year) <= 1:
            year_score = 3
        else:
            year_score = -4
        if title_score != 10 and year_score != 8:
            continue
        # Two results can both merely *contain* the query — searching "Spider-Man"
        # for the 2017 series returns "Marvel's Spider-Man" and "Marvel's
        # Spider-Man' Origin Short", identical on the coarse buckets above. The
        # closer title is the better answer, so how much extra text the candidate
        # carries breaks that tie.
        ranked.append(((title_score + year_score, title_score,
                        -abs(len(norm_title(name)) - len(want))), r["id"]))
    if not ranked:
        return None
    top = max(k for k, _ in ranked)
    winners = [i for k, i in ranked if k == top]
    # A genuine tie is ambiguity, not a coin toss to be settled by result order or
    # by whichever TMDB id happens to sort highest. Searching the unreleased "El
    # Muerto" with no year returns three unrelated Spanish-language films all
    # titled exactly that; picking one attributes its cast to our people.
    return winners[0] if len(winners) == 1 else None


def credit_names(tmdb_id, media_type, refresh=False):
    """Map normalized name -> TMDB person id for everyone credited on a work."""
    if media_type == "movie":
        data = get(f"/movie/{tmdb_id}/credits", refresh=refresh)
        people = (data.get("cast", []) + data.get("crew", [])) if data else []
    else:
        data = get(f"/tv/{tmdb_id}/aggregate_credits", refresh=refresh)
        people = (data.get("cast", []) + data.get("crew", [])) if data else []
    out = {}
    for p in people:
        if p.get("id") and p.get("name"):
            out.setdefault(norm_name(p["name"]), p["id"])
    return out


def person_details(tmdb_id, refresh=False):
    d = get(f"/person/{tmdb_id}", refresh=refresh, append_to_response="external_ids")
    if not d:
        return None
    ext = d.get("external_ids") or {}
    return {
        "tmdb_id": d.get("id"),
        "name": d.get("name"),
        "birth_date": d.get("birthday") or None,
        "death_date": d.get("deathday") or None,
        "birth_place": d.get("place_of_birth") or None,
        "imdb_id": d.get("imdb_id") or ext.get("imdb_id") or None,
        "wikidata_id": ext.get("wikidata_id") or None,
        "known_for_department": d.get("known_for_department") or None,
    }


def search_person(name, refresh=False):
    """Fallback lookup. Returns a TMDB id only when the answer is unambiguous."""
    data = get("/search/person", refresh=refresh, query=name)
    if not data or not data.get("results"):
        return None
    want = norm_name(name)
    exact = [r for r in data["results"] if norm_name(r.get("name")) == want]
    if len(exact) == 1:
        return exact[0]["id"]
    return None     # zero matches, or several people share the name


# Franchise titles that count as corroboration even when they are not one of our
# catalogue works — a person credited on any of these is plainly the right person.
FRANCHISE_HINTS = ("spider-man", "spiderman", "spider man", "venom", "morbius",
                   "kraven the hunter", "madame web", "spider-verse")


def verify_person(tmdb_id, expected_titles, refresh=False):
    """Confirm a searched-for person really worked on something in this franchise.

    "Exactly one TMDB person has this name" is not proof of identity: TMDB holds a
    1885-born Edward J. Montagne (the father) but not the 1977 producer, and one
    John Digweed who is the DJ. Both pass a name test and fail this one.

    Returns "verified" when a credit lines up with a work we expected them on or
    with the wider franchise, otherwise "unverified".
    """
    data = get(f"/person/{tmdb_id}/combined_credits", refresh=refresh)
    if not data:
        return "unverified"
    for credit in (data.get("cast", []) + data.get("crew", [])):
        title = norm_title(credit.get("title") or credit.get("name") or "")
        if title in expected_titles:
            return "verified"
        raw = (credit.get("title") or credit.get("name") or "").lower()
        if any(h in raw for h in FRANCHISE_HINTS):
            return "verified"
    return "unverified"


# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, help="only process the first N people")
    ap.add_argument("--refresh", action="store_true", help="bypass the response cache")
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()

    if not TOKEN:
        sys.exit("TMDB_TOKEN is not set. export TMDB_TOKEN='<v4 read access token>'")
    if not DB_PATH.exists():
        sys.exit(f"{DB_PATH} not found — run build_db_v2.py first.")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    people = [(r["id"], r["name"]) for r in conn.execute("SELECT id, name FROM people ORDER BY name")]
    if args.limit:
        people = people[:args.limit]
    works = conn.execute("""SELECT id, title, release_year, media_type FROM media_works
                            WHERE media_type IN ('movie','tv_show') ORDER BY release_year""").fetchall()
    # Which of our people are credited on which work — the basis for scoped matching.
    credited = {}
    for r in conn.execute("""SELECT DISTINCT cc.work_id, p.name FROM cast_crew cc
                             JOIN people p ON p.id = cc.person_id"""):
        credited.setdefault(r["work_id"], set()).add(r["name"])
    conn.close()

    # --- Pass 1: resolve works, pull their credit lists -------------------
    log(f"Resolving {len(works)} films/series to TMDB...")
    work_credits = {}       # our work_id -> {norm name: tmdb person id}
    unresolved_works = []

    def do_work(w):
        tid = resolve_work(w["title"], w["release_year"], w["media_type"], args.refresh)
        if not tid:
            unresolved_works.append(f'{w["title"]} ({w["release_year"]})')
            return
        work_credits[w["id"]] = credit_names(tid, w["media_type"], args.refresh)

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        list(ex.map(do_work, works))
    log(f"  matched {len(work_credits)}/{len(works)} works")
    for u in unresolved_works:
        log(f"  unresolved work: {u}")

    # --- Pass 2: match our people inside their own works' credits ---------
    name_to_tmdb = {}
    for work_id, names in credited.items():
        lookup = work_credits.get(work_id)
        if not lookup:
            continue
        for name in names:
            key = norm_name(name)
            if key in lookup and name not in name_to_tmdb:
                name_to_tmdb[name] = ("work_credits", lookup[key])
    log(f"Matched via work credit lists: {len(name_to_tmdb)}")

    # --- Pass 3: unambiguous name search for the remainder ----------------
    remaining = [n for _, n in people if n not in name_to_tmdb]
    log(f"Falling back to person search for {len(remaining)}...")

    def do_search(name):
        tid = search_person(name, args.refresh)
        if tid:
            name_to_tmdb[name] = ("search_exact", tid)

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        list(ex.map(do_search, remaining))
    log(f"Total matched: {len(name_to_tmdb)}/{len(people)}")

    # --- Pass 3b: corroborate the searched-for matches --------------------
    # Work-credit matches need no check: they came out of the credit list of a work
    # we had already identified. Search matches are only a name agreeing, so each
    # one has to show a franchise credit before it is trusted.
    expected_titles = {norm_title(w["title"]) for w in works}
    searched = [n for n, (how, _) in name_to_tmdb.items() if how == "search_exact"]
    log(f"Verifying {len(searched)} search matches against their TMDB credits...")

    def do_verify(name):
        _, tid = name_to_tmdb[name]
        if verify_person(tid, expected_titles, args.refresh) == "verified":
            name_to_tmdb[name] = ("search_verified", tid)

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        list(ex.map(do_verify, searched))
    rejected = [n for n, (how, _) in name_to_tmdb.items() if how == "search_exact"]
    for name in rejected:
        del name_to_tmdb[name]
    log(f"  verified {len(searched) - len(rejected)}, rejected {len(rejected)}")
    for n in sorted(rejected):
        log(f"    rejected (no franchise credit): {n}")

    # --- Pass 4: fetch details -------------------------------------------
    log("Fetching person details...")
    records, failed = {}, []

    def do_detail(item):
        name, (how, tid) = item
        d = person_details(tid, args.refresh)
        if not d:
            failed.append(name)
            return
        d["matched_by"] = how
        records[name] = d

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        list(ex.map(do_detail, list(name_to_tmdb.items())))

    # A record with no usable field is not worth storing.
    records = {n: d for n, d in records.items()
               if any(d[k] for k in ("birth_date", "birth_place", "imdb_id", "wikidata_id"))}

    payload = {
        "_source": "The Movie Database (TMDB) API v3",
        "_generated": time.strftime("%Y-%m-%d"),
        "_note": ("Generated by fetch_tmdb_people.py. Names are matched inside the "
                  "credit list of the work they are credited on; 'search_exact' "
                  "entries came from an unambiguous single-result name search. "
                  "This product uses the TMDB API but is not endorsed or certified "
                  "by TMDB."),
        "people": dict(sorted(records.items())),
    }
    OUT_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    by_how = {}
    for d in records.values():
        by_how[d["matched_by"]] = by_how.get(d["matched_by"], 0) + 1
    log(f"\nWrote {OUT_PATH} — {len(records)} people")
    log(f"  by match method: {by_how}")
    log(f"  with birth_date : {sum(1 for d in records.values() if d['birth_date'])}")
    log(f"  with birth_place: {sum(1 for d in records.values() if d['birth_place'])}")
    log(f"  with imdb_id    : {sum(1 for d in records.values() if d['imdb_id'])}")
    log(f"  with wikidata_id: {sum(1 for d in records.values() if d['wikidata_id'])}")
    log(f"  unresolved      : {len(people) - len(records)}")
    if failed:
        log(f"  detail fetch failed for {len(failed)}")


if __name__ == "__main__":
    main()
