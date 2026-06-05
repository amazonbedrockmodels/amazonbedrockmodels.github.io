#!/usr/bin/env python3
"""
Add mantle-only models to data/models.json.

Some models (notably the OpenAI gpt-5.x series) are served exclusively through
the OpenAI-compatible bedrock-mantle endpoint and never appear in the classic
control-plane list_foundation_models() response that refresh-bedrock-data.py
builds models.json from. They are therefore invisible on the site even though
they are live.

This script reconciles data/mantle_models.json (live /v1/models truth) against
models.json and appends synthetic entries for any mantle model that is genuinely
missing — using each model card's own enumeration of ID variants as the join
key, so models that are merely named differently (e.g. qwen3-coder-...-v1:0 vs
qwen.qwen3-coder-480b-a35b-instruct) are NOT duplicated.

Run AFTER scrape_model_cards.py --enrich-models (needs model_cards.json with
mantleRegions already applied). Idempotent: re-adds the same entries each run.

Output: rewrites data/models.json in place.
"""

import argparse
import json
import re
import sys
from pathlib import Path

# Strip a trailing dated snapshot suffix (e.g. -2026-04-23) to collapse
# point-in-time pins into their parent model.
_SNAPSHOT_RE = re.compile(r"-\d{4}-\d{2}-\d{2}$")


def parent_id(model_id: str) -> str:
    return _SNAPSHOT_RE.sub("", model_id)


def derive_name(model_id: str) -> str:
    """Best-effort display name from an id like 'zai.glm-4.6' -> 'GLM 4.6'."""
    tail = model_id.split(".", 1)[1] if "." in model_id else model_id
    return tail.replace("-", " ").replace("_", " ").upper()


def main():
    parser = argparse.ArgumentParser(description="Add mantle-only models to models.json")
    parser.add_argument("--models", default="data/models.json")
    parser.add_argument("--cards", default="data/model_cards.json")
    parser.add_argument("--mantle", default="data/mantle_models.json")
    args = parser.parse_args()

    models_path = Path(args.models)
    cards_path = Path(args.cards)
    mantle_path = Path(args.mantle)

    if not (models_path.exists() and mantle_path.exists()):
        print("models.json or mantle_models.json missing — nothing to do.")
        return

    models = json.loads(models_path.read_text())
    mantle = json.loads(mantle_path.read_text())
    cards = json.loads(cards_path.read_text()) if cards_path.exists() else {}

    mj_ids = {m.get("modelId", "") for m in models}

    # provider lookup from existing data: id-prefix -> providerName
    prov_by_prefix = {}
    for m in models:
        prefix = m.get("modelId", "").split(".")[0]
        if prefix and prefix not in prov_by_prefix:
            prov_by_prefix[prefix] = m.get("providerName", "")

    # modelId -> card (via the card's own modelIds enumeration)
    id_to_card = {}
    for slug, c in cards.items():
        for mid in c.get("metadata", {}).get("modelIds", []):
            id_to_card[mid] = (slug, c)

    # Find genuinely-missing mantle ids (no id form is in models.json)
    missing = []
    for mid in mantle:
        card = id_to_card.get(mid)
        if card:
            card_ids = card[1].get("metadata", {}).get("modelIds", [])
            if any(cid in mj_ids for cid in card_ids):
                continue  # already on site under another id
        elif mid in mj_ids:
            continue
        missing.append(mid)

    # Group by parent so dated snapshots fold into one entry
    by_parent = {}
    for mid in missing:
        by_parent.setdefault(parent_id(mid), []).append(mid)

    added = 0
    for parent in sorted(by_parent):
        if parent in mj_ids:
            continue
        snapshots = sorted(x for x in by_parent[parent] if x != parent)
        prefix = parent.split(".")[0]
        card = id_to_card.get(parent) or id_to_card.get(by_parent[parent][0])
        meta = card[1].get("metadata", {}) if card else {}

        regions = sorted(set(mantle.get(parent, [])).union(
            *[set(mantle.get(s, [])) for s in by_parent[parent]]
        )) if by_parent[parent] else mantle.get(parent, [])

        model_card = {
            "modelLaunchDate": meta.get("modelLaunchDate"),
            "modelEolDate": meta.get("modelEolDate"),
            "apisSupported": meta.get("apisSupported", {}),
            "endpointsSupported": meta.get(
                "endpointsSupported", {"bedrockRuntime": False, "bedrockMantle": True}
            ),
            "mantleRegions": meta.get("mantleRegions", regions),
            "modelCardUrl": card[1].get("url", "") if card else "",
        }

        entry = {
            "modelId": parent,
            "modelName": (card[1].get("title") if card else None) or derive_name(parent),
            "providerName": prov_by_prefix.get(prefix, prefix.replace("-", " ").title()),
            "inputModalities": [],
            "outputModalities": [],
            "inferenceTypesSupported": ["ON_DEMAND"],
            "modelLifecycle": {"status": "ACTIVE"},
            "regions": regions,
            "mantleOnly": True,
            "modelCard": model_card,
        }
        if snapshots:
            entry["snapshotIds"] = snapshots

        models.append(entry)
        mj_ids.add(parent)
        added += 1
        print(f"  + {parent}  ({entry['providerName']}, {len(regions)} mantle regions)"
              + (f"  snapshots={snapshots}" if snapshots else ""))

    models_path.write_text(json.dumps(models, indent=2, default=str))
    print(f"\nAdded {added} mantle-only model(s); models.json now has {len(models)} entries.")


if __name__ == "__main__":
    main()
