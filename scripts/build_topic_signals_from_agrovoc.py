"""
Build multilingual topic signals from the full AGROVOC export.

Topics are the 6 high-level EU-FarmBook topics (Forestry, Livestock,
Crop farming, Economics, Environment, Society). Unlike the agriculture
*buckets*, these are multi-label: one knowledge object can carry several
topics at once.

The signal sets are *curated by us* (the SEED_RULES below) and then expanded
through AGROVOC so that every matched concept contributes its labels in all
available languages (en/fr/es/de/it/nl/el). That is what makes downstream
matching multilingual without us hand-translating anything.

Output: data_model/runtime/topics/topic_signals.json
    {
      "version": ...,
      "topics": {
        "<Topic name>": {
          "seed_terms": [...],            # the curated English anchors
          "concept_ids": [...],           # AGROVOC concepts assigned here
          "anchors": [{language,label,concept_id,strong}, ...],
          "negative_terms": [...]
        }, ...
      }
    }
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

REPO_ROOT = Path(__file__).resolve().parents[1]
AGROVOC_EXPORT = REPO_ROOT / "data_model" / "build" / "agriculture" / "agrovoc_full_export.jsonl"
TOPICS_MODEL = REPO_ROOT / "data_model" / "build" / "topics" / "topics.json"
OUT_PATH = REPO_ROOT / "data_model" / "runtime" / "topics" / "topic_signals.json"

VERSION = "topic_signals_agrovoc_v1"

# Curated, hand-authored signal seeds per topic.
#   seed_terms : substrings matched against the English preferred/alt labels.
#   broader    : AGROVOC broader_prefLabels_en (lower-cased) used to pull whole
#                concept subtrees into a topic.
#   core       : the strongest, least ambiguous seeds; concepts whose English
#                preferred label contains one of these are flagged strong.
#   negative   : substrings that veto a concept (kill cross-topic false friends).
SEED_RULES: Dict[str, Dict[str, List[str]]] = {
    "Crop farming": {
        "core": ["crop", "cereal", "horticulture", "arable", "agronomy"],
        "seed_terms": [
            "crop", "cereal", "wheat", "maize", "barley", "rice", "soybean",
            "horticultur", "vegetable", "fruit", "vineyard", "orchard", "sowing",
            "harvest", "yield", "cultivar", "variety", "agronom", "tillage",
            "arable", "grain", "legume", "potato", "rye", "oat", "sorghum",
            "weed", "fungicide", "herbicide", "germination", "plant protection",
        ],
        "broader": ["crops", "plant production", "horticulture", "agronomy"],
        "negative": ["forest", "timber", "silvicult"],
    },
    "Livestock": {
        "core": ["livestock", "cattle", "dairy", "poultry", "animal husbandry"],
        "seed_terms": [
            "livestock", "cattle", "dairy", "milk", "poultry", "chicken", "pig",
            "swine", "sheep", "goat", "bovine", "ovine", "caprine", "fodder",
            "grazing", "pasture", "manure", "slurry", "veterinar", "animal health",
            "animal husbandry", "animal feeding", "herd", "beekeeping", "apicultur",
            "aquacultur", "fish farming", "breed",
        ],
        "broader": ["animal husbandry", "livestock", "animal production"],
        "negative": ["crop residue", "phytoplankton"],
    },
    "Forestry": {
        "core": ["forest", "forestry", "silvicult", "timber", "agroforest"],
        "seed_terms": [
            "forest", "forestry", "silvicult", "timber", "woodland", "agroforest",
            "reforest", "afforest", "deforest", "logging", "tree species", "woody",
            "woodchip", "coppice", "forest management",
        ],
        "broader": ["forestry", "forests"],
        "negative": [],
    },
    "Economics": {
        "core": ["market", "price", "subsid", "income", "value chain"],
        "seed_terms": [
            "market", "price", "subsid", "income", "value chain", "supply chain",
            "trade", "export", "import", "profit", "cost", "economic", "finance",
            "credit", "investment", "business model", "gross margin", "employment",
            "common agricultural policy", "farm income",
        ],
        "broader": ["economics", "marketing", "trade", "agricultural economics"],
        "negative": [],
    },
    "Environment": {
        "core": ["biodiversity", "climate", "ecosystem", "emission", "pollution"],
        "seed_terms": [
            "biodiversity", "climate", "greenhouse gas", "emission", "carbon",
            "ecosystem", "pollution", "water quality", "soil health", "erosion",
            "leaching", "sustainab", "environmental", "conservation", "habitat",
            "eutrophication", "renewable", "biogas", "circular", "land degradation",
            "drought", "flood", "ecosystem services",
        ],
        "broader": ["environment", "pollution", "climate", "ecology"],
        "negative": [],
    },
    "Society": {
        "core": ["rural", "gender", "governance", "cooperative", "extension"],
        "seed_terms": [
            "rural", "gender", "women", "youth", "labour", "training", "education",
            "extension service", "knowledge transfer", "governance", "social",
            "cooperative", "participatory", "inclusion", "equity", "wellbeing",
            "demographics", "migration", "food security", "capacity building",
        ],
        "broader": ["society", "rural communities", "social sciences", "education"],
        "negative": ["phytoplankton", "microbial community", "plant community"],
    },
}

MAX_ANCHORS_PER_TOPIC = 12000


def _parse_lang_label(item: str) -> tuple[str, str]:
    if "::" in item:
        lang, label = item.split("::", 1)
        return lang.strip().lower(), label.strip()
    return "en", item.strip()


def _matches(text: str, terms: List[str]) -> bool:
    return any(term in text for term in terms)


def _published_topic_names() -> List[str]:
    """Topic names from the canonical topics data model (keeps us aligned)."""
    try:
        rows = json.loads(TOPICS_MODEL.read_text(encoding="utf-8"))
        names = [str(r.get("name", "")).strip() for r in rows if r.get("name")]
        return [n for n in names if n]
    except Exception:
        return list(SEED_RULES.keys())


def main() -> None:
    published = set(_published_topic_names())
    missing = published - set(SEED_RULES.keys())
    if missing:
        print(f"[WARN] topics in data model with no seed rules: {sorted(missing)}")

    topics_out: Dict[str, Dict] = {
        name: {
            "seed_terms": rule["seed_terms"],
            "negative_terms": rule.get("negative", []),
            "concept_ids": [],
            "anchors": [],
            "_seen": set(),
        }
        for name, rule in SEED_RULES.items()
    }

    scanned = 0
    with AGROVOC_EXPORT.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            scanned += 1
            concept = json.loads(line)
            concept_id = str(concept.get("uri", "")).rsplit("/", 1)[-1]
            en_pref = str(concept.get("prefLabel_en", "")).lower()
            en_alts = " ".join(str(a).lower() for a in concept.get("altLabels_en", []))
            broader = [str(b).strip().lower() for b in concept.get("broader_prefLabels_en", [])]
            haystack = f"{en_pref} {en_alts}"

            for topic_name, rule in SEED_RULES.items():
                if _matches(haystack, rule.get("negative", [])):
                    continue
                hit = _matches(haystack, rule["seed_terms"]) or any(b in rule["broader"] for b in broader)
                if not hit:
                    continue

                bucket = topics_out[topic_name]
                if len(bucket["anchors"]) >= MAX_ANCHORS_PER_TOPIC:
                    continue
                # Strong = a curated seed term appears directly in the English
                # preferred label (a precise lexical hit). Concepts pulled in only
                # via the broader-subtree hierarchy stay weak (embedding-only).
                strong = _matches(en_pref, rule["seed_terms"])
                bucket["concept_ids"].append(concept_id)

                labels = list(concept.get("pref_labels", [])) + list(concept.get("alt_labels", []))
                for raw in labels:
                    lang, label = _parse_lang_label(raw)
                    norm = label.lower()
                    if not norm or len(norm) < 3:
                        continue
                    key = (lang, norm)
                    if key in bucket["_seen"]:
                        continue
                    bucket["_seen"].add(key)
                    bucket["anchors"].append(
                        {"language": lang, "label": label, "concept_id": concept_id, "strong": strong}
                    )

    payload = {
        "version": VERSION,
        "description": (
            "Multilingual topic signal sets derived from a full AGROVOC export using "
            "curated per-topic seed rules. Multi-label by design."
        ),
        "generated_ts": datetime.now(timezone.utc).isoformat(),
        "source": str(AGROVOC_EXPORT.relative_to(REPO_ROOT)),
        "topics": {},
    }
    for name, bucket in topics_out.items():
        bucket.pop("_seen", None)
        bucket["concept_ids"] = sorted(set(bucket["concept_ids"]))
        payload["topics"][name] = bucket

    OUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] Scanned {scanned} AGROVOC concepts")
    for name, bucket in payload["topics"].items():
        strong = sum(1 for a in bucket["anchors"] if a["strong"])
        langs = sorted({a["language"] for a in bucket["anchors"]})
        print(f"  {name:14} concepts={len(bucket['concept_ids']):5} anchors={len(bucket['anchors']):5} strong={strong:4} langs={langs}")
    print(f"[OK] Wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
