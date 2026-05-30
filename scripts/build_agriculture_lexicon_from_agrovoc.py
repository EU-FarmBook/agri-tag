"""
Build the runtime agriculture lexicon from a full AGROVOC export.

This builder intentionally separates:
- full AGROVOC concept storage
- filtered runtime lexical triggers

The full export can be broad. The runtime lexicon remains conservative so the
fast lexical stage stays precise and explainable.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Dict, Iterable, List, Tuple


DEFAULT_ALLOWED_LANGS = (
    "bg", "cs", "da", "de", "el", "en", "es", "et", "fi", "fr", "ga", "hr",
    "hu", "it", "lt", "lv", "mt", "nl", "pl", "pt", "ro", "sk", "sl", "sv",
)
DEFAULT_BUCKET_RULES = {
    "farming_systems": [
        "agriculture",
        "farm",
        "farming",
        "farmer",
        "farmland",
        "apiculture",
        "beekeeping",
        "apiary",
        "bee health",
        "agroforestry",
        "animal husbandry",
        "rural development",
        "food security",
    ],
    "crops_plants": [
        "crop",
        "crops",
        "cropping",
        "plant",
        "plants",
        "horticulture",
        "orchard",
        "pollination",
        "pollinator",
        "pollen",
        "flowering crop",
        "seed",
        "variety",
    ],
    "livestock_manure": [
        "livestock",
        "animal production",
        "manure",
        "slurry",
        "digestate",
        "cattle",
        "dairy",
        "poultry",
        "swine",
    ],
    "soil_water_nutrients": [
        "soil",
        "irrigation",
        "water management",
        "fertilizer",
        "fertiliser",
        "nutrient",
        "nitrate",
        "ammonium",
        "pesticide",
        "plant protection",
        "crop protection",
        "agrochemical",
        "herbicide",
        "fungicide",
        "insecticide",
    ],
    "agri_bioeconomy": [
        "biofertilizer",
        "biofertiliser",
        "biostimulant",
        "biogas",
        "nutrient recovery",
        "circular agriculture",
        "bioeconomy",
    ],
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="data_model/build/agriculture/agrovoc_full_export.jsonl")
    parser.add_argument("--out", default="data_model/runtime/agriculture/lexicon.json")
    parser.add_argument("--overrides", default="data_model/build/agriculture/lexicon_overrides.json")
    parser.add_argument("--blocklist", default="data_model/build/agriculture/lexicon_blocklist.json")
    parser.add_argument("--langs", nargs="*", default=list(DEFAULT_ALLOWED_LANGS))
    parser.add_argument("--include-unmapped", action="store_true")
    return parser.parse_args()


def _load_json(path: Path, default: Dict) -> Dict:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _concept_id_from_uri(uri: str) -> str:
    raw = (uri or "").rstrip("/")
    tail = raw.rsplit("/", 1)[-1]
    return f"AGROVOC:{tail}" if tail else raw


def _split_lang_labels(items: Iterable[str]) -> List[Tuple[str, str]]:
    labels: List[Tuple[str, str]] = []
    for item in items:
        if "::" not in item:
            continue
        lang, label = item.split("::", 1)
        lang = lang.strip().lower()
        label = label.strip()
        if lang and label:
            labels.append((lang, label))
    return labels


def _infer_bucket(texts: List[str], overrides: Dict) -> str | None:
    normalized_text = " ".join(_normalize(item) for item in texts if item)
    label_rules = overrides.get("bucket_by_pref_label", {})
    pref_exact = _normalize(texts[0]) if texts else ""
    if pref_exact in label_rules:
        return str(label_rules[pref_exact])

    merged_rules = dict(DEFAULT_BUCKET_RULES)
    merged_rules.update(overrides.get("bucket_keyword_rules", {}))
    scored: List[Tuple[str, int]] = []
    for bucket, keywords in merged_rules.items():
        score = sum(1 for keyword in keywords if _normalize(keyword) in normalized_text)
        if score:
            scored.append((bucket, score))
    if not scored:
        return None
    scored.sort(key=lambda item: item[1], reverse=True)
    return scored[0][0]


def _filter_labels(
    labels: List[Tuple[str, str]],
    *,
    allowed_langs: set[str],
    blocklist: Dict,
) -> List[Dict[str, str]]:
    blocked_exact = {_normalize(item) for item in blocklist.get("exact_labels", [])}
    blocked_regexes = [re.compile(pattern, re.I) for pattern in blocklist.get("regex_patterns", [])]
    min_label_length = int(blocklist.get("min_label_length", 3))
    max_labels_per_concept = int(blocklist.get("max_labels_per_concept", 24))

    kept: List[Dict[str, str]] = []
    seen: set[Tuple[str, str]] = set()
    for lang, label in labels:
        key = (lang, _normalize(label))
        if lang not in allowed_langs:
            continue
        if len(label.strip()) < min_label_length:
            continue
        if key[1] in blocked_exact:
            continue
        if any(regex.search(label) for regex in blocked_regexes):
            continue
        if key in seen:
            continue
        seen.add(key)
        kept.append({"language": lang, "label": label.strip()})
        if len(kept) >= max_labels_per_concept:
            break
    return kept


def main() -> None:
    args = parse_args()
    input_path = Path(args.input).resolve()
    out_path = Path(args.out).resolve()
    overrides_path = Path(args.overrides).resolve()
    blocklist_path = Path(args.blocklist).resolve()
    allowed_langs = {lang.strip().lower() for lang in args.langs}

    overrides = _load_json(
        overrides_path,
        {
            "bucket_by_concept_id": {},
            "bucket_by_pref_label": {},
            "bucket_keyword_rules": {},
            "strong_anchor_concept_ids": [],
            "strong_anchor_pref_labels": [],
        },
    )
    blocklist = _load_json(
        blocklist_path,
        {
            "exact_labels": [],
            "regex_patterns": [],
            "min_label_length": 3,
            "max_labels_per_concept": 24,
        },
    )

    concepts: List[Dict] = []
    strong_anchor_concept_ids = {item.strip() for item in overrides.get("strong_anchor_concept_ids", [])}
    strong_anchor_pref_labels = {_normalize(item) for item in overrides.get("strong_anchor_pref_labels", [])}
    bucket_by_concept_id = {key.strip(): value for key, value in overrides.get("bucket_by_concept_id", {}).items()}

    with input_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            pref_en = str(row.get("prefLabel_en", "")).strip()
            if not pref_en:
                continue

            concept_id = _concept_id_from_uri(str(row.get("uri", "")))
            bucket = bucket_by_concept_id.get(concept_id)
            if not bucket:
                bucket = _infer_bucket(
                    [
                        pref_en,
                        *row.get("altLabels_en", []),
                        *row.get("broader_prefLabels_en", []),
                        row.get("note_en", ""),
                    ],
                    overrides,
                )
            if not bucket and not args.include_unmapped:
                continue

            pref_labels = _split_lang_labels(row.get("pref_labels", []))
            alt_labels = _split_lang_labels(row.get("alt_labels", []))
            all_pref = pref_labels or [("en", pref_en)]
            primary_pref = next((item for item in all_pref if item[0] == "en"), all_pref[0])
            filtered_alt_labels = _filter_labels(
                [item for item in alt_labels if _normalize(item[1]) != _normalize(primary_pref[1])],
                allowed_langs=allowed_langs,
                blocklist=blocklist,
            )

            concept = {
                "concept_id": concept_id,
                "bucket": bucket or "unmapped",
                "preferred_label": {"language": primary_pref[0], "label": primary_pref[1]},
                "alt_labels": filtered_alt_labels,
                "strong_anchor": concept_id in strong_anchor_concept_ids or _normalize(primary_pref[1]) in strong_anchor_pref_labels,
            }
            concepts.append(concept)

    concepts.sort(key=lambda item: (item["bucket"], item["preferred_label"]["label"].lower(), item["concept_id"]))
    payload = {
        "version": "agrovoc_full_filtered_v1",
        "description": (
            "Generated runtime agriculture lexicon derived from a full AGROVOC export, "
            "with local overrides and blocklist filters applied for fast lexical matching."
        ),
        "concepts": concepts,
    }
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"[OK] Wrote {len(concepts)} concepts -> {out_path}")


if __name__ == "__main__":
    main()
