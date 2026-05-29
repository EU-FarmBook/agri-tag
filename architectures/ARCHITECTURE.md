# KO Classifier Architecture

## Scope

This service currently implements category and subtype classification for `.pdf`, `.txt`, `.docx`, `.pptx`, `.csv`, `.tsv`, `.xlsx`, `.jpg`, `.jpeg`, `.png`, `.mp3`, `.wav`, `.m4a`, `.mp4`, `.avi`, `.mov`, `.wmv`, `.mpeg`, `.mpg`, `.mkv`, `.flv`, `.webm`, `.3gp`, `.mts`, `.m2ts`, `.vob`, and `.rmvb`. It does not yet enforce the broader KO category-selection policy in runtime. That policy work, including `Document`, `Video`, `Audio`, `Image`, `Dataset`, and `Software Application`, is documented separately in:

- [category_auto_selection_policy.md](../data_model/docs/category_auto_selection_policy.md)
- [subcategories_consolidation_analysis.md](../data_model/docs/subcategories_consolidation_analysis.md)

The live API path in this repository accepts document-family, tabular, image, audio, and video uploads, plus public URLs. It can run Agri Gate before downstream processing, uses deterministic MIME/file-type routing for files, keeps category inference for URLs, and currently classifies:

- `Document` assets into 11 consolidated document subcategories
- `Dataset` assets into 8 consolidated dataset subcategories
- `Image` assets into 3 consolidated image subcategories
- `Audio` assets into 6 consolidated audio subcategories
- `Video` assets into 6 consolidated video subcategories

## High-Level Flow

```text
Client file upload or URL submission
  -> optional Agri Gate security screening
  -> FastAPI request handling
  -> normalized file ingestion or PageSense URL text extraction
  -> deterministic file MIME/type routing or URL category inference
  -> OCR fallback for PDFs and images if text quality is poor
  -> audio transcription for audio files when configured
  -> frame sampling and optional audio extraction for video files when configured
  -> agriculture relevance gate
  -> category-specific heuristic subtype scoring
  -> text LLM classification for agri docs, datasets, audio, and transcript-rich videos when enabled
  -> selective vision classification for PDFs, vision-first classification for images, and sampled-frame classification for videos
  -> probability fusion
  -> ranked response with evidence and contrastive rationale
```

## Runtime Pipeline

### 1. Ingress

- Entry point: [app.py](../app.py)
- Endpoint: `POST /classify`
- Endpoint: `POST /classify-url`
- Current file types: `.pdf`, `.txt`, `.docx`, `.pptx`, `.csv`, `.tsv`, `.xlsx`, `.jpg`, `.jpeg`, `.png`, `.mp3`, `.wav`, `.m4a`, `.mp4`, `.avi`, `.mov`, `.wmv`, `.mpeg`, `.mpg`, `.mkv`, `.flv`, `.webm`, `.3gp`, `.mts`, `.m2ts`, `.vob`, `.rmvb`
- URL mode: public `http` and `https` targets only
- Authentication: Basic Auth when `DOCINT_AUTH_USERS` and `DOCINT_AUTH_PASSWORD` are configured
- Exception: `GET /health` is intentionally unauthenticated so container and platform health probes can work without credentials

The runtime can call:

- [agrigate.py](../docint/integrations/agrigate.py)

before file classification and before URL extraction when `use_agri_gate=true`. If strict mode is enabled and Agri Gate rejects the input, the request stops immediately.

### 2. Text Extraction

- Dispatcher: [dispatcher.py](../docint/ingest/dispatcher.py)
- Normalized model: [models.py](../docint/ingest/models.py)
- PDF path: [pdf.py](../docint/ingest/pdf.py)
- TXT path: [text.py](../docint/ingest/text.py)
- DOCX path: [docx.py](../docint/ingest/docx.py)
- PPTX path: [pptx.py](../docint/ingest/pptx.py)
- Tabular path: [tabular.py](../docint/ingest/tabular.py)
- Image path: [image.py](../docint/ingest/image.py)
- Audio path: [audio.py](../docint/ingest/audio.py)
- Video path: [video.py](../docint/ingest/video.py)
- Quality check: [quality.py](../docint/extract/quality.py)
- OCR fallback: [ocr.py](../docint/extract/ocr.py)
- Audio transcription: [transcribe.py](../docint/audio/transcribe.py)
- Video helpers: [extract.py](../docint/video/extract.py)
- URL extraction: [pagesense.py](../docint/integrations/pagesense.py)

The service first normalizes supported document, tabular, image, audio, and video files into a common internal representation. OCR fallback is currently available for PDFs and images when extracted text quality is poor. CSV, TSV, and XLSX files are flattened into text summaries for agriculture gating and dataset classification. Audio files use optional transcription before agriculture gating and audio subtype scoring. Video files use optional audio extraction plus transcription and optional sampled-frame extraction through FFmpeg. URL submissions are sent to PageSense, which returns raw readable text only, so the URL branch is text-only after extraction. Successful URL extraction results are cached in-memory by URL, and agriculture relevance is cached by normalized text hash to reduce repeat latency. Those caches are bounded by both TTL and an approximate memory budget.

### 3. Category Routing And URL Inference

- Module: [infer.py](../docint/category/infer.py)

For file uploads, the service uses deterministic MIME/file-type routing before subtype scoring:

- `pdf`, `txt`, `docx`, `pptx` -> `Document`
- `csv`, `tsv` -> `Dataset`
- `xlsx` -> `Dataset` or `Document` depending on lightweight spreadsheet signals
- `jpg`, `jpeg`, `png` -> `Image`
- `mp3`, `wav`, `m4a` -> `Audio`
- common video formats such as `mp4`, `avi`, `mov`, `wmv`, `mpeg`, `mkv`, `webm` -> `Video`

If the routed category is `Dataset`, `Image`, `Audio`, or `Video`, the current `/classify` endpoint runs that category's subtype scoring path. If the routed category is not currently supported for subtype scoring, the API returns category and agriculture results and skips subcategory classification.

For `POST /classify-url`, category inference is text-based rather than extension-driven. The current URL branch can infer:

- `Dataset`
- `Software Application`
- `Document`

On the URL branch, text LLM is now conditional rather than automatic. It is primarily used when:

- the extracted content is strongly non-English
- heuristic subtype confidence is below threshold
- top candidates are too close to separate confidently

Strong heuristic URL outcomes can return without the extra text-LLM round-trip.

`Software Application` currently returns category-level output only and skips subtype scoring.

### 4. Agriculture Relevance Gate

- Module: [agriculture_pipeline.py](../docint/domain/agriculture_pipeline.py)
- Lexicon source: [agriculture_lexicon.json](../data_model/runtime/agriculture/lexicon.json)
- Generated Stage 2 resources: [data_model/runtime](../data_model/runtime)

The service now performs agriculture relevance assessment before document-subcategory classification:

- Stage 1: AGROVOC-style multilingual lexicon
- Stage 2: local multilingual embedding model when available, preferring generated per-bucket agriculture centroids over hand-written prototype strings
- Stage 3: text LLM fallback only for ambiguous cases

If `require_agriculture=true` and the file is assessed as non-agriculture, the API returns early and skips subcategory classification.

After the agriculture gate, the runtime now applies a KO-eligibility gate for text-bearing content. This prevents agriculture-adjacent but non-eligible artifacts such as vacancies, calls for applications, event notices, and procurement notices from reaching subtype classification.

The repo now includes an explicit build path for Stage 2 resources:

- [build_agriculture_anchor_texts.py](../scripts/build_agriculture_anchor_texts.py)
- [build_agrovoc_anchor_texts.py](../scripts/build_agrovoc_anchor_texts.py)
- [build_agrovoc_full_export.py](../scripts/build_agrovoc_full_export.py)
- [build_agriculture_lexicon_from_agrovoc.py](../scripts/build_agriculture_lexicon_from_agrovoc.py)
- [compute_agriculture_bucket_centroids.py](../scripts/compute_agriculture_bucket_centroids.py)

This keeps the runtime fast and explainable:

- Stage 1 handles obvious agriculture hits cheaply with multilingual lexicon matching from a filtered runtime lexicon
- Stage 2 uses a small multilingual embedding model plus generated per-bucket centroids for semantic recovery when Stage 1 is weak or incomplete
- Stage 3 stays reserved for the genuinely uncertain tail

The intended data flow is now:

- full AGROVOC export -> broad multilingual concept store
- override/blocklist layer -> conservative runtime lexical trigger set
- runtime lexicon -> fast Stage 1 matching
- generated anchor texts and centroids -> broad Stage 2 semantic recovery

Operational note:

- [build_agrovoc_full_export.py](../scripts/build_agrovoc_full_export.py) now supports retryable paging and checkpoint-based resume because the public FAO SPARQL endpoint can time out on broad export jobs.

### 5. Dataset Subtype Scoring

- Module: [dataset_scorer.py](../docint/category/dataset_scorer.py)

The dataset branch currently uses heuristic scoring over flattened tabular previews and schema/content markers, with an optional dataset-specific text-LLM classifier when `use_text_llm=true`. The active dataset subtype set is:

- `Geospatial Data`
- `Video Data`
- `Audio Data`
- `Image Data`
- `Text Data`
- `Graph/Network Data`
- `Agricultural Production Data`
- `Environmental & Temporal Data`

The document-oriented text and vision LLM prompts are not reused for datasets. Datasets now have a dedicated text-LLM prompt path; vision remains disabled for dataset routing.

### 6. Image Subtype Scoring

- Module: [image_scorer.py](../docint/category/image_scorer.py)
- Vision helper: [subcategory_classify.py](../docint/llm/subcategory_classify.py)

The image branch uses a vision-first classifier and lightweight OCR-text heuristics as fallback. The active image subtype set is:

- `Data Visualization`
- `Figure/Image`
- `Map`

For images, vision is the primary classifier. OCR text is used as supporting evidence and fallback only.

### 7. Audio Subtype Scoring

- Module: [audio_scorer.py](../docint/category/audio_scorer.py)
- Transcription helper: [transcribe.py](../docint/audio/transcribe.py)
- LLM helper: [subcategory_classify.py](../docint/llm/subcategory_classify.py)

The audio branch is transcript-first. It uses optional audio transcription to obtain text, then applies heuristic subtype scoring and an optional audio-specific text-LLM classifier. The active audio subtype set is:

- `Tutorial`
- `Educational/Training Media`
- `Recorded Session`
- `Interview`
- `Q&A Session`
- `Audio Program`

If no usable transcript is available, the API returns a skip response instead of pretending to classify the audio from filename-only evidence.

### 8. Video Subtype Scoring

- Module: [video_scorer.py](../docint/category/video_scorer.py)
- Extraction helpers: [extract.py](../docint/video/extract.py)
- LLM helper: [subcategory_classify.py](../docint/llm/subcategory_classify.py)

The video branch is multimodal. It uses transcript text when audio extraction plus transcription succeeds, and it uses sampled video frames through the vision model when FFmpeg and the vision backend are available. The active video subtype set is:

- `Tutorial`
- `Educational/Training Media`
- `Recorded Session`
- `Interview`
- `Q&A Session`
- `Demonstration/Field Recording`

If neither transcript text nor sampled-frame evidence is available, the API returns a skip response instead of inventing a subtype from filename-only evidence.

### 9. Feature Extraction

The heuristic layer is built around measurable signals rather than opaque labels. Core extraction helpers live under:

- [sections.py](../docint/features/sections.py)
- [citations.py](../docint/features/citations.py)
- [keywords.py](../docint/features/keywords.py)

Rubric-level scoring modules include:

- [imrad.py](../docint/rubrics/imrad.py)
- [citations.py](../docint/rubrics/citations.py)
- [deliverable.py](../docint/rubrics/deliverable.py)
- [pedagogy.py](../docint/rubrics/pedagogy.py)
- [procedure.py](../docint/rubrics/procedure.py)

The active heuristic signal set currently covers 27 features, including:

- academic signals such as `imrad_structure`, `citation_density`, `abstract_quality`, `peer_review_markers`
- technical signals such as `deliverable_markers`, `version_control`, `technical_specs`, `formal_structure`
- instructional signals such as `tutorial_structure`, `learning_objectives`, `exercises_assessments`, `procedure_steps`
- communication and policy signals such as `news_timeliness`, `press_release_format`, `regulatory_update_markers`, `compliance_language`, `governance_references`
- layout signals such as `slide_indicators`, `visual_heavy`, `short_form`

### 10. Heuristic Scoring

- Scorer: [subcategory_scorer.py](../docint/rubrics/subcategory_scorer.py)
- Criteria source of truth: [subcategories.py](../docint/rubrics/subcategories.py)

Each subcategory definition carries:

- detectable features
- positive signal hints
- negative signal hints
- close competitors
- minimum features required

The scorer uses those definitions together with feature-level evidence to produce:

- evidence score
- confidence
- normalized candidate probabilities
- per-feature excerpts
- base rationale text

Recent explainability-oriented changes include:

- feature caching to avoid repeated extractor work
- stronger policy and regulatory-update signals
- reduced phantom evidence for thesis and conference detection
- subcategory-specific bonuses and penalties for close competitors

### 11. Text LLM Classification

- Module: [subcategory_classify.py](../docint/llm/subcategory_classify.py)
- Intended model family: Qwen or any OpenAI-compatible text endpoint

For agriculture-related documents, datasets, audio assets, and transcript-rich videos, text LLM is allowed by default when `use_text_llm=true`. It receives extracted text or transcript content and is prompted with category-appropriate taxonomy criteria.

The runtime now also applies lightweight language detection. When the extracted text is strongly non-English, the text LLM becomes the primary subtype classifier for text-driven branches so the system does not over-trust English-oriented heuristic cues.

- detectable features
- positive signals
- negative signals
- close competitors
- minimum evidence expectation

The prompt also asks the model to report:

- matched signals
- conflicting signals
- closest alternative

This keeps the LLM output closer to the auditable heuristic taxonomy instead of allowing purely free-form reasoning.

### 12. Selective Vision LLM Classification

- Module: [subcategory_classify.py](../docint/llm/subcategory_classify.py)
- Intended model family: InternVL or any OpenAI-compatible vision endpoint

Vision is no longer treated as a default whole-document pass. When `use_vision=true`, routing decides whether vision is needed based on signals such as:

- poor text quality
- OCR usage
- low subcategory confidence
- close top candidates
- visual/slide cues
- disagreement between heuristics and text LLM

When vision is used, the service currently sends deterministic representative sampled PDF pages rather than overlapping page windows, sampled frames for video, and full images for image uploads.

### 13. Fusion

- Module: [intelligent_fusion.py](../docint/fusion/intelligent_fusion.py)

Supported strategies:

- `weighted`
- `adaptive`
- `agreement`
- `cascade`

Fusion operates on normalized source probability distributions and returns:

- fused best match
- fused ranking
- source weights
- agreement score
- fusion rationale

## Active Document Taxonomy

The runtime taxonomy currently contains 11 consolidated document subcategories:

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

The underlying consolidation rationale is documented in:

- [data_model.subcategories_document_consolidated.json](../data_model/data_model.subcategories_document_consolidated.json)

## Explainability Outputs

The API response includes both direct and contrastive explanation layers.

Candidate-level fields include:

- `features_found`
- `feature_details`
- `rationale`
- `contrastive_rationale`

`contrastive_rationale` is generated in [app.py](../app.py) by comparing the winner with nearby alternatives using the same criteria metadata from [subcategories.py](../docint/rubrics/subcategories.py).

The `/subcategories` endpoint also exposes criteria metadata so that documentation and UIs can stay aligned with runtime definitions.

## Current Architectural Boundaries

### What Is Implemented

- document-family, tabular, image, audio, and video upload and classification (`pdf`, `txt`, `docx`, `pptx`, `csv`, `tsv`, `xlsx`, `jpg`, `jpeg`, `png`, `mp3`, `wav`, `m4a`, `mp4`, `avi`, `mov`, `wmv`, `mpeg`, `mpg`, `mkv`, `flv`, `webm`, `3gp`, `mts`, `m2ts`, `vob`, `rmvb`)
- agriculture-first early reject
- heuristic scoring with measurable signals
- criteria-backed contrastive explanations
- text LLM allowed by default for agriculture-related documents, datasets, audio, and transcript-rich videos
- selective sampled-page vision classification for PDFs, vision-first classification for images, and sampled-frame classification for videos
- fusion across sources

### What Is Documented But Not Yet Enforced In Runtime

- category auto-selection by KO mode
- category filtering for file-based versus URL-based KOs
- `Software Application` availability only for URL-based KOs
- broader non-document category handling beyond the current `Dataset`, `Image`, `Audio`, and `Video` branches

Those rules are part of the taxonomy and ingestion design work, not the current `/classify` implementation.

## Deployment Paths

### Standalone

- install Python dependencies from [requirements.txt](../requirements.txt)
- install `poppler-utils`, `tesseract-ocr`, and required language packs
- install `ffmpeg` if `Video` uploads should support frame sampling and audio extraction
- configure `.env`
- run via [start_server.sh](../start_server.sh), [start_server.py](../start_server.py), or `uvicorn`

## Operational Readiness

The `/health` endpoint now exposes branch readiness for media processing under `models`:

- `audio_transcription`
  Shows whether the transcript backend is enabled and configured for `Audio` and transcript-first `Video` handling.
- `video_tooling`
  Shows whether `ffmpeg` and `ffprobe` are available for sampled-frame extraction and audio extraction from video.

### Docker

- build and run with [Dockerfile](../Dockerfile)
- local Compose path available in [docker-compose.yml](../docker-compose.yml)

## File Map

- [app.py](../app.py): API entry point and response shaping
- [subcategories.py](../docint/rubrics/subcategories.py): criteria source of truth
- [subcategory_scorer.py](../docint/rubrics/subcategory_scorer.py): heuristic scoring engine
- [subcategory_classify.py](../docint/llm/subcategory_classify.py): text and vision LLM integration
- [data_model](../data_model): taxonomy consolidation and category policy documents
