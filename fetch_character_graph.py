#!/usr/bin/env python3
"""fetch_character_graph.py — the relationships between characters.

Writes data_raw/v4/character_graph.json: enemies, family, partners and
alternate-universe counterparts for the 182 identities v3 already resolved to
Wikidata, plus a few descriptive traits (species/character type, abilities,
height, eye/hair colour) v3 fetched the entity for but never read.

    python3 fetch_character_graph.py [--refresh]

No re-resolution needed
------------------------
`fetch_wikidata_characters.py` already turned 182 of the 264 identities into
QIDs and cached the full entity under data_raw/.wd_cache/ — this just asks
those same items for properties v3 didn't read (P7047 enemy, P25/P22/P26/P40/
P451/P1038 family, P11799 alternate-universe counterpart, P2563 ability,
P9071 character type) and, separately, for every work in the dataset that has
a Wikidata id, its own P674 character list — which is how a film's own cast of
characters is known even when the identity search never found some of them.

An edge is *internal* when the other side is itself one of our 264 identities
(person QID -> our identity id, via the map v3 already built) and *external*
otherwise — Wolverine is Spider-Man's ally on Wikidata, but has no row in
`characters`. Both are kept: internal edges are the graph proper, external
edges are named strings that at least say who a character's world includes.
"""
import argparse
import json
from pathlib import Path

import wdlib as W

HERE = Path(__file__).resolve().parent
V3 = HERE / "data_raw" / "v3"
V4 = HERE / "data_raw" / "v4"
OUT = V4 / "character_graph.json"

REL_PROPS = {
    "P7047": "enemy", "P463": "ally",       # P463 filtered to teams below
    "P25": "mother", "P22": "father", "P26": "spouse", "P40": "child",
    "P451": "partner", "P1038": "relative",
    "P11799": "alternate_universe_counterpart",
}

TRAIT_PROPS = {
    "P9071": "character_type", "P2563": "ability", "P172": "ethnic_group",
    "P140": "religion", "P2048": "height", "P1340": "eye_color",
    "P1884": "hair_color", "P106": "occupation", "P641": "sport",
    "P1050": "medical_condition",
}

TEAM_ROOTS = ["Q17538722", "Q16334295", "Q7278"]  # superhero team-ish / group / party


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()

    with open(V3 / "characters_wikidata.json", encoding="utf-8") as f:
        src = json.load(f)
    by_id = src["characters"]
    qid_to_iid = {d["qid"]: int(iid) for iid, d in by_id.items()}
    W.log(f"{len(by_id)} resolved identities to query for relationships")

    qids = sorted(qid_to_iid)
    ents = W.entities_bulk(qids, props="claims|labels", refresh=args.refresh,
                           languages=W.LANGS)

    # Which P463 (member of) values are teams, so 'ally' means teammate, not
    # "works for a publisher" or "citizen of a fictional country".
    all_p463 = {v for e in ents.values() if isinstance(e, dict) for v in W.pvalues(e, "P463")}
    team_ents = W.entities_bulk(sorted(all_p463), props="claims", refresh=args.refresh)
    team_p31 = {c for e in team_ents.values() if isinstance(e, dict) for c in W.pvalues(e, "P31")}
    if team_p31:
        teams = set()
        vals = " ".join(f"wd:{q}" for q in sorted(team_p31))
        roots = " ".join(f"wd:{q}" for q in TEAM_ROOTS)
        for b in W.sparql(f"""SELECT DISTINCT ?c WHERE {{
          VALUES ?c {{ {vals} }} VALUES ?r {{ {roots} }} ?c wdt:P279* ?r . }}""", args.refresh):
            teams.add(b["c"]["value"].rsplit("/", 1)[-1])
    else:
        teams = set()

    edges = []           # {from_id, relation, to_id | to_qid, to_name}
    traits = {}           # identity_id -> {trait: [values]}
    ref_qids = set()

    for iid, d in by_id.items():
        iid = int(iid)
        e = ents.get(d["qid"])
        if not isinstance(e, dict):
            continue
        for prop, rel in REL_PROPS.items():
            vals = W.pvalues(e, prop)
            if prop == "P463":
                vals = [v for v in vals if v in teams]
            for v in vals:
                edge = {"from_id": iid, "relation": rel, "to_qid": v}
                if v in qid_to_iid:
                    edge["to_id"] = qid_to_iid[v]
                else:
                    ref_qids.add(v)
                edges.append(edge)
        for prop, trait in TRAIT_PROPS.items():
            vals = W.pvalues(e, prop)
            if not vals:
                continue
            traits.setdefault(str(iid), {})[trait] = vals
            ref_qids.update(v for v in vals if isinstance(v, str) and v.startswith("Q"))
        # teams as their own list, independent of the ally/teammate edges above,
        # since "member of the Sinister Six" is worth keeping even when the
        # fellow members aren't in `edges`.
        team_qids = [v for v in W.pvalues(e, "P463") if v in teams]
        if team_qids:
            traits.setdefault(str(iid), {})["team"] = team_qids
            ref_qids.update(team_qids)

    W.log(f"  {len(edges)} relationship edges "
          f"({sum(1 for x in edges if 'to_id' in x)} internal, "
          f"{sum(1 for x in edges if 'to_id' not in x)} external)")

    # -- work-level character lists (P674), keyed by the work's Wikidata id ---
    with open(V3 / "works_wikidata.json", encoding="utf-8") as f:
        works_src = json.load(f)
    work_casts = {}
    for wid, w in (works_src.get("works") or {}).items():
        chars_ = w.get("characters") or []
        if chars_:
            work_casts[int(wid)] = chars_
            ref_qids.update(chars_)
    W.log(f"  {len(work_casts)} works carry a Wikidata character list")

    W.log(f"labelling {len(ref_qids)} referenced items")
    labels = W.qid_labels(ref_qids, args.refresh, languages=W.LANGS)

    V4.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"edges": edges, "traits": traits, "work_casts": work_casts,
                   "labels": labels}, f, indent=1, sort_keys=True, ensure_ascii=False)
    W.log(f"wrote {OUT}")
    W.log(f"  {len(traits)} identities have at least one trait")


if __name__ == "__main__":
    main()
