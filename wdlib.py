#!/usr/bin/env python3
"""wdlib.py — shared Wikidata / Wikipedia / MusicBrainz access with an on-disk cache.

Every v3 fetcher goes through here so that a re-run costs no requests and the
offline build stays byte-for-byte reproducible. Responses land in
data_raw/.wd_cache/ keyed by a hash of the request.

No API keys: Wikidata's SPARQL endpoint, the MediaWiki Action API and MusicBrainz
are all open. The only obligation is a descriptive User-Agent and civilised
concurrency, both of which are enforced below.
"""
import hashlib
import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
CACHE_DIR = HERE / "data_raw" / ".wd_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

UA = os.environ.get(
    "SPIDERMAN_UA",
    "spiderman-dataset/3.0 (https://github.com/spiderman-dataset; contact via repo issues)",
)

SPARQL_URL = "https://query.wikidata.org/sparql"
WD_API = "https://www.wikidata.org/w/api.php"
WP_API = "https://en.wikipedia.org/w/api.php"
MB_API = "https://musicbrainz.org/ws/2"

_print_lock = threading.Lock()
_mb_lock = threading.Lock()
_mb_last = [0.0]


def log(msg):
    with _print_lock:
        print(msg, flush=True)


# ---------------------------------------------------------------------------
# cache
# ---------------------------------------------------------------------------
def _cache_path(kind, key):
    h = hashlib.sha256(key.encode("utf-8")).hexdigest()[:40]
    return CACHE_DIR / f"{kind}_{h}.json"


def cached(kind, key, produce, refresh=False):
    """Return produce()'s JSON, memoised on disk under (kind, key)."""
    p = _cache_path(kind, key)
    if p.exists() and not refresh:
        try:
            with open(p, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass  # corrupt cache entry, refetch
    val = produce()
    # Unique per writer: two threads can race on the same key and must not share
    # a temp path.
    tmp = p.with_suffix(f".{os.getpid()}.{threading.get_ident()}.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(val, f)
    os.replace(tmp, p)
    return val


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------
# Anonymous MediaWiki calls get throttled hard above a few per second, so every
# request passes a per-host bucket before it goes out. Values are requests/second.
_HOST_RATE = {
    "en.wikipedia.org": 2.0,
    "www.wikidata.org": 3.0,
    "query.wikidata.org": 1.5,
    "musicbrainz.org": 1.0,
}
_rate_lock = threading.Lock()
_rate_next = {}


def _throttle(url):
    host = urllib.parse.urlsplit(url).netloc
    rate = _HOST_RATE.get(host)
    if not rate:
        return
    gap = 1.0 / rate
    # Reserve exactly one slot, then sleep until it comes up. Re-checking in a
    # loop would reserve a fresh slot on every pass and the queue would run away
    # from itself once more than a couple of threads were waiting.
    with _rate_lock:
        now = time.monotonic()
        start = max(now, _rate_next.get(host, 0.0))
        _rate_next[host] = start + gap
    wait = start - now
    if wait > 0:
        time.sleep(wait)


def _fetch(url, headers=None, timeout=90, retries=6, data=None):
    hdr = {"User-Agent": UA, "Accept-Encoding": "gzip"}
    hdr.update(headers or {})
    last = None
    for attempt in range(retries):
        _throttle(url)
        try:
            req = urllib.request.Request(url, headers=hdr, data=data)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = r.read()
                if r.headers.get("Content-Encoding") == "gzip":
                    import gzip

                    raw = gzip.decompress(raw)
                return json.loads(raw.decode("utf-8"))
        except urllib.error.HTTPError as e:
            last = e
            if e.code in (429, 500, 502, 503, 504):
                retry_after = e.headers.get("Retry-After") if e.headers else None
                try:
                    delay = float(retry_after)
                except (TypeError, ValueError):
                    delay = 2 ** attempt + 1
                time.sleep(min(delay, 60))
                continue
            if e.code == 404:
                return None
            raise
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ConnectionError) as e:
            last = e
            time.sleep(2 ** attempt + 1)
    raise RuntimeError(f"giving up on {url[:120]}: {last}")


# ---------------------------------------------------------------------------
# Wikidata
# ---------------------------------------------------------------------------
def sparql(query, refresh=False):
    """Run a SPARQL query, return the bindings list."""

    def go():
        params = urllib.parse.urlencode({"query": query, "format": "json"})
        hdr = {"Accept": "application/sparql-results+json"}
        # A VALUES clause over a few thousand ids blows past the URL length the
        # endpoint accepts, so long queries go in a POST body instead.
        if len(params) > 3000:
            return _fetch(
                SPARQL_URL, headers={**hdr, "Content-Type": "application/x-www-form-urlencoded"},
                data=params.encode("utf-8"))
        return _fetch(SPARQL_URL + "?" + params, headers=hdr)

    res = cached("sparql", query, go, refresh)
    return (res or {}).get("results", {}).get("bindings", [])


def entity(qid, refresh=False):
    """Full JSON for one Wikidata entity (all claims, sitelinks, labels)."""

    def go():
        url = f"https://www.wikidata.org/wiki/Special:EntityData/{qid}.json"
        d = _fetch(url)
        return (d or {}).get("entities", {}).get(qid)

    return cached("entity", qid, go, refresh)


def wbsearch(text, kind="item", limit=15, refresh=False):
    """wbsearchentities — label/alias search, the entry point for resolution."""
    params = {
        "action": "wbsearchentities", "search": text, "language": "en",
        "uselang": "en", "type": kind, "limit": str(limit), "format": "json",
    }

    def go():
        return _fetch(WD_API + "?" + urllib.parse.urlencode(params))

    return (cached("wbsearch", json.dumps(params, sort_keys=True), go, refresh) or {}).get(
        "search", []
    )


def entities_bulk(qids, props="labels", refresh=False):
    """wbgetentities for up to 50 ids at a time; returns {qid: entity}."""
    out = {}
    qids = list(qids)
    for i in range(0, len(qids), 50):
        chunk = qids[i:i + 50]
        params = {
            "action": "wbgetentities", "ids": "|".join(chunk), "props": props,
            "languages": "en", "format": "json",
        }

        def go(p=params):
            return _fetch(WD_API + "?" + urllib.parse.urlencode(p))

        res = cached("wbget", json.dumps(params, sort_keys=True), go, refresh) or {}
        out.update(res.get("entities", {}))
    return out


def qid_labels(qids, refresh=False):
    """{qid: english label} for a set of ids."""
    ents = entities_bulk(sorted(set(q for q in qids if q)), "labels", refresh)
    return {
        k: v.get("labels", {}).get("en", {}).get("value")
        for k, v in ents.items()
        if isinstance(v, dict)
    }


# --- claim readers ---------------------------------------------------------
def claims(ent, prop):
    """Non-deprecated statements for a property, best rank first."""
    st = (ent or {}).get("claims", {}).get(prop, [])
    st = [s for s in st if s.get("rank") != "deprecated"]
    pref = [s for s in st if s.get("rank") == "preferred"]
    return pref + [s for s in st if s.get("rank") != "preferred"]


def snak_value(snak):
    """Unwrap a snak into a plain Python value."""
    if not snak or snak.get("snaktype") != "value":
        return None
    dv = snak.get("datavalue", {})
    v, t = dv.get("value"), dv.get("type")
    if t == "wikibase-entityid":
        return v.get("id")
    if t == "time":
        return v.get("time")
    if t == "quantity":
        return v
    if t == "monolingualtext":
        return v.get("text")
    if t == "globecoordinate":
        return v
    return v


def pvalues(ent, prop):
    """Plain values of a property."""
    return [v for v in (snak_value(s.get("mainsnak")) for s in claims(ent, prop)) if v is not None]


def pfirst(ent, prop):
    vs = pvalues(ent, prop)
    return vs[0] if vs else None


def qualifiers(stmt, prop):
    return [
        v for v in (snak_value(q) for q in stmt.get("qualifiers", {}).get(prop, []))
        if v is not None
    ]


def qual_first(stmt, prop):
    vs = qualifiers(stmt, prop)
    return vs[0] if vs else None


def wd_time_to_iso(t):
    """'+2002-05-03T00:00:00Z' -> '2002-05-03'; partial dates keep what's known."""
    if not t or not isinstance(t, str):
        return None
    t = t.lstrip("+")
    date = t.split("T")[0]
    y, m, d = (date.split("-") + ["00", "00"])[:3]
    if m == "00":
        return y
    if d == "00":
        return f"{y}-{m}"
    return f"{y}-{m}-{d}"


def wd_year(t):
    iso = wd_time_to_iso(t)
    if not iso:
        return None
    try:
        return int(iso[:4])
    except ValueError:
        return None


def quantity_amount(q):
    if isinstance(q, dict) and "amount" in q:
        try:
            return int(float(q["amount"]))
        except (TypeError, ValueError):
            return None
    return None


# ---------------------------------------------------------------------------
# Wikipedia
# ---------------------------------------------------------------------------
def wp_query(params, refresh=False):
    p = {"format": "json", "formatversion": "2", **params}

    def go():
        return _fetch(WP_API + "?" + urllib.parse.urlencode(p))

    return cached("wp", json.dumps(p, sort_keys=True), go, refresh)


def wp_qid(title, refresh=False):
    """Wikidata id for an English Wikipedia article title (redirects followed)."""
    d = wp_query(
        {"action": "query", "prop": "pageprops", "ppprop": "wikibase_item",
         "redirects": "1", "titles": title},
        refresh,
    )
    pages = (d or {}).get("query", {}).get("pages", [])
    if not pages or pages[0].get("missing"):
        return None
    return pages[0].get("pageprops", {}).get("wikibase_item")


def wp_search(text, limit=8, refresh=False):
    """Full-text article search; returns titles."""
    d = wp_query(
        {"action": "query", "list": "search", "srsearch": text, "srlimit": str(limit)}, refresh
    )
    return [h["title"] for h in (d or {}).get("query", {}).get("search", [])]


def wp_extract(title, refresh=False):
    """Lead-section plain text for an article."""
    d = wp_query(
        {"action": "query", "prop": "extracts", "exintro": "1", "explaintext": "1",
         "redirects": "1", "titles": title},
        refresh,
    )
    pages = (d or {}).get("query", {}).get("pages", [])
    if not pages or pages[0].get("missing"):
        return None
    return pages[0].get("extract")


def wp_parse_wikitext(title, section=None, refresh=False):
    """Raw wikitext of an article (or one section)."""
    p = {"action": "parse", "page": title, "prop": "wikitext", "redirects": "1"}
    if section is not None:
        p["section"] = str(section)
    d = wp_query(p, refresh)
    return ((d or {}).get("parse", {}) or {}).get("wikitext")


def wp_sections(title, refresh=False):
    d = wp_query({"action": "parse", "page": title, "prop": "sections", "redirects": "1"}, refresh)
    return ((d or {}).get("parse", {}) or {}).get("sections", [])


# ---------------------------------------------------------------------------
# MusicBrainz — 1 request/second, globally serialised
# ---------------------------------------------------------------------------
def mb(path, refresh=False, **params):
    params.setdefault("fmt", "json")
    url = MB_API + path + "?" + urllib.parse.urlencode(params)

    def go():
        with _mb_lock:
            gap = time.time() - _mb_last[0]
            if gap < 1.1:
                time.sleep(1.1 - gap)
            _mb_last[0] = time.time()
        return _fetch(url)

    return cached("mb", url, go, refresh)
