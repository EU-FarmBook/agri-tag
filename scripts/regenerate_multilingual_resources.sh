#!/usr/bin/env bash
#
# Regenerate the agriculture lexicon, topic signals, and their embedding centroids
# from AGROVOC in ALL 24 EU official languages.
#
# This is the *real* fix for the lexical multilingual gap: the runtime lexicon and
# topic signals ship English-biased, so non-English content currently leans on the
# (slower) embedding + LLM path. After this runs, the cheap lexical fast-path works
# in every EU language too.
#
# The language set lives in the build scripts' DEFAULT_LANGS (already set to the full
# EU set). Step 1 (AGROVOC SPARQL export) is the slow one — it hits a remote endpoint,
# can take a long time for 24 languages, and is resumable: re-run step 1 with
# `--resume` if it is interrupted (a checkpoint is written under data_model/build).
#
# Usage:
#   bash scripts/regenerate_multilingual_resources.sh
#   PYTHON=/path/to/python bash scripts/regenerate_multilingual_resources.sh
#
# After it finishes, restart the service so the new resources are loaded.

set -euo pipefail

PY="${PYTHON:-.venv/bin/python}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

EXPORT="data_model/build/agriculture/agrovoc_full_export.jsonl"

echo "==> 1/6  AGROVOC full export (multilingual; slow, network). Resume with: \\"
echo "         $PY scripts/build_agrovoc_full_export.py --page-size 100 --resume"
$PY scripts/build_agrovoc_full_export.py

echo "==> 2/6  Agriculture lexicon (multilingual triggers)"
$PY scripts/build_agriculture_lexicon_from_agrovoc.py --input "$EXPORT"

echo "==> 3/6  Agriculture anchor texts (from the runtime lexicon)"
$PY scripts/build_agriculture_anchor_texts.py

echo "==> 4/6  Agriculture bucket centroids (embedding stage 2)"
$PY scripts/compute_agriculture_bucket_centroids.py \
  --inputs data_model/build/agriculture/anchor_texts.jsonl

echo "==> 5/6  Topic signals (multilingual, from the same export)"
$PY scripts/build_topic_signals_from_agrovoc.py

echo "==> 6/6  Topic centroids"
$PY scripts/compute_topic_centroids.py

echo ""
echo "==> Done. Multilingual agriculture + topic resources regenerated."
echo "    Restart the service to load them (the lexicon/signals are read at startup)."
