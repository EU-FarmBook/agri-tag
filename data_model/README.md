# data_model/

Files are organised by **lifecycle**, not by feature:

```
data_model/
├── runtime/    # loaded at request time by docint/* — must ship in the image
├── build/      # inputs + intermediates used only to (re)generate runtime/
└── docs/       # design notes / policies (not loaded, not shipped)
```

`.dockerignore` excludes `build/` and `docs/`; only `runtime/` is copied into
the container. `.gitignore` commits everything here **except** the large,
regenerable AGROVOC exports under `build/agriculture/`.

## runtime/  (loaded on every classification)

| Path | Loaded by |
|------|-----------|
| `runtime/subcategories/subcategories_v5_full_model.json` | `docint/subtypes/unified.py` (primary subtype model) |
| `runtime/subcategories/signal_specs/*_signal_spec.json` | `docint/subtypes/unified.py` (hand-maintained — no generator) |
| `runtime/agriculture/lexicon.json` | `docint/domain/agriculture.py` |
| `runtime/agriculture/bucket_centroids.{npz,meta.json}` | `docint/domain/agriculture_pipeline.py` |
| `runtime/topics/topic_signals.json` | `docint/topics/infer.py` |
| `runtime/topics/topic_centroids.{npz,meta.json}` | `docint/topics/infer.py` |

## build/  (never loaded at runtime)

| Path | Role | Build step |
|------|------|------------|
| `build/subcategories_docx/*.docx` | source documents | input to `scripts/build_subcategory_model_v5_from_docx.py` |
| `build/subcategories/mongo_export.json` | Mongo import artifact | output of the v5 build |
| `build/agriculture/lexicon_overrides.json`, `lexicon_blocklist.json` | curated inputs | input to `scripts/build_agriculture_lexicon_from_agrovoc.py` |
| `build/agriculture/agrovoc_full_export.{jsonl,checkpoint.json}` | raw AGROVOC export (git-ignored) | output of `scripts/build_agrovoc_full_export.py` |
| `build/agriculture/anchor_texts.jsonl` | centroid anchors | output of `scripts/build_agriculture_anchor_texts.py` |
| `build/topics/topics.json` | canonical 6-topic list | input to `scripts/build_topic_signals_from_agrovoc.py` |

## Regenerating runtime artifacts

```bash
# subcategories: docx -> runtime model + mongo export
python3 scripts/build_subcategory_model_v5_from_docx.py

# agriculture: agrovoc export -> lexicon -> anchor texts -> centroids
python3 scripts/build_agriculture_lexicon_from_agrovoc.py
python3 scripts/build_agriculture_anchor_texts.py
python3 scripts/compute_agriculture_bucket_centroids.py --inputs data_model/build/agriculture/anchor_texts.jsonl

# topics: agrovoc export + topic list -> signals -> centroids
python3 scripts/build_topic_signals_from_agrovoc.py
python3 scripts/compute_topic_centroids.py
```

> Note: `runtime/subcategories/signal_specs/*.json` are hand-maintained and have
> no generator script — do not delete them expecting a rebuild.
