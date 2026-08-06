#!/usr/bin/env python3
"""fetch_related_characters.py — the second ring of the character graph.

v4 wrote 790 relationship edges, but 533 of them end in a name rather than a
row: Spider-Man is an enemy of Mysterio (in the dataset) and also of Mephisto,
the X-Men and Richard Fisk (not). Every one of those dead ends already carries
a Wikidata id, so the other side of the edge is identified — just not described.

This resolves them. It reads the QIDs v4 could not map from
data_raw/v4/character_graph.json — both the external edge targets and the
entries of a work's own P674 character list that never matched an identity —
and writes data_raw/v5/related_characters.json:

* one record per second-ring character: label, description, English Wikipedia
  title, instance-of, gender, publisher, narrative universe, first appearance
  and creators;
* the relationships *between* second-ring characters, and back to the 264.
  Only edges whose far side is itself in scope are kept, so the graph closes
  instead of sprouting a third ring of new dead ends.

    python3 fetch_related_characters.py [--refresh]

No search step is needed and nothing is guessed: every id here was published by
Wikidata as the value of a relationship claim on an item v3 had already
resolved. The cost is one bulk entity call per 50 ids.
"""
import argparse
import json
from pathlib import Path

import wdlib as W

HERE = Path(__file__).resolve().parent
V3 = HERE / "data_raw" / "v3"
V4 = HERE / "data_raw" / "v4"
V5 = HERE / "data_raw" / "v5"
OUT = V5 / "related_characters.json"

# Same relationship vocabulary v4 uses, so first-ring and second-ring edges are
# the same kind of thing and can be read out of one view.
REL_PROPS = {
    "P7047": "enemy",
    "P25": "mother", "P22": "father", "P26": "spouse", "P40": "child",
    "P451": "partner", "P1038": "relative",
    "P11799": "alternate_universe_counterpart",
}

ATTR_PROPS = {
    "P31": "instance_of", "P21": "gender", "P123": "publisher",
    "P1080": "narrative_universe", "P4584": "first_appearance",
    "P170": "creator", "P9071": "character_type",
}

MULTI = {"instance_of", "narrative_universe", "creator", "character_type"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()

    with open(V4 / "character_graph.json", encoding="utf-8") as f:
        graph = json.load(f)
    with open(V3 / "characters_wikidata.json", encoding="utf-8") as f:
        known = {d["qid"] for d in json.load(f)["characters"].values() if d.get("qid")}

    # The dead ends, from both directions v4 recorded them.
    targets = {e["to_qid"] for e in graph["edges"]
               if "to_id" not in e and e.get("to_qid")}
    cast_only = {q for qs in (graph.get("work_casts") or {}).values() for q in qs}
    unresolved = sorted((targets | cast_only) - known)
    W.log(f"{len(targets)} external edge targets, "
          f"{len(cast_only - known - targets)} more from work character lists")
    W.log(f"resolving {len(unresolved)} second-ring characters")

    ents = W.entities_bulk(unresolved, props="claims|labels|descriptions|sitelinks",
                           refresh=args.refresh, languages=W.LANGS)

    in_scope = known | set(unresolved)
    chars, edges, ref_qids = {}, [], set()

    for qid in unresolved:
        e = ents.get(qid)
        if not isinstance(e, dict):
            continue
        rec = {"qid": qid, "name": W.en_label(e)}
        desc = (e.get("descriptions") or {})
        rec["description"] = (desc.get("en") or desc.get("mul") or {}).get("value")
        rec["enwiki"] = (e.get("sitelinks") or {}).get("enwiki", {}).get("title")
        for prop, attr in ATTR_PROPS.items():
            vals = W.pvalues(e, prop)
            vals = [v for v in vals if isinstance(v, str) and v.startswith("Q")]
            if not vals:
                continue
            rec[attr] = vals if attr in MULTI else vals[0]
            ref_qids.update(vals)
        chars[qid] = rec

        for prop, rel in REL_PROPS.items():
            for v in W.pvalues(e, prop):
                if isinstance(v, str) and v in in_scope and v != qid:
                    edges.append({"from_qid": qid, "relation": rel, "to_qid": v})

    W.log(f"  {len(chars)} resolved, {len(edges)} edges between second-ring "
          f"characters and the rest of the graph")

    ref_qids -= set(chars)
    W.log(f"labelling {len(ref_qids)} referenced items")
    labels = W.qid_labels(ref_qids, args.refresh, languages=W.LANGS)
    labels.update({q: c["name"] for q, c in chars.items() if c.get("name")})

    V5.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"characters": chars, "edges": edges, "labels": labels},
                  f, indent=1, sort_keys=True, ensure_ascii=False)
    W.log(f"wrote {OUT}")
    named = sum(1 for c in chars.values() if c.get("name"))
    W.log(f"  {named} have a label, "
          f"{sum(1 for c in chars.values() if c.get('enwiki'))} a Wikipedia article, "
          f"{sum(1 for c in chars.values() if c.get('publisher'))} a publisher")


if __name__ == "__main__":
    main()
