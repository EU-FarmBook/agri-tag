"""
Compute per-bucket agriculture centroids from anchor JSONL files.

The output is designed for Stage 2 CPU scoring in the runtime agriculture
pipeline. It stores one centroid per bucket plus a global agriculture centroid.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Dict, List

import numpy as np
from sentence_transformers import SentenceTransformer


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--inputs", nargs="+", required=True)
    p.add_argument("--model", default="intfloat/multilingual-e5-small")
    p.add_argument("--out", default="data_model/runtime/agriculture/bucket_centroids.npz")
    p.add_argument("--meta", default="data_model/runtime/agriculture/bucket_centroids.meta.json")
    p.add_argument("--batch-size", type=int, default=64)
    return p.parse_args()


def _load_anchor_rows(paths: List[Path]) -> Dict[str, List[str]]:
    by_bucket: Dict[str, List[str]] = defaultdict(list)
    for path in paths:
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                bucket = str(row.get("bucket", "")).strip()
                text = str(row.get("anchor_text", "") or row.get("text", "")).strip()
                if bucket and text:
                    by_bucket[bucket].append(text)
    return by_bucket


def _normalized_mean(matrix: np.ndarray) -> np.ndarray:
    centroid = np.mean(matrix, axis=0)
    norm = np.linalg.norm(centroid)
    if norm > 0:
        centroid = centroid / norm
    return centroid.astype(np.float32)


def main() -> None:
    args = parse_args()
    input_paths = [Path(item).resolve() for item in args.inputs]
    bucket_texts = _load_anchor_rows(input_paths)
    if not bucket_texts:
        raise RuntimeError("No bucketed anchor texts found")

    model = SentenceTransformer(args.model, device="cpu")
    arrays: Dict[str, np.ndarray] = {}
    bucket_sizes: Dict[str, int] = {}
    all_texts: List[str] = []

    for bucket, texts in sorted(bucket_texts.items()):
        prefixed = [f"query: {text}" for text in texts]
        embs = model.encode(prefixed, normalize_embeddings=True, batch_size=args.batch_size, show_progress_bar=False)
        arrays[f"bucket::{bucket}"] = _normalized_mean(embs)
        bucket_sizes[bucket] = len(texts)
        all_texts.extend(prefixed)

    all_embs = model.encode(all_texts, normalize_embeddings=True, batch_size=args.batch_size, show_progress_bar=False)
    arrays["bucket::__all__"] = _normalized_mean(all_embs)

    out_path = Path(args.out).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez(out_path, **arrays)

    meta_path = Path(args.meta).resolve()
    meta_path.write_text(json.dumps({
        "model": args.model,
        "sources": [str(p) for p in input_paths],
        "bucket_sizes": bucket_sizes,
        "num_buckets": len(bucket_sizes),
    }, indent=2), encoding="utf-8")
    print(f"[OK] Wrote {out_path}")
    print(f"[OK] Wrote {meta_path}")


if __name__ == "__main__":
    main()
