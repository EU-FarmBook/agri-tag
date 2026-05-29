# KO Classifier API

FastAPI service for explainable category and subcategory classification. The current runtime scope covers document-family, tabular, image, audio, and video uploads in `.pdf`, `.txt`, `.docx`, `.pptx`, `.csv`, `.tsv`, `.xlsx`, `.jpg`, `.jpeg`, `.png`, `.mp3`, `.wav`, `.m4a`, `.mp4`, `.avi`, `.mov`, `.wmv`, `.mpeg`, `.mpg`, `.mkv`, `.flv`, `.webm`, `.3gp`, `.mts`, `.m2ts`, `.vob`, and `.rmvb`, plus public `http`/`https` URLs through a PageSense-backed text extraction path. Deterministic heuristics are always available, with optional text and vision LLM augmentation where the runtime path supports them. Agri Gate can be enabled per request for both files and URLs.

## Dependency Sync

To ensure the local virtualenv contains only the packages implied by [requirements.txt](requirements.txt), use:

```bash
bash scripts/sync_env.sh recreate
```

That removes `.venv`, creates a fresh one, and installs from `requirements.txt`.

If you want to keep the existing `.venv` but uninstall packages that are no longer required:

```bash
bash scripts/sync_env.sh sync
```

That uses `pip-tools` and `pip-sync` so only the packages required by `requirements.txt` remain installed.

The broader category and KO-ingestion policy work is documented under [category_auto_selection_policy.md](data_model/docs/category_auto_selection_policy.md). That policy covers `Document`, `Video`, `Audio`, `Image`, `Dataset`, and `Software Application`. The current `/classify` endpoint now uses deterministic MIME/file-type routing for `Document`, `Dataset`, `Image`, `Audio`, and `Video`, and routes each branch to its current subtype logic.

## What The API Does

- Extracts text from PDFs, TXT files, DOCX files, PPTX files, CSV/TSV files, and XLSX files through a normalized ingestion layer.
- Falls back to OCR for PDFs when extracted text quality is poor.
- Uses image OCR and a vision-first image classifier for `.jpg`, `.jpeg`, and `.png` uploads.
- Uses optional audio transcription for `.mp3`, `.wav`, and `.m4a` uploads before agriculture and subtype classification.
- Uses optional FFmpeg-based frame sampling and audio extraction for video uploads before agriculture and subtype classification.
- Can screen incoming files and submitted URLs with Agri Gate before downstream extraction or classification when `use_agri_gate=true`.
- Uses PageSense to turn a public URL into raw readable text for the URL classification path.
- Uses deterministic MIME/file-type routing for uploaded files and text-based category inference for URLs.
- Scores `Document` uploads against 11 consolidated document subcategories using measurable heuristic signals.
- Scores `Dataset` uploads against 8 consolidated dataset subcategories using heuristic schema/content signals and an optional dataset-specific text LLM path.
- Scores `Image` uploads against 3 consolidated image subcategories using a vision-first classifier with OCR-backed fallback heuristics.
- Scores `Audio` uploads against 6 consolidated audio subcategories using transcript-first heuristics and an optional audio-specific text LLM path.
- Scores `Video` uploads against 6 consolidated video subcategories using sampled frames, optional transcription, and category-specific fusion.
- Optionally asks a text LLM and/or a vision LLM to classify the same document.
- Fuses heuristic and LLM probabilities with configurable strategies.
- Returns feature-level evidence, rationale text, and contrastive explanations for top candidates.

## Current Document Subcategories

- `Journal article`
- `Article in conference proceedings`
- `Chapter in edited volume`
- `Thesis`
- `Book`
- `Technical Report`
- `Tutorial`
- `Guide/Manual`
- `Presentation`
- `News & Communication`
- `Informational Booklet`

The consolidation rationale is documented in:

- [subcategories_consolidation_analysis.md](data_model/docs/subcategories_consolidation_analysis.md)

## Current Dataset Subcategories

- `Geospatial Data`
- `Video Data`
- `Audio Data`
- `Image Data`
- `Text Data`
- `Graph/Network Data`
- `Agricultural Production Data`
- `Environmental & Temporal Data`

## Current Image Subcategories

- `Data Visualization`
- `Figure/Image`
- `Map`

## Current Audio Subcategories

- `Tutorial`
- `Educational/Training Media`
- `Recorded Session`
- `Interview`
- `Q&A Session`
- `Audio Program`

## Current Video Subcategories

- `Tutorial`
- `Educational/Training Media`
- `Recorded Session`
- `Interview`
- `Q&A Session`
- `Demonstration/Field Recording`

## Explainability Model

The heuristic layer uses 27 measurable signals, including:

- academic structure signals such as `imrad_structure`, `citation_density`, `abstract_quality`, `peer_review_markers`
- technical and deliverable signals such as `deliverable_markers`, `version_control`, `technical_specs`
- instructional signals such as `tutorial_structure`, `learning_objectives`, `procedure_steps`, `checklists`
- policy and communication signals such as `news_timeliness`, `press_release_format`, `regulatory_update_markers`, `compliance_language`, `governance_references`
- layout signals such as `slide_indicators`, `visual_heavy`, `short_form`

The source of truth for subcategory criteria is [subcategories.py](docint/rubrics/subcategories.py). Each subcategory definition carries:

- detectable features
- positive signal hints
- negative signal hints
- close competitors
- minimum features required

Those same criteria are now used in three places:

- heuristic scoring
- contrastive API explanations
- LLM prompting guidance

## Agriculture Relevance

The API now also returns an `agriculture_relevance` block for each classified asset.

The current design is staged:

- Stage 1: AGROVOC-style multilingual lexicon matcher backed by [agriculture_lexicon.json](data_model/runtime/agriculture/lexicon.json)
- Stage 2: small local multilingual embedding model for ambiguous cases, preferably driven by generated agriculture bucket centroids under [data_model/runtime](data_model/runtime)
- Stage 3: optional text LLM fallback only when the earlier stages remain uncertain

Eligibility note:

- after agriculture relevance, the runtime now applies a KO-eligibility gate
- this catches agriculture-related but non-eligible content such as:
  - job vacancies / PhD positions
  - call-for-applications style notices
  - event announcements
  - tender / procurement notices
- the gate uses high-precision heuristics first and can fall back to the text LLM for ambiguous cases

Default behavior:

- Stage 1 is always active
- Stage 2 is enabled by default and uses `intfloat/multilingual-e5-small` on CPU once `sentence-transformers` is installed
- Stage 3 is only active for ambiguous cases and only when text LLM use is enabled

Relevant settings:

- `AGRI_ENABLE_EMBEDDING=true`
- `AGRI_EMBEDDING_MODEL=intfloat/multilingual-e5-small`
- `AGRI_EMBEDDING_TEXT_LIMIT=3500`
- `AGRI_EMBEDDING_OVERRIDE_THRESHOLD=0.74`
- `AGRI_EMBEDDING_BLEND_WEIGHT=0.45`
- `AGRI_ENABLE_LLM_FALLBACK=true`
- `MEDIA_TRANSCRIBER_ENABLED=true`
- `MEDIA_TRANSCRIBER_BASE_URL=...`
- `MEDIA_TRANSCRIBER_WHISPER_MODEL=medium`
- `MEDIA_TRANSCRIBER_MODE=auto`
- FFmpeg available locally for video frame sampling and audio extraction

Operational note:

- Stage 2 stays fail-safe. If the embedding dependency or local model is unavailable, the API falls back to the Stage 1 lexicon result and records that in `agriculture_relevance.stage_results`.

Resource-generation note:

- The repo now includes a reproducible agriculture-anchor pipeline:
  - [scripts/build_agriculture_anchor_texts.py](scripts/build_agriculture_anchor_texts.py) builds bootstrap anchor texts from the runtime lexicon
  - [scripts/build_agrovoc_anchor_texts.py](scripts/build_agrovoc_anchor_texts.py) can fetch richer multilingual anchor texts from AGROVOC via SPARQL
  - [scripts/build_agrovoc_full_export.py](scripts/build_agrovoc_full_export.py) exports the broad AGROVOC concept store
  - [scripts/build_agriculture_lexicon_from_agrovoc.py](scripts/build_agriculture_lexicon_from_agrovoc.py) converts that full export into the conservative runtime lexical trigger set using [agriculture_lexicon_overrides.json](data_model/build/agriculture/lexicon_overrides.json) and [agriculture_lexicon_blocklist.json](data_model/build/agriculture/lexicon_blocklist.json)
  - [scripts/compute_agriculture_bucket_centroids.py](scripts/compute_agriculture_bucket_centroids.py) turns anchor JSONL files into per-bucket centroid resources for Stage 2
- Local bootstrap commands:

```bash
.venv/bin/python scripts/build_agriculture_anchor_texts.py
.venv/bin/python scripts/compute_agriculture_bucket_centroids.py \
  --inputs data_model/build/agriculture/anchor_texts.jsonl
```

- Full AGROVOC regeneration workflow:

```bash
.venv/bin/python scripts/build_agrovoc_full_export.py
.venv/bin/python scripts/build_agriculture_lexicon_from_agrovoc.py \
  --input data_model/build/agriculture/agrovoc_full_export.jsonl
.venv/bin/python scripts/build_agriculture_anchor_texts.py
.venv/bin/python scripts/compute_agriculture_bucket_centroids.py \
  --inputs data_model/build/agriculture/anchor_texts.jsonl
```

- The AGROVOC full-export script now supports retries and checkpointed resume:

```bash
.venv/bin/python scripts/build_agrovoc_full_export.py --page-size 100
.venv/bin/python scripts/build_agrovoc_full_export.py --page-size 100 --resume
```

- Checkpoint file:
  - `data_model/build/agriculture/agrovoc_full_export.checkpoint.json`

- Design principle:
  - the full AGROVOC export is intentionally broad and supports semantic coverage
  - the runtime lexicon remains filtered so exact lexical triggers do not become noisy

- The current curated lexicon already includes explicit bee-health, apiculture, pollination, and plant-protection concepts so agriculture gating does not depend solely on generic crop terms.

## API Endpoints

### `POST /classify`

Classifies a supported KO asset file. Agri Gate screening is optional and controlled by `use_agri_gate`.

Important runtime constraint:

- supported file types are currently `.pdf`, `.txt`, `.docx`, `.pptx`, `.csv`, `.tsv`, `.xlsx`, `.jpg`, `.jpeg`, `.png`, `.mp3`, `.wav`, `.m4a`, `.mp4`, `.avi`, `.mov`, `.wmv`, `.mpeg`, `.mpg`, `.mkv`, `.flv`, `.webm`, `.3gp`, `.mts`, `.m2ts`, `.vob`, and `.rmvb`
- OCR fallback currently applies to PDFs and images
- OCR also applies to image files
- vision routing currently applies to PDFs and image files
- audio transcription currently applies to audio files when the transcription backend is configured
- video frame sampling currently applies to video files when FFmpeg is available
- video audio transcription currently applies to video files when both FFmpeg and the transcription backend are configured
- synchronous media caps are enforced for large uploads:
  - `MAX_AUDIO_DURATION_SEC=3000`
  - `MAX_VIDEO_DURATION_SEC=3000`
  - `MAX_AUDIO_UPLOAD_SIZE_MB=768`
  - `MAX_VIDEO_UPLOAD_SIZE_MB=1024`
  - `MAX_OTHER_UPLOAD_SIZE_MB=50`
  - `MAX_REQUEST_BODY_MB=1024`
- document-family uploads are rejected early when they exceed the synchronous unit cap:
  - `MAX_DOCUMENT_UNITS=100`
  - applies to exact PDF pages, exact PPTX slides, DOCX page count when Office metadata is available, and a conservative TXT page estimate
- tabular ingestion uses bounded previews for speed:
  - `TABULAR_MAX_ROWS=100`
  - `TABULAR_PREVIEW_ROWS=30`
  - `XLSX_MAX_SHEETS=10`
  - `XLSX_MAX_ROWS_PER_SHEET=25`
- file MIME/type routing currently routes delimited files to `Dataset` and routes document-family files to `Document`
- file MIME/type routing routes image files to `Image`
- file MIME/type routing routes audio files to `Audio`
- file MIME/type routing routes video files to `Video`
- `Dataset` uploads now receive dataset subtype scoring
- `Document` uploads receive document subtype scoring
- `Image` uploads receive image subtype scoring
- `Audio` uploads receive audio subtype scoring when a usable transcript is available
- `Video` uploads receive video subtype scoring when sampled frames and/or a usable transcript are available

Deployment note:

- the app now performs an early `Content-Length` check using `MAX_REQUEST_BODY_MB`
- to reject oversized uploads before they reach the app process, the reverse proxy should enforce the same or lower limit
- for Traefik, use the request body buffering middleware with a matching limit
- for Nginx, set `client_max_body_size 1024M;` or a lower value if preferred

Query parameters:

- `use_agri_gate`: if `true`, send the uploaded file to Agri Gate before classification; default `false`
- `require_agriculture`: if `true`, non-agriculture documents return early and skip subcategory classification
- `auto_route_models`: if `true`, the API decides when text and vision models are actually used
- `use_vision`: allow InternVL-style vision classification when routing decides it is needed; default `true`
- `use_text_llm`: allow text LLM classification for agriculture-related documents; default `true`
- language-aware routing now detects probable text language and makes the text LLM the primary subtype classifier for strongly non-English content to avoid over-trusting English-biased heuristics
- `heuristics_alpha`: heuristic weight used by weighted fusion
- `classification_confidence_threshold`: confidence threshold used to treat a subcategory result as strong enough
- `vision_trigger_threshold`: confidence threshold below which vision may be triggered
- `candidate_gap_threshold`: probability gap threshold below which close candidates may trigger vision
- `fusion_strategy`: `weighted`, `adaptive`, `agreement`, or `cascade`
- `vision_max_pages`: maximum sampled pages passed to the vision model; runtime uses deterministic representative-page sampling rather than scanning every page
- `ocr_lang`: optional Tesseract OCR language bundle, used only when PDF OCR fallback is triggered
- `ocr_max_pages`: maximum pages sent through OCR fallback; default `5`, maximum `50`

Example:

```bash
curl -X POST "http://localhost:8011/classify?use_agri_gate=false&require_agriculture=true&auto_route_models=true&use_text_llm=true&use_vision=true&fusion_strategy=adaptive" \
  -F "file=@document.docx"
```

Representative response fields:

- `processing_info.security_gate`: Agri Gate scan status, reason code, and strict-mode outcome
- `processing_info.source_mode`: `file`
- `best_match`: top candidate after heuristics-only scoring or fusion
- `all_candidates`: full ranked list
- `classification_skipped`: whether classification stopped after the agriculture gate
- `skip_reason`: explanation when classification is intentionally skipped
- `category_used`: deterministic category routing used for the uploaded file
- `agriculture_relevance`: agri/non-agri decision with matched concepts and stage results

## Docker Build Notes

The Docker build now optimizes the heaviest layers:

- installs `torch` from the CPU wheel index instead of pulling larger default builds
- uses BuildKit cache mounts for `pip` and Hugging Face model downloads
- makes agriculture embedding predownload optional at build time

Default build script behavior in [build_and_push.sh](build_and_push.sh):

- `DOCKER_BUILDKIT=1`
- `PRELOAD_AGRI_MODEL=false`
- `TORCH_INDEX_URL=https://download.pytorch.org/whl/cpu`

Example:

```bash
bash build_and_push_images.sh
PRELOAD_AGRI_MODEL=true bash build_and_push_images.sh
```
- `processing_info.routing`: whether text and vision were requested, used, and why
- `processing_info.language_detection`: detected language, confidence, and whether non-English LLM-primary routing was applied
- `processing_info.routing.audio_mode`: present for the audio branch
- `processing_info.stage_timings_ms`: latency breakdown by extraction, OCR, agriculture, heuristics, LLM, and fusion stages
- `feature_details`: feature-level evidence and excerpts
- `rationale`: direct explanation for the candidate
- `contrastive_rationale`: why the winner beat nearby alternatives
- `fusion`: weights, agreement score, and fusion rationale

### `POST /classify-url`

Classifies a public URL after:

1. optional Agri Gate URL screening
2. local URL deny-list enforcement for dangerous direct-download targets
3. PageSense raw-text extraction
4. agriculture relevance, category inference, and text-based subtype classification

Current URL behavior:

- accepts only public `http` and `https` URLs
- uses PageSense raw text only; it does not ingest downloaded file bytes in this service
- stays text-only after extraction, so OCR and vision routing do not apply
- `use_agri_gate`: if `true`, send the URL to Agri Gate before PageSense extraction; default `false`
- successful PageSense results are cached in-memory by URL for faster repeat requests
- agriculture relevance results are cached in-memory by normalized text hash for faster repeat classification
- current default cache settings are:
  - `URL_EXTRACTION_CACHE_TTL_SEC=172800` (`48` hours)
  - `AGRICULTURE_CACHE_TTL_SEC=172800` (`48` hours)
  - `RUNTIME_CACHE_MAX_ENTRIES=256`
  - `RUNTIME_CACHE_MAX_BYTES=67108864` (`64` MB per in-memory cache, approximate)
- text LLM is no longer mandatory on the URL path:
  - it now runs mainly for non-English content, low-confidence heuristic outcomes, or close-candidate cases
  - strong heuristic URL classifications can return without paying the extra text-LLM round-trip
- URL text sent to the text LLM is now sampled from the beginning, middle, and end instead of always sending the full extracted body
- when PageSense returns metadata, the URL branch now enforces the same practical caps as file uploads:
  - document-like URL content above `MAX_DOCUMENT_UNITS=100` is rejected
  - audio/video URL content above `3000` seconds is rejected
  - non-audio/video URL content above `MAX_OTHER_UPLOAD_SIZE_MB=50` is rejected
- can currently route URL content into `Document`, `Dataset`, or `Software Application`
- returns category-level output for `Software Application` and skips subtype scoring for that category for now

Example:

```bash
curl -X POST "http://localhost:8011/classify-url?use_agri_gate=false&require_agriculture=true&use_text_llm=true&fusion_strategy=adaptive" \
  -H "Content-Type: application/json" \
  -d '{"url":"https://example.org/article"}'
```

Representative response fields:

- `processing_info.security_gate`: Agri Gate scan status, reason code, and strict-mode outcome
- `processing_info.source_mode`: `url`
- `processing_info.extraction`: PageSense extraction metadata
  it can now include `content_kind`, `content_type`, `size_bytes`, `page_count`, and `duration_seconds`
- `processing_info.cache`: cache-hit flags for `pagesense` and `agriculture`
- `processing_info.stage_timings_ms`: now includes URL-path timings such as `agri_gate_ms`, `pagesense_ms`, `agriculture_pipeline_ms`, `text_llm_ms`, and `fusion_ms`
- `best_match`: top candidate after heuristics-only scoring or fusion
- `classification_skipped`: whether the URL stopped at the agriculture gate or category gate
- `processing_info.eligibility_gate`: KO-eligibility decision used to skip agriculture-related but non-eligible content
- `category_used`: category selected for downstream URL classification
- `category_inference`: inferred high-level category for the extracted URL text
- `agriculture_relevance`: agri/non-agri decision with matched concepts and stage results

## Recommended Fusion Defaults

Recommended production default:

- `fusion_strategy=adaptive`
- `heuristics_alpha=0.5`

Why:

- heuristics remain valuable because they are deterministic and auditable
- LLMs remain valuable because they are stronger on short-form and semantically ambiguous material
- `adaptive` lets the system reweight sources based on confidence instead of relying only on fixed static weights

When to use each strategy:

- `adaptive`: best general default for mixed production traffic
- `weighted`: best for controlled evaluation and reproducible comparisons
- `agreement`: useful when multiple model sources are active and consensus should matter more
- `cascade`: best when latency or inference cost matters and heuristics often resolve the easy cases

Practical guidance for `heuristics_alpha`:

- `0.6`: more conservative and heuristic-led
- `0.5`: balanced default
- `0.4`: more LLM-led, useful for short flyers, newsletters, and visually formatted material

### `GET /subcategories`

Returns the active document subcategories together with their criteria metadata. This is useful for UI configuration, documentation generation, and debugging explainability output.

### `GET /health`

Returns service and model configuration status.

The health payload now also exposes operational readiness for the newer media branches:

- `models.audio_transcription.enabled`
- `models.audio_transcription.configured`
- `models.agrigate.configured`
- `models.agrigate.url_strict`
- `models.agrigate.file_strict`
- `models.pagesense.configured`
- `models.video_tooling.ffmpeg_available`
- `models.video_tooling.ffprobe_available`
- `models.video_tooling.frame_sampling_ready`
- `models.video_tooling.audio_extract_ready`

These fields indicate whether the `Audio` and `Video` branches are fully operable or will fall back to partial behavior / skip paths.

Operational note:

- `/health` is intentionally left unauthenticated so Docker and other health checks can probe the service without Basic Auth credentials

### `GET /docs`

Swagger UI for interactive API testing.

## Local Setup

### Standalone

System packages required for full PDF and OCR support:

```bash
sudo apt-get update
sudo apt-get install -y poppler-utils tesseract-ocr tesseract-ocr-eng
```

Optional:

- install additional Tesseract language packs if multilingual OCR is required

Python setup:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.sample .env
```

Minimal `.env` for local heuristics-only use:

```bash
HOST=0.0.0.0
PORT=8011
WORKERS=1

DOCINT_AUTH_USERS=
DOCINT_AUTH_PASSWORD=
```

Add these variables only if text LLM classification should be enabled:

```bash
DOCINT_LLM_BASE_URL=https://your-qwen-server.com/v1
DOCINT_LLM_MODEL=qwen3-30b-a3b-awq
DOCINT_LLM_API_KEY=your-key
```

Add these variables only if vision classification should be enabled:

```bash
VISION_LLM_BASE_URL=https://your-internvl-server.com/v1
VISION_LLM_MODEL=internvl3-5-14b
VISION_LLM_API_KEY=your-key
```

Add these variables if file and URL security screening should be enabled:

```bash
AGRI_GATE_BASE_URL=https://agrigate.nexavion.com
AGRI_GATE_API_TOKEN=your-token
AGRI_GATE_TIMEOUT=60
AGRI_GATE_URL_STRICT=true
AGRI_GATE_FILE_STRICT=true
```

Add these variables if URL extraction through PageSense should be enabled:

```bash
URL_CONTENT_EXTRACTOR_BASE=https://pagesense.nexavion.com
EXTRACTOR_TIMEOUT=150
EXTRACTOR_MIN_CHARS=100
```

Start the service with one of:

```bash
./start_server.sh
```

```bash
python start_server.py
```

```bash
uvicorn app:app --host 0.0.0.0 --port 8000 --reload
```

The API will be available at `http://localhost:8011` when `PORT=8011` is set in `.env`.

### Docker Compose

The repository includes a local Compose file at [docker-compose.yml](docker-compose.yml).

Basic flow:

```bash
cp .env.sample .env
docker compose up --build
```

The service will be exposed on `http://localhost:8011` when `PORT=8011` is set in `.env`.

For local testing, leaving `DOCINT_AUTH_USERS` and `DOCINT_AUTH_PASSWORD` empty is the simplest option. If Basic Auth is enabled, `/health` still remains public for container and load-balancer health checks.

### Docker Without Compose

Build:

```bash
docker build -t agri-tag:local .
```

Run:

```bash
docker run --rm -p 8000:8000 --env-file .env agri-tag:local
```

## Classifier Behavior Notes

- Heuristics are deterministic and comparatively fast.
- Most latency comes from remote LLM calls, not from local feature extraction.
- `cascade` fusion is the most practical speed-oriented option when heuristics are often decisive.
- The vision model now uses deterministic representative-page sampling rather than overlapping page windows.
- Text and vision prompts are aligned with the same criteria vocabulary used by heuristics.

## Project Structure

- [app.py](app.py): FastAPI app and response shaping
- [subcategories.py](docint/rubrics/subcategories.py): active subcategory source of truth
- [subcategory_scorer.py](docint/rubrics/subcategory_scorer.py): heuristic scoring engine
- [subcategory_classify.py](docint/llm/subcategory_classify.py): text and vision LLM classification
- [intelligent_fusion.py](docint/fusion/intelligent_fusion.py): fusion strategies
- [data_model](data_model): taxonomy, consolidation, and category policy documents

## Verification

Quick compile check:

```bash
python3 -m py_compile app.py docint/rubrics/subcategories.py docint/rubrics/subcategory_scorer.py docint/llm/subcategory_classify.py
```

Basic API test script:

```bash
python test_api.py
```
