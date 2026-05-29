"""
Compute per-topic centroids from data_model/runtime/topics/topic_signals.json.

Mirrors scripts/compute_agriculture_bucket_centroids.py but for the 6 EU-FarmBook
topics. Produces one normalized centroid per topic (keyed ``topic::<name>``)
plus a global ``topic::__all__`` centroid, for Stage 2 CPU scoring in the topic
inference pipeline. Multilingual by virtue of the multilingual-e5 model and the
multilingual anchors carried in topic_signals.json.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List

import numpy as np
from sentence_transformers import SentenceTransformer

REPO_ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--signals", default=str(REPO_ROOT / "data_model" / "runtime" / "topics" / "topic_signals.json"))
    p.add_argument("--model", default="intfloat/multilingual-e5-small")
    p.add_argument("--out", default=str(REPO_ROOT / "data_model" / "runtime" / "topics" / "topic_centroids.npz"))
    p.add_argument("--meta", default=str(REPO_ROOT / "data_model" / "runtime" / "topics" / "topic_centroids.meta.json"))
    p.add_argument("--batch-size", type=int, default=64)
    return p.parse_args()


def _anchor_texts(topic_payload: Dict) -> List[str]:
    """One short query string per anchor label, e5-style prefixed."""
    texts: List[str] = []
    for anchor in topic_payload.get("anchors", []):
        label = str(anchor.get("label", "")).strip()
        if label:
            texts.append(f"query: {label}")
    return texts


def _normalized_mean(matrix: np.ndarray) -> np.ndarray:
    centroid = np.mean(matrix, axis=0)
    norm = np.linalg.norm(centroid)
    if norm > 0:
        centroid = centroid / norm
    return centroid.astype(np.float32)


def main() -> None:
    args = parse_args()
    signals = json.loads(Path(args.signals).read_text(encoding="utf-8"))
    topics = signals.get("topics", {})
    if not topics:
        raise RuntimeError("No topics found in signals file")

    model = SentenceTransformer(args.model, device="cpu")
    arrays: Dict[str, np.ndarray] = {}
    topic_sizes: Dict[str, int] = {}
    all_texts: List[str] = []

    for topic_name, payload in sorted(topics.items()):
        texts = _anchor_texts(payload)
        if not texts:
            continue
        embs = model.encode(texts, normalize_embeddings=True, batch_size=args.batch_size, show_progress_bar=False)
        arrays[f"topic::{topic_name}"] = _normalized_mean(embs)
        topic_sizes[topic_name] = len(texts)
        all_texts.extend(texts)

    all_embs = model.encode(all_texts, normalize_embeddings=True, batch_size=args.batch_size, show_progress_bar=False)
    arrays["topic::__all__"] = _normalized_mean(all_embs)

    out_path = Path(args.out).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez(out_path, **arrays)

    meta_path = Path(args.meta).resolve()
    meta_path.write_text(json.dumps({
        "model": args.model,
        "source": str(Path(args.signals).resolve()),
        "signals_version": signals.get("version"),
        "topic_sizes": topic_sizes,
        "num_topics": len(topic_sizes),
    }, indent=2), encoding="utf-8")
    print(f"[OK] Wrote {out_path}")
    print(f"[OK] Wrote {meta_path}")
    for name, size in sorted(topic_sizes.items()):
        print(f"  {name:14} anchor_texts={size}")


if __name__ == "__main__":
    main()
