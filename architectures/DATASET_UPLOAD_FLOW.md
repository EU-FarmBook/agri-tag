# Dataset Upload — High-Level Flow

> How a `.csv`, `.tsv`, `.xlsx`, or `.json` file travels from the user to a classified `Dataset` response.

---

## 1. Upload Request

```
[User / Client]
       |
       |  POST /classify
       |  Content-Type: multipart/form-data
       |  file=dataset.csv
       v
[FastAPI Endpoint]
       |
       |  1. Read Content-Length header
       |  2. Check against MAX_REQUEST_BODY_MB
       v
[Size & Type Gate]
       |
       +-- Too large? ----> [HTTP 413 Payload Too Large]
       |
       +-- Unknown extension? -> [HTTP 415 Unsupported Media Type]
       |
       +-- OK? ----------> [Continue]
```

---

## 2. Security & Auth Layer

```
[Request]
       |
       v
[Basic Auth Middleware]
       |
       +-- use_agri_gate=true? ---> [Agri Gate Scan]
       |                             (file uploaded to agrigate API)
       |                                     |
       |                                     +-- Blocked? ---> [HTTP 403]
       |                                     |
       |                                     +-- Allowed? ---> [Continue]
       |
       +-- use_agri_gate=false? --> [Skip]
       |
       v
[Auth Check]
       |
       +-- Missing/Invalid credentials? ---> [HTTP 401 Unauthorized]
       |
       +-- Valid? -------------------------> [Continue]
       |
       v
[Save to Temporary Disk]
```

---

## 3. Ingestion & Normalisation

```
[Temp File on Disk]
       |
       |  Ingestion Dispatcher reads file extension
       v
+-------------------------------------------+
|  Extension Router                         |
|  .csv  --> ingest_delimited_file(delimiter=",")
|  .tsv  --> ingest_delimited_file(delimiter="\t")
|  .xlsx --> ingest_xlsx()
|  .json --> ingest_json()
+-------------------------------------------+
       |
       |  Each ingestor returns:
|  - Extracted text (flattened rows/columns)
|  - Column headers as strings
|  - Preview row count
|  - MIME type
|  - asset_type (csv / tsv / xlsx / json)
       v
[IngestedAsset]
       |
       |  text = "Columns: col1 | col2 | col3\nRow 1: ...\nRow 2: ..."
       |  lines = [header_line, row1_line, row2_line, ...]
       |  meta = {preview_rows, column_count, ...}
       v
```

### What each ingestor does

| File type | What gets extracted |
|-----------|---------------------|
| `.csv` / `.tsv` | Header row + first N preview rows (bounded by `TABULAR_MAX_ROWS=100`, `TABULAR_PREVIEW_ROWS=30`) |
| `.xlsx` | All sheets (up to `XLSX_MAX_SHEETS=10`), first 25 rows per sheet, column names inferred from first row |
| `.json` | Parsed JSON array or object; flattened into tabular records (up to `JSON_MAX_RECORDS=100`, `JSON_PREVIEW_RECORDS=30`) |

---

## 4. Category Routing — "Why is this a Dataset?"

```
[IngestedAsset]
       |
       v
[Category Inference (infer_file_category)]
       |
       |  Step 1: Check MIME type
       |  -----------------------------------------
       |  text/csv                 --> Dataset
       |  text/tab-separated-values --> Dataset
       |  application/json         --> Dataset
       |  application/vnd.openxmlformats-officedocument.spreadsheetml.sheet
       |                           --> Dataset
       |  -----------------------------------------
       |
       |  Step 2: Fallback to extension (if MIME missing)
       |  -----------------------------------------
       |  asset_type in {csv, tsv, json} --> Dataset
       |  asset_type == xlsx --> Check heuristics:
       |      sheet_count > 1 OR preview_rows >= 6 OR max_columns >= 4
       |          --> Dataset
       |      otherwise --> Document (lightweight spreadsheet)
       |  -----------------------------------------
       |
       v
[CategoryInferenceResult]
       |
       |  category = "Dataset"
       |  confidence = 0.96 - 0.98
       |  rationale = "File MIME ... is routed as Dataset"
       v
```

### Key routing rules for datasets

```
MIME-based (primary):
  text/csv                                          -> Dataset
  text/tab-separated-values                         -> Dataset
  application/json                                  -> Dataset
  application/vnd.openxmlformats-officedocument.spreadsheetml.sheet -> Dataset

Extension-based (fallback):
  .csv / .tsv / .json                               -> Dataset
  .xlsx (with tabular heuristics)                   -> Dataset
  .xlsx (lightweight, few rows/cols)                -> Document
```

---

## 5. Agriculture Relevance Gate

```
[IngestedAsset text]
       |
       v
[Agriculture Relevance Pipeline]
       |
       |  Stage 1: Lexicon Match
       |  ---------------------------------
       |  Scan text against agriculture_lexicon.json
       |  (AGROVOC-style multilingual terms)
       |  Hit? --> Score = high
       |  Miss or ambiguous? --> Stage 2
       |
       |  Stage 2: Embedding Model (optional)
       |  ---------------------------------
       |  If AGRI_ENABLE_EMBEDDING=true
       |  Compute embedding vs bucket centroids
       |  (intfloat/multilingual-e5-small on CPU)
       |  Confident? --> Finalize score
       |  Still ambiguous? --> Stage 3
       |
       |  Stage 3: Text LLM Fallback (optional)
       |  ---------------------------------
       |  If AGRI_ENABLE_LLM_FALLBACK=true
       |  Send text snippet to text LLM (Qwen-style)
       |  Ask: "Is this agriculture-related?"
       |  ---------------------------------
       |
       v
[AgricultureDecision]
       |
       |  is_agriculture = true / false
       |  matched_concepts = ["crop", "fertiliser", ...]
       |  stage_results = {lexicon, embedding, llm}
       |
       +-- require_agriculture=true AND is_agriculture=false?
       |       |
       |       +-- YES --> [RETURN EARLY]
       |       |           classification_skipped = true
       |       |           skip_reason = "Non-agriculture content"
       |       |
       |       +-- NO  --> [Continue to subtype scoring]
       |
       v
```

---

## 6. Dataset Subtype Scoring

```
[Flattened dataset text + column headers]
       |
       v
[Dataset Subtype Scorer (dataset_scorer.py)]
       |
       |  For each of the 8 dataset subtypes:
       |      1. Count domain-term hits in full text
       |      2. Count schema-marker hits in column names
       |      3. Count file-extension markers
       |
       |  Subtypes scored:
       |  ---------------------------------
       |  1. Geospatial Data
       |     Signals: lat, lon, geometry, coordinate, spatial, epsg
       |
       |  2. Video Data
       |     Signals: video, clip, frame, duration, fps, .mp4, .avi
       |
       |  3. Audio Data
       |     Signals: audio, speaker, transcript, duration, .mp3, .wav
       |
       |  4. Image Data
       |     Signals: image, img, filename, bbox, mask, .jpg, .png
       |
       |  5. Text Data
       |     Signals: text, content, document, sentence, paragraph, abstract
       |
       |  6. Graph/Network Data
       |     Signals: source, target, node, edge, from, to, weight
       |
       |  7. Agricultural Production Data
       |     Signals: crop, yield, farm, field, fertilizer, harvest, livestock
       |
       |  8. Environmental & Temporal Data
       |     Signals: date, time, timestamp, temperature, rainfall, humidity, weather
       |  ---------------------------------
       |
       v
[8 SubcategoryScore objects]
       |
       |  Each contains:
       |    - confidence (0.0 - 1.0)
       |    - evidence_score
       |    - features_found: ["domain_terms", "schema_markers", ...]
       |    - feature_details: matched terms + excerpts
       |    - rationale: human-readable explanation
       v
```

---

## 7. Language Detection & LLM Augmentation

```
[IngestedAsset text]
       |
       v
[Language Detection]
       |
       |  Detects: English vs non-English (Greek, etc.)
       |  Confidence threshold: 0.75
       |
       +-- Non-English & confident? ---> [Text LLM becomes PRIMARY]
       |                                   (heuristics demoted)
       |
       +-- English or low confidence? -> [Heuristics remain primary]
       |
       v
[Text LLM (optional)]
       |
       |  Triggered if:
       |    - use_text_llm=true
       |    - is_agriculture=true
       |    - LLM backend configured
       |    - OR non-english_llm_primary=true
       |
       |  Prompt includes:
       |    - Dataset taxonomy (8 subtypes)
       |    - Positive/negative signals for each
       |    - Close competitors
       |
       |  Returns:
       |    - Normalized probabilities across 8 subtypes
       |    - Matched signals + conflicting signals
       |    - Closest alternative subtype
       |
       v
```

---

## 8. Fusion

```
[Heuristic Scores] --------+
                            |
[Text LLM Scores] ----------+---> [Intelligent Fusion]
                            |         (weighted / adaptive /
                            |          agreement / cascade)
                            |
       +--------------------+
       |
       v
[FusionResult]
       |
       |  fused_best_match
       |  fused_ranking (all 8 subtypes sorted)
       |  source_weights
       |  agreement_score
       |  fusion_rationale
       v
```

---

## 9. Response Assembly

```
[FusionResult + All Metadata]
       |
       v
[ClassificationResponse]
       |
       |  best_match           --> Top fused subtype
       |  all_candidates       --> Ranked list of all 8
       |  category_used        --> "Dataset"
       |  agriculture_relevance --> Lexicon hits + stage results
       |  classification_skipped --> false (unless agri-gated)
       |  processing_info       --> {
       |                              source_mode: "file",
       |                              stage_timings_ms: {...},
       |                              language_detection: {...},
       |                              routing: {...}
       |                           }
       |  feature_details       --> Per-subtype evidence
       |  rationale             --> Why this subtype won
       |  contrastive_rationale --> Why it beat the runner-up
       |  fusion                --> Weights, agreement, rationale
       |
       v
[HTTP 200 JSON Response]
       |
       v
[User / Client]
```

---

## Complete End-to-End Flow

```
[USER]
   |
   | POST /classify (dataset.csv)
   v
[FastAPI]
   |
   +-- Size check (MAX_OTHER_UPLOAD_SIZE_MB=50)
   +-- Extension check (.csv / .tsv / .xlsx / .json)
   +-- Optional Agri Gate
   +-- Basic Auth
   v
[Save to disk]
   |
   v
[Ingestion Dispatcher]
   |
   +-- .csv  --> ingest_delimited_file(",")
   +-- .tsv  --> ingest_delimited_file("\t")
   +-- .xlsx --> ingest_xlsx()
   +-- .json --> ingest_json()
   |
   v
[IngestedAsset]
   |  text = flattened rows + columns
   |  asset_type = csv / tsv / xlsx / json
   v
[Category Router]
   |  MIME or extension -> "Dataset"
   v
[Agriculture Relevance]
   |  Stage 1: Lexicon
   |  Stage 2: Embedding (optional)
   |  Stage 3: LLM fallback (optional)
   |
   +-- Non-agriculture + require_agriculture=true?
   |       +-- YES --> [RETURN EARLY]
   |       +-- NO  --> [Continue]
   v
[Dataset Subtype Scorer]
   |  8 subtypes scored via:
   |    - domain terms in text
   |    - schema markers in columns
   |    - file extension markers
   v
[Language Detection]
   |  Non-English? -> Text LLM primary
   v
[Text LLM (optional)]
   |  Dataset-specific prompt
   |  Returns 8-way probabilities
   v
[Fusion]
   |  Merges heuristic + LLM scores
   |  Strategy: weighted / adaptive / agreement / cascade
   v
[Response Shaper]
   |  best_match, all_candidates, evidence,
   |  rationale, contrastive_rationale, fusion info
   v
[JSON HTTP 200]
   |
   v
[USER]
```

---

## Key Configuration Variables

```
# Upload limits
MAX_OTHER_UPLOAD_SIZE_MB=50
MAX_REQUEST_BODY_MB=1024

# Tabular ingestion bounds
TABULAR_MAX_ROWS=100
TABULAR_PREVIEW_ROWS=30
XLSX_MAX_SHEETS=10
XLSX_MAX_ROWS_PER_SHEET=25
JSON_MAX_RECORDS=100
JSON_PREVIEW_RECORDS=30

# Agriculture pipeline
AGRI_ENABLE_EMBEDDING=true
AGRI_EMBEDDING_MODEL=intfloat/multilingual-e5-small
AGRI_ENABLE_LLM_FALLBACK=true

# LLM routing
use_text_llm=true
fusion_strategy=adaptive
```

---

*Generated from code analysis on 2026-05-04.*
