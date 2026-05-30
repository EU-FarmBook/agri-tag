#!/usr/bin/env python3
"""
Seed a ground-truth label set for the document classification eval.

Labels come from two sources:
  - "agreement": files where BOTH providers produced the same result in the given
    eval CSV (bootstrap ground truth — if heuristics + two independent LLM stacks
    agree, it is very likely correct).
  - "manual": hand-judged calls on mismatched files (read first page vs the subtype
    definitions). These are the rows that actually differentiate the providers.

Output: data_model/eval/labels.json  (committed; used by scripts/score_eval.py)

Usage:
    python scripts/seed_eval_labels.py --eval eval_212.csv
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Hand-judged calls (file -> expected subcategory). See the eval discussion: the
# DESIRA *_fv tool factsheets are Summaries/Factsheets/Outreach; speaker decks are
# Talks; "policy analysis"/"recommendations" are Policy; etc.
MANUAL = {
    "1 PT_09-PA_EN.pdf": "Case Studies & Practice Stories",
    "20220316-DELGADO-LTVRA.pdf": "Talks, Lectures & Webinars",
    "38_ILVO_Farmcafe_fv.pdf": "Summaries, Factsheets & Outreach",
    "3_DESIRA_Dominic.pdf": "Talks, Lectures & Webinars",
    "41-50 WP4.-National-Policy-Framework-Analysis_France.pdf": "Policy & Governance Content",
    "42_UJYV_Biomass_atlas_fv.pdf": "Summaries, Factsheets & Outreach",
    "43_INRA_Treemetrics_fv.pdf": "Summaries, Factsheets & Outreach",
    "44_INRA_XAG_Drones_fv.pdf": "Summaries, Factsheets & Outreach",
    "46_ATHENA_FARM_Machine_Interoperability_fv.pdf": "Summaries, Factsheets & Outreach",
    "47_ATHENA_SQAPP_fv.pdf": "Summaries, Factsheets & Outreach",
    "48_ATHENA_WAZIUP_fv.pdf": "Summaries, Factsheets & Outreach",
    "4_HUTTON_HandsFreeHectare_fv.pdf": "Summaries, Factsheets & Outreach",
    "51_PEFC_TRACE_fv.pdf": "Summaries, Factsheets & Outreach",
    "5_Rural_EmilijaStojmenova.pdf": "Talks, Lectures & Webinars",
    "9-DESIRA_Leanne_ScottishLL.pdf": "Case Studies & Practice Stories",
    "DESIRA-_-WP4-1.pdf": "Policy & Governance Content",
    "DESIRA_Boosting-sustainable-digitalisation_webinar_highlights.pdf": "Summaries, Factsheets & Outreach",
    "DESIRA_LTVRA_Agriculture_fv.pdf": "Technical & Research Content",
    "DESIRA_LTVRA_Forestry_fv.pdf": "Technical & Research Content",
    "DESIRA_LTVRA_General_fv.pdf": "Policy & Governance Content",
    "DESIRA_RDF_Workshop2.pdf": "Project & Deliverable Reports",
    "LivingLab_UnkrautmanagementBiogemusebau_Zusammenfassung.pdf": "Project & Deliverable Reports",
    "20211207_LTVRA_RuralDigitalisationForum.pdf": "Talks, Lectures & Webinars",
}


def _pred(row):
    if not row or row.get("http_status") != "200":
        return None
    if row.get("classification_skipped") == "True":
        return "SKIP"
    return row.get("best_subcategory") or None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--eval", default="eval_212.csv", help="eval CSV to derive agreement labels from")
    ap.add_argument("--out", default=str(ROOT / "data_model" / "eval" / "labels.json"))
    args = ap.parse_args()

    rows = list(csv.DictReader(open(args.eval)))
    by = {}
    for r in rows:
        by.setdefault(r["file"], {})[r["provider"]] = r

    labels = {}
    for f, d in by.items():
        c, m = _pred(d.get("custom")), _pred(d.get("mistral"))
        if c is not None and c == m:
            labels[f] = {"expected": c, "source": "agreement"}

    # Manual judgments override / add (the differentiating rows).
    applied = 0
    for f, exp in MANUAL.items():
        if f in by:
            labels[f] = {"expected": exp, "source": "manual"}
            applied += 1

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": "doc_subcategory_labels_v1",
        "note": "agreement = both providers concurred (bootstrap); manual = hand-judged from page-1 vs subtype definitions",
        "labels": dict(sorted(labels.items())),
    }
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    n_agree = sum(1 for v in labels.values() if v["source"] == "agreement")
    n_manual = sum(1 for v in labels.values() if v["source"] == "manual")
    print(f"Wrote {len(labels)} labels -> {out}  ({n_agree} agreement, {n_manual} manual; {applied}/{len(MANUAL)} manual files matched)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
