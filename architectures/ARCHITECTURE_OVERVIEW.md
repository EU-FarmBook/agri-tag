================================================================================
                    KO CLASSIFIER — HIGH-LEVEL ARCHITECTURE
================================================================================

                                     CLIENT
                                       |
                                       |  POST /classify      (file upload)
                                       |  POST /classify-url  (public URL)
                                       |  GET  /health        (unauthenticated)
                                       |  GET  /subcategories
                                       v
                            +---------------------+
                            |   FastAPI (app.py)  |
                            +---------------------+
                                       |
                    +------------------+------------------+
                    |                                     |
                    v                                     v
        +--------------------+              +--------------------+
        | [File Upload Path] |              |      [URL Path]    |
        +--------------------+              +--------------------+
                    |                                     |
                    v                                     v
         +--------------------+              +--------------------+
         | Optional Agri Gate |              | Optional Agri Gate |
         +--------------------+              +--------------------+
                    |                                     |
                    v                                     v
         +--------------------+              +--------------------+
         |  Basic Auth Check  |              |  Basic Auth Check  |
         +--------------------+              +--------------------+
                    |                                     |
                    v                                     v
         +--------------------+              +--------------------+
         | Ingestion Dispatcher |            |  PageSense Extract |
         |  (pdf/docx/pptx/     |            |  (raw text + cache)|
         |   csv/xlsx/image/    |            +--------------------+
         |   audio/video)       |                      |
         +--------------------+                         v
                    |                          +--------------------+
                    v                          | URL Deny-List      |
         +--------------------+               +--------------------+
         | OCR Fallback       |                         |
         | (PDF/Image only)   |                         v
         +--------------------+               +--------------------+
                    |                          | Category Inference |
                    v                          | (Document/Dataset/ |
         +--------------------+               |  Software App)     |
         | Category Router    |               +--------------------+
         | (Document/Dataset/ |                         |
         |  Image/Audio/Video)|                         |
         +--------------------+                         |
                    |                                     |
                    +------------------+------------------+
                                       |
                                       v
                    +-------------------------------------+
                    |      Agriculture Relevance Gate     |
                    |  Stage 1: Multilingual Lexicon      |
                    |  Stage 2: Embedding (e5-small)      |
                    |  Stage 3: Text LLM Fallback         |
                    +-------------------------------------+
                                       |
                    +------------------+------------------+
                    |                                     |
            [require_agriculture=true]           [URL Path Only]
            [non-agriculture]                    +------------------+
                    |                            | KO-Eligibility   |
                    v                            | Gate             |
         +--------------------+                  | (heuristics +    |
         | RETURN EARLY       |                  |  LLM fallback)   |
         | skip_reason set    |                  +------------------+
         +--------------------+                            |
                                                           |
                    +--------------------------------------+
                    |
                    v
    +-------------------------------------------------------------+
    |                    CATEGORY-SPECIFIC SCORING                  |
    +---------------+---------------+---------------+---------------+
                    |               |               |               |
                    v               v               v               v
            +-----------+   +-----------+   +-----------+   +-----------+
            | Document  |   | Dataset   |   |  Image    |   |  Audio    |
            +-----------+   +-----------+   +-----------+   +-----------+
                  |               |               |               |
                  v               v               v               v
         +--------------+  +--------------+  +--------------+  +--------------+
         | 27 Heuristic |  | Schema/Content|  | Vision LLM   |  | Transcription|
         | Signals      |  | Signals       |  | (primary)    |  | (optional)   |
         +--------------+  +--------------+  +--------------+  +--------------+
                  |               |               |               |
                  v               v               v               v
         +--------------+  +--------------+  +--------------+  +--------------+
         | Text LLM     |  | Text LLM     |  | OCR Heuristics|  | Heuristics   |
         | (optional)   |  | (optional)   |  | (fallback)   |  | + Text LLM   |
         +--------------+  +--------------+  +--------------+  +--------------+
                  |               |               |               |
                  +---------------+---------------+---------------+
                                  |
                                  v
                    +-----------------------------+
                    |       Video Branch          |
                    |  (multimodal — parallel)    |
                    |  Frame Sampling + Audio Ext |
                    |  -> Heuristics + Text LLM   |
                    |  + Vision LLM (frames)      |
                    +-----------------------------+
                                  |
                                  v
                    +-----------------------------+
                    |      INTELLIGENT FUSION     |
                    |   weighted / adaptive /     |
                    |   agreement / cascade       |
                    +-----------------------------+
                                  |
                                  v
                    +-----------------------------+
                    |        RESPONSE SHAPER      |
                    |  best_match + all_candidates|
                    |  feature_details + rationale|
                    |  contrastive_rationale      |
                    |  processing_info (timings,  |
                    |   routing, language, gate)  |
                    +-----------------------------+
                                  |
                                  v
                               [CLIENT]

================================================================================
                         DATA & CONFIGURATION LAYERS
================================================================================

   Runtime Taxonomy                    Agriculture Resources
   -----------------                   ---------------------
   [subcategories.py]                  [agriculture_lexicon.json]
        |                              [generated/centroids/]
        v                              [generated/anchor_texts/]
   [dataset_scorer.py]                      |
   [image_scorer.py]                        v
   [audio_scorer.py]                 [agriculture_pipeline.py]
   [video_scorer.py]
        |
        v
   [intelligent_fusion.py]

   External Integrations
   ---------------------
   [agrigate.py]  ---->  Agri Gate API
   [pagesense.py] ---->  PageSense Extract API
   [transcribe.py] --->  Whisper Transcription Backend
   [subcategory_classify.py] --> Text LLM (Qwen) + Vision LLM (InternVL)

================================================================================
                               LEGEND
================================================================================

   []  = Component / Module
   --> = Data flow / Call direction
   +   = Parallel branches

================================================================================
