# Agri-Tag API

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
- Infers up to 3 `intended_purposes` (user intents, e.g. *Ensure compliance*, *Access data*) — see [Intended Purposes](#intended-purposes-user-intent).

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

## Output Cardinality

Each classification axis is returned with a fixed cardinality:

| Axis | Count |
| --- | --- |
| `category_used` | exactly 1 (deterministic routing) |
| subcategory (`all_candidates`) | 1, or 2 when the runner-up is a close contender (within `SUBCATEGORY_SECOND_GAP`, default `0.15`) |
| `topics` | 1–3 |
| `intended_purposes` | 1–3 |

(`best_match` is always the single top subcategory; the optional second candidate
surfaces only when the decision is genuinely close. Tunable via
`SUBCATEGORY_MAX_CANDIDATES` and `SUBCATEGORY_SECOND_GAP`.)

## Intended Purposes (User Intent)

Alongside `topics`, each classified asset now carries an `intended_purposes` block —
the **user-intent / functional** facet: *what a user would come to this resource to
do* (e.g. *Ensure compliance with regulations*, *Access data*, *Build professional
networks*). It is **orthogonal** to both the subcategory (genre/form) and topics
(subject matter), and it is **multi-label, capped at 3** (ranked, so a clear primary
still surfaces).

The taxonomy is the published EU FarmBook purpose list at
[data_model/runtime/purposes/intended_purposes.json](data_model/runtime/purposes/intended_purposes.json)
(15 purposes across 8 categories such as *Data & Information*, *Governance &
Compliance*, *Practice Implementation*, plus *Other*).

Like topics, intended purposes are **only emitted for agriculture-related assets** — a
document that fails the agriculture gate is skipped, so it produces neither topics nor
purposes (and pays for neither stage). For agriculture-related assets, inference is
staged (mirroring the agriculture/topics pipelines), in
[docint/purposes/infer.py](docint/purposes/infer.py):

- **Stage 1 — embedding:** CPU-first multilingual match
  (`intfloat/multilingual-e5-small`) of the document against each purpose's
  `name + description` anchor. This is the baseline and offline fallback.
- **Stage 2 — LLM (primary when available):** ranks the purposes for the document
  and returns up to 3 with confidence + rationale. It **rides the configured text
  LLM** (so it honours `provider=custom|mistral`) and is gated by `use_text_llm`.
  Falls back to Stage 1 if the LLM is off or fails.

The embedding model is **shared** across the agriculture, topics, and purpose stages
(one in-memory copy of `e5-small`, not three) and is **pre-warmed at startup**
(`PREWARM_EMBEDDINGS=true`) so the first request isn't the one that pays the load cost.

Example output for an ethics/compliance deliverable:

```json
"intended_purposes": {
  "purposes": [
    {"key": "NKixsHVz", "name": "Ensure compliance with regulations, policies, and guidelines",
     "category": "Governance & Compliance", "score": 0.95, "rationale": "..."}
  ],
  "method": "llm",
  "stages_used": ["llm"],
  "version": "intended_purpose_v1",
  "rationale": "..."
}
```

Relevant settings (all optional): `PURPOSE_ENABLE_EMBEDDING`, `PURPOSE_EMBEDDING_MODEL`,
`PURPOSE_MAX_SELECTED` (default `3`), `PURPOSE_SELECT_THRESHOLD`, `PURPOSE_LLM_MAX_CHARS`.
Latency is reported under `processing_info.stage_timings_ms.intended_purposes_ms`.

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

### Multilingual lexicon/topic regeneration

The build scripts now default to the **full 24-language EU set** (`build_agrovoc_full_export.py`,
`build_agriculture_lexicon_from_agrovoc.py`, `build_agrovoc_anchor_texts.py` — `DEFAULT_LANGS`).
Regenerating produces a **multilingual** agriculture lexicon + topic signals (Cyrillic, Slavic,
Nordic included), so the cheap lexical fast-path works in every EU language — not just via the
embedding/LLM path. One-shot runner (the AGROVOC export step is slow and resumable):

```bash
bash scripts/regenerate_multilingual_resources.sh
# then restart the service to load the new resources
```

- Full AGROVOC regeneration workflow (what the runner does, step by step):

```bash
.venv/bin/python scripts/build_agrovoc_full_export.py
.venv/bin/python scripts/build_agriculture_lexicon_from_agrovoc.py \
  --input data_model/build/agriculture/agrovoc_full_export.jsonl
.venv/bin/python scripts/build_agriculture_anchor_texts.py
.venv/bin/python scripts/compute_agriculture_bucket_centroids.py \
  --inputs data_model/build/agriculture/anchor_texts.jsonl
.venv/bin/python scripts/build_topic_signals_from_agrovoc.py
.venv/bin/python scripts/compute_topic_centroids.py
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

The service exposes 4 `POST` classification endpoints (`/classify`, `/classify-url`,
`/classify-text`, `/classify-media-llm`) and 4 `GET` informational endpoints (`/`,
`/health`, `/subcategories`, `/intended-purposes`), plus the auto-generated `/docs`
Swagger UI. A side-by-side comparison of what each one does and how they differ is in
[documentation/api_endpoints_overview.md](documentation/api_endpoints_overview.md).

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
- `vision_max_pages`: ceiling on page-images sent to the vision model per request (default `8`); the runtime chooses the actual count **length-adaptively** up to this ceiling and samples pages deterministically across the **whole** document (first page, last page, and a stratified spread of the body). It is **clamped server-side to `VISION_MAX_PAGES_CAP`** (default `8`), which **must match your vLLM server's `--limit-mm-per-prompt image:N`** — otherwise the VLM rejects the request. See [Long-PDF Handling and Literature](#long-pdf-handling-rationale-and-literature).
- `ocr_lang`: optional Tesseract OCR language bundle, used only when PDF OCR fallback is triggered
- `ocr_max_pages`: maximum pages sent through OCR fallback; default `5`, maximum `50`
- `provider`: LLM provider flow, `custom` (default) or `mistral`. See [LLM Providers: Custom vs Mistral](#llm-providers-custom-vs-mistral).

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

### `POST /classify-text`

Classifies a **raw text snippet** with no file upload — useful when the caller already
has extracted text. The snippet is treated as a text document and run through the same
pipeline as a file, so you get all four axes: `category_used` (always `Document`),
subcategory, `topics`, and `intended_purposes`. Because there is no file, **OCR and
vision do not apply** (those are for scanned pages/images).

- Capped at `MAX_TEXT_INPUT_WORDS` (default `5000` words ≈ 10 A4 pages); longer input
  returns `413`. Empty text returns `400`.
- Supports the same `provider` (`custom` | `mistral`), `require_agriculture`,
  `use_text_llm`, `fusion_strategy`, and `heuristics_alpha` controls as `/classify`.
- Response is the standard `ClassificationResponse` with `processing_info.source_mode = "text"`
  and `processing_info.input_word_count`.

```bash
curl -X POST "http://localhost:8011/classify-text?provider=mistral&use_text_llm=true&fusion_strategy=adaptive" \
  -H "Content-Type: application/json" \
  -d '{"text": "Step-by-step guide to adopting precision irrigation for smallholder farms ..."}'
```

## LLM Providers: Custom vs Mistral

Every classification endpoint accepts a `provider` parameter that selects which
LLM backend handles the request:

- `provider=custom` (default) — the self-hosted, OpenAI-compatible flow we have
  always used: Qwen for text, InternVL for vision, Tesseract for OCR fallback,
  and the Whisper media-transcriber service for audio/video.
- `provider=mistral` — routes the same pipeline to Mistral. Text and vision
  classification go to Mistral's **OpenAI-compatible** chat endpoint (so the
  existing classification logic is reused unchanged), while OCR and transcription
  use Mistral's **native SDK** (`mistral-ocr-latest` and Voxtral).

What each stage uses under `provider=mistral`:

| Stage | `custom` | `mistral` |
| --- | --- | --- |
| Text classification | Qwen (`DOCINT_LLM_*`) | `MISTRAL_TEXT_MODEL` via OpenAI-compatible endpoint |
| Vision (PDF pages / image / video frames) | InternVL (`VISION_LLM_*`) | `MISTRAL_VISION_MODEL` via OpenAI-compatible endpoint |
| OCR fallback (scanned PDFs / images) | Tesseract | `MISTRAL_OCR_MODEL` (`mistral-ocr-latest`) |
| Audio / video transcription | Whisper service (`MEDIA_TRANSCRIBER_*`) | Voxtral (`MISTRAL_AUDIO_MODEL`); for video, audio is first extracted with FFmpeg, then sent to Voxtral |

The Mistral integration lives in a dedicated, self-contained module —
[docint/providers/mistral_provider.py](docint/providers/mistral_provider.py) — so
the two flows never get mixed up. Install the SDK with `pip install -r requirements.txt`
(adds `mistralai`).

### Configuration

Only `MISTRAL_API_KEY` is required; the rest default sensibly:

```bash
MISTRAL_API_KEY=your-mistral-key
MISTRAL_OPENAI_BASE_URL=https://api.mistral.ai/v1
MISTRAL_TEXT_MODEL=mistral-small-latest
MISTRAL_VISION_MODEL=mistral-medium-latest
MISTRAL_OCR_MODEL=mistral-ocr-latest
MISTRAL_AUDIO_MODEL=voxtral-mini-latest
```

### Recommended models

- **Text** (`MISTRAL_TEXT_MODEL`): `mistral-small-latest` — cheap, fast, and
  strong enough for classification. Step up to `mistral-medium-latest` if accuracy
  falls short.
- **Vision** (`MISTRAL_VISION_MODEL`): `mistral-medium-latest` or
  `pixtral-large-latest`. (Mistral Small 3.1+ is also multimodal, so you can use
  one model for both stages if you prefer.)
- Avoid Magistral (reasoning, slow/costly overkill), Ministral 3B/8B (edge models),
  and Codestral/Devstral (coding) for this task.

### Why these models (model-selection rationale)

These defaults are matched to **what the task is**, not chosen to minimise cost for
its own sake. `/classify` does **bounded-label classification** — pick one of a fixed
set of subcategories and emit JSON probabilities + a short rationale, with the rubric
supplied in the prompt — and the LLM output is then **fused with deterministic
heuristics**, so it is one weighted signal, not the sole judge. That profile rewards
reliable instruction-following and JSON formatting, not deep reasoning or long-form
generation.

**Text — why `small`, not `medium`/`large`:**

- The task sits well inside Small's competence band; document *genre* signal is
  structural and strong, and fusion partly washes out marginal gains from a bigger
  model.
- You send up to ~15k characters per document, so per-token cost compounds. Small is
  roughly **5–8× cheaper than Medium** and **15–20× cheaper than Large**, and faster
  for synchronous requests.
- **The "Large" trap:** `mistral-large-latest` currently resolves to **Large 2**, an
  *older generation* than Medium 3, and is **text-only**. Mistral positions Medium 3
  as matching or beating Large 2 at a fraction of the cost — so picking Large over
  Medium often means **paying more for an older, non-multimodal model**. If you step
  text up, go to `mistral-medium-latest`, not Large.
- **When to upgrade text:** heavy non-English traffic (the runtime already makes the
  text LLM primary for strongly non-English content, where a larger model genuinely
  helps), or if evaluation shows Small confusing close competitors (e.g. *Tutorial*
  vs *Guide/Manual*).

**Vision — why `medium`, not "large":**

- The naming is the catch: `mistral-large-latest` is **text-only**, so it is not even
  a vision candidate. The real "large vision" option is **`pixtral-large-latest`**
  (a vision specialist), not "Mistral Large".
- So the honest comparison is **Medium 3 vs Pixtral Large**. Medium 3 is the modern
  multimodal model — strong on document pages (layout, title, structure), cheaper, and
  lower-latency — which is exactly what *genre* classification from page images needs.
  Pixtral Large's extra capacity targets harder visual reasoning (dense charts,
  diagrams, intricate tables) that this task does not require.
- Vision is the **biggest token sink** (up to `VISION_MAX_PAGES_CAP` page-images per request, default 8), so
  over-provisioning the vision model is the most expensive mistake. Try
  `pixtral-large-latest` only if evaluation shows figure-heavy or scanned cases
  underperforming.

**Bottom line:** `small` (text) + `medium` (vision) is the **accuracy-per-euro knee**
for a fused, rubric-driven classifier. Both are single env vars, so upgrading is a
one-line A/B test — and the right way to settle it is a small labelled eval set, not
priors. (Approximate cost multipliers above are order-of-magnitude and shift over
time; confirm against current Mistral pricing.)

### Usage

```bash
curl -X POST "http://localhost:8011/classify?provider=mistral&use_text_llm=true&use_vision=true&fusion_strategy=adaptive" \
  -F "file=@document.pdf"
```

`provider` is an enum (`custom` | `mistral`), so the Swagger UI at `/docs` renders it
as a **dropdown** and rejects invalid values with `422`. A request with
`provider=mistral` returns `503` if `MISTRAL_API_KEY` is not set.
`GET /health` exposes a `models.mistral` block with the active models and a
`configured` flag.

### Caveats

- **Cost moves from GPUs to per-token API.** Under `custom` the self-hosted models
  make page-images effectively free; on Mistral you pay per image/token, so the
  length-adaptive vision sampling (see below) directly controls your bill. Consider
  a lower `vision_max_pages` ceiling for Mistral than for a self-hosted model.
- **Image/audio format support is unchanged** — the same upload allowlist applies
  regardless of provider (e.g. `.xls` and exotic audio/image formats are still not
  accepted).
- **Agriculture-relevance Stage 3** (the optional LLM tie-breaker for the agri gate)
  always uses the `custom` text LLM, not Mistral; if no custom LLM is configured it
  simply falls back to the lexicon/embedding stages.

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

### `GET /intended-purposes`

Returns the intended-purpose (user-intent) taxonomy used for the `intended_purposes` block — the full list with `key`, `name`, `category`, and `description`, grouped by category, plus `max_selected_per_asset`. Useful for UI configuration. See [Intended Purposes](#intended-purposes-user-intent).

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

System packages required for full PDF, OCR, and media support:

```bash
sudo apt-get update
# poppler-utils: PDF->image rendering (OCR fallback + vision page sampling)
# ffmpeg:        audio/video frame sampling + audio extraction
# tesseract-ocr-all: OCR. The default OCR bundle is the full EU language set
#                    (ALL_OCR_LANGS), so 'eng' alone is NOT enough -- a non-English
#                    PDF (e.g. Greek) fails with "Failed loading language 'ell'".
sudo apt-get install -y poppler-utils ffmpeg tesseract-ocr tesseract-ocr-all
```

Notes:

- **`poppler-utils` is required** for any PDF that hits OCR or vision — without it you get
  `Unable to get page count. Is poppler installed and in PATH?`.
- If you don't need full multilingual OCR you can replace `tesseract-ocr-all` with just the
  language packs you use (e.g. `tesseract-ocr-eng tesseract-ocr-ell tesseract-ocr-nld`), or
  pass a narrower `ocr_lang` per request.
- **Performance:** OCR runs *every* language in the bundle, so the full 24-language default
  is ~40 s/page. Set `OCR_DEFAULT_LANGS` (e.g. `eng+ell+nld+deu+fra+spa+ita+por`) to a curated
  subset for production — it drops OCR to a few seconds. Per-request `ocr_lang` still overrides it.
- These are invoked as subprocesses at request time, so installing them does **not** require
  restarting the service.
- Verify with: `which pdfinfo pdftoppm tesseract ffmpeg` and `tesseract --list-langs`.

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
# Raster DPI for PDF page rendering sent to the vision model (150-200 recommended)
VISION_RENDER_DPI=150
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
- The agriculture-relevance and KO-eligibility LLM stages follow the request's `provider` (so `provider=mistral` no longer falls back to the self-hosted endpoint).
- **Experimental** `MERGE_AGRI_SUBCATEGORY_LLM` (default off): for an *ambiguous-agriculture document*, the Stage-3 agriculture LLM and the document subtype LLM are collapsed into a **single** call (saves one round-trip). Only the ambiguous path is affected; clearly agri/non-agri docs are still decided cheaply by lexicon/embedding. Validate agriculture-gate accuracy on an eval set before enabling in production.

## Long-PDF Handling: Rationale and Literature

This service is a **classifier**, not an extraction/QA pipeline. The goal is a label
(category + subcategory) plus an auditable rationale — not the recovery of every fact
in the document. That distinction drives how long PDFs are handled and why we sample
rather than read every page.

### How a PDF flows through the pipeline

| Stage | What it sees | Limit | Env / param |
| --- | --- | --- | --- |
| Text extraction (PyMuPDF) | **All pages** | none — full text feeds the deterministic heuristics | — |
| Text LLM | head 45% / mid 25% / tail ~30% sample of the full text | `15000` chars (document path) | `_sample_text_for_llm` |
| Vision LLM | stratified page **images** across the whole document | length-adaptive, ceiling `vision_max_pages` (default `8`), hard-clamped to `VISION_MAX_PAGES_CAP` | `vision_max_pages`, `VISION_MAX_PAGES_CAP`, `VISION_RENDER_DPI` |
| OCR fallback (scanned PDFs only) | first N pages | `ocr_max_pages` (default `5`, max `50`), DPI `220` | `ocr_max_pages`, `ocr_lang` |
| Hard reject | — | `MAX_DOCUMENT_UNITS` pages | `MAX_DOCUMENT_UNITS=100` |

The full extracted text always feeds the deterministic heuristic scorer, so the
heuristic layer is never sampled — it is the information-complete safety net. Sampling
only affects the *optional* LLM augmentation layers.

### Vision page sampling

`vision_max_pages` is a **ceiling**, not a fixed count. The actual number of pages sent
to the vision model is chosen length-adaptively:

- documents at or below the ceiling are covered in full
- longer documents get `max(6, ceil(total_pages / 8))` pages, clamped to the ceiling

Pages are sampled at evenly spaced fractional positions so the **first page** (title,
abstract, layout), the **last page** (references, appendices, back-matter), and a
**stratified spread of the body** are always represented. The per-request count is
**clamped to `VISION_MAX_PAGES_CAP` (default 8) to match the vLLM `image:N` limit**, so
example coverage at the default ceiling of 8:

| Document length | Pages sent to vision |
| --- | --- |
| ≤8 pages | all of them |
| 40 pages | 6 (pages 1, 9, 17, 24, 32, 40) |
| 100 pages | 8 (stratified 1 → 100) |
| 250 pages | 8 (stratified 1 → 250) |

> ⚠️ `VISION_MAX_PAGES_CAP` **must equal your vLLM server's `--limit-mm-per-prompt image:N`**.
> If the cap is higher than the server allows, the VLM rejects the request and the vision
> call fails silently (it's caught), so the asset is classified on heuristics+text only.

`VISION_RENDER_DPI` (default `150`) controls raster resolution, and only the sampled
pages are rendered — rendering is page-by-page, so vision cost scales with the number of
pages actually used, not with document length.

### Why sample instead of reading every page

1. **The task is genre classification, and genre signal is front/back-loaded.** Whether a
   PDF is a *journal article*, a *manual*, a *presentation*, or a *technical report* is
   largely determined by its title page, abstract, table of contents, layout, and
   reference/appendix structure. Interior body pages add little discriminative signal for
   this specific decision, so stratified sampling loses very little classification accuracy.
2. **"Lost in the Middle" (Liu et al., 2023, *TACL*).** Transformer LLMs attend most
   reliably to the **beginning and end** of their context and degrade in the middle. Both
   the text sampler (head/mid/tail) and the vision sampler (first + last always included)
   are aligned with this finding. The corollary: the sampled middle is also the part the
   model attends to worst, which is acceptable for classification but a known limitation for
   content-sensitive tasks.
3. **Resolution beats page count for text-bearing documents.** Under a fixed token budget,
   VLM document-understanding work consistently finds that *fewer pages at higher
   resolution* beats *more pages at low resolution*. The practical sweet spot is
   **150–200 DPI**; below ~100 DPI small text becomes unreliable, above ~300 DPI mostly
   burns tokens for diminishing returns. `VISION_RENDER_DPI=150` sits at the efficient end
   of that band.
4. **VLM tiling makes pages expensive.** InternVL-style models use dynamic tiling (multiple
   tiles per image), so a single high-resolution page can cost many hundreds to a few
   thousand tokens. A flat "send 8 pages" cap exists for this reason; the length-adaptive
   budget keeps cost bounded while restoring whole-document coverage.
5. **Empirical band for classification: ~8–16 well-chosen pages.** For documents up to the
   `MAX_DOCUMENT_UNITS=100` cap, accuracy plateaus past roughly a dozen stratified pages,
   while latency and cost keep rising. The defaults target that knee.

### Tuning guidance (finding the sweet spot)

- **Default (`vision_max_pages=8`, `VISION_RENDER_DPI=150`)** is the recommended balance
  for mixed traffic up to 100 pages, and matches a vLLM `image:8` limit. To go higher you
  must raise **both** `VISION_MAX_PAGES_CAP` **and** the server's `--limit-mm-per-prompt`.
- **Dense, text-heavy reports** benefit more from the text path than from vision; consider
  raising the document text sample (`_sample_text_for_llm` `max_chars`, currently `15000` ≈
  6–10 dense pages) before raising vision pages.
- **Scanned or visually formatted material** (flyers, slide decks, posters) benefits from
  vision; raise `vision_max_pages` toward `24` and/or `VISION_RENDER_DPI` toward `200`.
- **Latency/cost-sensitive deployments**: prefer `fusion_strategy=cascade` so heuristics
  resolve the easy cases and vision is only triggered when heuristics are weak or
  candidates are close.
- **Rule of thumb**: budget ~12–15 "page-equivalents" of LLM attention per document and
  split it between text characters and vision pages based on whether the signal is textual
  or visual. Past that, classification accuracy plateaus.

A side-by-side comparison of all endpoints lives in
[documentation/api_endpoints_overview.md](documentation/api_endpoints_overview.md).

## Project Structure

- [app.py](app.py): FastAPI app and response shaping
- [subcategories.py](docint/rubrics/subcategories.py): active subcategory source of truth
- [subcategory_scorer.py](docint/rubrics/subcategory_scorer.py): heuristic scoring engine
- [subcategory_classify.py](docint/llm/subcategory_classify.py): text and vision LLM classification
- [mistral_provider.py](docint/providers/mistral_provider.py): self-contained Mistral provider (OCR, Voxtral transcription, config) for `provider=mistral`
- [purposes/infer.py](docint/purposes/infer.py): intended-purpose (user-intent) inference (embedding + LLM stages)
- [intelligent_fusion.py](docint/fusion/intelligent_fusion.py): fusion strategies
- [data_model](data_model): taxonomy, consolidation, and category policy documents

## Verification

Quick compile check:

```bash
python3 -m py_compile app.py docint/rubrics/subcategories.py docint/rubrics/subcategory_scorer.py docint/llm/subcategory_classify.py
```

Smoke tests (offline — no running server, no remote LLM calls). Runs under pytest or standalone:

```bash
python tests/test_smoke.py          # standalone, no pytest needed
pytest tests/test_smoke.py -v       # if pytest is installed
```

## Evaluation harness

[scripts/eval_harness.py](scripts/eval_harness.py) runs every supported file under a
folder through `POST /classify` (in-process, no server needed) and writes a CSV — one
row per file (per provider) with category, subcategory, candidates, agriculture verdict,
topics, intended purposes, and per-stage timings.

```bash
# every supported file in files/, provider=custom -> eval_results.csv
python scripts/eval_harness.py

# compare both providers side by side (one row per file per provider)
python scripts/eval_harness.py --providers custom,mistral

# heuristics-only, fast, no remote LLM calls
python scripts/eval_harness.py --no-vision --no-text-llm

# narrow run
python scripts/eval_harness.py --files-dir files/Dataset --limit 5 --vision-max-pages 8 --ocr-lang eng+ell
```

`vision_max_pages` defaults to `8` to respect a VLM launched with an `image:8` limit.
Auth is read from `DOCINT_AUTH_USERS` / `DOCINT_AUTH_PASSWORD`. Use this to measure
**warm-path** latency and to A/B provider/model accuracy on a labelled set.
