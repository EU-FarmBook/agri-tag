#!/usr/bin/env python3
"""
Score an eval CSV against ground-truth labels (data_model/eval/labels.json).

Reports per-provider accuracy on the labelled subset, split by label source
(agreement vs the hand-judged "manual" rows that actually differentiate providers),
plus the per-file errors so you can see exactly where each provider is wrong.

Usage:
    python scripts/score_eval.py --eval eval_212.csv
    python scripts/score_eval.py --eval eval_after_prompt_fix.csv   # before/after a change
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _pred(row):
    if not row or row.get("http_status") != "200":
        return f"HTTP{row.get('http_status') if row else '?'}"
    if row.get("classification_skipped") == "True":
        return "SKIP"
    return row.get("best_subcategory") or "?"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--eval", default="eval_212.csv")
    ap.add_argument("--labels", default=str(ROOT / "data_model" / "eval" / "labels.json"))
    ap.add_argument("--show-errors", action="store_true", help="list every wrong prediction")
    args = ap.parse_args()

    labels = json.loads(Path(args.labels).read_text())["labels"]
    rows = list(csv.DictReader(open(args.eval)))
    by = {}
    for r in rows:
        by.setdefault(r["file"], {})[r["provider"]] = r

    providers = sorted({r["provider"] for r in rows})
    # tallies[provider][source] = [correct, total]
    tallies = {p: {"agreement": [0, 0], "manual": [0, 0], "all": [0, 0]} for p in providers}
    errors = {p: [] for p in providers}

    for f, meta in labels.items():
        if f not in by:
            continue
        exp, src = meta["expected"], meta["source"]
        for p in providers:
            pred = _pred(by[f].get(p))
            ok = pred == exp
            for bucket in (src, "all"):
                tallies[p][bucket][0] += int(ok)
                tallies[p][bucket][1] += 1
            if not ok:
                errors[p].append((f, exp, pred, src))

    def pct(ct):
        c, t = ct
        return f"{(100*c/t):5.1f}% ({c}/{t})" if t else "  n/a"

    print(f"Eval: {args.eval}   labelled files: {len(labels)}\n")
    print(f"{'provider':9} | {'ALL':18} | {'agreement (bootstrap)':22} | {'MANUAL (differentiating)':24}")
    print("-" * 82)
    for p in providers:
        t = tallies[p]
        print(f"{p:9} | {pct(t['all']):18} | {pct(t['agreement']):22} | {pct(t['manual']):24}")

    print("\nThe MANUAL column is the real signal — agreement rows score ~100% for both")
    print("by construction (the label IS what both produced).")

    if args.show_errors:
        for p in providers:
            print(f"\n=== {p} errors ({len(errors[p])}) ===")
            for f, exp, pred, src in sorted(errors[p], key=lambda x: x[3]):
                print(f"  [{src:10}] {f[:46]:46} expected={exp[:28]:28} got={pred}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
