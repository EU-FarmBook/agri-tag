"""
Build agriculture anchor texts from the runtime lexicon JSON.

This gives the repo a reproducible bootstrap path for Stage 2 even before a
full AGROVOC export is available locally.
"""

from __future__ import annotations

import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
LEXICON_PATH = REPO_ROOT / "data_model" / "runtime" / "agriculture" / "lexicon.json"
OUT_PATH = REPO_ROOT / "data_model" / "build" / "agriculture" / "anchor_texts.jsonl"


def main() -> None:
    payload = json.loads(LEXICON_PATH.read_text(encoding="utf-8"))
    concepts = payload.get("concepts", [])
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    with OUT_PATH.open("w", encoding="utf-8") as fh:
        for concept in concepts:
            pref = concept["preferred_label"]
            pref_text = str(pref["label"]).strip()
            pref_lang = str(pref["language"]).strip().lower()
            alt_labels = concept.get("alt_labels", [])
            labels = [f"{pref_lang}::{pref_text}"] + [
                f"{str(item['language']).strip().lower()}::{str(item['label']).strip()}"
                for item in alt_labels
                if str(item.get("label", "")).strip()
            ]
            text = (
                f"Concept: {pref_text}. "
                f"Bucket: {concept['bucket']}. "
                f"Strong anchor: {'yes' if concept.get('strong_anchor', False) else 'no'}. "
                f"Labels: {'; '.join(labels)}."
            )
            fh.write(json.dumps({
                "concept_id": concept["concept_id"],
                "bucket": concept["bucket"],
                "source": "runtime_lexicon",
                "anchor_text": text,
            }, ensure_ascii=False) + "\n")

    print(f"[OK] Wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
