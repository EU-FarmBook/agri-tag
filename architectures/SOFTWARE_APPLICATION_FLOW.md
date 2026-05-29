# Software Application Classification — High-Level Flow

> How a URL (or theoretically a software artefact) is classified as `Software Application`.
>
> ⚠️ **Important runtime limitation:** `Software Application` currently has **no dedicated file-upload extensions**. It is **only inferred from URL content** via `POST /classify-url`. The file-upload path (`POST /classify`) does not route any uploaded extension to `Software Application`.

---

## 1. Two Entry Points (One Active)

```
[User / Client]
       |
       +-- POST /classify (file upload)
       |       |
       |       +-- .exe, .zip, .app, .apk, etc.
       |       |       NOT SUPPORTED — returns HTTP 415
       |       |
       |       +-- .pdf, .txt, .docx, .pptx
       |       |       --> Document
       |       +-- .csv, .tsv, .xlsx, .json
       |       |       --> Dataset
       |       +-- .jpg, .png
       |       |       --> Image
       |       +-- .mp3, .wav, .m4a
       |       |       --> Audio
       |       +-- .mp4, .avi, .mov, etc.
       |               --> Video
       |
       +-- POST /classify-url (public URL)
               |
               +-- http://example.com/farm-tool
               |       --> Software Application (if text matches)
               +-- https://github.com/.../my-farm-app
                       --> Software Application (if text matches)
```

### Why file upload doesn't work for software

```
[Category Router (infer.py)]
       |
       |  infer_file_category(asset, mime_type)
       |
       |  Supported MIME families:
       |    application/pdf, text/*, word/powerpoint  --> Document
       |    text/csv, text/tab-separated-values,
       |    application/json, spreadsheet MIME        --> Dataset
       |    image/*                                    --> Image
       |    audio/*                                    --> Audio
       |    video/*                                    --> Video
       |
       |  Fallback by extension:
       |    pdf, txt, docx, pptx                      --> Document
       |    csv, tsv, json                            --> Dataset
       |    xlsx (with tabular heuristics)            --> Dataset
       |    jpeg, jpg, png                            --> Image
       |    mp3, wav, m4a                             --> Audio
       |    mp4, avi, mov, ...                        --> Video
       |
       |  There is NO branch for:
       |    .exe, .zip, .tar.gz, .app, .apk,
       |    .deb, .rpm, .dmg, .msi, etc.
       |
       v
[Result]
       Any unsupported extension --> HTTP 415 Unsupported Media Type
```

---

## 2. URL Classification Flow (Active Path)

```
[User / Client]
       |
       |  POST /classify-url
       |  {"url": "https://example.com/farm-management-tool"}
       v
[FastAPI Endpoint]
       |
       v
[Optional Agri Gate]
       |  Scan URL before extraction
       +-- Blocked? --> [HTTP 403]
       +-- Allowed? --> [Continue]
       v
[URL Deny-List Check]
       |  Blocks dangerous direct-download targets
       v
[PageSense Extraction]
       |  Fetches raw text from public URL
       |  Cached by URL (TTL = 48 hours)
       v
[Extracted Text]
       |
       v
[Category Inference (infer_url_category)]
       |
       |  Step 1: Check URL suffix
       |  -----------------------------------------
       |  .pdf, .doc, .docx, .ppt, .pptx, .txt  --> Document
       |  .csv, .tsv, .xlsx, .xls, .json        --> Dataset
       |  -----------------------------------------
       |
       |  Step 2: Text-based heuristic inference
       |  -----------------------------------------
       |  Count "dataset" terms in URL+text:
       |    dataset, data catalogue, schema, csv,
       |    download data, observations, variables,
       |    records, tabular, ...
       |
       |  Count "software" terms in URL+text:
       |    software, tool, platform, application,
       |    app, repository, github, gitlab,
       |    dashboard, api, plugin, install, ...
       |
       |  If dataset_hits >= 2 AND dataset_hits >= software_hits
       |       --> Dataset
       |
       |  If software_hits >= 2 AND software_hits > dataset_hits
       |       --> Software Application
       |
       |  Otherwise --> Document (fallback)
       |  -----------------------------------------
       v
```

---

## 3. Agriculture Relevance Gate

```
[Extracted URL Text]
       |
       v
[Agriculture Relevance Pipeline]
       |
       |  Same 3-stage pipeline as all other categories:
       |    Stage 1: Multilingual lexicon match
       |    Stage 2: Embedding model (optional)
       |    Stage 3: Text LLM fallback (optional)
       |
       v
[AgricultureDecision]
       |
       +-- require_agriculture=true AND non-agriculture?
       |       +-- YES --> [RETURN EARLY]
       |       |           skip_reason = "Non-agriculture content"
       |       |
       |       +-- NO  --> [Continue]
       |
       v
[KO-Eligibility Gate]
       |  (URL path only)
       |  Heuristics + optional LLM fallback
       |  Catches: job vacancies, calls for applications,
       |           event announcements, procurement notices
       |
       +-- Ineligible? --> [RETURN EARLY]
       |                     skip_reason = "KO ineligible"
       |
       +-- Eligible? --> [Continue to subtype scoring]
       v
```

---

## 4. Software Subtype Scoring

```
[URL Text + Extracted Content]
       |
       v
[Software Subtype Scorer]
       |
       |  Software uses the UNIFIED subcategory system
       |  (not a separate modality-specific scorer like datasets)
       |
       |  The 8 v4 software types map to ONE unified category:
       |  "Software Tools & Applications" (Unified #24)
       |
       |  But the scorer still evaluates all 24 unified
       |  subcategories and picks the best match.
       |
       |  Heuristic signals for software:
       |  ---------------------------------
       |  Domain terms in text:
       |    software, tool, platform, application,
       |    dashboard, api, github, repository,
       |    farm management, mapping, gis,
       |    simulation, automation, training, ...
       |
       |  Structure signals:
       |    feature lists, screenshots, install instructions,
       |    download links, version numbers, changelog,
       |    system requirements, pricing tables
       |
       v
[24 Unified Subcategory Scores]
       |
       |  Software-related unified categories that may score highly:
       |    - Software Tools & Applications (primary)
       |    - Tool, Machinery & Software Walkthroughs
       |    - Maps & Geospatial Content (for GIS tools)
       |    - Simulations, Forecasts & Model Visualisations
       |    - Monitoring, Operations & Sensor Records
       |    - How-To Guides (for training apps)
       |
       v
```

### The 8 v4 Software Types (source taxonomy)

| # | Type | Definition | Key Feature |
|---|------|-----------|-------------|
| 1 | **Farm Management System (FMIS)** | Complete platform for farm operations, planning, records | `workflow_role_and_scope` + integration across modules |
| 2 | **Monitoring & Recording Tools** | Track, log, and review data over time | `temporal_recording_orientation` |
| 3 | **Field Data Collection Apps** | Capture data directly in the field | `field_capture_and_observation_structure` |
| 4 | **Mapping & GIS Tools** | Maps, spatial data, geolocation analysis | `spatial_interaction_and_georeferenced_analysis` |
| 5 | **Data Analysis & Dashboard Tools** | Process and visualise data for insights | `analysis_visualisation_and_insight_generation` |
| 6 | **Simulation & Forecasting Tools** | Predict or simulate scenarios | `model_prediction_and_scenario_logic` |
| 7 | **Automation & Control Systems** | Automate actions or control devices | `automation_control_and_triggering` |
| 8 | **Training & Learning Applications** | Interactive learning and skill development | `learning_mechanics_and_training_design` |

### Unified mapping (v5)

All 8 software types map **strongly** to:

```
[Unified #24] Software Tools & Applications
  User-facing label: "Use tools"
  Definition: Interactive software systems, applications, dashboards,
              control systems, or digital tools that perform workflows
              or support decisions.
```

Secondary mappings:
- FMIS + Monitoring + Automation → `Monitoring, Operations & Sensor Records` (partial)
- GIS Tools → `Maps & Geospatial Content` (strong for the tool type)
- Simulation → `Simulations, Forecasts & Model Visualisations` (strong)
- Training apps → `How-To Guides` (weak/partial)
- Data Analysis → `Charts & Data Visualisations` (partial)

---

## 5. Language Detection & LLM Augmentation

```
[URL Text]
       |
       v
[Language Detection]
       |
       +-- Non-English & high confidence?
       |       +-- YES --> [Text LLM becomes PRIMARY]
       |       |           Heuristics demoted
       |
       +-- English or low confidence?
       |       +-- NO  --> [Heuristics remain primary]
       |
       v
[Text LLM (optional)]
       |
       |  Triggered if:
       |    - use_text_llm=true
       |    - is_agriculture=true
       |    - LLM backend configured
       |    - OR non_english_llm_primary=true
       |
       |  Special handling for software:
       |    - Calls llm_classify_software_subcategories_text()
       |    - Prompt includes all 24 unified subcategories
       |    - Asks for matched signals, conflicting signals,
       |      closest alternative
       |
       |  Returns:
       |    - Normalized probabilities across 24 unified subtypes
       |    - Matched / conflicting signal lists
       |
       v
```

---

## 6. Fusion

```
[Heuristic Scores (24 unified subcategories)]
       |
       +---------------------+
                             |
[Text LLM Scores (24 unified subcategories)]
       |
       v
[Intelligent Fusion]
       |
       |  Strategy: weighted / adaptive / agreement / cascade
       |
       |  Special note for software:
       |    - heuristics_alpha = 0.34 (text >= 500 chars)
       |    - heuristics_alpha = 0.26 (text < 500 chars)
       |    - OR heuristics_alpha = 0.38 (text >= 1200 chars)
       |    - OR heuristics_alpha = 0.28 (text < 1200 chars)
       |
       |  This means the Text LLM has MORE weight than
       |  heuristics for software classification.
       |
       v
[FusionResult]
       |  fused_best_match
       |  fused_ranking
       |  source_weights
       |  agreement_score
       |  fusion_rationale
       v
```

---

## 7. Response Assembly

```
[FusionResult + All Metadata]
       |
       v
[ClassificationResponse]
       |
       |  best_match           --> Top unified subtype
       |                         (most often "Software Tools & Applications")
       |  all_candidates       --> Ranked list of all 24 unified subtypes
       |  category_used        --> "Software Application"
       |  category_inference   --> "Software Application"
       |  agriculture_relevance --> Lexicon hits + stage results
       |  classification_skipped --> false (unless gated)
       |  processing_info       --> {
       |                              source_mode: "url",
       |                              stage_timings_ms: {...},
       |                              language_detection: {...},
       |                              routing: {
       |                                software_mode: true,
       |                                text_llm: {requested, used, reason},
       |                                vision_llm: {
       |                                  requested: true/false,
       |                                  used: false,
       |                                  reasons: ["software_vision_not_yet_enabled"]
       |                                }
       |                              }
       |                           }
       |  feature_details       --> Per-subtype evidence
       |  rationale             --> Why this subtype won
       |  contrastive_rationale --> Why it beat runner-up
       |  fusion                --> Weights, agreement, rationale
       |
       v
[HTTP 200 JSON Response]
       |
       v
[User / Client]
```

---

## Complete End-to-End Flow (URL Path Only)

```
[USER]
   |
   | POST /classify-url
   | {"url": "https://example.com/farm-app"}
   v
[FastAPI]
   |
   +-- Optional Agri Gate (URL scan)
   +-- URL Deny-List check
   +-- PageSense extraction (cached)
   v
[Extracted Text]
   |
   v
[Category Inference]
   |  URL suffix check:
   |    .pdf/.doc/.txt  --> Document
   |    .csv/.xlsx      --> Dataset
   |    (no suffix match) --> Text heuristics
   |
   |  Text heuristics:
   |    software terms > dataset terms?
   |        YES --> "Software Application"
   |        NO  --> "Dataset" or "Document"
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
[KO-Eligibility Gate]
   |  (URL only)
   +-- Ineligible? --> [RETURN EARLY]
   +-- Eligible? --> [Continue]
   v
[Software Subtype Scorer]
   |  Evaluates 24 unified subcategories
   |  Software types map to:
   |    "Software Tools & Applications" (primary)
   |    + secondary unified categories
   v
[Language Detection]
   |  Non-English? --> Text LLM primary
   v
[Text LLM (optional)]
   |  llm_classify_software_subcategories_text()
   |  Returns 24-way probabilities
   |
   |  NOTE: Vision LLM is EXPLICITLY DISABLED
   |  reason: "software_vision_not_yet_enabled"
   v
[Fusion]
   |  Merges heuristic + text LLM scores
   |  Software gets lower heuristic alpha
   |  (LLM weighted more heavily)
   v
[Response Shaper]
   |  best_match, all_candidates, evidence,
   |  rationale, contrastive_rationale,
   |  processing_info.software_mode = true
   v
[JSON HTTP 200]
   |
   v
[USER]
```

---

## Key Differences: Software vs. Dataset / Document

| Aspect | Dataset (file upload) | Software Application (URL only) |
|--------|----------------------|--------------------------------|
| **Entry point** | `POST /classify` | `POST /classify-url` |
| **Supported inputs** | `.csv`, `.tsv`, `.xlsx`, `.json` | Public `http`/`https` URLs only |
| **File upload?** | ✅ Yes | ❌ No |
| **Ingestion** | Tabular flattening (rows/columns) | PageSense raw text extraction |
| **Category routing** | MIME / extension based | URL suffix + text heuristics |
| **Subtype count** | 8 dataset-specific subtypes | 24 unified subcategories (software maps to 1 primary) |
| **Scorer type** | Dedicated `dataset_scorer.py` | Unified subcategory heuristic scorer |
| **Vision LLM** | Not used for datasets | Explicitly disabled (`software_vision_not_yet_enabled`) |
| **Text LLM weight** | Balanced with heuristics | LLM weighted MORE heavily (alpha 0.62-0.74) |
| **KO-eligibility gate** | ❌ Not applied to file uploads | ✅ Applied to URL path |

---

## Why File Upload for Software Is Not Implemented

```
[Current SUPPORTED_DOCUMENT_EXTENSIONS]
  .pdf, .txt, .docx, .pptx        --> Document
  .csv, .tsv, .xlsx, .json        --> Dataset
  .jpg, .jpeg, .png               --> Image
  .mp3, .wav, .m4a                --> Audio
  .mp4, .avi, .mov, ...           --> Video

[Missing]
  .exe, .zip, .tar.gz, .app, .apk,
  .deb, .rpm, .dmg, .msi, .jar,
  .py, .js, .sh, .yml, .toml, ...
```

Software applications are typically:
- Distributed as compressed archives (`.zip`, `.tar.gz`)
- Platform-specific installers (`.exe`, `.dmg`, `.deb`, `.apk`)
- Source code repositories (not single-file uploads)
- Web-based tools (accessible via URL, not file)

Therefore, the current architecture assumes software is discovered and classified via **URL/metadata** rather than direct file upload.

---

*Generated from code analysis on 2026-05-04.*
