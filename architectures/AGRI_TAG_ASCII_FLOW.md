# Agri-Tag ASCII Flow Diagram

This document shows how Agri-Tag handles files, URLs, text, images, audio, and video.
It uses plain text diagrams only, so it is readable in any editor.

## 1. Big Picture

```text
Client / caller
     |
     |  POST /classify              upload a file
     |  POST /classify-url          submit a public URL
     |  POST /classify-text         submit raw text
     |  POST /classify-media-llm    audio/video shortcut
     v
+-------------------------------+
| FastAPI app.py                 |
| - validates request            |
| - applies auth when enabled    |
| - chooses provider             |
| - routes to the right pipeline |
+-------------------------------+
     |
     v
+--------------------------------------------------------------+
| Input-specific preparation                                    |
| - file: save to temp file, validate limits, inspect type      |
| - URL: validate URL, scan target, extract text with PageSense |
| - text: validate word cap, treat as document text             |
| - media shortcut: transcribe audio/video first                |
+--------------------------------------------------------------+
     |
     v
+--------------------------------------------------------------+
| Classification pipeline                                       |
| - category detection                                          |
| - text extraction / OCR / transcription                       |
| - agriculture relevance gate                                 |
| - KO eligibility gate                                         |
| - category-specific subtype scoring                           |
| - optional LLM / vision calls                                 |
| - fusion of evidence                                          |
+--------------------------------------------------------------+
     |
     v
+--------------------------------------------------------------+
| Response                                                     |
| - category_used                                               |
| - agriculture_relevance                                      |
| - best_match and all_candidates                              |
| - topics                                                     |
| - intended_purposes                                          |
| - processing_info and timings                                |
+--------------------------------------------------------------+
```

## 2. Endpoint Router

```text
Request arrives
     |
     v
+-----------------------------+
| Which endpoint was called?  |
+-----------------------------+
     |
     +-------------------+--------------------+--------------------+----------------------+
     |                   |                    |                    |                      |
     v                   v                    v                    v                      v
+------------+    +---------------+    +---------------+    +------------------+    +-------------+
| /classify  |    | /classify-url |    | /classify-text|    | /classify-media- |    | GET routes  |
| file input |    | URL input     |    | raw text      |    | llm              |    | health/docs |
+------------+    +---------------+    +---------------+    +------------------+    +-------------+
     |                   |                    |                    |                      |
     v                   v                    v                    v                      v
Full file          Text from URL       Text document       Transcript-first       No asset
pipeline           pipeline            pipeline            media pipeline         classification
```

## 3. Uploaded File Flow: `/classify`

```text
Uploaded file
     |
     v
+-----------------------------+
| Check extension             |
| Allowed:                    |
| pdf, doc, docx, ppt, pptx   |
| txt, csv, tsv, xls, xlsx    |
| json, jpg, jpeg, png        |
| mp3, wav, m4a               |
| common video formats        |
| zip, tar, rar archives      |
+-----------------------------+
     |
     v
+-----------------------------+
| Save upload to temp file    |
| in 1 MB chunks              |
| reject if over 1 GiB        |
+-----------------------------+
     |
     v
+-----------------------------+
| Apply AI Uploader limits    |
| - PDF <= 100 pages          |
| - Office <= 100 pages       |
| - text <= 5 MB / 500k chars |
| - image side <= 10000 px    |
| - media <= 3000 seconds     |
+-----------------------------+
     |
     v
+-----------------------------+
| Optional Agri Gate scan     |
| if use_agri_gate=true       |
+-----------------------------+
     |
     v
+-----------------------------+
| Is this an archive?         |
+-----------------------------+
     |
     +------------------------------+
     |                              |
     v                              v
No archive                    Archive file
     |                              |
     |                              v
     |                    +--------------------------+
     |                    | Extract supported files  |
     |                    | - reject unsafe paths    |
     |                    | - reject blocked scripts |
     |                    | - reject nested archives |
     |                    | - enforce archive caps   |
     |                    +--------------------------+
     |                              |
     |                              v
     |                    Validate each extracted file
     |                              |
     +---------------+--------------+
                     |
                     v
             classify_document()
```

## 4. Category Detection And Preparation

```text
classify_document()
     |
     v
+-------------------------------+
| ingest_asset()                |
| Converts input into one shape |
| called IngestedAsset          |
+-------------------------------+
     |
     v
+-------------------------------+
| IngestedAsset contains:       |
| - asset_type                  |
| - filename                    |
| - extracted text              |
| - lines                       |
| - units and unit_label        |
| - mime_type                   |
| - OCR support flag            |
| - visual candidate flag       |
| - metadata                    |
+-------------------------------+
     |
     v
+-------------------------------+
| infer_file_category()         |
| Decides the high-level type:  |
| Document, Dataset, Image,     |
| Audio, Video, or Software     |
+-------------------------------+
     |
     v
+-----------------------------------------+
| Prepare usable text                     |
|                                         |
| Document: extract PDF/DOCX/PPTX text    |
| Dataset: preview rows / JSON records    |
| Image: OCR if text is weak              |
| Audio: transcribe audio                 |
| Video: extract audio, transcribe it     |
+-----------------------------------------+
```

## 5. Agriculture Relevance Gate

```text
Prepared text
     |
     v
+------------------------------------------------+
| Agriculture relevance pipeline                  |
| assess_agriculture_relevance_staged()           |
+------------------------------------------------+
     |
     +------------------------+------------------------+--------------------------+
     |                        |                        |                          |
     v                        v                        v                          v
+------------------+   +------------------+   +----------------------+   +----------------+
| Stage 1          |   | Stage 2          |   | Stage 3              |   | Cache          |
| multilingual     |   | embedding model  |   | optional text LLM    |   | avoids repeat  |
| lexicon/rules    |   | similarity       |   | fallback             |   | work           |
+------------------+   +------------------+   +----------------------+   +----------------+
     |                        |                        |
     +------------------------+------------------------+
                              |
                              v
                 +-----------------------------+
                 | is_agriculture_related?     |
                 +-----------------------------+
                              |
             +----------------+----------------+
             |                                 |
             v                                 v
    false and require_agriculture=true         true
             |                                 |
             v                                 v
    Return early with skip_reason       Continue classification
```

Important detail:

```text
Image and video can also use vision models.
If the vision model returns agriculture relevance,
it can override the text/OCR/transcript-based agriculture result.
```

## 6. KO Eligibility Gate

```text
Agriculture-related asset
     |
     v
+----------------------------------------+
| KO eligibility gate                    |
| _assess_ko_eligibility()               |
+----------------------------------------+
     |
     v
+----------------------------------------+
| Rejects things that may mention        |
| agriculture but are not useful KOs:    |
| - job vacancies                        |
| - tenders                              |
| - event announcements                  |
| - calls for applications               |
+----------------------------------------+
     |
     +-----------------------------+
     |                             |
     v                             v
Not eligible                 Eligible
     |                             |
     v                             v
Return early                 Continue to subtype scoring
```

## 7. Document Flow

```text
Document file
     |
     v
+------------------------------------+
| Text extraction                    |
| - PDF via PyMuPDF                  |
| - DOC/DOCX via document parser     |
| - PPT/PPTX via slide text parser   |
| - TXT as plain text                |
+------------------------------------+
     |
     v
+------------------------------------+
| If text quality is poor            |
| and OCR is supported:              |
| - custom provider: Tesseract OCR   |
| - mistral provider: Mistral OCR    |
+------------------------------------+
     |
     v
+------------------------------------+
| Agriculture relevance gate         |
+------------------------------------+
     |
     v
+------------------------------------+
| Document subtype scoring           |
| - deterministic heuristics         |
| - optional text LLM                |
| - optional vision LLM for PDFs     |
| - fusion if multiple sources exist |
+------------------------------------+
     |
     v
Document classification response
```

## 8. Dataset Flow

```text
Dataset file
     |
     v
+----------------------------------------+
| Preview extraction                     |
| - CSV/TSV: columns + preview rows      |
| - XLS/XLSX: sheet names + preview rows |
| - JSON: flattened preview records      |
+----------------------------------------+
     |
     v
+----------------------------------------+
| Agriculture relevance gate             |
| Uses extracted dataset text preview    |
+----------------------------------------+
     |
     v
+----------------------------------------+
| Dataset subtype scoring                |
| - schema/content signals               |
| - optional text LLM                    |
| - fusion if needed                     |
+----------------------------------------+
     |
     v
Dataset classification response
```

## 9. Image Flow

```text
Image file
     |
     v
+--------------------------------------+
| Image ingest                         |
| No text at first                     |
| OCR supported = yes                  |
+--------------------------------------+
     |
     v
+--------------------------------------+
| OCR if needed                        |
| - custom provider: Tesseract OCR     |
| - mistral provider: Mistral OCR      |
+--------------------------------------+
     |
     v
+--------------------------------------+
| Agriculture relevance from OCR text  |
+--------------------------------------+
     |
     v
+--------------------------------------+
| Optional image vision model          |
| Can detect:                          |
| - image subtype                      |
| - agriculture relevance              |
| - agriculture confidence             |
+--------------------------------------+
     |
     v
+--------------------------------------+
| Image subtype scoring                |
| - image heuristics                   |
| - optional vision LLM                |
| - fusion if vision is available      |
+--------------------------------------+
     |
     v
Image classification response
```

## 10. Audio Flow

```text
Audio file
     |
     v
+-----------------------------------------+
| Transcription                           |
+-----------------------------------------+
     |
     +------------------------------+-------------------------------+
     |                              |
     v                              v
provider=custom                     provider=mistral
     |                              |
     v                              v
+-----------------------------+  +------------------------------+
| External media transcriber  |  | Mistral Voxtral              |
| POST /transcribe/upload     |  | via Mistral SDK              |
| MEDIA_TRANSCRIBER_BASE_URL  |  | MISTRAL_AUDIO_MODEL          |
+-----------------------------+  +------------------------------+
     |                              |
     +---------------+--------------+
                     |
                     v
              Transcript text
                     |
                     v
+-----------------------------------------+
| Agriculture relevance from transcript   |
+-----------------------------------------+
                     |
                     v
+-----------------------------------------+
| Audio subtype scoring                   |
| - transcript heuristics                 |
| - optional audio text LLM               |
| - fusion if text LLM is used            |
+-----------------------------------------+
                     |
                     v
Audio classification response
```

If transcription fails:

```text
No usable transcript
     |
     v
agriculture_relevance = false / unavailable
     |
     v
Return early with skip_reason
```

## 11. Video Flow

```text
Video file
     |
     v
+-----------------------------------------+
| Local FFmpeg checks                     |
| - get duration with ffprobe             |
| - check if audio stream exists          |
+-----------------------------------------+
     |
     v
+-----------------------------------------+
| Extract audio track with FFmpeg         |
| Output: temporary .mp3                  |
+-----------------------------------------+
     |
     v
+-----------------------------------------+
| Transcribe extracted audio              |
| - custom: MEDIA_TRANSCRIBER_BASE_URL    |
| - mistral: Mistral Voxtral              |
+-----------------------------------------+
     |
     v
Transcript text
     |
     v
+-----------------------------------------+
| Agriculture relevance from transcript   |
+-----------------------------------------+
     |
     v
+-----------------------------------------+
| Optional frame sampling                 |
| - sample representative frames          |
| - max 8 frames in current sampler       |
+-----------------------------------------+
     |
     v
+-----------------------------------------+
| Optional video vision model             |
| Can detect:                             |
| - video subtype                         |
| - agriculture relevance                 |
| - agriculture confidence                |
+-----------------------------------------+
     |
     v
+-----------------------------------------+
| Video subtype scoring                   |
| - transcript heuristics                 |
| - optional text LLM                     |
| - optional vision LLM on sampled frames |
| - fusion if multiple sources exist      |
+-----------------------------------------+
     |
     v
Video classification response
```

## 12. URL Flow: `/classify-url`

```text
Submitted URL
     |
     v
+-----------------------------------+
| Validate public HTTP/HTTPS URL    |
| Reject local/private/internal URLs |
+-----------------------------------+
     |
     v
+-----------------------------------+
| Optional Agri Gate URL scan       |
+-----------------------------------+
     |
     v
+-----------------------------------+
| Block risky URL targets           |
| - executable files                |
| - installer files                 |
| - script payloads                 |
| - direct archive targets          |
+-----------------------------------+
     |
     v
+-----------------------------------+
| PageSense extraction              |
| Converts URL content to text      |
+-----------------------------------+
     |
     v
+-----------------------------------+
| URL text classification           |
| - category inference              |
| - agriculture relevance gate      |
| - KO eligibility gate             |
| - heuristics                      |
| - optional text LLM               |
+-----------------------------------+
     |
     v
URL classification response
```

## 13. Raw Text Flow: `/classify-text`

```text
Raw text JSON body
     |
     v
+--------------------------------------+
| Validate text                         |
| - must not be empty                   |
| - max around 5000 words               |
+--------------------------------------+
     |
     v
+--------------------------------------+
| Treat as Document text                |
+--------------------------------------+
     |
     v
+--------------------------------------+
| Agriculture relevance gate            |
+--------------------------------------+
     |
     v
+--------------------------------------+
| Document-style subtype scoring        |
| - heuristics                          |
| - optional text LLM                   |
| - no OCR                              |
| - no vision                           |
+--------------------------------------+
     |
     v
Text classification response
```

## 14. Media Shortcut Flow: `/classify-media-llm`

```text
Audio/video file
     |
     v
+-------------------------------------+
| Validate shared upload limits       |
+-------------------------------------+
     |
     v
+-------------------------------------+
| Transcribe media                    |
| - audio: send audio to transcriber  |
| - video: extract audio, then send   |
+-------------------------------------+
     |
     v
+-------------------------------------+
| Text LLM subtype classification     |
| No full agriculture response object |
| No heuristics fusion                |
| No vision                           |
+-------------------------------------+
     |
     v
MediaLlmOnlyResponse
```

Use this endpoint only when you want a transcript-first media subtype result.
Use `/classify` when you want the full agriculture relevance and fusion pipeline.

## 15. Provider Selection

```text
provider query parameter
     |
     v
+-----------------------------+
| provider=custom             |
+-----------------------------+
     |
     +--> Text LLM: self-hosted OpenAI-compatible model
     +--> Vision LLM: self-hosted OpenAI-compatible model
     +--> OCR: Tesseract
     +--> Audio/video transcription:
          MEDIA_TRANSCRIBER_BASE_URL /transcribe/upload


provider query parameter
     |
     v
+-----------------------------+
| provider=mistral            |
+-----------------------------+
     |
     +--> Text LLM: Mistral OpenAI-compatible endpoint
     +--> Vision LLM: Mistral OpenAI-compatible endpoint
     +--> OCR: Mistral OCR
     +--> Audio/video transcription: Mistral Voxtral
```

## 16. External Services

```text
Agri-Tag
   |
   +--> Agri Gate
   |    Security scan for files and URLs when use_agri_gate=true
   |
   +--> PageSense
   |    Extracts readable text from public URLs
   |
   +--> Media Transcriber
   |    Custom provider audio/video transcription
   |    POST {MEDIA_TRANSCRIBER_BASE_URL}/transcribe/upload
   |
   +--> Mistral
   |    Used only when provider=mistral
   |    Text, vision, OCR, and Voxtral transcription
   |
   +--> Self-hosted LLM endpoints
        Used when provider=custom and model URLs are configured
```

## 17. Important Limits

```text
Shared upload limits aligned with AI Uploader
     |
     +--> Any uploaded file: max 1 GiB
     +--> PDF: max 100 pages
     +--> Office document: max 100 converted pages/slides
     +--> TXT/CSV/TSV/JSON: max 5 MB raw or 500000 chars
     +--> Image: max 10000 px width or height
     +--> Audio/video: max 3000 seconds

Agri-Tag-specific archive limits
     |
     +--> max files in archive: 100
     +--> max extracted size: 100 MB
     +--> max supported inner files classified synchronously: 10
```

## 18. What The Final Response Means

```text
ClassificationResponse
     |
     +--> category_used
     |    The high-level type Agri-Tag used.
     |
     +--> agriculture_relevance
     |    Whether the asset appears agriculture-related.
     |
     +--> best_match
     |    The best subtype/subcategory candidate.
     |
     +--> all_candidates
     |    Usually one candidate, sometimes two if close.
     |
     +--> topics
     |    Agriculture topics detected from the text.
     |
     +--> intended_purposes
     |    What the asset is probably meant for.
     |
     +--> processing_info
          Routing decisions, timings, model use, gate results.
```

