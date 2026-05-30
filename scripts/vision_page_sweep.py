#!/usr/bin/env python3
"""
Vision page-count sweep: send N pages to the vision model and compare speed + result.

Forces vision ON (auto_route_models=false, use_vision=true, use_text_llm=false) so each
run actually calls the VLM and isolates the vision signal, and varies vision_max_pages
so the deterministic sampler sends exactly N stratified pages per run.

Usage:
  python scripts/vision_page_sweep.py "files/11-20 DESIRA-_-WP4-1.pdf"
  python scripts/vision_page_sweep.py <file> --pages 1 2 3 4 8 --provider custom
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--pages", nargs="+", type=int, default=[1, 2, 3, 4])
    ap.add_argument("--provider", default="custom")
    ap.add_argument("--repeat", type=int, default=1, help="runs per page-count (median of vision_ms)")
    args = ap.parse_args()

    from fastapi.testclient import TestClient
    import app as appmod

    client = TestClient(appmod.app)
    user = os.getenv("DOCINT_AUTH_USERS", "").split(",")[0].strip()
    pw = os.getenv("DOCINT_AUTH_PASSWORD", "").strip()
    auth = (user, pw) if user and pw else None

    f = Path(args.file)
    if not f.is_file():
        print(f"file not found: {f}", file=sys.stderr)
        return 2

    print(f"Sweep: {f.name}  provider={args.provider}  (vision forced on, text LLM off)\n")
    header = f"{'pages':>5} {'vision_ms':>10} {'wall_ms':>8}  {'vision_subcategory':34} {'conf':>5}  {'fused_best':30}"
    print(header)
    print("-" * len(header))
    for n in args.pages:
        params = {
            "use_vision": "true",
            "use_text_llm": "false",
            "auto_route_models": "false",
            "require_agriculture": "false",
            "fusion_strategy": "adaptive",
            "vision_max_pages": n,
            "provider": args.provider,
            "debug": "true",
        }
        vms_runs = []
        last = None
        wall = 0
        for _ in range(max(1, args.repeat)):
            t0 = time.time()
            with open(f, "rb") as fh:
                r = client.post("/classify", params=params, files={"file": (f.name, fh, "application/pdf")}, auth=auth)
            wall = round((time.time() - t0) * 1000)
            if r.status_code != 200:
                print(f"{n:>5}  HTTP {r.status_code}: {r.text[:90]}")
                last = None
                break
            d = r.json()
            last = d
            vms = (d.get("processing_info", {}).get("stage_timings_ms", {}) or {}).get("vision_llm_ms")
            if vms is not None:
                vms_runs.append(float(vms))
        if last is None:
            continue
        vis = last.get("vision_llm") or {}
        best = (last.get("best_match") or {}).get("subcategory_name")
        vms_med = round(sorted(vms_runs)[len(vms_runs) // 2]) if vms_runs else "n/a"
        print(f"{n:>5} {str(vms_med):>10} {wall:>8}  {str(vis.get('subcategory_name'))[:34]:34} {str(vis.get('confidence'))[:5]:>5}  {str(best)[:30]:30}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
