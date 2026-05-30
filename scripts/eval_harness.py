#!/usr/bin/env python3
"""
Eval harness — run every file under a folder through POST /classify and write a CSV.

Runs the FastAPI app **in-process** via TestClient (no running server needed) and
reads Basic Auth from DOCINT_AUTH_USERS / DOCINT_AUTH_PASSWORD in .env.

Examples:
    # default: every supported file in files/, provider=custom -> eval_results.csv
    python scripts/eval_harness.py

    # compare both providers (one CSV row per file per provider)
    python scripts/eval_harness.py --providers custom,mistral

    # heuristics-only, fast, no remote LLM calls
    python scripts/eval_harness.py --no-vision --no-text-llm

    # custom dir / output / limits
    python scripts/eval_harness.py --files-dir files --out out.csv --limit 5 --vision-max-pages 8

Notes:
- vision_max_pages defaults to 8 to respect a VLM launched with image:8 limits.
- Each file is processed independently; an error on one file is recorded and the
  run continues.
"""
from __future__ import annotations

import argparse
import csv
import mimetypes
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _join_scored(items, name_key, score_key, limit=3):
    out = []
    for it in (items or [])[:limit]:
        try:
            out.append(f"{it.get(name_key)}:{round(float(it.get(score_key, 0)), 3)}")
        except Exception:
            out.append(str(it.get(name_key)))
    return " | ".join(out)


def _extract_row(rel_path, ext, provider, status, wall_ms, payload, error=""):
    d = payload or {}
    best = d.get("best_match") or {}
    cands = d.get("all_candidates") or []
    agri = d.get("agriculture_relevance") or {}
    topics = (d.get("topics") or {}).get("topics") if d.get("topics") else []
    purposes = (d.get("intended_purposes") or {}).get("purposes") if d.get("intended_purposes") else []
    pinfo = d.get("processing_info") or {}
    timings = pinfo.get("stage_timings_ms") or {}
    return {
        "file": rel_path,
        "ext": ext,
        "provider": provider,
        "http_status": status,
        "category_used": d.get("category_used"),
        "best_subcategory": best.get("subcategory_name"),
        "best_confidence": best.get("confidence"),
        "n_candidates": len(cands),
        "second_subcategory": (cands[1].get("subcategory_name") if len(cands) > 1 else ""),
        "agri_related": agri.get("is_agriculture_related"),
        "agri_confidence": agri.get("confidence"),
        "agri_method": agri.get("method"),
        "topics": _join_scored(topics, "topic", "score"),
        "intended_purposes": _join_scored(purposes, "name", "score"),
        "classification_skipped": d.get("classification_skipped"),
        "skip_reason": d.get("skip_reason"),
        "sources_used": " | ".join(pinfo.get("sources_used") or []),
        "wall_ms": wall_ms,
        "processing_time_ms": pinfo.get("processing_time_ms"),
        "ocr_used": pinfo.get("ocr_used"),
        "t_ocr_ms": timings.get("ocr_fallback_ms"),
        "t_agri_ms": timings.get("agriculture_pipeline_ms"),
        "t_text_llm_ms": timings.get("text_llm_ms"),
        "t_vision_llm_ms": timings.get("vision_llm_ms"),
        "t_purposes_ms": timings.get("intended_purposes_ms"),
        "error": error,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Run files through /classify and write a CSV")
    ap.add_argument("--files-dir", default="files")
    ap.add_argument("--out", default="eval_results.csv")
    ap.add_argument("--providers", default="custom", help="comma-separated: custom,mistral")
    ap.add_argument("--limit", type=int, default=0, help="max files (0 = all)")
    ap.add_argument("--no-vision", action="store_true")
    ap.add_argument("--no-text-llm", action="store_true")
    ap.add_argument("--no-require-agriculture", action="store_true")
    ap.add_argument("--fusion-strategy", default="adaptive")
    ap.add_argument("--vision-max-pages", type=int, default=8)
    ap.add_argument("--ocr-lang", default=None, help="override OCR languages, e.g. eng+ell")
    ap.add_argument("--only-labels", default=None, help="run only files present in this labels.json")
    ap.add_argument("--only-source", default=None, help="with --only-labels: filter by source (e.g. manual)")
    ap.add_argument("--debug", action="store_true")
    args = ap.parse_args()

    from fastapi.testclient import TestClient
    import app as appmod
    from docint.ingest.dispatcher import SUPPORTED_DOCUMENT_EXTENSIONS

    client = TestClient(appmod.app)
    user = os.getenv("DOCINT_AUTH_USERS", "").split(",")[0].strip()
    pw = os.getenv("DOCINT_AUTH_PASSWORD", "").strip()
    auth = (user, pw) if user and pw else None

    files_dir = Path(args.files_dir)
    if not files_dir.is_dir():
        print(f"ERROR: files dir not found: {files_dir}", file=sys.stderr)
        return 2
    files = sorted(
        p for p in files_dir.rglob("*")
        if p.is_file() and p.suffix.lower() in SUPPORTED_DOCUMENT_EXTENSIONS
    )
    if args.only_labels:
        import json
        lbl = json.loads(Path(args.only_labels).read_text())["labels"]
        wanted = {k for k, v in lbl.items() if not args.only_source or v.get("source") == args.only_source}
        files = [p for p in files if str(p.relative_to(files_dir)) in wanted]
        print(f"[only-labels] filtered to {len(files)} file(s)" + (f" (source={args.only_source})" if args.only_source else ""))
    if args.limit:
        files = files[: args.limit]
    providers = [p.strip() for p in args.providers.split(",") if p.strip()]
    if not files:
        print(f"No supported files found under {files_dir}", file=sys.stderr)
        return 1

    base_params = {
        "debug": str(args.debug).lower(),
        "use_vision": str(not args.no_vision).lower(),
        "use_text_llm": str(not args.no_text_llm).lower(),
        "require_agriculture": str(not args.no_require_agriculture).lower(),
        "fusion_strategy": args.fusion_strategy,
        "vision_max_pages": args.vision_max_pages,
    }
    if args.ocr_lang:
        base_params["ocr_lang"] = args.ocr_lang

    print(f"Running {len(files)} file(s) x {len(providers)} provider(s) -> {args.out}\n")
    rows = []
    for f in files:
        rel = str(f.relative_to(files_dir))
        ext = f.suffix.lower()
        mime = mimetypes.guess_type(f.name)[0] or "application/octet-stream"
        for provider in providers:
            params = {**base_params, "provider": provider}
            t0 = time.time()
            try:
                with open(f, "rb") as fh:
                    resp = client.post("/classify", params=params, files={"file": (f.name, fh, mime)}, auth=auth)
                wall = round((time.time() - t0) * 1000, 1)
                if resp.status_code == 200:
                    payload = resp.json()
                    row = _extract_row(rel, ext, provider, 200, wall, payload)
                    tag = "SKIP" if payload.get("classification_skipped") else (row["best_subcategory"] or "?")
                    print(f"  [{provider:7}] {rel[:48]:48} {wall:8.0f}ms  {row['category_used']}/{tag}")
                else:
                    detail = ""
                    try:
                        detail = resp.json().get("detail", "")
                    except Exception:
                        detail = resp.text[:120]
                    row = _extract_row(rel, ext, provider, resp.status_code, wall, None, error=str(detail))
                    print(f"  [{provider:7}] {rel[:48]:48} {wall:8.0f}ms  HTTP {resp.status_code}: {str(detail)[:50]}")
            except Exception as exc:  # noqa: BLE001 - one bad file must not abort the run
                wall = round((time.time() - t0) * 1000, 1)
                row = _extract_row(rel, ext, provider, "error", wall, None, error=f"{type(exc).__name__}: {exc}")
                print(f"  [{provider:7}] {rel[:48]:48} {wall:8.0f}ms  ERROR {type(exc).__name__}")
            rows.append(row)

    fieldnames = list(rows[0].keys())
    with open(args.out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    ok = sum(1 for r in rows if r["http_status"] == 200)
    print(f"\nDone: {ok}/{len(rows)} OK. Wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
