# app.py
"""
Agri-Tag API - FastAPI application for KO category and subtype classification.

This API provides evidence-based KO classification with optional LLM enhancement.
It supports text-based, vision-based, and category-specific hybrid routing with intelligent
fusion of results.

Run with: uvicorn app:app --reload --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import os
import shutil
import tempfile
import re
import time
import hashlib
import sys
import threading
from enum import Enum
from typing import Any, Dict, List, Optional
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

# Load .env BEFORE importing any docint module: several of them (mistral_provider,
# agriculture/topics/purposes pipelines) read configuration via os.getenv at import
# time, so the environment must be populated first. Previously load_dotenv() ran
# after these imports, which left MISTRAL_API_KEY unset -> provider=mistral 503'd.
load_dotenv()

from fastapi import FastAPI, UploadFile, File, Query, HTTPException, Depends, Request
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.responses import JSONResponse
from starlette.staticfiles import StaticFiles
from pydantic import BaseModel, Field
import secrets

try:
    from langdetect import DetectorFactory, detect_langs

    DetectorFactory.seed = 0
    LANGDETECT_AVAILABLE = True
except Exception:
    detect_langs = None
    LANGDETECT_AVAILABLE = False

from docint.audio.transcribe import transcribe_audio_file
from docint.providers.mistral_provider import (
    MISTRAL_CONFIGURED,
    MISTRAL_OPENAI_BASE_URL,
    MISTRAL_API_KEY,
    MISTRAL_TEXT_MODEL,
    MISTRAL_VISION_MODEL,
    MISTRAL_OCR_MODEL,
    MISTRAL_AUDIO_MODEL,
    mistral_ocr_pdf,
    mistral_ocr_image,
    mistral_transcribe,
)
from docint.security.upload_security import (
    get_archive_suffix,
    get_blocked_suffix,
    get_archive_url_suffix,
    get_blocked_url_suffix,
)
from docint.extract.quality import text_quality_ok
from docint.extract.ocr import ocr_pdf, ocr_image
from docint.category.infer import infer_category, infer_file_category, infer_url_category
from docint.topics.infer import infer_topics
from docint.purposes.infer import infer_intended_purposes
from docint.ingest.dispatcher import ingest_asset, SUPPORTED_DOCUMENT_EXTENSIONS
from docint.ingest.archive import ARCHIVE_UPLOAD_EXTENSIONS, extract_supported_archive
from docint.video.extract import media_duration_seconds, sample_video_frames, transcribe_video_audio
from docint.ingest.ai_uploader_criteria import (
    AUDIO_EXTS,
    MAX_BYTES,
    MEDIA_MAX_DURATION_SECONDS,
    VIDEO_EXTS,
    CriteriaViolation,
    validate_asset_against_ai_uploader_criteria,
)
from docint.integrations.agrigate import scan_file as agrigate_scan_file, scan_url as agrigate_scan_url
from docint.integrations.pagesense import extract_url_text
from docint.features.sections import count_sections
from docint.features.citations import detect_citations
from docint.features.keywords import count_keywords
from docint.domain.agriculture_pipeline import assess_agriculture_relevance_staged
from docint.domain.ko_eligibility import assess_ko_eligibility
from docint.rubrics.imrad import score_imrad
from docint.rubrics.citations import score_citations
from docint.rubrics.deliverable import score_deliverable
from docint.rubrics.pedagogy import score_pedagogy
from docint.rubrics.procedure import score_procedure
from docint.rubrics.subcategory_scorer import score_subcategories, SubcategoryScore
from docint.rubrics.subcategories import SUBCATEGORIES, get_subcategory_criteria
from docint.subtypes.unified import (
    LEGACY_TO_UNIFIED,
    load_unified_subtypes,
    map_probs_to_unified,
    score_unified_subcategories,
)
from docint.fusion.intelligent_fusion import (
    intelligent_fusion, 
    SourceResult, 
    FusionStrategy,
    convert_to_source_result
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
VISUALISATIONS_DIR = os.path.join(BASE_DIR, "visualisations")

SUPPORTED_FILE_TYPES_BY_CATEGORY: Dict[str, List[str]] = {
    "Document": [".pdf", ".txt", ".doc", ".docx", ".ppt", ".pptx"],
    "Dataset": [".csv", ".tsv", ".xls", ".xlsx", ".json"],
    "Image": [".jpg", ".jpeg", ".png"],
    "Audio": [".mp3", ".wav", ".m4a"],
    "Video": [".mp4", ".avi", ".mov", ".wmv", ".mpeg", ".mpg", ".mkv", ".flv", ".webm", ".3gp", ".mts", ".m2ts", ".vob", ".rmvb"],
    "Software Application": [],
    "Archive Bundle": [".zip", ".tar", ".rar"],
}

URL_SUFFIX_HINTS_BY_CATEGORY: Dict[str, List[str]] = {
    "Document": [".pdf", ".doc", ".docx", ".ppt", ".pptx", ".txt"],
    "Dataset": [".csv", ".tsv", ".xlsx", ".xls", ".json"],
}

# =============================================================================
# CONFIGURATION
# =============================================================================

# Text LLM (Qwen) Configuration
LLM_BASE_URL = os.getenv("DOCINT_LLM_BASE_URL", "").rstrip("/")
if LLM_BASE_URL and not LLM_BASE_URL.endswith("/v1"):
    LLM_BASE_URL = f"{LLM_BASE_URL}/v1"
LLM_MODEL = os.getenv("DOCINT_LLM_MODEL", "qwen3-30b-a3b-awq")
LLM_API_KEY = os.getenv("DOCINT_LLM_API_KEY", "").strip()

# Vision LLM (InternVL) Configuration
VISION_LLM_BASE_URL = os.getenv("VISION_LLM_BASE_URL", "").rstrip("/")
if VISION_LLM_BASE_URL and not VISION_LLM_BASE_URL.endswith("/v1"):
    VISION_LLM_BASE_URL = f"{VISION_LLM_BASE_URL}/v1"
VISION_LLM_MODEL = os.getenv("VISION_LLM_MODEL", "internvl3-5-14b")
VISION_LLM_API_KEY = os.getenv("VISION_LLM_API_KEY", LLM_API_KEY).strip()

LLM_CONFIGURED = bool(LLM_BASE_URL and LLM_MODEL)

MEDIA_TRANSCRIBER_BASE_URL = os.getenv("MEDIA_TRANSCRIBER_BASE_URL", "").rstrip("/")
MEDIA_TRANSCRIBER_WHISPER_MODEL = os.getenv("MEDIA_TRANSCRIBER_WHISPER_MODEL", "").strip()
MEDIA_TRANSCRIBER_API_KEY = os.getenv("MEDIA_TRANSCRIBER_API_KEY", "").strip()
MEDIA_TRANSCRIBER_MODE = os.getenv("MEDIA_TRANSCRIBER_MODE", "auto").strip() or "auto"
MEDIA_TRANSCRIBER_BASIC_USER = os.getenv("MEDIA_TRANSCRIBER_BASIC_USER", "").strip()
MEDIA_TRANSCRIBER_BASIC_PASS = os.getenv("MEDIA_TRANSCRIBER_BASIC_PASS", "").strip()
MEDIA_TRANSCRIBER_ENABLED = os.getenv("MEDIA_TRANSCRIBER_ENABLED", "false").lower() == "true"
AUDIO_TRANSCRIPTION_CONFIGURED = bool(
    MEDIA_TRANSCRIBER_ENABLED and MEDIA_TRANSCRIBER_BASE_URL and MEDIA_TRANSCRIBER_WHISPER_MODEL
)

FFMPEG_AVAILABLE = bool(shutil.which("ffmpeg"))
FFPROBE_AVAILABLE = bool(shutil.which("ffprobe"))
MAX_AUDIO_DURATION_SEC = MEDIA_MAX_DURATION_SECONDS
MAX_VIDEO_DURATION_SEC = MEDIA_MAX_DURATION_SECONDS
MAX_AUDIO_UPLOAD_SIZE_MB = MAX_BYTES // (1024 * 1024)
MAX_VIDEO_UPLOAD_SIZE_MB = MAX_BYTES // (1024 * 1024)
MAX_OTHER_UPLOAD_SIZE_MB = MAX_BYTES // (1024 * 1024)
MAX_REQUEST_BODY_MB = int(os.getenv("MAX_REQUEST_BODY_MB", str(MAX_BYTES // (1024 * 1024))))
MAX_DOCUMENT_UNITS = int(os.getenv("MAX_DOCUMENT_UNITS", "100"))
# Raw-text endpoint cap: ~10 A4 pages * ~500 words = 5000 words.
MAX_TEXT_INPUT_WORDS = int(os.getenv("MAX_TEXT_INPUT_WORDS", "5000"))
VISION_RENDER_DPI = int(os.getenv("VISION_RENDER_DPI", "150"))
# Hard cap on page-images sent to the vision model in ONE request. MUST match the
# vLLM server's --limit-mm-per-prompt image:N (default 8). The effective per-request
# vision_max_pages is clamped to this, so no caller can exceed the VLM's limit and
# trigger a (silently caught) rejected vision call.
VISION_MAX_PAGES_CAP = int(os.getenv("VISION_MAX_PAGES_CAP", "8"))
# Sampling temperature for the classification LLM calls (text + vision subtype).
# Default 0 = deterministic/reproducible (no run-to-run flip-flopping on the same input).
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0"))
# Surface at most 2 subcategory candidates (always the best; a second only when it
# is a genuinely close contender within SUBCATEGORY_SECOND_GAP probability).
SUBCATEGORY_MAX_CANDIDATES = int(os.getenv("SUBCATEGORY_MAX_CANDIDATES", "2"))
SUBCATEGORY_SECOND_GAP = float(os.getenv("SUBCATEGORY_SECOND_GAP", "0.15"))
# EXPERIMENTAL: for ambiguous-agriculture *documents*, replace the separate
# Stage-3 agriculture LLM call + the document subtype LLM call with ONE combined
# call. Off by default; validate agriculture-gate accuracy on an eval set before
# enabling in production.
MERGE_AGRI_SUBCATEGORY_LLM = os.getenv("MERGE_AGRI_SUBCATEGORY_LLM", "false").strip().lower() in {"1", "true", "yes"}
AGRI_GATE_BASE_URL = os.getenv("AGRI_GATE_BASE_URL", "").rstrip("/")
AGRI_GATE_TIMEOUT = float(os.getenv("AGRI_GATE_TIMEOUT", "60"))
AGRI_GATE_URL_STRICT = os.getenv("AGRI_GATE_URL_STRICT", "true").lower() == "true"
AGRI_GATE_FILE_STRICT = os.getenv("AGRI_GATE_FILE_STRICT", "true").lower() == "true"
URL_CONTENT_EXTRACTOR_BASE = os.getenv("URL_CONTENT_EXTRACTOR_BASE", "").rstrip("/")
EXTRACTOR_TIMEOUT = float(os.getenv("EXTRACTOR_TIMEOUT", "60"))
EXTRACTOR_MIN_CHARS = int(os.getenv("EXTRACTOR_MIN_CHARS", "100"))
URL_EXTRACTION_CACHE_TTL_SEC = int(os.getenv("URL_EXTRACTION_CACHE_TTL_SEC", "172800"))
AGRICULTURE_CACHE_TTL_SEC = int(os.getenv("AGRICULTURE_CACHE_TTL_SEC", "172800"))
RUNTIME_CACHE_MAX_ENTRIES = int(os.getenv("RUNTIME_CACHE_MAX_ENTRIES", "256"))
RUNTIME_CACHE_MAX_BYTES = int(os.getenv("RUNTIME_CACHE_MAX_BYTES", str(64 * 1024 * 1024)))
TEXT_LLM_GAP_THRESHOLD = float(os.getenv("TEXT_LLM_GAP_THRESHOLD", "0.12"))
URL_TEXT_LLM_MAX_CHARS = int(os.getenv("URL_TEXT_LLM_MAX_CHARS", "7000"))
URL_DATASET_LLM_MAX_CHARS = int(os.getenv("URL_DATASET_LLM_MAX_CHARS", "6000"))

# All EU languages for Tesseract OCR
ALL_OCR_LANGS = "bul+ces+dan+deu+ell+eng+est+fin+fra+hrv+hun+ita+lav+lit+mlt+nld+pol+por+ron+slk+slv+spa+swe+gle"
# Default OCR language bundle. The full 24-language set is correct but SLOW
# (Tesseract runs every language -> ~40s/page). Set OCR_DEFAULT_LANGS to a curated
# subset (e.g. "eng+ell+nld+deu+fra") in production, or pass `ocr_lang` per request.
OCR_DEFAULT_LANGS = os.getenv("OCR_DEFAULT_LANGS", ALL_OCR_LANGS).strip() or ALL_OCR_LANGS
# Pre-warm the shared embedding model at startup so the first request isn't the one
# that pays the model download/load cost.
PREWARM_EMBEDDINGS = os.getenv("PREWARM_EMBEDDINGS", "true").strip().lower() in {"1", "true", "yes"}
EMBEDDING_MODEL_NAME = os.getenv("AGRI_EMBEDDING_MODEL", "intfloat/multilingual-e5-small").strip()

# =============================================================================
# BASIC AUTH CONFIGURATION
# =============================================================================

# Initialize HTTPBasic security
security = HTTPBasic()

# Load authorized users from env
AUTH_USERS_STR = os.getenv("DOCINT_AUTH_USERS", "")
AUTH_PASSWORD = os.getenv("DOCINT_AUTH_PASSWORD", "")

# Parse comma-separated usernames
AUTHORIZED_USERS = {}
if AUTH_USERS_STR and AUTH_PASSWORD:
    for username in AUTH_USERS_STR.split(","):
        username = username.strip()
        if username:
            AUTHORIZED_USERS[username] = AUTH_PASSWORD

# Track if auth is enabled
AUTH_ENABLED = bool(AUTHORIZED_USERS)
PAGESENSE_CACHE: Dict[str, tuple[float, Any, int]] = {}
AGRICULTURE_CACHE: Dict[str, tuple[float, Any, int]] = {}

# Supported LLM providers for the classification flow.
#   "custom" -> the self-hosted OpenAI-compatible Qwen/InternVL flow (default)
#   "mistral" -> route chat (text+vision) at Mistral's OpenAI-compatible endpoint,
#                and OCR/transcription through the native Mistral adapters.
# Declared as a str-Enum so FastAPI renders a dropdown for the `provider` query
# parameter in the Swagger UI (/docs) and validates the value automatically.
class ProviderChoice(str, Enum):
    custom = "custom"
    mistral = "mistral"


PROVIDER_CHOICES = tuple(choice.value for choice in ProviderChoice)


def _resolve_llm_config(provider: str):
    """Return provider-aware (text + vision) LLM config.

    The tuple is unpacked into local names that *shadow* the module-level
    ``LLM_*`` / ``VISION_LLM_*`` globals inside a request handler, so the existing
    classification call sites and gating conditions work unchanged for both
    providers. Mistral chat is OpenAI-compatible, so only the endpoint/key/model
    differ here; OCR and transcription are routed separately at their call sites.

    Order: (text_base_url, text_api_key, text_model, text_configured,
            vision_base_url, vision_api_key, vision_model, vision_configured)
    """
    g = globals()
    if provider == "mistral":
        base = MISTRAL_OPENAI_BASE_URL if MISTRAL_CONFIGURED else ""
        return (
            base, MISTRAL_API_KEY, MISTRAL_TEXT_MODEL, MISTRAL_CONFIGURED,
            base, MISTRAL_API_KEY, MISTRAL_VISION_MODEL, MISTRAL_CONFIGURED,
        )
    return (
        g["LLM_BASE_URL"], g["LLM_API_KEY"], g["LLM_MODEL"], g["LLM_CONFIGURED"],
        g["VISION_LLM_BASE_URL"], g["VISION_LLM_API_KEY"], g["VISION_LLM_MODEL"], bool(g["VISION_LLM_BASE_URL"]),
    )


def verify_credentials(credentials: HTTPBasicCredentials = Depends(security)):
    """
    Verify Basic Auth credentials.
    
    Args:
        credentials: HTTP Basic auth credentials
        
    Returns:
        str: The authenticated username
        
    Raises:
        HTTPException: If credentials are invalid
    """
    if not AUTH_ENABLED:
        # No auth configured, allow all
        return "anonymous"
    
    # Check if username exists
    stored_password = AUTHORIZED_USERS.get(credentials.username)
    
    if stored_password is None:
        raise HTTPException(
            status_code=401,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": 'Basic realm="Agri-Tag API"'},
        )
    
    # Verify password using constant-time comparison
    if not secrets.compare_digest(credentials.password, stored_password):
        raise HTTPException(
            status_code=401,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": 'Basic realm="Agri-Tag API"'},
        )
    
    return credentials.username


def require_auth():
    """
    Dependency that enforces authentication.
    Use this when auth should be required even if not globally enabled.
    """
    if not AUTH_ENABLED:
        return "anonymous"
    return Depends(verify_credentials)


# =============================================================================
# PYDANTIC MODELS
# =============================================================================

class FeatureEvidence(BaseModel):
    """Evidence for a single feature detection."""
    feature_name: str
    detected: bool
    score: float
    raw_value: Any
    excerpts: List[str]


class SubcategoryCandidate(BaseModel):
    """A single subcategory candidate with scoring."""
    subcategory_id: str
    subcategory_name: str
    parent_type: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    probability: float = Field(..., ge=0.0, le=1.0)
    evidence_score: float
    max_possible_evidence: float
    features_found: List[str]
    feature_details: Dict[str, FeatureEvidence]
    rationale: str
    contrastive_rationale: Optional[str] = None
    selection_basis: Optional[str] = None
    supporting_sources: Optional[List[str]] = None
    source_confidences: Optional[Dict[str, float]] = None
    source_rationales: Optional[Dict[str, str]] = None
    rank: int = Field(..., description="Rank by confidence (1 = best match)")


class FusionInfo(BaseModel):
    """Information about the fusion process."""
    fused: bool
    strategy: str
    weights: Dict[str, float]
    agreement_score: float
    rationale: str


class AgricultureRelevance(BaseModel):
    """Agriculture domain relevance assessment."""
    is_agriculture_related: bool
    confidence: float = Field(..., ge=0.0, le=1.0)
    score: float = Field(..., ge=0.0, le=1.0)
    method: str
    lexicon_version: str
    matched_terms: List[str]
    matched_buckets: List[str]
    matched_concepts: List[str]
    bucket_scores: Dict[str, float]
    rationale: str
    stages_used: List[str]
    stage_results: List[Dict[str, Any]]


class TopicResult(BaseModel):
    """A single inferred topic with its supporting evidence."""
    topic: str
    score: float = Field(..., ge=0.0, le=1.0)
    lexical_score: float = Field(..., ge=0.0, le=1.0)
    embedding_score: float = Field(..., ge=0.0, le=1.0)
    matched_terms: List[str] = []
    rationale: str = ""


class TopicInference(BaseModel):
    """Multi-label topic assignment (orthogonal to category/subcategory)."""
    topics: List[TopicResult] = []
    method: str
    stages_used: List[str] = []
    signals_version: str
    rationale: str = ""


class IntendedPurposeResult(BaseModel):
    """A single inferred user-intent / intended purpose."""
    key: str
    name: str
    category: str = ""
    score: float = Field(..., ge=0.0, le=1.0)
    rationale: str = ""


class IntendedPurposeInference(BaseModel):
    """Multi-label intended-purpose assignment (orthogonal to category and topics; capped at 3)."""
    purposes: List[IntendedPurposeResult] = []
    method: str = "none"
    stages_used: List[str] = []
    version: str = "intended_purpose_v1"
    rationale: str = ""


class CategoryInference(BaseModel):
    """Inferred high-level category for the uploaded asset."""
    category: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    rationale: str


class ClassificationResponse(BaseModel):
    """Complete classification response."""
    # Primary results
    best_match: Optional[SubcategoryCandidate] = None
    all_candidates: List[SubcategoryCandidate] = []
    
    # Fusion info (if multiple sources used)
    fusion: Optional[FusionInfo] = None
    
    # Individual source results
    heuristics: Optional[SubcategoryCandidate] = None
    vision_llm: Optional[Dict[str, Any]] = None
    text_llm: Optional[Dict[str, Any]] = None
    category_used: str
    category_inference: Optional[CategoryInference] = None
    agriculture_relevance: AgricultureRelevance
    topics: Optional[TopicInference] = None
    intended_purposes: Optional[IntendedPurposeInference] = None
    classification_skipped: bool = False
    skip_reason: Optional[str] = None
    
    # Metadata
    total_candidates: int
    confidence_threshold_met: bool
    document_info: Dict[str, Any]
    processing_info: Dict[str, Any]


class UrlClassificationRequest(BaseModel):
    url: str = Field(..., description="Public http/https URL to classify")


class TextClassificationRequest(BaseModel):
    text: str = Field(..., description="Raw text to classify (up to ~10 A4 pages / 5000 words)")
    filename: Optional[str] = Field(None, description="Optional label for the snippet; informational only")


class MediaLlmTranscriptInfo(BaseModel):
    available: bool
    used: bool
    method: str
    model: Optional[str] = None
    rationale: str
    text_length: int
    preview: str
    full_text: Optional[str] = None


class MediaLlmOnlyResponse(BaseModel):
    category_used: str
    best_match: Optional[SubcategoryCandidate] = None
    all_candidates: List[SubcategoryCandidate] = []
    text_llm: Optional[Dict[str, Any]] = None
    transcript: MediaLlmTranscriptInfo
    total_candidates: int
    confidence_threshold_met: bool
    document_info: Dict[str, Any]
    processing_info: Dict[str, Any]


# =============================================================================
# FASTAPI APP
# =============================================================================

app = FastAPI(
    title="Agri-Tag API",
    description="""
**Agriculture-gated knowledge-object classification** with explainable, category-specific
subtype scoring. Accepts files, public URLs, and raw text — via the self-hosted or
**Mistral** provider (`provider=custom|mistral`).

## Providers (`provider=custom | mistral`)

* **custom** — your self-hosted vLLM models (text + vision), Tesseract (OCR), Whisper (audio)
* **mistral** — mistral-small (text), mistral-medium (vision), mistral-ocr, Voxtral

## File type coverage

| Category | Upload extensions |
| --- | --- |
| **Document** | `.pdf` · `.txt` · `.doc` · `.docx` · `.ppt` · `.pptx` |
| **Dataset** | `.csv` · `.tsv` · `.xls` · `.xlsx` · `.json` |
| **Image** | `.jpg` · `.jpeg` · `.png` |
| **Audio** | `.mp3` · `.wav` · `.m4a` |
| **Video** | `.mp4` · `.avi` · `.mov` · `.wmv` · `.mpeg` · `.mpg` · `.mkv` · `.flv` · `.webm` · `.3gp` · `.mts` · `.m2ts` · `.vob` · `.rmvb` |
| **Archive Bundle** | `.zip` · `.tar` · `.rar` |
| **Software Application** | no upload types — inferred from URL content only |
""",
    version="2.0.0",
    docs_url="/docs",  # Enable docs - they'll be protected by middleware
    redoc_url="/redoc",
)

if os.path.isdir(VISUALISATIONS_DIR):
    app.mount(
        "/visualisations",
        StaticFiles(directory=VISUALISATIONS_DIR, html=False),
        name="visualisations",
    )


@app.on_event("startup")
def _prewarm_embeddings() -> None:
    """Load the shared embedding model in the background at boot.

    Runs in a daemon thread so the server starts serving immediately while the
    model (used by the agriculture, topics, and intended-purpose stages) loads
    once in the background — keeping the first real request off the cold path.
    """
    if not PREWARM_EMBEDDINGS:
        return

    def _warm() -> None:
        try:
            from docint.embedding.shared import prewarm_embedding_model

            prewarm_embedding_model(EMBEDDING_MODEL_NAME, device="cpu")
        except Exception:
            pass

    threading.Thread(target=_warm, daemon=True, name="embedding-prewarm").start()


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def convert_to_candidate(
    score: SubcategoryScore, 
    rank: int,
    total_probability: float
) -> SubcategoryCandidate:
    """Convert SubcategoryScore to API response model."""
    if total_probability > 0:
        probability = score.confidence / total_probability
    else:
        probability = 1.0 / 11
    
    return SubcategoryCandidate(
        subcategory_id=score.subcategory_id,
        subcategory_name=score.subcategory_name,
        parent_type=score.parent_type,
        confidence=round(score.confidence, 4),
        probability=round(probability, 4),
        evidence_score=round(score.evidence_score, 4),
        max_possible_evidence=round(score.max_possible_evidence, 4),
        features_found=score.features_found,
        feature_details={
            k: FeatureEvidence(**v.to_dict())
            for k, v in score.feature_details.items()
        },
        rationale=score.rationale,
        rank=rank
    )


def build_probability_distribution(
    scores: List[SubcategoryScore]
) -> List[SubcategoryCandidate]:
    """Build probability distribution from all subcategory scores."""
    sorted_scores = sorted(scores, key=lambda x: x.confidence, reverse=True)
    total_confidence = sum(s.confidence for s in sorted_scores)
    
    candidates = []
    for rank, score in enumerate(sorted_scores, 1):
        candidate = convert_to_candidate(score, rank, total_confidence)
        candidates.append(candidate)
    
    # Renormalize probabilities
    total_prob = sum(c.probability for c in candidates)
    if total_prob > 0:
        for c in candidates:
            c.probability = round(c.probability / total_prob, 4)
    
    return candidates


def _candidate_missing_features(candidate: SubcategoryCandidate) -> List[str]:
    """List expected features for a candidate that were not detected."""
    missing: List[str] = []
    for feat_name, evidence in candidate.feature_details.items():
        if not evidence.detected:
            missing.append(feat_name)
    return missing


def _criteria_by_name() -> Dict[str, Dict[str, Any]]:
    criteria = {}
    for item in get_subcategory_criteria().values():
        criteria[item["name"]] = item
    return criteria


def _subcategory_key_by_name() -> Dict[str, str]:
    return {subcat.name: key for key, subcat in SUBCATEGORIES.items()}


def _unified_key_by_name() -> Dict[str, str]:
    return {subcat.name: key for key, subcat in load_unified_subtypes().items()}


def _legacy_name_probs_from_candidates(candidates: List[SubcategoryCandidate]) -> Dict[str, float]:
    return {candidate.subcategory_name: candidate.probability for candidate in candidates}


def _build_unified_candidates(
    *,
    category: str,
    text: str,
    filename: str,
    legacy_probs: Dict[str, float],
) -> tuple[List[SubcategoryCandidate], Optional[SubcategoryCandidate]]:
    unified_scores = score_unified_subcategories(
        text=text,
        category=category,
        legacy_probs=legacy_probs,
        filename=filename,
    )
    unified_candidates = build_probability_distribution(unified_scores)
    add_contrastive_rationales(unified_candidates)
    best = unified_candidates[0] if unified_candidates else None
    return unified_candidates, best


def _map_source_result_to_unified(source: Optional[SourceResult]) -> Optional[SourceResult]:
    if not source:
        return None
    mapped_probs = map_probs_to_unified(source.probs)
    mapped_key = LEGACY_TO_UNIFIED.get(source.subcategory_key, source.subcategory_key)
    return SourceResult(
        source_name=source.source_name,
        subcategory_key=mapped_key,
        confidence=source.confidence,
        probs=mapped_probs,
        evidence_score=source.evidence_score,
        rationale=source.rationale,
    )


def _map_llm_payload_to_unified(payload: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not payload or "error" in payload:
        return payload
    mapped_key = LEGACY_TO_UNIFIED.get(str(payload.get("subcategory_key", "")), str(payload.get("subcategory_key", "")))
    name = load_unified_subtypes().get(mapped_key).name if mapped_key in load_unified_subtypes() else payload.get("subcategory_name")
    mapped = dict(payload)
    mapped["subcategory_key"] = mapped_key
    mapped["subcategory_name"] = name
    if isinstance(mapped.get("probs"), dict):
        mapped["probs"] = map_probs_to_unified(mapped["probs"])
    return mapped


def _compact_candidate(candidate: SubcategoryCandidate) -> SubcategoryCandidate:
    compact = candidate.model_copy(deep=True)
    compact.feature_details = {}
    compact.supporting_sources = None
    compact.source_confidences = None
    compact.source_rationales = None
    return compact


def _compact_security_gate(security_gate: Dict[str, Any]) -> Dict[str, Any]:
    compact = dict(security_gate or {})
    details = compact.get("details")
    if isinstance(details, dict):
        compact["details"] = {
            "mime_type": details.get("mime_type"),
            "extension": details.get("extension"),
            "size_bytes": details.get("size_bytes"),
            "scan_duration_ms": details.get("scan_duration_ms"),
            "malware_scan": details.get("malware_scan"),
            "format": (details.get("deep_inspection") or {}).get("format") if isinstance(details.get("deep_inspection"), dict) else None,
            "inspection_status": (details.get("deep_inspection") or {}).get("status") if isinstance(details.get("deep_inspection"), dict) else None,
            "findings_count": len((details.get("deep_inspection") or {}).get("findings", [])) if isinstance(details.get("deep_inspection"), dict) else None,
        }
    return compact


def _compact_model_payload(payload: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not payload:
        return payload
    if "error" in payload:
        return {"error": payload.get("error"), "model": payload.get("model")}
    compact = {
        "subcategory_key": payload.get("subcategory_key"),
        "subcategory_name": payload.get("subcategory_name"),
        "confidence": payload.get("confidence"),
        "model": payload.get("model"),
    }
    if payload.get("agriculture_related") is not None:
        compact["agriculture_related"] = payload.get("agriculture_related")
    if payload.get("agriculture_confidence") is not None:
        compact["agriculture_confidence"] = payload.get("agriculture_confidence")
    return compact


def _compact_agriculture_response(agri: AgricultureRelevance) -> AgricultureRelevance:
    compact = agri.model_copy(deep=True)
    compact.matched_terms = compact.matched_terms[:8]
    compact.matched_buckets = compact.matched_buckets[:5]
    compact.matched_concepts = compact.matched_concepts[:8]
    compact.stage_results = []
    return compact


def _compact_processing_info(processing_info: Dict[str, Any]) -> Dict[str, Any]:
    compact = dict(processing_info or {})
    compact["security_gate"] = _compact_security_gate(compact.get("security_gate", {}))
    return compact


def _media_llm_candidates_from_result(
    llm_res: Any,
    *,
    top_k_candidates: int,
) -> List[SubcategoryCandidate]:
    unified_defs = load_unified_subtypes()
    sorted_probs = sorted(
        ((str(key), float(prob)) for key, prob in (llm_res.probs or {}).items()),
        key=lambda item: item[1],
        reverse=True,
    )

    candidates: List[SubcategoryCandidate] = []
    for rank, (subcat_key, prob) in enumerate(sorted_probs[:top_k_candidates], start=1):
        subtype = unified_defs.get(subcat_key)
        if not subtype:
            continue

        rationale = llm_res.rationale if rank == 1 else f"Transcript-first text LLM ranked {subtype.name} with probability {round(prob, 4)}."
        candidates.append(
            SubcategoryCandidate(
                subcategory_id=subcat_key,
                subcategory_name=subtype.name,
                parent_type="unified",
                confidence=round(prob, 4),
                probability=round(prob, 4),
                evidence_score=round(prob, 4),
                max_possible_evidence=1.0,
                features_found=["text_llm", "media_transcript"],
                feature_details={},
                rationale=rationale,
                selection_basis="text_llm",
                rank=rank,
            )
        )

    return candidates


def _apply_dataset_consensus_boost(
    candidates: List[SubcategoryCandidate],
    *,
    heuristics_best: Optional[SubcategoryCandidate],
    text_source: Optional[SourceResult],
    fusion_info: Optional["FusionInfo"],
) -> None:
    if not candidates or not heuristics_best or not text_source or not fusion_info:
        return

    broad_fallback_ids = {
        "structured_domain_datasets",
        "templates_and_reusable_formats",
        "technical_and_research_content",
    }

    agreed_id = heuristics_best.subcategory_id
    if text_source.subcategory_key != agreed_id:
        return
    if agreed_id in broad_fallback_ids:
        return
    if fusion_info.agreement_score < 0.95:
        return

    top = next((candidate for candidate in candidates if candidate.subcategory_id == agreed_id), None)
    if not top:
        return

    heuristic_conf = float(heuristics_best.confidence)
    text_conf = float(text_source.confidence)
    target = max(top.probability, min(0.92, (0.45 * heuristic_conf) + (0.55 * text_conf) + 0.08))
    if target <= top.probability:
        return

    remaining = 1.0 - target
    others = [candidate for candidate in candidates if candidate.subcategory_id != agreed_id]
    others_total = sum(max(candidate.probability, 0.0) for candidate in others)

    top.probability = round(target, 4)
    top.confidence = round(target, 4)
    top.selection_basis = "fusion"

    if others and others_total > 0:
        scale = remaining / others_total
        for candidate in others:
            adjusted = max(0.0, candidate.probability * scale)
            candidate.probability = round(adjusted, 4)
            candidate.confidence = round(adjusted, 4)
    elif others:
        share = remaining / len(others)
        for candidate in others:
            candidate.probability = round(share, 4)
            candidate.confidence = round(share, 4)

    candidates.sort(key=lambda item: item.probability, reverse=True)
    for idx, candidate in enumerate(candidates, start=1):
        candidate.rank = idx


def _prepare_response(
    result: ClassificationResponse,
    *,
    debug: bool,
) -> ClassificationResponse:
    prepared = result.model_copy(deep=True)
    if debug:
        return prepared

    # Surface 1 subcategory, or at most SUBCATEGORY_MAX_CANDIDATES when the runner-up
    # is a close contender. This (+ SUBCATEGORY_SECOND_GAP) is the single source of
    # truth for how many subcategory candidates are returned.
    surfaced = prepared.all_candidates[:SUBCATEGORY_MAX_CANDIDATES]
    if (
        len(surfaced) >= 2
        and (surfaced[0].probability - surfaced[1].probability) > SUBCATEGORY_SECOND_GAP
    ):
        surfaced = surfaced[:1]
    prepared.all_candidates = [_compact_candidate(c) for c in surfaced]
    prepared.best_match = _compact_candidate(prepared.best_match) if prepared.best_match else None
    prepared.heuristics = _compact_candidate(prepared.heuristics) if prepared.heuristics else None
    prepared.vision_llm = _compact_model_payload(prepared.vision_llm)
    prepared.text_llm = _compact_model_payload(prepared.text_llm)
    prepared.agriculture_relevance = _compact_agriculture_response(prepared.agriculture_relevance)
    prepared.processing_info = _compact_processing_info(prepared.processing_info)
    prepared.total_candidates = len(prepared.all_candidates)
    return prepared


def add_fusion_explanations(
    candidates: List[SubcategoryCandidate],
    fusion_result: Any,
    source_results: Dict[str, Any],
) -> None:
    """Annotate fused candidates with source-aware explanations."""
    if not candidates:
        return

    key_by_name = _subcategory_key_by_name()
    name_by_key = {key: subcat.name for key, subcat in SUBCATEGORIES.items()}

    for cand in candidates:
        cand.selection_basis = "fusion"
        subcat_key = key_by_name.get(cand.subcategory_name, cand.subcategory_name)

        source_confidences: Dict[str, float] = {}
        source_rationales: Dict[str, str] = {}
        supporting_sources: List[str] = []

        for source_name, source in source_results.items():
            if not source:
                continue
            source_confidences[source_name] = round(source.confidence, 4)
            if getattr(source, "rationale", None):
                source_rationales[source_name] = source.rationale

            source_top_key = getattr(source, "subcategory_key", "")
            source_prob = round(source.probs.get(subcat_key, 0.0), 4)
            if source_top_key == subcat_key or source_prob >= 0.2:
                supporting_sources.append(source_name)

        cand.supporting_sources = supporting_sources or None
        cand.source_confidences = source_confidences or None
        cand.source_rationales = source_rationales or None

        if cand.rank != 1:
            continue

        source_summaries: List[str] = []
        for source_name, source in source_results.items():
            if not source:
                continue
            source_top_key = getattr(source, "subcategory_key", "")
            source_top_name = name_by_key.get(source_top_key, source_top_key)
            source_summaries.append(
                f"{source_name} favored {source_top_name} ({source.confidence:.2f})"
            )

        fused_bits = [
            f"Fused result selected {cand.subcategory_name} with probability {cand.probability:.2f}.",
        ]
        if supporting_sources:
            fused_bits.append(
                "Supporting sources: " + ", ".join(supporting_sources) + "."
            )
        if source_summaries:
            fused_bits.append("Source summary: " + "; ".join(source_summaries) + ".")
        if fusion_result and getattr(fusion_result, "rationale", None):
            fused_bits.append(fusion_result.rationale)

        cand.rationale = " ".join(fused_bits)


def add_contrastive_rationales(candidates: List[SubcategoryCandidate], top_k: int = 3) -> None:
    """
    Add a short contrastive explanation for the top candidates so the response
    states not only what won, but what close alternatives were missing.
    """
    if len(candidates) < 2:
        return

    criteria_by_name = _criteria_by_name()
    focus = candidates[:max(2, min(top_k, len(candidates)))]
    winner = focus[0]
    winner_feats = set(winner.features_found)
    winner_criteria = criteria_by_name.get(winner.subcategory_name, {})

    contrasts: List[str] = []
    for alt in focus[1:]:
        alt_feats = set(alt.features_found)
        winner_adv = sorted(winner_feats - alt_feats)
        alt_missing = _candidate_missing_features(alt)
        alt_criteria = criteria_by_name.get(alt.subcategory_name, {})

        pieces: List[str] = []
        if winner_adv:
            pieces.append(f"stronger on {', '.join(winner_adv[:2])}")
        elif winner_criteria.get("positive_signal_hints"):
            pieces.append(
                "better matches "
                + ", ".join(winner_criteria["positive_signal_hints"][:2])
            )
        if alt_missing:
            pieces.append(f"{alt.subcategory_name} missing {', '.join(alt_missing[:2])}")
        elif alt_criteria.get("negative_signal_hints"):
            pieces.append(
                f"{alt.subcategory_name} conflicted with "
                + ", ".join(alt_criteria["negative_signal_hints"][:1])
            )
        if not pieces:
            pieces.append(f"higher overall evidence than {alt.subcategory_name}")

        contrasts.append(f"vs {alt.subcategory_name}: " + "; ".join(pieces))

    if contrasts:
        winner.contrastive_rationale = " | ".join(contrasts)

    # Add a compact note for near-miss alternatives too.
    for idx, cand in enumerate(focus[1:], start=1):
        missing = _candidate_missing_features(cand)
        cand_criteria = criteria_by_name.get(cand.subcategory_name, {})
        if missing:
            cand.contrastive_rationale = (
                f"Near miss behind {winner.subcategory_name}; missing "
                f"{', '.join(missing[:3])}"
            )
        elif cand_criteria.get("negative_signal_hints"):
            cand.contrastive_rationale = (
                f"Near miss behind {winner.subcategory_name}; conflicted with "
                f"{cand_criteria['negative_signal_hints'][0]}"
            )
        else:
            cand.contrastive_rationale = f"Near miss behind {winner.subcategory_name}"


def _top_probability_gap(candidates: List[SubcategoryCandidate]) -> float:
    if len(candidates) < 2:
        return 1.0
    return max(0.0, round(candidates[0].probability - candidates[1].probability, 4))


def _model_keys_disagree(*sources: Optional[SourceResult]) -> bool:
    tops = [s.subcategory_key for s in sources if s and getattr(s, "subcategory_key", "")]
    return len(set(tops)) > 1 if len(tops) >= 2 else False


def _candidate_visual_signals(candidate: Optional[SubcategoryCandidate]) -> bool:
    if not candidate:
        return False
    return bool({"visual_heavy", "slide_indicators"} & set(candidate.features_found))


def _should_run_text_llm(
    *,
    use_text_llm: bool,
    is_agriculture_related: bool,
    best_candidate: Optional[SubcategoryCandidate] = None,
    current_candidates: Optional[List[SubcategoryCandidate]] = None,
    confidence_threshold: float = 0.35,
    gap_threshold: float = TEXT_LLM_GAP_THRESHOLD,
    non_english_llm_primary: bool = False,
) -> bool:
    if not (use_text_llm and is_agriculture_related and LLM_CONFIGURED):
        return False
    if non_english_llm_primary:
        return True
    if best_candidate is None:
        return True
    if best_candidate.confidence < confidence_threshold:
        return True
    if _top_probability_gap(current_candidates or []) < gap_threshold:
        return True
    return False


def _should_run_vision(
    *,
    use_vision: bool,
    ocr_used: bool,
    text_quality_ok_flag: bool,
    heuristics_source: Optional[SourceResult],
    best_candidate: Optional[SubcategoryCandidate],
    current_candidates: List[SubcategoryCandidate],
    text_source: Optional[SourceResult],
    confidence_threshold: float,
    gap_threshold: float,
) -> tuple[bool, List[str]]:
    reasons: List[str] = []
    if not use_vision or not VISION_LLM_BASE_URL:
        return False, reasons

    top_confidence = best_candidate.confidence if best_candidate else 0.0
    top_gap = _top_probability_gap(current_candidates)

    if not text_quality_ok_flag:
        reasons.append("text_quality_poor")
    if ocr_used:
        reasons.append("ocr_used")
    if top_confidence < confidence_threshold:
        reasons.append("low_subcategory_confidence")
    if top_gap < gap_threshold:
        reasons.append("close_top_candidates")
    if _candidate_visual_signals(best_candidate):
        reasons.append("visual_or_slide_signals")
    if _model_keys_disagree(heuristics_source, text_source):
        reasons.append("heuristics_text_disagreement")

    deduped_reasons = list(dict.fromkeys(reasons))
    return bool(deduped_reasons), deduped_reasons


def _masked_origin(url: str) -> Optional[str]:
    from urllib.parse import urlparse

    if not url:
        return None
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


def _cache_total_bytes(cache: Dict[str, tuple[float, Any, int]]) -> int:
    return sum(item[2] for item in cache.values())


def _estimate_cache_value_size(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, str):
        return len(value.encode("utf-8"))
    if isinstance(value, bytes):
        return len(value)
    if isinstance(value, (int, float, bool)):
        return sys.getsizeof(value)
    if isinstance(value, dict):
        return sum(_estimate_cache_value_size(k) + _estimate_cache_value_size(v) for k, v in value.items())
    if isinstance(value, (list, tuple, set)):
        return sum(_estimate_cache_value_size(item) for item in value)
    if hasattr(value, "__dict__"):
        return _estimate_cache_value_size(vars(value))
    return sys.getsizeof(value)


def _cache_get(cache: Dict[str, tuple[float, Any, int]], key: str) -> Any | None:
    entry = cache.get(key)
    if not entry:
        return None
    expires_at, value, _ = entry
    if expires_at < time.time():
        cache.pop(key, None)
        return None
    return value


def _cache_set(cache: Dict[str, tuple[float, Any, int]], key: str, value: Any, ttl_seconds: int) -> None:
    if ttl_seconds <= 0:
        return
    now = time.time()
    expired_keys = [cache_key for cache_key, (expires_at, _, _) in cache.items() if expires_at < now]
    for expired_key in expired_keys:
        cache.pop(expired_key, None)

    estimated_size = _estimate_cache_value_size(value)
    if estimated_size > RUNTIME_CACHE_MAX_BYTES:
        return

    cache.pop(key, None)
    cache[key] = (now + ttl_seconds, value, estimated_size)

    while len(cache) > RUNTIME_CACHE_MAX_ENTRIES or _cache_total_bytes(cache) > RUNTIME_CACHE_MAX_BYTES:
        oldest_key = next(iter(cache), None)
        if oldest_key is None:
            break
        cache.pop(oldest_key, None)



def _criteria_http_error(exc: CriteriaViolation) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.message)


async def _save_upload_to_temp(file: UploadFile, *, suffix: str, max_bytes: int = MAX_BYTES) -> tuple[str, int]:
    tmp_path = None
    total = 0
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix or ".bin") as tmp:
            tmp_path = tmp.name
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail="File is too large for AI-assisted ingestion. Maximum allowed size is 1 GB.",
                    )
                tmp.write(chunk)
        if total <= 0:
            raise HTTPException(status_code=400, detail="Empty file")
        return tmp_path, total
    except Exception:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass
        raise


def _validate_ai_uploader_criteria_or_413(file_path: str, filename: str, *, size_bytes: int | None = None) -> dict:
    try:
        return validate_asset_against_ai_uploader_criteria(file_path, filename, size_bytes=size_bytes)
    except CriteriaViolation as exc:
        raise _criteria_http_error(exc) from exc

def _sample_text_for_llm(text: str, *, max_chars: int) -> str:
    compact = " ".join((text or "").split())
    if len(compact) <= max_chars:
        return compact
    head_len = int(max_chars * 0.45)
    mid_len = int(max_chars * 0.25)
    tail_len = max_chars - head_len - mid_len - 64
    midpoint = len(compact) // 2
    mid_start = max(0, midpoint - (mid_len // 2))
    mid_end = min(len(compact), mid_start + mid_len)
    parts = [
        compact[:head_len].strip(),
        compact[mid_start:mid_end].strip(),
        compact[-tail_len:].strip() if tail_len > 0 else "",
    ]
    return "\n\n[...]\n\n".join([part for part in parts if part])


def _agriculture_cache_key(text: str, *, allow_llm_fallback: bool, llm_configured: bool, llm_model: str) -> str:
    normalized = " ".join((text or "").split())
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return f"{digest}|llm={int(bool(allow_llm_fallback and llm_configured))}|model={llm_model}"


def _assess_agriculture_cached(
    *,
    text: str,
    lines: List[str],
    allow_llm_fallback: bool,
    llm_base_url: str = "",
    llm_api_key: str = "",
    llm_model: str = "",
    llm_configured: bool = False,
    defer_llm: bool = False,
):
    # The Stage-3 agriculture LLM uses the *same* provider selected for the request
    # (custom or mistral), so under provider=mistral it no longer falls back to the
    # self-hosted endpoint. The model is part of the cache key so the two providers
    # do not share cached agriculture decisions.
    cache_key = _agriculture_cache_key(
        text, allow_llm_fallback=allow_llm_fallback, llm_configured=llm_configured, llm_model=llm_model
    )
    cached = _cache_get(AGRICULTURE_CACHE, cache_key)
    if cached is not None:
        return cached, True

    result = assess_agriculture_relevance_staged(
        text,
        lines=lines,
        allow_llm_fallback=allow_llm_fallback,
        llm_config={
            "base_url": llm_base_url,
            "api_key": llm_api_key,
            "model": llm_model,
        } if allow_llm_fallback and llm_configured else None,
        defer_llm=defer_llm,
    )
    # Do not cache a provisional (deferred) verdict; the caller finalises it via the
    # combined agri+subtype call and caches the resolved result.
    if not getattr(result, "needs_llm_decision", False):
        _cache_set(AGRICULTURE_CACHE, cache_key, result, AGRICULTURE_CACHE_TTL_SEC)
    return result, False


def _assess_ko_eligibility(
    *,
    text: str,
    use_text_llm: bool,
    llm_base_url: str = "",
    llm_api_key: str = "",
    llm_model: str = "",
    llm_configured: bool = False,
) -> Dict[str, Any]:
    heuristic = assess_ko_eligibility(text)
    result = {
        "is_eligible": heuristic.is_eligible,
        "confidence": round(heuristic.confidence, 4),
        "exclusion_type": heuristic.exclusion_type,
        "rationale": heuristic.rationale,
        "matched_signals": heuristic.matched_signals,
        "method": heuristic.method,
    }

    ambiguous = (not heuristic.is_eligible and heuristic.confidence < 0.8) or (heuristic.is_eligible and heuristic.confidence < 0.6)
    if ambiguous and use_text_llm and llm_configured:
        try:
            from docint.llm.eligibility_classify import llm_classify_ko_eligibility_text

            llm_res = llm_classify_ko_eligibility_text(
                text,
                base_url=llm_base_url,
                api_key=llm_api_key,
                model=llm_model,
            )
            result = {
                "is_eligible": llm_res.is_eligible,
                "confidence": round(llm_res.confidence, 4),
                "exclusion_type": llm_res.exclusion_type,
                "rationale": llm_res.rationale,
                "matched_signals": list(llm_res.raw_json.get("matched_signals", []) or []),
                "method": "llm_eligibility_fallback",
            }
        except Exception as exc:
            result["llm_error"] = str(exc)

    return result


def _validate_public_http_url(url: str) -> str:
    from urllib.parse import urlparse

    clean_url = (url or "").strip()
    parsed = urlparse(clean_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(status_code=400, detail="Only public http/https URLs are supported")
    return clean_url


def detect_text_language(text: str) -> Dict[str, Any]:
    sample = " ".join((text or "").split())[:4000]
    if len(sample) < 80:
        return {
            "language": "unknown",
            "confidence": 0.0,
            "is_english": False,
            "non_english_llm_primary": False,
            "method": "insufficient_text",
        }

    greek_chars = len(re.findall(r"[\u0370-\u03FF\u1F00-\u1FFF]", sample))
    if greek_chars >= 12:
        return {
            "language": "el",
            "confidence": 0.95,
            "is_english": False,
            "non_english_llm_primary": True,
            "method": "script_heuristic",
        }

    if LANGDETECT_AVAILABLE and detect_langs is not None:
        try:
            langs = detect_langs(sample)
            if langs:
                top = langs[0]
                lang = str(top.lang)
                conf = float(top.prob)
                is_english = lang.startswith("en")
                return {
                    "language": lang,
                    "confidence": round(conf, 4),
                    "is_english": is_english,
                    "non_english_llm_primary": (not is_english and conf >= 0.75),
                    "method": "langdetect",
                }
        except Exception:
            pass

    lowered = sample.lower()
    english_hits = sum(
        lowered.count(token)
        for token in (" the ", " and ", " with ", " for ", " from ", " report ", " guide ", " introduction ")
    )
    return {
        "language": "en" if english_hits >= 3 else "unknown",
        "confidence": 0.55 if english_hits >= 3 else 0.0,
        "is_english": english_hits >= 3,
        "non_english_llm_primary": False,
        "method": "fallback_stopwords",
    }


def _apply_source_probabilities(
    candidates: List[SubcategoryCandidate],
    probs: Dict[str, float],
    key_by_name: Dict[str, str],
) -> None:
    for candidate in candidates:
        subcat_key = key_by_name.get(candidate.subcategory_name, candidate.subcategory_name)
        source_prob = round(float(probs.get(subcat_key, 0.0)), 4)
        candidate.probability = source_prob
        candidate.confidence = source_prob
    candidates.sort(key=lambda item: item.probability, reverse=True)
    for idx, candidate in enumerate(candidates, start=1):
        candidate.rank = idx


def _agri_gate_or_raise(scan_result: Any, *, strict: bool, source_label: str) -> Dict[str, Any]:
    payload = {
        "enabled": bool(AGRI_GATE_BASE_URL),
        "ok": scan_result.ok,
        "allowed": scan_result.allowed,
        "status": scan_result.status,
        "reason_code": scan_result.reason_code,
        "reason": scan_result.reason,
        "details": scan_result.details,
        "strict": strict,
        "source": source_label,
    }
    if not scan_result.ok:
        if strict:
            raise HTTPException(
                status_code=502,
                detail=f"Agri Gate scan failed for {source_label}: {scan_result.reason}",
            )
        payload["warning"] = "Agri Gate unavailable; continuing because strict mode is disabled"
        return payload

    if not scan_result.allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Agri Gate rejected the {source_label}: {scan_result.reason}",
        )
    return payload


# Topics are only inferred for assets that cleared the agriculture gate and have
# enough text to score; below this many characters lexical/embedding signals are
# too thin to be trustworthy.
TOPIC_MIN_CHARS = int(os.getenv("TOPIC_MIN_CHARS", "120"))


def _infer_topics_response(
    *,
    text: str,
    lines: Optional[List[str]],
    agri_relevance: Any,
) -> Optional[TopicInference]:
    """Run multi-label topic inference, gated on agriculture relevance.

    Returns None (no topics emitted) when the asset is not agriculture-related
    or has too little text. Never raises: topic inference must not be able to
    fail a classification request.
    """
    if not getattr(agri_relevance, "is_agriculture_related", False):
        return None
    if not text or len(text.strip()) < TOPIC_MIN_CHARS:
        return None
    try:
        result = infer_topics(text, lines=lines)
    except Exception as exc:
        return TopicInference(
            topics=[],
            method="error",
            stages_used=[],
            signals_version="unknown",
            rationale=f"Topic inference unavailable: {exc}",
        )
    return TopicInference(
        topics=[
            TopicResult(
                topic=t.topic,
                score=t.score,
                lexical_score=t.lexical_score,
                embedding_score=t.embedding_score,
                matched_terms=t.matched_terms,
                rationale=t.rationale,
            )
            for t in result.topics
        ],
        method=result.method,
        stages_used=result.stages_used,
        signals_version=result.signals_version,
        rationale=result.rationale,
    )


def _infer_intended_purposes_response(
    *,
    text: str,
    agri_relevance: Any,
    use_text_llm: bool,
    llm_base_url: str,
    llm_api_key: str,
    llm_model: str,
    llm_configured: bool,
) -> Optional[IntendedPurposeInference]:
    """Infer up to 3 intended purposes (user intents). Never raises.

    Gated on agriculture relevance, exactly like topics: a non-agriculture asset
    is skipped, so we emit no purposes for it (and pay for neither the embedding
    nor the LLM stage). When the asset is agriculture-related, the LLM stage is
    used if the text LLM is enabled/configured, otherwise the embedding stage.
    """
    if not getattr(agri_relevance, "is_agriculture_related", False):
        return None
    if not text or len(text.strip()) < TOPIC_MIN_CHARS:
        return None
    use_llm = bool(use_text_llm and llm_configured)
    llm_config = {"base_url": llm_base_url, "api_key": llm_api_key, "model": llm_model} if use_llm else None
    try:
        result = infer_intended_purposes(text, max_results=3, use_llm=use_llm, llm_config=llm_config)
    except Exception as exc:
        return IntendedPurposeInference(purposes=[], method="error", stages_used=[], rationale=f"Intended-purpose inference unavailable: {exc}")
    return IntendedPurposeInference(
        purposes=[
            IntendedPurposeResult(key=p.key, name=p.name, category=p.category, score=p.score, rationale=p.rationale)
            for p in result.purposes
        ],
        method=result.method,
        stages_used=result.stages_used,
        version=result.version,
        rationale=result.rationale,
    )


def classify_url_text(
    *,
    url: str,
    extracted_text: str,
    title: Optional[str],
    pagesense_meta: Dict[str, Any],
    require_agriculture: bool = True,
    auto_route_models: bool = True,
    use_text_llm: bool = True,
    heuristics_alpha: float = 0.4,
    classification_confidence_threshold: float = 0.35,
    fusion_strategy: str = "adaptive",
    provider: str = "custom",
) -> ClassificationResponse:
    # Provider-aware text-LLM config (URL path is text-only; no OCR/vision/audio).
    (LLM_BASE_URL, LLM_API_KEY, LLM_MODEL, LLM_CONFIGURED,
     VISION_LLM_BASE_URL, VISION_LLM_API_KEY, VISION_LLM_MODEL, _vision_configured) = _resolve_llm_config(provider)

    start_time = time.time()
    stage_timings_ms: Dict[str, float] = {}
    text = extracted_text.strip()
    if not text:
        raise HTTPException(status_code=422, detail="PageSense returned no usable text for this URL")

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    quality = text_quality_ok(text)
    language_info = detect_text_language(text)
    non_english_llm_primary = bool(language_info["non_english_llm_primary"] and use_text_llm and LLM_CONFIGURED)

    stage_start = time.time()
    category_result = infer_url_category(url, text)
    category_response = CategoryInference(
        category=category_result.category,
        confidence=round(category_result.confidence, 4),
        rationale=category_result.rationale,
    )
    stage_timings_ms["category_inference_ms"] = round((time.time() - stage_start) * 1000, 2)

    stage_start = time.time()
    agri_relevance, agriculture_cache_hit = _assess_agriculture_cached(
        text=text,
        lines=lines,
        allow_llm_fallback=use_text_llm and LLM_CONFIGURED,
        llm_base_url=LLM_BASE_URL,
        llm_api_key=LLM_API_KEY,
        llm_model=LLM_MODEL,
        llm_configured=LLM_CONFIGURED,
    )
    stage_timings_ms["agriculture_pipeline_ms"] = round((time.time() - stage_start) * 1000, 2)
    agriculture_response = AgricultureRelevance(
        is_agriculture_related=agri_relevance.is_agriculture_related,
        confidence=round(agri_relevance.confidence, 4),
        score=round(agri_relevance.score, 4),
        method=agri_relevance.method,
        lexicon_version=agri_relevance.lexicon_version,
        matched_terms=agri_relevance.matched_terms,
        matched_buckets=agri_relevance.matched_buckets,
        matched_concepts=agri_relevance.matched_concepts,
        bucket_scores={k: round(v, 4) for k, v in agri_relevance.bucket_scores.items()},
        rationale=agri_relevance.rationale,
        stages_used=agri_relevance.stages_used,
        stage_results=[
            {
                "stage": item.stage,
                "available": item.available,
                "used": item.used,
                "is_agriculture_related": item.is_agriculture_related,
                "confidence": item.confidence,
                "rationale": item.rationale,
                "details": item.details,
            }
            for item in agri_relevance.stage_results
        ],
    )

    topics_response = _infer_topics_response(text=text, lines=lines, agri_relevance=agri_relevance)
    _purpose_start = time.time()
    intended_purposes_response = _infer_intended_purposes_response(
        text=text,
        agri_relevance=agri_relevance,
        use_text_llm=use_text_llm,
        llm_base_url=LLM_BASE_URL,
        llm_api_key=LLM_API_KEY,
        llm_model=LLM_MODEL,
        llm_configured=LLM_CONFIGURED,
    )
    stage_timings_ms["intended_purposes_ms"] = round((time.time() - _purpose_start) * 1000, 2)

    base_document_info = {
        "filename": url,
        "pages": 1,
        "unit_label": "url",
        "asset_type": "url",
        "inferred_category": category_result.category,
        "source": "pagesense",
        "text_length": len(text),
        "text_quality": {
            "chars": quality.metrics.get("chars"),
            "letters": quality.metrics.get("letters"),
            "letter_ratio": quality.metrics.get("letter_ratio"),
            "ok": quality.ok,
        } if hasattr(quality, "metrics") else None,
        "title": title,
    }

    stage_start = time.time()
    eligibility_result = _assess_ko_eligibility(
        text=text,
        use_text_llm=use_text_llm,
        llm_base_url=LLM_BASE_URL,
        llm_api_key=LLM_API_KEY,
        llm_model=LLM_MODEL,
        llm_configured=LLM_CONFIGURED,
    )
    stage_timings_ms["ko_eligibility_ms"] = round((time.time() - stage_start) * 1000, 2)
    if agri_relevance.is_agriculture_related and not eligibility_result["is_eligible"]:
        processing_time_ms = (time.time() - start_time) * 1000
        exclusion_label = (eligibility_result.get("exclusion_type") or "ineligible_content").replace("_", " ")
        return ClassificationResponse(
            best_match=None,
            all_candidates=[],
            fusion=None,
            heuristics=None,
            vision_llm=None,
            text_llm=None,
            category_used=category_result.category,
            category_inference=category_response,
            agriculture_relevance=agriculture_response,
            topics=topics_response,
            intended_purposes=intended_purposes_response,
            classification_skipped=True,
            skip_reason=f"Agriculture-related but not an eligible knowledge object: {exclusion_label}",
            total_candidates=0,
            confidence_threshold_met=False,
            document_info=base_document_info,
            processing_info={
                "processing_time_ms": round(processing_time_ms, 2),
                "ocr_used": False,
                "sources_used": [],
                "fusion_enabled": False,
                "require_agriculture": require_agriculture,
                "auto_route_models": auto_route_models,
                "source_mode": "url",
                "extraction": pagesense_meta,
                "eligibility_gate": eligibility_result,
                "cache": {
                    "pagesense": pagesense_meta.get("cache_hit", False),
                    "agriculture": agriculture_cache_hit,
                },
                "language_detection": language_info,
                "stage_timings_ms": stage_timings_ms,
            },
        )

    if require_agriculture and not agri_relevance.is_agriculture_related:
        processing_time_ms = (time.time() - start_time) * 1000
        return ClassificationResponse(
            best_match=None,
            all_candidates=[],
            fusion=None,
            heuristics=None,
            vision_llm=None,
            text_llm=None,
            category_used=category_result.category,
            category_inference=category_response,
            agriculture_relevance=agriculture_response,
            topics=topics_response,
            intended_purposes=intended_purposes_response,
            classification_skipped=True,
            skip_reason=f"{category_result.category} URL classified as non-agriculture; subcategory classification skipped",
            total_candidates=0,
            confidence_threshold_met=False,
            document_info=base_document_info,
            processing_info={
                "processing_time_ms": round(processing_time_ms, 2),
                "ocr_used": False,
                "sources_used": [],
                "fusion_enabled": False,
                "require_agriculture": require_agriculture,
                "auto_route_models": auto_route_models,
                "source_mode": "url",
                "extraction": pagesense_meta,
                "cache": {
                    "pagesense": pagesense_meta.get("cache_hit", False),
                    "agriculture": agriculture_cache_hit,
                },
                "language_detection": language_info,
                "stage_timings_ms": stage_timings_ms,
            },
        )

    stage_start = time.time()
    eligibility_result = _assess_ko_eligibility(
        text=text,
        use_text_llm=use_text_llm,
        llm_base_url=LLM_BASE_URL,
        llm_api_key=LLM_API_KEY,
        llm_model=LLM_MODEL,
        llm_configured=LLM_CONFIGURED,
    )
    stage_timings_ms["ko_eligibility_ms"] = round((time.time() - stage_start) * 1000, 2)
    if not eligibility_result["is_eligible"]:
        processing_time_ms = (time.time() - start_time) * 1000
        exclusion_label = (eligibility_result.get("exclusion_type") or "ineligible_content").replace("_", " ")
        return ClassificationResponse(
            best_match=None,
            all_candidates=[],
            fusion=None,
            heuristics=None,
            vision_llm=None,
            text_llm=None,
            category_used=category_result.category,
            category_inference=category_response,
            agriculture_relevance=agriculture_response,
            topics=topics_response,
            intended_purposes=intended_purposes_response,
            classification_skipped=True,
            skip_reason=f"Agriculture-related but not an eligible knowledge object: {exclusion_label}",
            total_candidates=0,
            confidence_threshold_met=False,
            document_info=base_document_info,
            processing_info={
                "processing_time_ms": round(processing_time_ms, 2),
                "ocr_used": False,
                "sources_used": [],
                "fusion_enabled": False,
                "require_agriculture": require_agriculture,
                "auto_route_models": auto_route_models,
                "source_mode": "url",
                "extraction": pagesense_meta,
                "cache": {
                    "pagesense": pagesense_meta.get("cache_hit", False),
                    "agriculture": agriculture_cache_hit,
                },
                "eligibility_gate": eligibility_result,
                "language_detection": language_info,
                "stage_timings_ms": stage_timings_ms,
            },
        )

    if category_result.category == "Software Application":
        stage_start = time.time()
        software_candidates, software_best = _build_unified_candidates(
            category=category_result.category,
            text=text,
            filename=url,
            legacy_probs={},
        )
        software_heuristics_best = software_best.model_copy(deep=True) if software_best else None
        stage_timings_ms["software_classification_ms"] = round((time.time() - stage_start) * 1000, 2)
        software_text_result = None
        software_text_source = None
        software_fusion = None

        should_use_software_text_llm = (
            use_text_llm
            and LLM_CONFIGURED
            and (
                non_english_llm_primary
                or software_best is None
                or software_best.confidence < classification_confidence_threshold
                or _top_probability_gap(software_candidates) < TEXT_LLM_GAP_THRESHOLD
            )
        )

        if should_use_software_text_llm:
            stage_start = time.time()
            try:
                from docint.llm.subcategory_classify import llm_classify_software_subcategories_text

                llm_res = llm_classify_software_subcategories_text(
                    _sample_text_for_llm(text, max_chars=URL_TEXT_LLM_MAX_CHARS),
                    base_url=LLM_BASE_URL,
                    api_key=LLM_API_KEY,
                    model=LLM_MODEL,
                    max_chars=URL_TEXT_LLM_MAX_CHARS,
                    temperature=LLM_TEMPERATURE,
                )
                software_text_source = convert_to_source_result(
                    subcategory_key=llm_res.subcategory_key,
                    confidence=llm_res.confidence,
                    probs=llm_res.probs,
                    source_name="text_llm",
                    rationale=llm_res.rationale,
                )
                software_text_result = {
                    "subcategory_key": llm_res.subcategory_key,
                    "subcategory_name": llm_res.subcategory_name,
                    "confidence": round(llm_res.confidence, 4),
                    "rationale": llm_res.rationale,
                    "model": LLM_MODEL,
                    "probs": llm_res.probs,
                }
            except Exception as e:
                software_text_result = {"error": str(e), "model": LLM_MODEL}
            stage_timings_ms["software_text_llm_ms"] = round((time.time() - stage_start) * 1000, 2)

        if non_english_llm_primary and software_text_source:
            _apply_source_probabilities(software_candidates, software_text_source.probs, _unified_key_by_name())
            add_contrastive_rationales(software_candidates)
            software_best = software_candidates[0] if software_candidates else None
        elif software_best and software_text_source:
            software_heuristics_source = convert_to_source_result(
                subcategory_key=software_best.subcategory_id,
                confidence=software_best.confidence,
                probs={candidate.subcategory_id: candidate.probability for candidate in software_candidates},
                source_name="heuristics",
                evidence_score=software_best.evidence_score,
                rationale=software_best.rationale,
            )
            software_alpha = 0.34 if len(text) >= 500 else 0.26
            fusion_result = intelligent_fusion(
                heuristics_result=software_heuristics_source,
                vision_result=None,
                text_result=software_text_source,
                strategy=FusionStrategy.CONFIDENCE_ADAPTIVE if fusion_strategy == "adaptive" else FusionStrategy.WEIGHTED,
                heuristics_alpha=software_alpha,
                llm_alpha=1.0 - software_alpha,
            )
            software_fusion = FusionInfo(
                fused=True,
                strategy=fusion_result.fusion_strategy,
                weights=fusion_result.weights,
                agreement_score=fusion_result.agreement_score,
                rationale=fusion_result.rationale,
            )
            for candidate in software_candidates:
                fused_prob = round(fusion_result.probs.get(candidate.subcategory_id, 0), 4)
                candidate.probability = fused_prob
                candidate.confidence = fused_prob
            software_candidates.sort(key=lambda item: item.probability, reverse=True)
            for idx, candidate in enumerate(software_candidates, start=1):
                candidate.rank = idx
            add_contrastive_rationales(software_candidates)
            software_best = software_candidates[0] if software_candidates else None

        processing_time_ms = (time.time() - start_time) * 1000
        return ClassificationResponse(
            best_match=software_best,
            all_candidates=software_candidates,
            fusion=software_fusion,
            heuristics=software_heuristics_best,
            vision_llm=None,
            text_llm=software_text_result,
            category_used=category_result.category,
            category_inference=category_response,
            agriculture_relevance=agriculture_response,
            topics=topics_response,
            intended_purposes=intended_purposes_response,
            classification_skipped=False,
            skip_reason=None,
            total_candidates=len(software_candidates),
            confidence_threshold_met=bool(software_best and software_best.confidence >= classification_confidence_threshold),
            document_info=base_document_info,
            processing_info={
                "processing_time_ms": round(processing_time_ms, 2),
                "ocr_used": False,
                "sources_used": ["heuristics"] + (["text_llm"] if software_text_result is not None and "error" not in software_text_result else []),
                "fusion_enabled": software_fusion is not None,
                "require_agriculture": require_agriculture,
                "auto_route_models": auto_route_models,
                "source_mode": "url",
                "extraction": pagesense_meta,
                "routing": {
                    "software_mode": True,
                    "text_llm": {
                        "requested": use_text_llm,
                        "used": software_text_result is not None and "error" not in software_text_result,
                        "reason": "software_text_llm_enabled" if should_use_software_text_llm else "heuristics_strong_enough",
                    },
                    "vision_llm": {"requested": False, "used": False, "reasons": ["url_text_mode_no_vision"]},
                    "language_detection": language_info,
                },
                "cache": {
                    "pagesense": pagesense_meta.get("cache_hit", False),
                    "agriculture": agriculture_cache_hit,
                },
                "eligibility_gate": eligibility_result,
                "language_detection": language_info,
                "stage_timings_ms": stage_timings_ms,
            },
        )

    if category_result.category == "Dataset":
        stage_start = time.time()
        dataset_candidates, dataset_best = _build_unified_candidates(
            category=category_result.category,
            text=text,
            filename=url,
            legacy_probs={},
        )
        dataset_heuristics_best = dataset_best.model_copy(deep=True) if dataset_best else None
        stage_timings_ms["dataset_classification_ms"] = round((time.time() - stage_start) * 1000, 2)
        dataset_text_result = None
        dataset_text_source = None
        dataset_fusion = None

        should_use_dataset_text_llm = (
            use_text_llm
            and LLM_CONFIGURED
            and (
                non_english_llm_primary
                or dataset_best is None
                or dataset_best.confidence < classification_confidence_threshold
                or _top_probability_gap(dataset_candidates) < TEXT_LLM_GAP_THRESHOLD
            )
        )

        if should_use_dataset_text_llm:
            stage_start = time.time()
            try:
                from docint.llm.subcategory_classify import llm_classify_dataset_subcategories_text

                llm_res = llm_classify_dataset_subcategories_text(
                    _sample_text_for_llm(text, max_chars=URL_DATASET_LLM_MAX_CHARS),
                    base_url=LLM_BASE_URL,
                    api_key=LLM_API_KEY,
                    model=LLM_MODEL,
                    max_chars=URL_DATASET_LLM_MAX_CHARS,
                    temperature=LLM_TEMPERATURE,
                )
                dataset_text_source = convert_to_source_result(
                    subcategory_key=llm_res.subcategory_key,
                    confidence=llm_res.confidence,
                    probs=llm_res.probs,
                    source_name="text_llm",
                    rationale=llm_res.rationale,
                )
                dataset_text_result = _map_llm_payload_to_unified({
                    "subcategory_key": llm_res.subcategory_key,
                    "subcategory_name": llm_res.subcategory_name,
                    "confidence": round(llm_res.confidence, 4),
                    "rationale": llm_res.rationale,
                    "model": LLM_MODEL,
                    "probs": llm_res.probs,
                })
                dataset_text_source = _map_source_result_to_unified(dataset_text_source)
            except Exception as e:
                dataset_text_result = {"error": str(e), "model": LLM_MODEL}
            stage_timings_ms["dataset_text_llm_ms"] = round((time.time() - stage_start) * 1000, 2)

        if non_english_llm_primary and dataset_text_source:
            _apply_source_probabilities(dataset_candidates, dataset_text_source.probs, _unified_key_by_name())
            add_contrastive_rationales(dataset_candidates)
            dataset_best = dataset_candidates[0] if dataset_candidates else None
        elif dataset_best and dataset_text_source:
            dataset_heuristics_source = convert_to_source_result(
                subcategory_key=dataset_best.subcategory_id,
                confidence=dataset_best.confidence,
                probs={candidate.subcategory_id: candidate.probability for candidate in dataset_candidates},
                source_name="heuristics",
                evidence_score=dataset_best.evidence_score,
                rationale=dataset_best.rationale,
            )
            fusion_result = intelligent_fusion(
                heuristics_result=dataset_heuristics_source,
                vision_result=None,
                text_result=dataset_text_source,
                strategy=FusionStrategy.CONFIDENCE_ADAPTIVE if fusion_strategy == "adaptive" else FusionStrategy.WEIGHTED,
                heuristics_alpha=heuristics_alpha,
                llm_alpha=1.0 - heuristics_alpha,
            )
            dataset_fusion = FusionInfo(
                fused=True,
                strategy=fusion_result.fusion_strategy,
                weights=fusion_result.weights,
                agreement_score=fusion_result.agreement_score,
                rationale=fusion_result.rationale,
            )
            for candidate in dataset_candidates:
                fused_prob = round(fusion_result.probs.get(candidate.subcategory_id, 0), 4)
                candidate.probability = fused_prob
                candidate.confidence = fused_prob
            dataset_candidates.sort(key=lambda item: item.probability, reverse=True)
            for idx, candidate in enumerate(dataset_candidates, start=1):
                candidate.rank = idx
            _apply_dataset_consensus_boost(
                dataset_candidates,
                heuristics_best=dataset_heuristics_best,
                text_source=dataset_text_source,
                fusion_info=dataset_fusion,
            )
            add_contrastive_rationales(dataset_candidates)
            dataset_best = dataset_candidates[0] if dataset_candidates else None

        processing_time_ms = (time.time() - start_time) * 1000
        return ClassificationResponse(
            best_match=dataset_best,
            all_candidates=dataset_candidates,
            fusion=dataset_fusion,
            heuristics=dataset_heuristics_best,
            vision_llm=None,
            text_llm=dataset_text_result,
            category_used=category_result.category,
            category_inference=category_response,
            agriculture_relevance=agriculture_response,
            topics=topics_response,
            intended_purposes=intended_purposes_response,
            classification_skipped=False,
            skip_reason=None,
            total_candidates=len(dataset_candidates),
            confidence_threshold_met=bool(dataset_best and dataset_best.confidence >= classification_confidence_threshold),
            document_info=base_document_info,
            processing_info={
                "processing_time_ms": round(processing_time_ms, 2),
                "ocr_used": False,
                "sources_used": ["heuristics"] + (["text_llm"] if dataset_text_result is not None and "error" not in dataset_text_result else []),
                "fusion_enabled": dataset_fusion is not None,
                "require_agriculture": require_agriculture,
                "auto_route_models": auto_route_models,
                "source_mode": "url",
                "routing": {
                    "dataset_mode": True,
                    "text_llm": {"requested": use_text_llm, "used": dataset_text_result is not None and "error" not in dataset_text_result, "reason": "dataset_text_llm_enabled" if should_use_dataset_text_llm else "heuristics_strong_enough"},
                    "vision_llm": {"requested": False, "used": False, "reasons": ["url_text_mode_no_vision"]},
                    "language_detection": language_info,
                },
                "classification_confidence_threshold": classification_confidence_threshold,
                "extraction": pagesense_meta,
                "cache": {
                    "pagesense": pagesense_meta.get("cache_hit", False),
                    "agriculture": agriculture_cache_hit,
                },
                "eligibility_gate": eligibility_result,
                "stage_timings_ms": stage_timings_ms,
            },
        )

    stage_start = time.time()
    sections = count_sections(lines)
    cites = detect_citations(text, has_references_heading=sections.present.get("references", False))
    kw = count_keywords(text)
    r_imrad = score_imrad(sections)
    r_cites = score_citations(cites, text_len=len(text))
    r_deliv = score_deliverable(kw, sections=sections)
    r_ped = score_pedagogy(kw)
    r_proc = score_procedure(kw)
    rubric_scores = {
        "imrad": r_imrad.score,
        "citations": r_cites.score,
        "deliverable": r_deliv.score,
        "pedagogy": r_ped.score,
        "procedure": r_proc.score,
    }
    stage_timings_ms["feature_and_rubric_ms"] = round((time.time() - stage_start) * 1000, 2)

    stage_start = time.time()
    _, all_scores, _ = score_subcategories(
        text=text,
        lines=lines,
        page_count=1,
        sections=sections,
        rubric_scores=rubric_scores,
        parent_type_filter=None,
    )
    legacy_candidates = build_probability_distribution(all_scores)
    legacy_probs = _legacy_name_probs_from_candidates(legacy_candidates)
    candidates, best_candidate = _build_unified_candidates(
        category=category_result.category,
        text=text,
        filename=url,
        legacy_probs=legacy_probs,
    )
    heuristics_best = best_candidate.model_copy(deep=True) if best_candidate else None
    final_candidates = [c.model_copy(deep=True) for c in candidates]
    heuristics_probs = {
        c.subcategory_id: c.probability
        for c in candidates
    }
    heuristics_source = convert_to_source_result(
        subcategory_key=best_candidate.subcategory_id if best_candidate else "",
        confidence=best_candidate.confidence if best_candidate else 0.0,
        probs=heuristics_probs,
        source_name="heuristics",
        evidence_score=best_candidate.evidence_score if best_candidate else 0.0,
        rationale=best_candidate.rationale if best_candidate else "",
    )
    stage_timings_ms["heuristics_classification_ms"] = round((time.time() - stage_start) * 1000, 2)

    text_source = None
    llm_results: Dict[str, Any] = {}
    should_use_text_llm = _should_run_text_llm(
        use_text_llm=use_text_llm,
        is_agriculture_related=agri_relevance.is_agriculture_related,
        best_candidate=best_candidate,
        current_candidates=final_candidates,
        confidence_threshold=classification_confidence_threshold,
        gap_threshold=TEXT_LLM_GAP_THRESHOLD,
        non_english_llm_primary=non_english_llm_primary,
    ) if auto_route_models else (use_text_llm and LLM_CONFIGURED)
    text_llm_reason = (
        "non_english_text_llm_primary"
        if non_english_llm_primary and should_use_text_llm
        else (
            "low_confidence_or_close_candidates"
            if should_use_text_llm and auto_route_models
            else ("manual_request" if should_use_text_llm else "heuristics_strong_enough")
        )
    )
    if should_use_text_llm:
        stage_start = time.time()
        try:
            from docint.llm.subcategory_classify import llm_classify_subcategories_text

            llm_res = llm_classify_subcategories_text(
                _sample_text_for_llm(text, max_chars=URL_TEXT_LLM_MAX_CHARS),
                base_url=LLM_BASE_URL,
                api_key=LLM_API_KEY,
                model=LLM_MODEL,
                max_chars=URL_TEXT_LLM_MAX_CHARS,
                temperature=LLM_TEMPERATURE,
            )
            text_source = convert_to_source_result(
                subcategory_key=llm_res.subcategory_key,
                confidence=llm_res.confidence,
                probs=llm_res.probs,
                source_name="text_llm",
                rationale=llm_res.rationale,
            )
            llm_results["text"] = _map_llm_payload_to_unified({
                "subcategory_key": llm_res.subcategory_key,
                "subcategory_name": llm_res.subcategory_name,
                "confidence": round(llm_res.confidence, 4),
                "rationale": llm_res.rationale,
                "model": LLM_MODEL,
                "probs": llm_res.probs,
            })
            text_source = _map_source_result_to_unified(text_source)
        except Exception as e:
            llm_results["text"] = {"error": str(e), "model": LLM_MODEL}
        stage_timings_ms["text_llm_ms"] = round((time.time() - stage_start) * 1000, 2)

    fusion_info = None
    sources_for_fusion = [heuristics_source]
    if text_source:
        sources_for_fusion.append(text_source)
    if non_english_llm_primary and text_source:
        _apply_source_probabilities(final_candidates, text_source.probs, _unified_key_by_name())
        add_contrastive_rationales(final_candidates)
    elif text_source:
        stage_start = time.time()
        fusion_result = intelligent_fusion(
            heuristics_result=heuristics_source,
            vision_result=None,
            text_result=text_source,
            strategy=FusionStrategy.CONFIDENCE_ADAPTIVE if fusion_strategy == "adaptive" else FusionStrategy.WEIGHTED,
            heuristics_alpha=heuristics_alpha,
            llm_alpha=1.0 - heuristics_alpha,
        )
        fusion_info = FusionInfo(
            fused=True,
            strategy=fusion_result.fusion_strategy,
            weights=fusion_result.weights,
            agreement_score=fusion_result.agreement_score,
            rationale=fusion_result.rationale,
        )
        for c in final_candidates:
            fused_prob = round(fusion_result.probs.get(c.subcategory_id, 0), 4)
            c.probability = fused_prob
            c.confidence = fused_prob
        final_candidates.sort(key=lambda x: x.probability, reverse=True)
        for i, c in enumerate(final_candidates, 1):
            c.rank = i
        add_fusion_explanations(
            final_candidates,
            fusion_result,
            {"heuristics": heuristics_source, "text_llm": text_source},
        )
        add_contrastive_rationales(final_candidates)
        stage_timings_ms["fusion_ms"] = round((time.time() - stage_start) * 1000, 2)

    final_best = final_candidates[0] if final_candidates else None
    processing_time_ms = (time.time() - start_time) * 1000
    return ClassificationResponse(
        best_match=final_best,
        all_candidates=final_candidates,
        fusion=fusion_info,
        heuristics=heuristics_best,
        vision_llm=None,
        text_llm=llm_results.get("text"),
        category_used=category_result.category,
        category_inference=category_response,
        agriculture_relevance=agriculture_response,
        topics=topics_response,
        intended_purposes=intended_purposes_response,
        classification_skipped=False,
        skip_reason=None,
        total_candidates=len(final_candidates),
        confidence_threshold_met=bool(final_best and final_best.confidence >= classification_confidence_threshold),
        document_info=base_document_info,
        processing_info={
            "processing_time_ms": round(processing_time_ms, 2),
            "ocr_used": False,
            "sources_used": [s.source_name for s in sources_for_fusion],
            "fusion_enabled": fusion_info is not None,
            "require_agriculture": require_agriculture,
            "auto_route_models": auto_route_models,
            "source_mode": "url",
            "routing": {
                "text_llm": {"requested": use_text_llm, "used": bool(text_source), "reason": text_llm_reason},
                "vision_llm": {"requested": False, "used": False, "reasons": ["url_text_mode_no_vision"]},
                "language_detection": language_info,
            },
            "classification_confidence_threshold": classification_confidence_threshold,
            "extraction": pagesense_meta,
            "cache": {
                "pagesense": pagesense_meta.get("cache_hit", False),
                "agriculture": agriculture_cache_hit,
            },
            "eligibility_gate": eligibility_result,
            "stage_timings_ms": stage_timings_ms,
        },
    )


def classify_document(
    file_path: str,
    filename: str,
    upload_content_type: Optional[str] = None,
    require_agriculture: bool = True,
    auto_route_models: bool = True,
    use_vision: bool = False,
    use_text_llm: bool = False,
    heuristics_alpha: float = 0.4,
    classification_confidence_threshold: float = 0.35,
    vision_trigger_threshold: float = 0.6,
    candidate_gap_threshold: float = 0.12,
    fusion_strategy: str = "adaptive",
    vision_max_pages: int = 8,
    ocr_lang: str = OCR_DEFAULT_LANGS,
    ocr_max_pages: int = 10,
    provider: str = "custom",
) -> ClassificationResponse:
    """
    Main classification function with optional LLM fusion.

    Args:
        file_path: Path to uploaded file
        filename: Original filename
        require_agriculture: Whether to stop early for non-agriculture assets
        auto_route_models: Whether to decide text/vision usage automatically
        use_vision: Whether to use Vision LLM
        use_text_llm: Whether to use Text LLM
        heuristics_alpha: Weight for heuristics (0.0-1.0), LLM gets (1-alpha)
        classification_confidence_threshold: Minimum confidence considered acceptable
        vision_trigger_threshold: Confidence below which vision may be triggered
        candidate_gap_threshold: Gap below which close candidates may trigger vision
        fusion_strategy: Fusion strategy (weighted, adaptive, agreement, cascade)
        vision_max_pages: Max pages for vision analysis
        ocr_lang: Tesseract OCR languages
        ocr_max_pages: Max pages for OCR fallback
        provider: LLM provider flow: "custom" (default, self-hosted) or "mistral"
    
    Returns:
        ClassificationResponse with results and fusion info
    """
    import time

    # Provider-aware LLM config. For "mistral" these shadow the module globals so
    # every chat (text+vision) call site below targets Mistral's OpenAI-compatible
    # endpoint. OCR and transcription are routed separately (they use the native
    # Mistral SDK), keyed off `use_mistral`.
    use_mistral = provider == "mistral"
    (LLM_BASE_URL, LLM_API_KEY, LLM_MODEL, LLM_CONFIGURED,
     VISION_LLM_BASE_URL, VISION_LLM_API_KEY, VISION_LLM_MODEL, _vision_configured) = _resolve_llm_config(provider)

    # Never send more page-images than the vision server accepts in one request
    # (vLLM --limit-mm-per-prompt image:N). Clamp here so every downstream vision call
    # (document pages + video frames) is bounded regardless of the requested value.
    vision_max_pages = max(1, min(vision_max_pages, VISION_MAX_PAGES_CAP))

    start_time = time.time()
    stage_timings_ms: Dict[str, float] = {}

    # 1) Extract text from PDF
    stage_start = time.time()
    asset = ingest_asset(file_path, filename)
    stage_timings_ms["text_extraction_ms"] = round((time.time() - stage_start) * 1000, 2)

    stage_start = time.time()
    category_result = infer_file_category(asset, upload_content_type=upload_content_type)
    category_response = CategoryInference(
        category=category_result.category,
        confidence=round(category_result.confidence, 4),
        rationale=category_result.rationale,
    )
    stage_timings_ms["category_inference_ms"] = round((time.time() - stage_start) * 1000, 2)
    
    # 2) OCR fallback or audio transcription if needed
    stage_start = time.time()
    quality = text_quality_ok(asset.text)
    if asset.ocr_supported and not quality.ok:
        if category_result.category == "Image":
            ocr_doc = mistral_ocr_image(file_path) if use_mistral else ocr_image(file_path, lang=ocr_lang)
        else:
            ocr_doc = (
                mistral_ocr_pdf(file_path, max_pages=ocr_max_pages)
                if use_mistral
                else ocr_pdf(file_path, max_pages=ocr_max_pages, lang=ocr_lang)
            )
        from dataclasses import replace
        asset = replace(
            asset,
            text=ocr_doc.text,
            lines=ocr_doc.lines,
            source="ocr",
            meta={**asset.meta, **ocr_doc.meta},
        )
    if category_result.category == "Audio":
        transcript = mistral_transcribe(file_path) if use_mistral else transcribe_audio_file(file_path)
        if transcript.text:
            from dataclasses import replace
            asset = replace(
                asset,
                text=transcript.text,
                lines=[line.strip() for line in transcript.text.splitlines() if line.strip()],
                source="audio_transcript",
                meta={
                    **asset.meta,
                    "transcription_available": transcript.available,
                    "transcription_used": transcript.used,
                    "transcription_method": transcript.method,
                    "transcription_model": transcript.model,
                    "transcription_rationale": transcript.rationale,
                },
            )
        else:
            asset.meta.update(
                {
                    "transcription_available": transcript.available,
                    "transcription_used": transcript.used,
                    "transcription_method": transcript.method,
                    "transcription_model": transcript.model,
                    "transcription_rationale": transcript.rationale,
                }
            )
        stage_timings_ms["audio_transcription_ms"] = round((time.time() - stage_start) * 1000, 2)
    if category_result.category == "Video":
        transcript = transcribe_video_audio(file_path, transcriber=mistral_transcribe) if use_mistral else transcribe_video_audio(file_path)
        if transcript.text:
            from dataclasses import replace
            asset = replace(
                asset,
                text=transcript.text,
                lines=[line.strip() for line in transcript.text.splitlines() if line.strip()],
                source="video_transcript",
                meta={
                    **asset.meta,
                    "transcription_available": transcript.available,
                    "transcription_used": transcript.used,
                    "transcription_method": transcript.method,
                    "transcription_model": transcript.model,
                    "transcription_rationale": transcript.rationale,
                },
            )
        else:
            asset.meta.update(
                {
                    "transcription_available": transcript.available,
                    "transcription_used": transcript.used,
                    "transcription_method": transcript.method,
                    "transcription_model": transcript.model,
                    "transcription_rationale": transcript.rationale,
                }
            )
        stage_timings_ms["video_transcription_ms"] = round((time.time() - stage_start) * 1000, 2)
    quality = text_quality_ok(asset.text)
    stage_timings_ms["ocr_fallback_ms"] = round((time.time() - stage_start) * 1000, 2)
    
    # 3) Agriculture gate before the heavier classification pipeline
    stage_start = time.time()
    # For ambiguous-agriculture documents we can defer the Stage-3 agriculture LLM
    # and resolve it together with the document subtype in ONE combined call.
    merge_agri_subtype = (
        MERGE_AGRI_SUBCATEGORY_LLM
        and use_text_llm
        and LLM_CONFIGURED
        and category_result.category == "Document"
    )
    agri_relevance, agriculture_cache_hit = _assess_agriculture_cached(
        text=asset.text,
        lines=asset.lines,
        allow_llm_fallback=use_text_llm and LLM_CONFIGURED,
        llm_base_url=LLM_BASE_URL,
        llm_api_key=LLM_API_KEY,
        llm_model=LLM_MODEL,
        llm_configured=LLM_CONFIGURED,
        defer_llm=merge_agri_subtype,
    )

    merged_document_text_result = None
    if merge_agri_subtype and getattr(agri_relevance, "needs_llm_decision", False):
        from dataclasses import replace
        try:
            from docint.llm.subcategory_classify import llm_classify_document_with_agriculture

            combined = llm_classify_document_with_agriculture(
                asset.text,
                base_url=LLM_BASE_URL,
                api_key=LLM_API_KEY,
                model=LLM_MODEL,
                max_chars=15000,
                temperature=LLM_TEMPERATURE,
            )
            combined_is_agri = bool(combined.raw_json.get("is_agriculture_related", agri_relevance.is_agriculture_related))
            try:
                combined_conf = float(combined.raw_json.get("agriculture_confidence", agri_relevance.confidence))
            except (TypeError, ValueError):
                combined_conf = agri_relevance.confidence
            agri_relevance = replace(
                agri_relevance,
                is_agriculture_related=combined_is_agri,
                confidence=round(combined_conf, 4),
                score=round(combined_conf, 4),
                method="combined_agri_subtype_llm",
                stages_used=list(agri_relevance.stages_used) + ["combined_llm"],
                needs_llm_decision=False,
            )
            # Reuse this subtype result later instead of a second text-LLM call.
            merged_document_text_result = combined
            # Cache the finalised agriculture verdict under the same key.
            _cache_set(
                AGRICULTURE_CACHE,
                _agriculture_cache_key(asset.text, allow_llm_fallback=True, llm_configured=LLM_CONFIGURED, llm_model=LLM_MODEL),
                agri_relevance,
                AGRICULTURE_CACHE_TTL_SEC,
            )
        except Exception:
            # Fall back to the standard standalone agriculture LLM path.
            agri_relevance, agriculture_cache_hit = _assess_agriculture_cached(
                text=asset.text,
                lines=asset.lines,
                allow_llm_fallback=use_text_llm and LLM_CONFIGURED,
                llm_base_url=LLM_BASE_URL,
                llm_api_key=LLM_API_KEY,
                llm_model=LLM_MODEL,
                llm_configured=LLM_CONFIGURED,
                defer_llm=False,
            )
    stage_timings_ms["agriculture_pipeline_ms"] = round((time.time() - stage_start) * 1000, 2)
    agriculture_response = AgricultureRelevance(
        is_agriculture_related=agri_relevance.is_agriculture_related,
        confidence=round(agri_relevance.confidence, 4),
        score=round(agri_relevance.score, 4),
        method=agri_relevance.method,
        lexicon_version=agri_relevance.lexicon_version,
        matched_terms=agri_relevance.matched_terms,
        matched_buckets=agri_relevance.matched_buckets,
        matched_concepts=agri_relevance.matched_concepts,
        bucket_scores={k: round(v, 4) for k, v in agri_relevance.bucket_scores.items()},
        rationale=agri_relevance.rationale,
        stages_used=agri_relevance.stages_used,
        stage_results=[
            {
                "stage": item.stage,
                "available": item.available,
                "used": item.used,
                "is_agriculture_related": item.is_agriculture_related,
                "confidence": item.confidence,
                "rationale": item.rationale,
                "details": item.details,
            }
            for item in agri_relevance.stage_results
        ],
    )

    topics_response = _infer_topics_response(
        text=asset.text,
        lines=[line.strip() for line in asset.text.splitlines() if line.strip()][:20] or None,
        agri_relevance=agri_relevance,
    )
    _purpose_start = time.time()
    intended_purposes_response = _infer_intended_purposes_response(
        text=asset.text,
        agri_relevance=agri_relevance,
        use_text_llm=use_text_llm,
        llm_base_url=LLM_BASE_URL,
        llm_api_key=LLM_API_KEY,
        llm_model=LLM_MODEL,
        llm_configured=LLM_CONFIGURED,
    )
    stage_timings_ms["intended_purposes_ms"] = round((time.time() - _purpose_start) * 1000, 2)

    # KO-eligibility gate (file path): drop agriculture-related but NON-eligible
    # knowledge objects (job vacancies, tenders, event/call-for-applications notices)
    # before any subtype scoring — mirrors the URL path, which already does this.
    _elig_start = time.time()
    eligibility_result = _assess_ko_eligibility(
        text=asset.text,
        use_text_llm=use_text_llm,
        llm_base_url=LLM_BASE_URL,
        llm_api_key=LLM_API_KEY,
        llm_model=LLM_MODEL,
        llm_configured=LLM_CONFIGURED,
    )
    stage_timings_ms["ko_eligibility_ms"] = round((time.time() - _elig_start) * 1000, 2)
    if agriculture_response.is_agriculture_related and not eligibility_result["is_eligible"]:
        processing_time_ms = (time.time() - start_time) * 1000
        exclusion_label = (eligibility_result.get("exclusion_type") or "ineligible_content").replace("_", " ")
        return ClassificationResponse(
            best_match=None,
            all_candidates=[],
            fusion=None,
            heuristics=None,
            vision_llm=None,
            text_llm=None,
            category_used=category_result.category,
            category_inference=None,
            agriculture_relevance=agriculture_response,
            topics=topics_response,
            intended_purposes=intended_purposes_response,
            classification_skipped=True,
            skip_reason=f"Agriculture-related but not an eligible knowledge object: {exclusion_label}",
            total_candidates=0,
            confidence_threshold_met=False,
            document_info={
                "filename": filename,
                "pages": asset.units,
                "unit_label": asset.unit_label,
                "asset_type": asset.asset_type,
                "inferred_category": category_result.category,
                "source": asset.source,
                "text_length": len(asset.text),
                "text_quality": {
                    "chars": quality.metrics.get("chars"),
                    "letters": quality.metrics.get("letters"),
                    "letter_ratio": quality.metrics.get("letter_ratio"),
                    "ok": quality.ok,
                } if hasattr(quality, "metrics") else None,
            },
            processing_info={
                "processing_time_ms": round(processing_time_ms, 2),
                "ocr_used": asset.source == "ocr",
                "sources_used": [],
                "fusion_enabled": False,
                "require_agriculture": require_agriculture,
                "auto_route_models": auto_route_models,
                "eligibility_gate": eligibility_result,
                "stage_timings_ms": stage_timings_ms,
            },
        )

    if category_result.category == "Image":
        stage_start = time.time()
        unified_image_candidates, unified_image_best = _build_unified_candidates(
            category=category_result.category,
            text=asset.text,
            filename=filename,
            legacy_probs=None,
        )
        image_heuristics_best = unified_image_best.model_copy(deep=True) if unified_image_best else None
        stage_timings_ms["image_classification_ms"] = round((time.time() - stage_start) * 1000, 2)
        image_vision_result = None
        image_fusion = None

        if use_vision and VISION_LLM_BASE_URL:
            stage_start = time.time()
            try:
                from docint.llm.subcategory_classify import llm_classify_image_with_vision

                vlm_res = llm_classify_image_with_vision(
                    file_path,
                    base_url=VISION_LLM_BASE_URL,
                    api_key=VISION_LLM_API_KEY,
                    model=VISION_LLM_MODEL,
                    temperature=LLM_TEMPERATURE,
                )
                image_unified_key = vlm_res.get("subcategory")
                image_vision_result = {
                    "subcategory_key": image_unified_key,
                    "subcategory_name": load_unified_subtypes().get(image_unified_key).name if image_unified_key in load_unified_subtypes() else None,
                    "confidence": round(float(vlm_res.get("confidence", 0.0)), 4),
                    "rationale": vlm_res.get("rationale", ""),
                    "model": VISION_LLM_MODEL,
                    "agriculture_related": bool(vlm_res.get("is_agriculture_related", False)),
                    "agriculture_confidence": round(float(vlm_res.get("agriculture_confidence", 0.0)), 4),
                }
                agriculture_response.is_agriculture_related = bool(vlm_res.get("is_agriculture_related", agriculture_response.is_agriculture_related))
                agriculture_response.confidence = round(float(vlm_res.get("agriculture_confidence", agriculture_response.confidence)), 4)
                agriculture_response.score = agriculture_response.confidence
                agriculture_response.method = "image_vision_override"
                agriculture_response.rationale = str(vlm_res.get("rationale", agriculture_response.rationale))

                if unified_image_best:
                    heuristics_probs = {
                        candidate.subcategory_id: candidate.probability
                        for candidate in unified_image_candidates
                    }
                    heuristics_source = convert_to_source_result(
                        subcategory_key=unified_image_best.subcategory_id,
                        confidence=unified_image_best.confidence,
                        probs=heuristics_probs,
                        source_name="heuristics",
                        evidence_score=unified_image_best.evidence_score,
                        rationale=unified_image_best.rationale,
                    )
                    vision_source = convert_to_source_result(
                        subcategory_key=image_unified_key or list(heuristics_probs.keys())[0],
                        confidence=float(vlm_res.get("confidence", 0.0)),
                        probs=vlm_res.get("probs", {}),
                        source_name="vision_llm",
                        rationale=str(vlm_res.get("rationale", "")),
                    )
                    image_ocr_chars = int((quality.metrics or {}).get("chars", 0)) if hasattr(quality, "metrics") else 0
                    image_heuristics_alpha = min(heuristics_alpha, 0.35)
                    if image_ocr_chars < 120 or not quality.ok:
                        image_heuristics_alpha = 0.2
                    fusion_result = intelligent_fusion(
                        heuristics_result=heuristics_source,
                        vision_result=vision_source,
                        text_result=None,
                        strategy=FusionStrategy.CONFIDENCE_ADAPTIVE if fusion_strategy == "adaptive" else FusionStrategy.WEIGHTED,
                        heuristics_alpha=image_heuristics_alpha,
                        llm_alpha=1.0 - image_heuristics_alpha,
                    )
                    image_fusion = FusionInfo(
                        fused=True,
                        strategy=fusion_result.fusion_strategy,
                        weights=fusion_result.weights,
                        agreement_score=fusion_result.agreement_score,
                        rationale=fusion_result.rationale,
                    )
                    for candidate in unified_image_candidates:
                        fused_prob = round(fusion_result.probs.get(candidate.subcategory_id, 0), 4)
                        candidate.probability = fused_prob
                        candidate.confidence = fused_prob
                    unified_image_candidates.sort(key=lambda item: item.probability, reverse=True)
                    for idx, candidate in enumerate(unified_image_candidates, start=1):
                        candidate.rank = idx
                    add_contrastive_rationales(unified_image_candidates)
                    unified_image_best = unified_image_candidates[0] if unified_image_candidates else None
            except Exception as e:
                image_vision_result = {"error": str(e), "model": VISION_LLM_MODEL}
            stage_timings_ms["image_vision_llm_ms"] = round((time.time() - stage_start) * 1000, 2)

        if require_agriculture and not agriculture_response.is_agriculture_related:
            processing_time_ms = (time.time() - start_time) * 1000
            return ClassificationResponse(
                best_match=None,
                all_candidates=[],
                fusion=None,
                heuristics=None,
                vision_llm=image_vision_result,
                text_llm=None,
                category_used=category_result.category,
                category_inference=None,
                agriculture_relevance=agriculture_response,
            topics=topics_response,
            intended_purposes=intended_purposes_response,
                classification_skipped=True,
                skip_reason="Image classified as non-agriculture; image subcategory classification skipped",
                total_candidates=0,
                confidence_threshold_met=False,
                document_info={
                    "filename": filename,
                    "pages": asset.units,
                    "unit_label": asset.unit_label,
                    "asset_type": asset.asset_type,
                    "inferred_category": category_result.category,
                    "source": asset.source,
                    "text_length": len(asset.text),
                    "text_quality": {
                        "chars": quality.metrics.get("chars"),
                        "letters": quality.metrics.get("letters"),
                        "letter_ratio": quality.metrics.get("letter_ratio"),
                        "ok": quality.ok,
                    } if hasattr(quality, 'metrics') else None,
                },
                processing_info={
                    "processing_time_ms": round(processing_time_ms, 2),
                    "ocr_used": asset.source == "ocr",
                    "sources_used": ["vision_llm"] if image_vision_result and "error" not in image_vision_result else [],
                    "fusion_enabled": False,
                    "require_agriculture": require_agriculture,
                    "auto_route_models": auto_route_models,
                    "stage_timings_ms": stage_timings_ms,
                },
            )

        processing_time_ms = (time.time() - start_time) * 1000
        unified_image_heuristics = image_heuristics_best
        return ClassificationResponse(
            best_match=unified_image_best,
            all_candidates=unified_image_candidates,
            fusion=image_fusion,
            heuristics=unified_image_heuristics,
            vision_llm=_map_llm_payload_to_unified(image_vision_result),
            text_llm=None,
            category_used=category_result.category,
            category_inference=None,
            agriculture_relevance=agriculture_response,
            topics=topics_response,
            intended_purposes=intended_purposes_response,
            classification_skipped=False,
            skip_reason=None,
            total_candidates=len(unified_image_candidates),
            confidence_threshold_met=bool(unified_image_best and unified_image_best.confidence >= classification_confidence_threshold),
            document_info={
                "filename": filename,
                "pages": asset.units,
                "unit_label": asset.unit_label,
                "asset_type": asset.asset_type,
                "inferred_category": category_result.category,
                "source": asset.source,
                "text_length": len(asset.text),
                "text_quality": {
                    "chars": quality.metrics.get("chars"),
                    "letters": quality.metrics.get("letters"),
                    "letter_ratio": quality.metrics.get("letter_ratio"),
                    "ok": quality.ok,
                } if hasattr(quality, 'metrics') else None,
            },
            processing_info={
                "processing_time_ms": round(processing_time_ms, 2),
                "ocr_used": asset.source == "ocr",
                "sources_used": ["heuristics"] + (["vision_llm"] if image_vision_result and "error" not in image_vision_result else []),
                "fusion_enabled": image_fusion is not None,
                "require_agriculture": require_agriculture,
                "auto_route_models": auto_route_models,
                "routing": {
                    "image_mode": True,
                    "text_llm": {"requested": use_text_llm, "used": False, "reason": "image_text_llm_not_enabled"},
                    "vision_llm": {"requested": use_vision, "used": image_vision_result is not None and "error" not in image_vision_result, "reasons": ["image_primary_classifier"]},
                },
                "classification_confidence_threshold": classification_confidence_threshold,
                "stage_timings_ms": stage_timings_ms,
            },
        )

    if category_result.category == "Video":
        language_info = detect_text_language(asset.text)
        non_english_llm_primary = bool(language_info["non_english_llm_primary"] and use_text_llm and LLM_CONFIGURED)
        stage_start = time.time()
        unified_video_candidates, unified_video_best = _build_unified_candidates(
            category=category_result.category,
            text=asset.text,
            filename=filename,
            legacy_probs=None,
        )
        video_heuristics_best = unified_video_best.model_copy(deep=True) if unified_video_best else None
        stage_timings_ms["video_classification_ms"] = round((time.time() - stage_start) * 1000, 2)
        video_text_result = None
        video_text_source = None
        video_vision_result = None
        video_vision_source = None
        video_fusion = None

        if use_text_llm and LLM_CONFIGURED and asset.text.strip():
            stage_start = time.time()
            try:
                from docint.llm.subcategory_classify import llm_classify_video_subcategories_text

                llm_res = llm_classify_video_subcategories_text(
                    asset.text,
                    base_url=LLM_BASE_URL,
                    api_key=LLM_API_KEY,
                    model=LLM_MODEL,
                    max_chars=12000,
                    temperature=LLM_TEMPERATURE,
                )
                video_text_source = convert_to_source_result(
                    subcategory_key=llm_res.subcategory_key,
                    confidence=llm_res.confidence,
                    probs=llm_res.probs,
                    source_name="text_llm",
                    rationale=llm_res.rationale,
                )
                video_text_result = {
                    "subcategory_key": llm_res.subcategory_key,
                    "subcategory_name": llm_res.subcategory_name,
                    "confidence": round(llm_res.confidence, 4),
                    "rationale": llm_res.rationale,
                    "model": LLM_MODEL,
                }
            except Exception as e:
                video_text_result = {"error": str(e), "model": LLM_MODEL}
            stage_timings_ms["video_text_llm_ms"] = round((time.time() - stage_start) * 1000, 2)

        if use_vision and VISION_LLM_BASE_URL and not non_english_llm_primary:
            stage_start = time.time()
            try:
                from docint.llm.subcategory_classify import llm_classify_video_with_vision

                frame_sampling = sample_video_frames(file_path, max_frames=min(vision_max_pages, 8))
                stage_timings_ms["video_frame_sampling_ms"] = round((time.time() - stage_start) * 1000, 2)
                if frame_sampling.frame_paths:
                    vlm_res = llm_classify_video_with_vision(
                        frame_sampling.frame_paths,
                        asset.text,
                        base_url=VISION_LLM_BASE_URL,
                        api_key=VISION_LLM_API_KEY,
                        model=VISION_LLM_MODEL,
                        temperature=LLM_TEMPERATURE,
                    )
                    video_vision_result = {
                        "subcategory_key": vlm_res.get("subcategory"),
                        "subcategory_name": load_unified_subtypes().get(vlm_res.get("subcategory")).name if vlm_res.get("subcategory") in load_unified_subtypes() else None,
                        "confidence": round(float(vlm_res.get("confidence", 0.0)), 4),
                        "rationale": vlm_res.get("rationale", ""),
                        "model": VISION_LLM_MODEL,
                        "agriculture_related": bool(vlm_res.get("is_agriculture_related", False)),
                        "agriculture_confidence": round(float(vlm_res.get("agriculture_confidence", 0.0)), 4),
                        "sampled_frame_count": int(vlm_res.get("sampled_frame_count", len(frame_sampling.frame_paths))),
                    }
                    agriculture_response.is_agriculture_related = bool(vlm_res.get("is_agriculture_related", agriculture_response.is_agriculture_related))
                    agriculture_response.confidence = round(float(vlm_res.get("agriculture_confidence", agriculture_response.confidence)), 4)
                    agriculture_response.score = agriculture_response.confidence
                    agriculture_response.method = "video_vision_override"
                    agriculture_response.rationale = str(vlm_res.get("rationale", agriculture_response.rationale))
                    fallback_key = unified_video_best.subcategory_id if unified_video_best else next(iter(_unified_key_by_name().values()), "")
                    video_vision_source = convert_to_source_result(
                        subcategory_key=vlm_res.get("subcategory") or fallback_key,
                        confidence=float(vlm_res.get("confidence", 0.0)),
                        probs=vlm_res.get("probs", {}),
                        source_name="vision_llm",
                        rationale=str(vlm_res.get("rationale", "")),
                    )
                else:
                    video_vision_result = {
                        "error": frame_sampling.rationale,
                        "model": VISION_LLM_MODEL,
                    }
            except Exception as e:
                video_vision_result = {"error": str(e), "model": VISION_LLM_MODEL}
            stage_timings_ms["video_vision_llm_ms"] = round((time.time() - stage_start) * 1000, 2)

        if require_agriculture and not agriculture_response.is_agriculture_related:
            processing_time_ms = (time.time() - start_time) * 1000
            return ClassificationResponse(
                best_match=None,
                all_candidates=[],
                fusion=None,
                heuristics=None,
                vision_llm=video_vision_result,
                text_llm=video_text_result,
                category_used=category_result.category,
                category_inference=None,
                agriculture_relevance=agriculture_response,
            topics=topics_response,
            intended_purposes=intended_purposes_response,
                classification_skipped=True,
                skip_reason="Video classified as non-agriculture; video subcategory classification skipped",
                total_candidates=0,
                confidence_threshold_met=False,
                document_info={
                    "filename": filename,
                    "pages": asset.units,
                    "unit_label": asset.unit_label,
                    "asset_type": asset.asset_type,
                    "inferred_category": category_result.category,
                    "source": asset.source,
                    "text_length": len(asset.text),
                    "text_quality": {
                        "chars": quality.metrics.get("chars"),
                        "letters": quality.metrics.get("letters"),
                        "letter_ratio": quality.metrics.get("letter_ratio"),
                        "ok": quality.ok,
                    } if hasattr(quality, 'metrics') else None,
                },
                processing_info={
                    "processing_time_ms": round(processing_time_ms, 2),
                    "ocr_used": False,
                    "sources_used": [src for src, val in [("text_llm", video_text_result), ("vision_llm", video_vision_result)] if val and "error" not in val],
                    "fusion_enabled": False,
                    "require_agriculture": require_agriculture,
                    "auto_route_models": auto_route_models,
                    "stage_timings_ms": stage_timings_ms,
                },
            )

        if not asset.text.strip() and not (video_vision_result and "error" not in video_vision_result):
            processing_time_ms = (time.time() - start_time) * 1000
            return ClassificationResponse(
                best_match=None,
                all_candidates=[],
                fusion=None,
                heuristics=None,
                vision_llm=video_vision_result,
                text_llm=video_text_result,
                category_used=category_result.category,
                category_inference=None,
                agriculture_relevance=agriculture_response,
            topics=topics_response,
            intended_purposes=intended_purposes_response,
                classification_skipped=True,
                skip_reason="Video transcript and sampled-frame evidence unavailable; video subtype classification skipped",
                total_candidates=0,
                confidence_threshold_met=False,
                document_info={
                    "filename": filename,
                    "pages": asset.units,
                    "unit_label": asset.unit_label,
                    "asset_type": asset.asset_type,
                    "inferred_category": category_result.category,
                    "source": asset.source,
                    "text_length": len(asset.text),
                    "text_quality": {
                        "chars": quality.metrics.get("chars"),
                        "letters": quality.metrics.get("letters"),
                        "letter_ratio": quality.metrics.get("letter_ratio"),
                        "ok": quality.ok,
                    } if hasattr(quality, 'metrics') else None,
                },
                processing_info={
                    "processing_time_ms": round(processing_time_ms, 2),
                    "ocr_used": False,
                    "sources_used": [],
                    "fusion_enabled": False,
                    "require_agriculture": require_agriculture,
                    "auto_route_models": auto_route_models,
                    "stage_timings_ms": stage_timings_ms,
                },
            )

        if non_english_llm_primary and video_text_source:
            _apply_source_probabilities(unified_video_candidates, video_text_source.probs, _unified_key_by_name())
            unified_video_best = unified_video_candidates[0] if unified_video_candidates else None
            add_contrastive_rationales(unified_video_candidates)
        elif unified_video_best:
            video_heuristics_probs = {
                candidate.subcategory_id: candidate.probability
                for candidate in unified_video_candidates
            }
            video_heuristics_source = convert_to_source_result(
                subcategory_key=unified_video_best.subcategory_id,
                confidence=unified_video_best.confidence,
                probs=video_heuristics_probs,
                source_name="heuristics",
                evidence_score=unified_video_best.evidence_score,
                rationale=unified_video_best.rationale,
            )
            if video_text_source or video_vision_source:
                transcript_chars = int((quality.metrics or {}).get("chars", 0)) if hasattr(quality, "metrics") else 0
                if video_text_source and video_vision_source:
                    video_heuristics_alpha = 0.28 if transcript_chars < 250 else 0.24
                elif video_text_source:
                    video_heuristics_alpha = 0.34 if transcript_chars >= 250 else 0.26
                else:
                    video_heuristics_alpha = 0.18
                fusion_result = intelligent_fusion(
                    heuristics_result=video_heuristics_source,
                    vision_result=video_vision_source,
                    text_result=video_text_source,
                    strategy=FusionStrategy.CONFIDENCE_ADAPTIVE if fusion_strategy == "adaptive" else FusionStrategy.WEIGHTED,
                    heuristics_alpha=video_heuristics_alpha,
                    llm_alpha=1.0 - video_heuristics_alpha,
                )
                video_fusion = FusionInfo(
                    fused=True,
                    strategy=fusion_result.fusion_strategy,
                    weights=fusion_result.weights,
                    agreement_score=fusion_result.agreement_score,
                    rationale=fusion_result.rationale,
                )
                for candidate in unified_video_candidates:
                    fused_prob = round(fusion_result.probs.get(candidate.subcategory_id, 0), 4)
                    candidate.probability = fused_prob
                    candidate.confidence = fused_prob
                unified_video_candidates.sort(key=lambda item: item.probability, reverse=True)
                for idx, candidate in enumerate(unified_video_candidates, start=1):
                    candidate.rank = idx
                unified_video_best = unified_video_candidates[0] if unified_video_candidates else None
                add_contrastive_rationales(unified_video_candidates)

        processing_time_ms = (time.time() - start_time) * 1000
        unified_video_heuristics = video_heuristics_best
        return ClassificationResponse(
            best_match=unified_video_best,
            all_candidates=unified_video_candidates,
            fusion=video_fusion,
            heuristics=unified_video_heuristics,
            vision_llm=_map_llm_payload_to_unified(video_vision_result),
            text_llm=_map_llm_payload_to_unified(video_text_result),
            category_used=category_result.category,
            category_inference=None,
            agriculture_relevance=agriculture_response,
            topics=topics_response,
            intended_purposes=intended_purposes_response,
            classification_skipped=False,
            skip_reason=None,
            total_candidates=len(unified_video_candidates),
            confidence_threshold_met=bool(unified_video_best and unified_video_best.confidence >= classification_confidence_threshold),
            document_info={
                "filename": filename,
                "pages": asset.units,
                "unit_label": asset.unit_label,
                "asset_type": asset.asset_type,
                "inferred_category": category_result.category,
                "source": asset.source,
                "text_length": len(asset.text),
                "text_quality": {
                    "chars": quality.metrics.get("chars"),
                    "letters": quality.metrics.get("letters"),
                    "letter_ratio": quality.metrics.get("letter_ratio"),
                    "ok": quality.ok,
                } if hasattr(quality, 'metrics') else None,
            },
            processing_info={
                "processing_time_ms": round(processing_time_ms, 2),
                "ocr_used": False,
                "sources_used": ["heuristics"] + (["text_llm"] if video_text_result is not None and "error" not in video_text_result else []) + (["vision_llm"] if video_vision_result is not None and "error" not in video_vision_result else []),
                "fusion_enabled": video_fusion is not None,
                "require_agriculture": require_agriculture,
                "auto_route_models": auto_route_models,
                "routing": {
                    "video_mode": True,
                    "text_llm": {"requested": use_text_llm, "used": video_text_result is not None and "error" not in video_text_result, "reason": "video_text_llm_enabled" if use_text_llm else "disabled"},
                    "vision_llm": {"requested": use_vision, "used": video_vision_result is not None and "error" not in video_vision_result, "reasons": ["video_frame_sampling"] if video_vision_result and "error" not in video_vision_result else (["non_english_text_llm_primary"] if non_english_llm_primary else [])},
                    "language_detection": language_info,
                },
                "classification_confidence_threshold": classification_confidence_threshold,
                "stage_timings_ms": stage_timings_ms,
            },
        )

    if category_result.category == "Audio" and not asset.text.strip():
        processing_time_ms = (time.time() - start_time) * 1000
        agriculture_response = AgricultureRelevance(
            is_agriculture_related=False,
            confidence=0.0,
            score=0.0,
            method="audio_transcript_unavailable",
            lexicon_version="not_applicable",
            matched_terms=[],
            matched_buckets=[],
            matched_concepts=[],
            bucket_scores={},
            rationale="Audio transcription was unavailable or produced no usable transcript, so agriculture relevance could not be assessed reliably",
            stages_used=["audio_transcription"],
            stage_results=[
                {
                    "stage": "audio_transcription",
                    "available": bool(asset.meta.get("transcription_available", False)),
                    "used": bool(asset.meta.get("transcription_used", False)),
                    "is_agriculture_related": False,
                    "confidence": 0.0,
                    "rationale": asset.meta.get("transcription_rationale", "No usable transcript available"),
                    "details": {
                        "transcription_method": asset.meta.get("transcription_method"),
                        "transcription_model": asset.meta.get("transcription_model"),
                    },
                }
            ],
        )
        return ClassificationResponse(
            best_match=None,
            all_candidates=[],
            fusion=None,
            heuristics=None,
            vision_llm=None,
            text_llm=None,
            category_used=category_result.category,
            category_inference=None,
            agriculture_relevance=agriculture_response,
            topics=topics_response,
            intended_purposes=intended_purposes_response,
            classification_skipped=True,
            skip_reason="Audio transcription unavailable; agriculture and audio subtype classification skipped",
            total_candidates=0,
            confidence_threshold_met=False,
            document_info={
                "filename": filename,
                "pages": asset.units,
                "unit_label": asset.unit_label,
                "asset_type": asset.asset_type,
                "inferred_category": category_result.category,
                "source": asset.source,
                "text_length": len(asset.text),
                "text_quality": {
                    "chars": quality.metrics.get("chars"),
                    "letters": quality.metrics.get("letters"),
                    "letter_ratio": quality.metrics.get("letter_ratio"),
                    "ok": quality.ok,
                } if hasattr(quality, 'metrics') else None,
            },
            processing_info={
                "processing_time_ms": round(processing_time_ms, 2),
                "ocr_used": False,
                "sources_used": [],
                "fusion_enabled": False,
                "require_agriculture": require_agriculture,
                "auto_route_models": auto_route_models,
                "stage_timings_ms": stage_timings_ms,
            },
        )

    if require_agriculture and not agri_relevance.is_agriculture_related:
        processing_time_ms = (time.time() - start_time) * 1000
        return ClassificationResponse(
            best_match=None,
            all_candidates=[],
            fusion=None,
            heuristics=None,
            vision_llm=None,
            text_llm=None,
            category_used=category_result.category,
            category_inference=None,
            agriculture_relevance=agriculture_response,
            topics=topics_response,
            intended_purposes=intended_purposes_response,
            classification_skipped=True,
            skip_reason=f"{category_result.category} classified as non-agriculture; subcategory classification skipped",
            total_candidates=0,
            confidence_threshold_met=False,
            document_info={
                "filename": filename,
                "pages": asset.units,
                "unit_label": asset.unit_label,
                "asset_type": asset.asset_type,
                "inferred_category": category_result.category,
                "source": asset.source,
                "text_length": len(asset.text),
                "text_quality": {
                    "chars": quality.metrics.get("chars"),
                    "letters": quality.metrics.get("letters"),
                    "letter_ratio": quality.metrics.get("letter_ratio"),
                    "ok": quality.ok,
                } if hasattr(quality, 'metrics') else None,
            },
            processing_info={
                "processing_time_ms": round(processing_time_ms, 2),
                "ocr_used": asset.source == "ocr",
                "sources_used": [],
                "fusion_enabled": False,
                "require_agriculture": require_agriculture,
                "auto_route_models": auto_route_models,
                "stage_timings_ms": stage_timings_ms,
            },
        )

    if category_result.category == "Audio":
        language_info = detect_text_language(asset.text)
        non_english_llm_primary = bool(language_info["non_english_llm_primary"] and use_text_llm and LLM_CONFIGURED)
        stage_start = time.time()
        unified_audio_candidates, unified_audio_best = _build_unified_candidates(
            category=category_result.category,
            text=asset.text,
            filename=filename,
            legacy_probs=None,
        )
        audio_heuristics_best = unified_audio_best.model_copy(deep=True) if unified_audio_best else None
        stage_timings_ms["audio_classification_ms"] = round((time.time() - stage_start) * 1000, 2)
        audio_text_result = None
        audio_text_source = None
        audio_fusion = None

        if use_text_llm and LLM_CONFIGURED:
            stage_start = time.time()
            try:
                from docint.llm.subcategory_classify import llm_classify_audio_subcategories_text

                llm_res = llm_classify_audio_subcategories_text(
                    asset.text,
                    base_url=LLM_BASE_URL,
                    api_key=LLM_API_KEY,
                    model=LLM_MODEL,
                    max_chars=12000,
                    temperature=LLM_TEMPERATURE,
                )
                audio_text_source = convert_to_source_result(
                    subcategory_key=llm_res.subcategory_key,
                    confidence=llm_res.confidence,
                    probs=llm_res.probs,
                    source_name="text_llm",
                    rationale=llm_res.rationale,
                )
                audio_text_result = {
                    "subcategory_key": llm_res.subcategory_key,
                    "subcategory_name": llm_res.subcategory_name,
                    "confidence": round(llm_res.confidence, 4),
                    "rationale": llm_res.rationale,
                    "model": LLM_MODEL,
                }
            except Exception as e:
                audio_text_result = {"error": str(e), "model": LLM_MODEL}
            stage_timings_ms["audio_text_llm_ms"] = round((time.time() - stage_start) * 1000, 2)

        if non_english_llm_primary and audio_text_source:
            _apply_source_probabilities(unified_audio_candidates, audio_text_source.probs, _unified_key_by_name())
            unified_audio_best = unified_audio_candidates[0] if unified_audio_candidates else None
            add_contrastive_rationales(unified_audio_candidates)
        elif unified_audio_best and audio_text_source:
            audio_heuristics_probs = {
                candidate.subcategory_id: candidate.probability
                for candidate in unified_audio_candidates
            }
            audio_heuristics_source = convert_to_source_result(
                subcategory_key=unified_audio_best.subcategory_id,
                confidence=unified_audio_best.confidence,
                probs=audio_heuristics_probs,
                source_name="heuristics",
                evidence_score=unified_audio_best.evidence_score,
                rationale=unified_audio_best.rationale,
            )
            transcript_chars = int((quality.metrics or {}).get("chars", 0)) if hasattr(quality, "metrics") else 0
            audio_heuristics_alpha = 0.30 if transcript_chars >= 250 else 0.22
            fusion_result = intelligent_fusion(
                heuristics_result=audio_heuristics_source,
                vision_result=None,
                text_result=audio_text_source,
                strategy=FusionStrategy.CONFIDENCE_ADAPTIVE if fusion_strategy == "adaptive" else FusionStrategy.WEIGHTED,
                heuristics_alpha=audio_heuristics_alpha,
                llm_alpha=1.0 - audio_heuristics_alpha,
            )
            audio_fusion = FusionInfo(
                fused=True,
                strategy=fusion_result.fusion_strategy,
                weights=fusion_result.weights,
                agreement_score=fusion_result.agreement_score,
                rationale=fusion_result.rationale,
            )
            for candidate in unified_audio_candidates:
                fused_prob = round(fusion_result.probs.get(candidate.subcategory_id, 0), 4)
                candidate.probability = fused_prob
                candidate.confidence = fused_prob
            unified_audio_candidates.sort(key=lambda item: item.probability, reverse=True)
            for idx, candidate in enumerate(unified_audio_candidates, start=1):
                candidate.rank = idx
            unified_audio_best = unified_audio_candidates[0] if unified_audio_candidates else None
            add_contrastive_rationales(unified_audio_candidates)

        processing_time_ms = (time.time() - start_time) * 1000
        unified_audio_heuristics = audio_heuristics_best
        return ClassificationResponse(
            best_match=unified_audio_best,
            all_candidates=unified_audio_candidates,
            fusion=audio_fusion,
            heuristics=unified_audio_heuristics,
            vision_llm=None,
            text_llm=_map_llm_payload_to_unified(audio_text_result),
            category_used=category_result.category,
            category_inference=None,
            agriculture_relevance=agriculture_response,
            topics=topics_response,
            intended_purposes=intended_purposes_response,
            classification_skipped=False,
            skip_reason=None,
            total_candidates=len(unified_audio_candidates),
            confidence_threshold_met=bool(unified_audio_best and unified_audio_best.confidence >= classification_confidence_threshold),
            document_info={
                "filename": filename,
                "pages": asset.units,
                "unit_label": asset.unit_label,
                "asset_type": asset.asset_type,
                "inferred_category": category_result.category,
                "source": asset.source,
                "text_length": len(asset.text),
                "text_quality": {
                    "chars": quality.metrics.get("chars"),
                    "letters": quality.metrics.get("letters"),
                    "letter_ratio": quality.metrics.get("letter_ratio"),
                    "ok": quality.ok,
                } if hasattr(quality, 'metrics') else None,
            },
            processing_info={
                "processing_time_ms": round(processing_time_ms, 2),
                "ocr_used": False,
                "sources_used": ["heuristics"] + (["text_llm"] if audio_text_result is not None and "error" not in audio_text_result else []),
                "fusion_enabled": audio_fusion is not None,
                "require_agriculture": require_agriculture,
                "auto_route_models": auto_route_models,
                "routing": {
                    "audio_mode": True,
                    "text_llm": {"requested": use_text_llm, "used": audio_text_result is not None and "error" not in audio_text_result, "reason": "audio_text_llm_enabled" if use_text_llm else "disabled"},
                    "vision_llm": {"requested": use_vision, "used": False, "reasons": ["audio_vision_not_applicable"]},
                    "language_detection": language_info,
                },
                "classification_confidence_threshold": classification_confidence_threshold,
                "stage_timings_ms": stage_timings_ms,
            },
        )

    if category_result.category == "Dataset":
        language_info = detect_text_language(asset.text)
        non_english_llm_primary = bool(language_info["non_english_llm_primary"] and use_text_llm and LLM_CONFIGURED)
        stage_start = time.time()
        unified_dataset_candidates, unified_dataset_best = _build_unified_candidates(
            category=category_result.category,
            text=asset.text,
            filename=filename,
            legacy_probs={},
        )
        dataset_heuristics_best = unified_dataset_best.model_copy(deep=True) if unified_dataset_best else None
        stage_timings_ms["dataset_classification_ms"] = round((time.time() - stage_start) * 1000, 2)
        dataset_text_result = None
        dataset_text_source = None
        dataset_fusion = None
        should_use_dataset_text_llm = (
            use_text_llm
            and LLM_CONFIGURED
            and (
                non_english_llm_primary
                or unified_dataset_best is None
                or unified_dataset_best.confidence < classification_confidence_threshold
                or _top_probability_gap(unified_dataset_candidates) < TEXT_LLM_GAP_THRESHOLD
            )
        )

        if should_use_dataset_text_llm:
            stage_start = time.time()
            try:
                from docint.llm.subcategory_classify import llm_classify_dataset_subcategories_text

                llm_res = llm_classify_dataset_subcategories_text(
                    asset.text,
                    base_url=LLM_BASE_URL,
                    api_key=LLM_API_KEY,
                    model=LLM_MODEL,
                    max_chars=12000,
                    temperature=LLM_TEMPERATURE,
                )
                dataset_text_source = convert_to_source_result(
                    subcategory_key=llm_res.subcategory_key,
                    confidence=llm_res.confidence,
                    probs=llm_res.probs,
                    source_name="text_llm",
                    rationale=llm_res.rationale,
                )
                dataset_text_result = {
                    "subcategory_key": llm_res.subcategory_key,
                    "subcategory_name": llm_res.subcategory_name,
                    "confidence": round(llm_res.confidence, 4),
                    "rationale": llm_res.rationale,
                    "model": LLM_MODEL,
                    "probs": llm_res.probs,
                }
            except Exception as e:
                dataset_text_result = {"error": str(e), "model": LLM_MODEL}
            stage_timings_ms["dataset_text_llm_ms"] = round((time.time() - stage_start) * 1000, 2)

        if non_english_llm_primary and dataset_text_source:
            _apply_source_probabilities(unified_dataset_candidates, dataset_text_source.probs, _unified_key_by_name())
            unified_dataset_best = unified_dataset_candidates[0] if unified_dataset_candidates else None
            add_contrastive_rationales(unified_dataset_candidates)
        elif unified_dataset_best and dataset_text_source:
            dataset_heuristics_source = convert_to_source_result(
                subcategory_key=unified_dataset_best.subcategory_id,
                confidence=unified_dataset_best.confidence,
                probs={candidate.subcategory_id: candidate.probability for candidate in unified_dataset_candidates},
                source_name="heuristics",
                evidence_score=unified_dataset_best.evidence_score,
                rationale=unified_dataset_best.rationale,
            )
            dataset_alpha = 0.42 if len(asset.text) >= 1200 else 0.32
            fusion_result = intelligent_fusion(
                heuristics_result=dataset_heuristics_source,
                vision_result=None,
                text_result=dataset_text_source,
                strategy=FusionStrategy.CONFIDENCE_ADAPTIVE if fusion_strategy == "adaptive" else FusionStrategy.WEIGHTED,
                heuristics_alpha=dataset_alpha,
                llm_alpha=1.0 - dataset_alpha,
            )
            dataset_fusion = FusionInfo(
                fused=True,
                strategy=fusion_result.fusion_strategy,
                weights=fusion_result.weights,
                agreement_score=fusion_result.agreement_score,
                rationale=fusion_result.rationale,
            )
            for candidate in unified_dataset_candidates:
                fused_prob = round(fusion_result.probs.get(candidate.subcategory_id, 0), 4)
                candidate.probability = fused_prob
                candidate.confidence = fused_prob
            unified_dataset_candidates.sort(key=lambda item: item.probability, reverse=True)
            for idx, candidate in enumerate(unified_dataset_candidates, start=1):
                candidate.rank = idx
            _apply_dataset_consensus_boost(
                unified_dataset_candidates,
                heuristics_best=dataset_heuristics_best,
                text_source=dataset_text_source,
                fusion_info=dataset_fusion,
            )
            unified_dataset_best = unified_dataset_candidates[0] if unified_dataset_candidates else None
            add_contrastive_rationales(unified_dataset_candidates)
        processing_time_ms = (time.time() - start_time) * 1000
        return ClassificationResponse(
            best_match=unified_dataset_best,
            all_candidates=unified_dataset_candidates,
            fusion=dataset_fusion,
            heuristics=dataset_heuristics_best,
            vision_llm=None,
            text_llm=_map_llm_payload_to_unified(dataset_text_result),
            category_used=category_result.category,
            category_inference=None,
            agriculture_relevance=agriculture_response,
            topics=topics_response,
            intended_purposes=intended_purposes_response,
            classification_skipped=False,
            skip_reason=None,
            total_candidates=len(unified_dataset_candidates),
            confidence_threshold_met=bool(unified_dataset_best and unified_dataset_best.confidence >= classification_confidence_threshold),
            document_info={
                "filename": filename,
                "pages": asset.units,
                "unit_label": asset.unit_label,
                "asset_type": asset.asset_type,
                "inferred_category": category_result.category,
                "source": asset.source,
                "text_length": len(asset.text),
                "text_quality": {
                    "chars": quality.metrics.get("chars"),
                    "letters": quality.metrics.get("letters"),
                    "letter_ratio": quality.metrics.get("letter_ratio"),
                    "ok": quality.ok,
                } if hasattr(quality, 'metrics') else None,
            },
            processing_info={
                "processing_time_ms": round(processing_time_ms, 2),
                "ocr_used": asset.source == "ocr",
                "sources_used": ["heuristics"] + (["text_llm"] if dataset_text_result is not None and "error" not in dataset_text_result else []),
                "fusion_enabled": dataset_fusion is not None,
                "require_agriculture": require_agriculture,
                "auto_route_models": auto_route_models,
                "routing": {
                    "dataset_mode": True,
                    "text_llm": {"requested": use_text_llm, "used": dataset_text_result is not None and "error" not in dataset_text_result, "reason": "dataset_text_llm_enabled" if should_use_dataset_text_llm else "heuristics_strong_enough"},
                    "vision_llm": {"requested": use_vision, "used": False, "reasons": ["dataset_vision_not_yet_enabled"]},
                    "language_detection": language_info,
                },
                "classification_confidence_threshold": classification_confidence_threshold,
                "stage_timings_ms": stage_timings_ms,
            },
        )

    if category_result.category == "Software Application":
        language_info = detect_text_language(asset.text)
        non_english_llm_primary = bool(language_info["non_english_llm_primary"] and use_text_llm and LLM_CONFIGURED)
        stage_start = time.time()
        unified_software_candidates, unified_software_best = _build_unified_candidates(
            category=category_result.category,
            text=asset.text,
            filename=filename,
            legacy_probs={},
        )
        software_heuristics_best = unified_software_best.model_copy(deep=True) if unified_software_best else None
        stage_timings_ms["software_classification_ms"] = round((time.time() - stage_start) * 1000, 2)
        software_text_result = None
        software_text_source = None
        software_fusion = None

        should_use_software_text_llm = (
            use_text_llm
            and LLM_CONFIGURED
            and (
                non_english_llm_primary
                or unified_software_best is None
                or unified_software_best.confidence < classification_confidence_threshold
                or _top_probability_gap(unified_software_candidates) < TEXT_LLM_GAP_THRESHOLD
            )
        )

        if should_use_software_text_llm:
            stage_start = time.time()
            try:
                from docint.llm.subcategory_classify import llm_classify_software_subcategories_text

                llm_res = llm_classify_software_subcategories_text(
                    asset.text,
                    base_url=LLM_BASE_URL,
                    api_key=LLM_API_KEY,
                    model=LLM_MODEL,
                    max_chars=12000,
                    temperature=LLM_TEMPERATURE,
                )
                software_text_source = convert_to_source_result(
                    subcategory_key=llm_res.subcategory_key,
                    confidence=llm_res.confidence,
                    probs=llm_res.probs,
                    source_name="text_llm",
                    rationale=llm_res.rationale,
                )
                software_text_result = {
                    "subcategory_key": llm_res.subcategory_key,
                    "subcategory_name": llm_res.subcategory_name,
                    "confidence": round(llm_res.confidence, 4),
                    "rationale": llm_res.rationale,
                    "model": LLM_MODEL,
                    "probs": llm_res.probs,
                }
            except Exception as e:
                software_text_result = {"error": str(e), "model": LLM_MODEL}
            stage_timings_ms["software_text_llm_ms"] = round((time.time() - stage_start) * 1000, 2)

        if non_english_llm_primary and software_text_source:
            _apply_source_probabilities(unified_software_candidates, software_text_source.probs, _unified_key_by_name())
            unified_software_best = unified_software_candidates[0] if unified_software_candidates else None
            add_contrastive_rationales(unified_software_candidates)
        elif unified_software_best and software_text_source:
            software_heuristics_source = convert_to_source_result(
                subcategory_key=unified_software_best.subcategory_id,
                confidence=unified_software_best.confidence,
                probs={candidate.subcategory_id: candidate.probability for candidate in unified_software_candidates},
                source_name="heuristics",
                evidence_score=unified_software_best.evidence_score,
                rationale=unified_software_best.rationale,
            )
            software_alpha = 0.38 if len(asset.text) >= 1200 else 0.28
            fusion_result = intelligent_fusion(
                heuristics_result=software_heuristics_source,
                vision_result=None,
                text_result=software_text_source,
                strategy=FusionStrategy.CONFIDENCE_ADAPTIVE if fusion_strategy == "adaptive" else FusionStrategy.WEIGHTED,
                heuristics_alpha=software_alpha,
                llm_alpha=1.0 - software_alpha,
            )
            software_fusion = FusionInfo(
                fused=True,
                strategy=fusion_result.fusion_strategy,
                weights=fusion_result.weights,
                agreement_score=fusion_result.agreement_score,
                rationale=fusion_result.rationale,
            )
            for candidate in unified_software_candidates:
                fused_prob = round(fusion_result.probs.get(candidate.subcategory_id, 0), 4)
                candidate.probability = fused_prob
                candidate.confidence = fused_prob
            unified_software_candidates.sort(key=lambda item: item.probability, reverse=True)
            for idx, candidate in enumerate(unified_software_candidates, start=1):
                candidate.rank = idx
            unified_software_best = unified_software_candidates[0] if unified_software_candidates else None
            add_contrastive_rationales(unified_software_candidates)

        processing_time_ms = (time.time() - start_time) * 1000
        return ClassificationResponse(
            best_match=unified_software_best,
            all_candidates=unified_software_candidates,
            fusion=software_fusion,
            heuristics=software_heuristics_best,
            vision_llm=None,
            text_llm=_map_llm_payload_to_unified(software_text_result),
            category_used=category_result.category,
            category_inference=None,
            agriculture_relevance=agriculture_response,
            topics=topics_response,
            intended_purposes=intended_purposes_response,
            classification_skipped=False,
            skip_reason=None,
            total_candidates=len(unified_software_candidates),
            confidence_threshold_met=bool(unified_software_best and unified_software_best.confidence >= classification_confidence_threshold),
            document_info={
                "filename": filename,
                "pages": asset.units,
                "unit_label": asset.unit_label,
                "asset_type": asset.asset_type,
                "inferred_category": category_result.category,
                "source": asset.source,
                "text_length": len(asset.text),
                "text_quality": {
                    "chars": quality.metrics.get("chars"),
                    "letters": quality.metrics.get("letters"),
                    "letter_ratio": quality.metrics.get("letter_ratio"),
                    "ok": quality.ok,
                } if hasattr(quality, 'metrics') else None,
            },
            processing_info={
                "processing_time_ms": round(processing_time_ms, 2),
                "ocr_used": asset.source == "ocr",
                "sources_used": ["heuristics"] + (["text_llm"] if software_text_result is not None and "error" not in software_text_result else []),
                "fusion_enabled": software_fusion is not None,
                "require_agriculture": require_agriculture,
                "auto_route_models": auto_route_models,
                "routing": {
                    "software_mode": True,
                    "text_llm": {"requested": use_text_llm, "used": software_text_result is not None and "error" not in software_text_result, "reason": "software_text_llm_enabled" if should_use_software_text_llm else "heuristics_strong_enough"},
                    "vision_llm": {"requested": use_vision, "used": False, "reasons": ["software_vision_not_yet_enabled"]},
                    "language_detection": language_info,
                },
                "classification_confidence_threshold": classification_confidence_threshold,
                "stage_timings_ms": stage_timings_ms,
            },
        )

    if category_result.category != "Document":
        processing_time_ms = (time.time() - start_time) * 1000
        return ClassificationResponse(
            best_match=None,
            all_candidates=[],
            fusion=None,
            heuristics=None,
            vision_llm=None,
            text_llm=None,
            category_used=category_result.category,
            category_inference=None,
            agriculture_relevance=agriculture_response,
            topics=topics_response,
            intended_purposes=intended_purposes_response,
            classification_skipped=True,
            skip_reason=f"Inferred category is {category_result.category}; document subcategory classification skipped",
            total_candidates=0,
            confidence_threshold_met=False,
            document_info={
                "filename": filename,
                "pages": asset.units,
                "unit_label": asset.unit_label,
                "asset_type": asset.asset_type,
                "inferred_category": category_result.category,
                "source": asset.source,
                "text_length": len(asset.text),
                "text_quality": {
                    "chars": quality.metrics.get("chars"),
                    "letters": quality.metrics.get("letters"),
                    "letter_ratio": quality.metrics.get("letter_ratio"),
                    "ok": quality.ok,
                } if hasattr(quality, 'metrics') else None,
            },
            processing_info={
                "processing_time_ms": round(processing_time_ms, 2),
                "ocr_used": asset.source == "ocr",
                "sources_used": [],
                "fusion_enabled": False,
                "require_agriculture": require_agriculture,
                "auto_route_models": auto_route_models,
                "stage_timings_ms": stage_timings_ms,
            },
        )

    # 4) Extract features and compute rubric scores
    stage_start = time.time()
    sections = count_sections(asset.lines)
    cites = detect_citations(asset.text, has_references_heading=sections.present.get("references", False))
    kw = count_keywords(asset.text)
    
    r_imrad = score_imrad(sections)
    r_cites = score_citations(cites, text_len=len(asset.text))
    r_deliv = score_deliverable(kw, sections=sections)
    r_ped = score_pedagogy(kw)
    r_proc = score_procedure(kw)
    rubric_scores = {
        "imrad": r_imrad.score,
        "citations": r_cites.score,
        "deliverable": r_deliv.score,
        "pedagogy": r_ped.score,
        "procedure": r_proc.score,
    }
    stage_timings_ms["feature_and_rubric_ms"] = round((time.time() - stage_start) * 1000, 2)
    
    # 4) Evidence-based classification
    stage_start = time.time()
    best_match, all_scores, _ = score_subcategories(
        text=asset.text,
        lines=asset.lines,
        page_count=asset.units,
        sections=sections,
        rubric_scores=rubric_scores,
        parent_type_filter=None,
    )
    
    candidates = build_probability_distribution(all_scores)
    add_contrastive_rationales(candidates)
    best_candidate = candidates[0] if candidates else None
    unified_document_candidates, unified_document_best = _build_unified_candidates(
        category=category_result.category,
        text=asset.text,
        filename=filename,
        legacy_probs=_legacy_name_probs_from_candidates(candidates),
    )
    heuristics_best = unified_document_best.model_copy(deep=True) if unified_document_best else None
    final_candidates = [c.model_copy(deep=True) for c in unified_document_candidates]
    key_by_name = _unified_key_by_name()
    
    # Convert heuristics to SourceResult for fusion
    heuristics_probs = {
        c.subcategory_id: c.probability
        for c in final_candidates
    }
    heuristics_source = convert_to_source_result(
        subcategory_key=unified_document_best.subcategory_id if unified_document_best else "",
        confidence=unified_document_best.confidence if unified_document_best else 0.0,
        probs=heuristics_probs,
        source_name="heuristics",
        evidence_score=unified_document_best.evidence_score if unified_document_best else 0.0,
        rationale=unified_document_best.rationale if unified_document_best else "",
    )
    stage_timings_ms["heuristics_classification_ms"] = round((time.time() - stage_start) * 1000, 2)
    
    # 5) Optional LLM analysis
    vision_source = None
    text_source = None
    llm_results = {}
    routing_info: Dict[str, Any] = {
        "auto_route_models": auto_route_models,
        "text_llm": {"requested": use_text_llm, "used": False, "reason": None},
        "vision_llm": {"requested": use_vision, "used": False, "reasons": []},
        "top_candidate_gap": _top_probability_gap(final_candidates),
    }
    language_info = detect_text_language(asset.text)
    non_english_llm_primary = bool(language_info["non_english_llm_primary"] and use_text_llm and LLM_CONFIGURED)

    should_use_text_llm = _should_run_text_llm(
        use_text_llm=use_text_llm,
        is_agriculture_related=agri_relevance.is_agriculture_related,
        best_candidate=unified_document_best,
        current_candidates=final_candidates,
        confidence_threshold=classification_confidence_threshold,
        gap_threshold=TEXT_LLM_GAP_THRESHOLD,
        non_english_llm_primary=non_english_llm_primary,
    ) if auto_route_models else (use_text_llm and LLM_CONFIGURED)
    routing_info["text_llm"]["reason"] = (
        "non_english_text_llm_primary"
        if non_english_llm_primary and should_use_text_llm
        else (
            "low_confidence_or_close_candidates"
            if should_use_text_llm and auto_route_models
            else ("manual_request" if should_use_text_llm else "heuristics_strong_enough")
        )
    )

    if merged_document_text_result is not None:
        # Reuse the combined agriculture+subtype call instead of a second text-LLM
        # round-trip (the agriculture verdict already came from this same response).
        llm_res = merged_document_text_result
        text_source = convert_to_source_result(
            subcategory_key=llm_res.subcategory_key,
            confidence=llm_res.confidence,
            probs=llm_res.probs,
            source_name="text_llm",
            rationale=llm_res.rationale,
        )
        llm_results["text"] = {
            "subcategory_key": llm_res.subcategory_key,
            "subcategory_name": llm_res.subcategory_name,
            "confidence": round(llm_res.confidence, 4),
            "rationale": llm_res.rationale,
            "model": LLM_MODEL,
            "merged_with_agriculture_gate": True,
        }
        routing_info["text_llm"]["used"] = True
        routing_info["text_llm"]["reason"] = "merged_agriculture_subtype_call"
    elif should_use_text_llm:
        stage_start = time.time()
        try:
            from docint.llm.subcategory_classify import llm_classify_subcategories_text

            llm_res = llm_classify_subcategories_text(
                asset.text,
                base_url=LLM_BASE_URL,
                api_key=LLM_API_KEY,
                model=LLM_MODEL,
                max_chars=15000,
                temperature=LLM_TEMPERATURE,
            )

            text_source = convert_to_source_result(
                subcategory_key=llm_res.subcategory_key,
                confidence=llm_res.confidence,
                probs=llm_res.probs,
                source_name="text_llm",
                rationale=llm_res.rationale,
            )

            llm_results["text"] = {
                "subcategory_key": llm_res.subcategory_key,
                "subcategory_name": llm_res.subcategory_name,
                "confidence": round(llm_res.confidence, 4),
                "rationale": llm_res.rationale,
                "model": LLM_MODEL,
            }
            routing_info["text_llm"]["used"] = True
        except Exception as e:
            llm_results["text"] = {"error": str(e), "model": LLM_MODEL}
        stage_timings_ms["text_llm_ms"] = round((time.time() - stage_start) * 1000, 2)

    should_use_vision, vision_reasons = _should_run_vision(
        use_vision=use_vision and asset.asset_type == "pdf",
        ocr_used=asset.source == "ocr",
        text_quality_ok_flag=quality.ok,
        heuristics_source=heuristics_source,
        best_candidate=unified_document_best,
        current_candidates=final_candidates,
        text_source=text_source,
        confidence_threshold=vision_trigger_threshold,
        gap_threshold=candidate_gap_threshold,
    ) if auto_route_models else ((use_vision and bool(VISION_LLM_BASE_URL)), ["manual_request"] if use_vision and VISION_LLM_BASE_URL else [])
    if non_english_llm_primary and auto_route_models:
        should_use_vision = False
        vision_reasons = ["non_english_text_llm_primary"]
    routing_info["vision_llm"]["reasons"] = vision_reasons

    if should_use_vision:
        stage_start = time.time()
        try:
            from docint.llm.subcategory_classify import llm_classify_subcategories_vision
            
            llm_res = llm_classify_subcategories_vision(
                file_path,
                base_url=VISION_LLM_BASE_URL,
                api_key=VISION_LLM_API_KEY,
                model=VISION_LLM_MODEL,
                max_total_pages=vision_max_pages,
                temperature=LLM_TEMPERATURE,
                dpi=VISION_RENDER_DPI,
            )
            
            vision_source = convert_to_source_result(
                subcategory_key=llm_res.subcategory_key,
                confidence=llm_res.confidence,
                probs=llm_res.probs,
                source_name="vision_llm",
                rationale=llm_res.rationale,
            )
            
            llm_results["vision"] = {
                "subcategory_key": llm_res.subcategory_key,
                "subcategory_name": llm_res.subcategory_name,
                "confidence": round(llm_res.confidence, 4),
                "rationale": llm_res.rationale,
                "model": VISION_LLM_MODEL,
            }
            routing_info["vision_llm"]["used"] = True
        except Exception as e:
            llm_results["vision"] = {"error": str(e), "model": VISION_LLM_MODEL}
        stage_timings_ms["vision_llm_ms"] = round((time.time() - stage_start) * 1000, 2)
    
    # 6) Intelligent fusion if multiple sources
    fusion_info = None
    final_best = final_candidates[0] if final_candidates else None
    
    sources_for_fusion = [heuristics_source]
    if vision_source:
        sources_for_fusion.append(vision_source)
    if text_source:
        sources_for_fusion.append(text_source)
    
    if non_english_llm_primary and text_source:
        _apply_source_probabilities(final_candidates, text_source.probs, key_by_name)
        final_best = final_candidates[0]
        add_contrastive_rationales(final_candidates)
    elif len(sources_for_fusion) > 1:
        stage_start = time.time()
        strategy_map = {
            "weighted": FusionStrategy.WEIGHTED,
            "adaptive": FusionStrategy.CONFIDENCE_ADAPTIVE,
            "agreement": FusionStrategy.AGREEMENT_BASED,
            "cascade": FusionStrategy.CASCADE,
        }
        strategy = strategy_map.get(fusion_strategy, FusionStrategy.CONFIDENCE_ADAPTIVE)
        
        fusion_result = intelligent_fusion(
            heuristics_result=heuristics_source,
            vision_result=vision_source,
            text_result=text_source,
            strategy=strategy,
            heuristics_alpha=heuristics_alpha,
            llm_alpha=1.0 - heuristics_alpha,
        )
        
        # Convert fusion result to candidate format
        fusion_info = FusionInfo(
            fused=True,
            strategy=fusion_result.fusion_strategy,
            weights=fusion_result.weights,
            agreement_score=fusion_result.agreement_score,
            rationale=fusion_result.rationale,
        )
        
        # Re-rank candidates based on fusion probabilities. Fusion stores
        # probabilities by internal subcategory key, not display name.
        for c in final_candidates:
            subcat_key = key_by_name.get(c.subcategory_name, c.subcategory_name)
            fused_prob = round(fusion_result.probs.get(subcat_key, 0), 4)
            c.probability = fused_prob
            c.confidence = fused_prob

        # Sort by new probabilities
        final_candidates.sort(key=lambda x: x.probability, reverse=True)
        for i, c in enumerate(final_candidates, 1):
            c.rank = i
        add_fusion_explanations(
            final_candidates,
            fusion_result,
            {
                "heuristics": heuristics_source,
                "vision_llm": vision_source,
                "text_llm": text_source,
            },
        )
        add_contrastive_rationales(final_candidates)

        final_best = final_candidates[0]
        stage_timings_ms["fusion_ms"] = round((time.time() - stage_start) * 1000, 2)
    
    threshold_met = final_best.confidence >= classification_confidence_threshold if final_best else False
    
    processing_time_ms = (time.time() - start_time) * 1000
    unified_document_candidates = final_candidates
    unified_document_best = final_best
    unified_document_heuristics = heuristics_best
    threshold_met = bool(unified_document_best and unified_document_best.confidence >= classification_confidence_threshold)
    
    return ClassificationResponse(
        best_match=unified_document_best,
        all_candidates=unified_document_candidates,
        fusion=fusion_info,
        heuristics=unified_document_heuristics,
        vision_llm=_map_llm_payload_to_unified(llm_results.get("vision")),
        text_llm=_map_llm_payload_to_unified(llm_results.get("text")),
        category_used=category_result.category,
        category_inference=None,
        agriculture_relevance=agriculture_response,
        topics=topics_response,
        intended_purposes=intended_purposes_response,
        classification_skipped=False,
        skip_reason=None,
        total_candidates=len(unified_document_candidates),
        confidence_threshold_met=threshold_met,
        document_info={
            "filename": filename,
            "pages": asset.units,
            "unit_label": asset.unit_label,
            "asset_type": asset.asset_type,
            "inferred_category": category_result.category,
            "source": asset.source,
            "text_length": len(asset.text),
            "text_quality": {
                "chars": quality.metrics.get("chars"),
                "letters": quality.metrics.get("letters"),
                "letter_ratio": quality.metrics.get("letter_ratio"),
                "ok": quality.ok,
            } if hasattr(quality, 'metrics') else None,
        },
        processing_info={
            "processing_time_ms": round(processing_time_ms, 2),
            "ocr_used": asset.source == "ocr",
            "sources_used": [s.source_name for s in sources_for_fusion],
            "fusion_enabled": fusion_info is not None,
            "require_agriculture": require_agriculture,
            "auto_route_models": auto_route_models,
            "routing": routing_info,
            "language_detection": language_info,
            "cache": {
                "agriculture": agriculture_cache_hit,
            },
            "classification_confidence_threshold": classification_confidence_threshold,
            "vision_trigger_threshold": vision_trigger_threshold,
            "candidate_gap_threshold": candidate_gap_threshold,
            "stage_timings_ms": stage_timings_ms,
        },
    )


# =============================================================================
# API ENDPOINTS
# =============================================================================

@app.middleware("http")
async def auth_middleware(request, call_next):
    """
    Global middleware to enforce Basic Auth on all requests.
    Skips auth for OPTIONS requests (CORS preflight) and health checks.
    """
    # Skip auth if not enabled
    if not AUTH_ENABLED:
        return await call_next(request)
    
    # Skip auth for OPTIONS requests (CORS preflight)
    if request.method == "OPTIONS":
        return await call_next(request)
    
    # Skip auth for health check endpoint
    if request.url.path == "/health":
        return await call_next(request)
    
    # Get Authorization header
    auth_header = request.headers.get("Authorization")
    
    if not auth_header or not auth_header.startswith("Basic "):
        return JSONResponse(
            status_code=401,
            headers={"WWW-Authenticate": 'Basic realm="Agri-Tag API"'},
            content={"detail": "Authentication required"},
        )
    
    # Decode credentials
    try:
        import base64
        encoded_credentials = auth_header.split(" ", 1)[1]
        decoded = base64.b64decode(encoded_credentials).decode("utf-8")
        username, password = decoded.split(":", 1)
        
        # Verify
        stored_password = AUTHORIZED_USERS.get(username)
        if stored_password is None or not secrets.compare_digest(password, stored_password):
            return JSONResponse(
                status_code=401,
                headers={"WWW-Authenticate": 'Basic realm="Agri-Tag API"'},
                content={"detail": "Invalid credentials"},
            )
        
        # Store username in request state for later use
        request.state.username = username
        
    except Exception:
        return JSONResponse(
            status_code=401,
            headers={"WWW-Authenticate": 'Basic realm="Agri-Tag API"'},
            content={"detail": "Invalid authentication format"},
        )
    
    return await call_next(request)


@app.get("/")
async def root(request: Request):
    """Root endpoint with API info."""
    username = getattr(request.state, 'username', 'anonymous')
    return {
        "name": "Agri-Tag API",
        "version": "2.0.0",
        "authenticated_user": username,
        "auth_enabled": AUTH_ENABLED,
        "features": ["heuristics", "vision_llm", "text_llm", "intelligent_fusion"],
        "docs": "/docs",
        "health": "/health",
        "visualisations": {
            "subcategories_graph": "/visualisations/subcategories_graph.html",
        },
        "supported_file_types": {
            "upload": SUPPORTED_FILE_TYPES_BY_CATEGORY,
            "url_suffix_hints": URL_SUFFIX_HINTS_BY_CATEGORY,
            "upload_total": sum(len(values) for values in SUPPORTED_FILE_TYPES_BY_CATEGORY.values()),
        },
    }


@app.get("/health")
async def health(request: Request):
    """Health check endpoint."""
    username = getattr(request.state, 'username', 'anonymous')
    
    return {
        "status": "ok",
        "version": "2.0.0",
        "timestamp": datetime.utcnow().isoformat(),
        "authenticated_user": username,
        "auth_enabled": AUTH_ENABLED,
        "models": {
            "heuristics": {"available": True},
            "text_llm": {
                "configured": LLM_CONFIGURED,
                "model": LLM_MODEL if LLM_CONFIGURED else None,
                "base_url": _masked_origin(LLM_BASE_URL),
            },
            "vision_llm": {
                "configured": bool(VISION_LLM_BASE_URL),
                "model": VISION_LLM_MODEL if VISION_LLM_BASE_URL else None,
                "base_url": _masked_origin(VISION_LLM_BASE_URL),
            },
            "audio_transcription": {
                "enabled": MEDIA_TRANSCRIBER_ENABLED,
                "configured": AUDIO_TRANSCRIPTION_CONFIGURED,
                "model": MEDIA_TRANSCRIBER_WHISPER_MODEL if AUDIO_TRANSCRIPTION_CONFIGURED else None,
                "mode": MEDIA_TRANSCRIBER_MODE if AUDIO_TRANSCRIPTION_CONFIGURED else None,
                "base_url": _masked_origin(MEDIA_TRANSCRIBER_BASE_URL),
                "basic_auth_configured": bool(MEDIA_TRANSCRIBER_BASIC_USER and MEDIA_TRANSCRIBER_BASIC_PASS),
                "api_key_configured": bool(MEDIA_TRANSCRIBER_API_KEY),
            },
            "agrigate": {
                "configured": bool(AGRI_GATE_BASE_URL),
                "base_url": _masked_origin(AGRI_GATE_BASE_URL),
                "timeout_seconds": AGRI_GATE_TIMEOUT,
                "url_strict": AGRI_GATE_URL_STRICT,
                "file_strict": AGRI_GATE_FILE_STRICT,
            },
            "pagesense": {
                "configured": bool(URL_CONTENT_EXTRACTOR_BASE),
                "base_url": _masked_origin(URL_CONTENT_EXTRACTOR_BASE),
                "timeout_seconds": EXTRACTOR_TIMEOUT,
                "min_chars": EXTRACTOR_MIN_CHARS,
            },
            "video_tooling": {
                "ffmpeg_available": FFMPEG_AVAILABLE,
                "ffprobe_available": FFPROBE_AVAILABLE,
                "frame_sampling_ready": FFMPEG_AVAILABLE and FFPROBE_AVAILABLE,
                "audio_extract_ready": FFMPEG_AVAILABLE,
            },
            "mistral": {
                "configured": MISTRAL_CONFIGURED,
                "openai_base_url": MISTRAL_OPENAI_BASE_URL if MISTRAL_CONFIGURED else None,
                "text_model": MISTRAL_TEXT_MODEL if MISTRAL_CONFIGURED else None,
                "vision_model": MISTRAL_VISION_MODEL if MISTRAL_CONFIGURED else None,
                "ocr_model": MISTRAL_OCR_MODEL if MISTRAL_CONFIGURED else None,
                "audio_model": MISTRAL_AUDIO_MODEL if MISTRAL_CONFIGURED else None,
            },
        },
    }


@app.post("/classify", response_model=ClassificationResponse)
async def classify_endpoint(
    request: Request,
    file: UploadFile = File(..., description="Supported KO asset file to classify"),
    debug: bool = Query(False, description="If true, include full internal scoring/debug details in the response"),
    use_agri_gate: bool = Query(False, description="If true, send the uploaded file to Agri Gate before classification"),
    require_agriculture: bool = Query(True, description="Skip subtype classification for assets assessed as non-agriculture"),
    auto_route_models: bool = Query(True, description="Automatically decide whether text and vision models should be used"),
    use_vision: bool = Query(True, description="Allow Vision LLM (InternVL) when routing decides it is needed"),
    use_text_llm: bool = Query(True, description="Allow Text LLM (Qwen) for agriculture-related documents"),
    heuristics_alpha: float = Query(
        0.4,
        ge=0.0,
        le=1.0,
        description="Weight for heuristics (0.4 = 40% heuristics, 60% LLM)"
    ),
    classification_confidence_threshold: float = Query(0.35, ge=0.0, le=1.0, description="Confidence threshold used to mark subtype classification as strong enough"),
    vision_trigger_threshold: float = Query(0.6, ge=0.0, le=1.0, description="Subcategory confidence threshold below which vision may be triggered"),
    candidate_gap_threshold: float = Query(0.12, ge=0.0, le=1.0, description="Top-candidate probability gap below which vision may be triggered"),
    fusion_strategy: str = Query(
        "adaptive",
        description="Fusion strategy: weighted, adaptive, agreement, cascade"
    ),
    vision_max_pages: int = Query(
        8,
        ge=1,
        le=24,
        description="Ceiling on page-images sent to the vision model per request; chosen length-adaptively up to this value and clamped server-side to VISION_MAX_PAGES_CAP (must match the vLLM image:N limit, default 8)"
    ),
    ocr_lang: Optional[str] = Query(
        None,
        description="Optional Tesseract OCR language bundle used only when OCR fallback is triggered; if omitted, the configured multilingual default is used"
    ),
    ocr_max_pages: int = Query(
        5,
        ge=1,
        le=50,
        description="Maximum pages sent through OCR fallback when extracted text quality is poor"
    ),
    provider: ProviderChoice = Query(
        ProviderChoice.custom,
        description="LLM provider flow: 'custom' uses the self-hosted OpenAI-compatible models (text+vision) plus Tesseract OCR and the Whisper transcriber; 'mistral' routes text+vision to Mistral's OpenAI-compatible endpoint and uses Mistral OCR + Voxtral transcription"
    ),
):
    """Classify a supported KO asset file with optional model routing."""
    if provider == ProviderChoice.mistral and not MISTRAL_CONFIGURED:
        raise HTTPException(status_code=503, detail="Mistral provider selected but MISTRAL_API_KEY is not configured.")
    filename = file.filename or "unknown.pdf"
    suffix = os.path.splitext(filename)[1].lower()
    audio_suffixes = AUDIO_EXTS
    video_suffixes = VIDEO_EXTS
    archive_suffix = get_archive_suffix(filename)
    is_archive_upload = archive_suffix in ARCHIVE_UPLOAD_EXTENSIONS
    content_length = request.headers.get("content-length")

    if suffix not in SUPPORTED_DOCUMENT_EXTENSIONS and not is_archive_upload:
        blocked_suffix = get_blocked_suffix(filename)
        if blocked_suffix:
            raise HTTPException(
                status_code=415,
                detail=f"Blocked file type '{blocked_suffix}'. Executable, installer, and script payloads are not allowed.",
            )
        archive_suffix = get_archive_suffix(filename)
        if archive_suffix:
            raise HTTPException(
                status_code=415,
                detail=f"Archive file type '{archive_suffix}' is not allowed in the current upload flow.",
            )
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type '{suffix}'. Supported types: {', '.join(sorted(SUPPORTED_DOCUMENT_EXTENSIONS))}",
        )

    if content_length:
        try:
            request_size_bytes = int(content_length)
            if request_size_bytes > MAX_REQUEST_BODY_MB * 1024 * 1024:
                raise HTTPException(
                    status_code=413,
                    detail=f"Request body too large ({round(request_size_bytes / (1024 * 1024), 2)} MB). Maximum allowed is {MAX_REQUEST_BODY_MB} MB.",
                )
        except ValueError:
            pass

    tmp_path = None
    archive_extract_dir = None
    try:
        tmp_path, file_size_bytes = await _save_upload_to_temp(file, suffix=suffix or ".bin")
        _validate_ai_uploader_criteria_or_413(tmp_path, filename, size_bytes=file_size_bytes)

        agri_gate_payload = {
            "enabled": use_agri_gate,
            "source": "file",
            "strict": AGRI_GATE_FILE_STRICT,
            "skipped": not use_agri_gate,
        }
        if use_agri_gate:
            agri_gate_payload = _agri_gate_or_raise(
                agrigate_scan_file(tmp_path, filename=filename),
                strict=AGRI_GATE_FILE_STRICT,
                source_label="file",
            )

        if is_archive_upload:
            try:
                archive = extract_supported_archive(tmp_path, filename)
                archive_extract_dir = archive.extract_dir
            except ValueError as exc:
                message = str(exc)
                status = 413 if "too many" in message or "expands to" in message else 415
                raise HTTPException(status_code=status, detail=message)
            except RuntimeError as exc:
                raise HTTPException(status_code=422, detail=str(exc))

            archive_results = []
            for inner_path, inner_name in archive.supported_files:
                _validate_ai_uploader_criteria_or_413(
                    inner_path,
                    inner_name,
                    size_bytes=Path(inner_path).stat().st_size,
                )
                archive_results.append(
                    classify_document(
                        file_path=inner_path,
                        filename=inner_name,
                        upload_content_type=None,
                        require_agriculture=require_agriculture,
                        auto_route_models=auto_route_models,
                        use_vision=use_vision,
                        use_text_llm=use_text_llm,
                        heuristics_alpha=heuristics_alpha,
                        classification_confidence_threshold=classification_confidence_threshold,
                        vision_trigger_threshold=vision_trigger_threshold,
                        candidate_gap_threshold=candidate_gap_threshold,
                        fusion_strategy=fusion_strategy,
                        vision_max_pages=vision_max_pages,
                        ocr_lang=ocr_lang or OCR_DEFAULT_LANGS,
                        ocr_max_pages=ocr_max_pages,
                        provider=provider,
                    )
                )

            def _archive_result_score(item: ClassificationResponse) -> float:
                return float(item.best_match.confidence) if item.best_match else 0.0

            result = max(archive_results, key=_archive_result_score)
            archive_items = []
            for inner_result in archive_results:
                archive_items.append({
                    "filename": inner_result.document_info.get("filename"),
                    "category_used": inner_result.category_used,
                    "classification_skipped": inner_result.classification_skipped,
                    "skip_reason": inner_result.skip_reason,
                    "best_match": inner_result.best_match.model_dump() if inner_result.best_match else None,
                    "confidence_threshold_met": inner_result.confidence_threshold_met,
                })
            result.document_info["source_archive"] = filename
            result.processing_info["security_gate"] = agri_gate_payload
            result.processing_info["source_mode"] = "archive"
            result.processing_info["archive"] = {
                "filename": filename,
                "archive_type": archive.archive_type,
                "total_files": archive.total_files,
                "supported_files": len(archive.supported_files),
                "skipped_files": archive.skipped_files,
                "total_extracted_bytes": archive.total_extracted_bytes,
                "selected_result_filename": result.document_info.get("filename"),
                "items": archive_items,
            }
            return _prepare_response(result, debug=debug)

        result = classify_document(
            file_path=tmp_path,
            filename=filename,
            upload_content_type=file.content_type,
            require_agriculture=require_agriculture,
            auto_route_models=auto_route_models,
            use_vision=use_vision,
            use_text_llm=use_text_llm,
            heuristics_alpha=heuristics_alpha,
            classification_confidence_threshold=classification_confidence_threshold,
            vision_trigger_threshold=vision_trigger_threshold,
            candidate_gap_threshold=candidate_gap_threshold,
            fusion_strategy=fusion_strategy,
            vision_max_pages=vision_max_pages,
            ocr_lang=ocr_lang or OCR_DEFAULT_LANGS,
            ocr_max_pages=ocr_max_pages,
            provider=provider,
        )
        result.processing_info["security_gate"] = agri_gate_payload
        result.processing_info["source_mode"] = "file"
        return _prepare_response(result, debug=debug)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Classification failed: {str(e)}")
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass
        if archive_extract_dir and os.path.isdir(archive_extract_dir):
            try:
                shutil.rmtree(archive_extract_dir)
            except Exception:
                pass


@app.post("/classify-text", response_model=ClassificationResponse)
async def classify_text_endpoint(
    body: TextClassificationRequest,
    debug: bool = Query(False, description="If true, include full internal scoring/debug details in the response"),
    require_agriculture: bool = Query(True, description="Skip subtype classification for text assessed as non-agriculture"),
    auto_route_models: bool = Query(True, description="Automatically decide whether the text LLM is used"),
    use_text_llm: bool = Query(True, description="Allow Text LLM classification for agriculture-related text"),
    heuristics_alpha: float = Query(0.4, ge=0.0, le=1.0, description="Weight for heuristics (0.4 = 40% heuristics, 60% LLM)"),
    classification_confidence_threshold: float = Query(0.35, ge=0.0, le=1.0, description="Confidence threshold used to mark subtype classification as strong enough"),
    candidate_gap_threshold: float = Query(0.12, ge=0.0, le=1.0, description="Top-candidate probability gap threshold"),
    fusion_strategy: str = Query("adaptive", description="Fusion strategy: weighted, adaptive, agreement, cascade"),
    provider: ProviderChoice = Query(ProviderChoice.custom, description="LLM provider flow: 'custom' (self-hosted) or 'mistral'"),
):
    """Classify a raw text snippet (no file upload).

    Infers category, subcategory, topics, and intended purposes from the text. The
    snippet is treated as a text document, so there is no OCR or vision routing
    (those only apply to files/images). Capped at MAX_TEXT_INPUT_WORDS (~10 A4
    pages / 5000 words).
    """
    if provider == ProviderChoice.mistral and not MISTRAL_CONFIGURED:
        raise HTTPException(status_code=503, detail="Mistral provider selected but MISTRAL_API_KEY is not configured.")

    text = (body.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Empty text")

    word_count = len(text.split())
    if word_count > MAX_TEXT_INPUT_WORDS:
        raise HTTPException(
            status_code=413,
            detail=(
                f"Text too long ({word_count} words). Maximum allowed is {MAX_TEXT_INPUT_WORDS} words "
                f"(~10 A4 pages) for the text endpoint."
            ),
        )

    filename = body.filename or "input.txt"
    if not filename.lower().endswith(".txt"):
        filename = f"{filename}.txt"

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".txt", mode="w", encoding="utf-8") as tmp:
            tmp_path = tmp.name
            tmp.write(text)

        result = classify_document(
            file_path=tmp_path,
            filename=filename,
            upload_content_type="text/plain",
            require_agriculture=require_agriculture,
            auto_route_models=auto_route_models,
            use_vision=False,  # raw text has no pages/images to render
            use_text_llm=use_text_llm,
            heuristics_alpha=heuristics_alpha,
            classification_confidence_threshold=classification_confidence_threshold,
            candidate_gap_threshold=candidate_gap_threshold,
            fusion_strategy=fusion_strategy,
            provider=provider,
        )
        result.processing_info["security_gate"] = {"enabled": False, "source": "text", "skipped": True}
        result.processing_info["source_mode"] = "text"
        result.processing_info["input_word_count"] = word_count
        return _prepare_response(result, debug=debug)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Classification failed: {str(e)}")
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass


@app.post("/classify-media-llm", response_model=MediaLlmOnlyResponse)
async def classify_media_llm_endpoint(
    request: Request,
    file: UploadFile = File(..., description="Audio or video asset to classify through transcript-first text LLM only"),
    top_k_candidates: int = Query(5, ge=1, le=10, description="Maximum number of ranked subtype candidates returned"),
    include_transcript: bool = Query(False, description="If true, include the full recovered transcript in the response"),
    temperature: float = Query(0.0, ge=0.0, le=1.0, description="Sampling temperature for transcript-first text LLM classification (0 = deterministic)"),
    max_chars: int = Query(12000, ge=1000, le=24000, description="Maximum transcript characters sent to the text LLM"),
    provider: ProviderChoice = Query(ProviderChoice.custom, description="Provider for transcription + text LLM: 'custom' (Whisper + self-hosted LLM) or 'mistral' (Voxtral + Mistral LLM)"),
):
    """Classify audio/video using transcript-first text LLM only."""
    use_mistral = provider == "mistral"
    (LLM_BASE_URL, LLM_API_KEY, LLM_MODEL, LLM_CONFIGURED,
     VISION_LLM_BASE_URL, VISION_LLM_API_KEY, VISION_LLM_MODEL, _vision_configured) = _resolve_llm_config(provider)

    if not LLM_CONFIGURED:
        raise HTTPException(status_code=503, detail="Text LLM is not configured for the selected provider.")
    if not use_mistral and not AUDIO_TRANSCRIPTION_CONFIGURED:
        raise HTTPException(status_code=503, detail="Media transcriber is not configured or not enabled.")

    filename = file.filename or "unknown.bin"
    suffix = os.path.splitext(filename)[1].lower()
    audio_suffixes = AUDIO_EXTS
    video_suffixes = VIDEO_EXTS

    if suffix not in audio_suffixes | video_suffixes:
        blocked_suffix = get_blocked_suffix(filename)
        if blocked_suffix:
            raise HTTPException(
                status_code=415,
                detail=f"Blocked file type '{blocked_suffix}'. Executable, installer, and script payloads are not allowed.",
            )
        archive_suffix = get_archive_suffix(filename)
        if archive_suffix:
            raise HTTPException(
                status_code=415,
                detail=f"Archive file type '{archive_suffix}' is not allowed in the current upload flow.",
            )
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported media file type '{suffix}'. Supported types: {', '.join(sorted(audio_suffixes | video_suffixes))}",
        )

    content_length = request.headers.get("content-length")
    if content_length:
        try:
            request_size_bytes = int(content_length)
            if request_size_bytes > MAX_REQUEST_BODY_MB * 1024 * 1024:
                raise HTTPException(
                    status_code=413,
                    detail=f"Request body too large ({round(request_size_bytes / (1024 * 1024), 2)} MB). Maximum allowed is {MAX_REQUEST_BODY_MB} MB.",
                )
        except ValueError:
            pass

    category_used = "Audio" if suffix in audio_suffixes else "Video"
    stage_timings_ms: Dict[str, float] = {}
    tmp_path = None

    try:
        tmp_path, file_size_bytes = await _save_upload_to_temp(file, suffix=suffix or ".bin")
        duration_stage_start = time.time()
        criteria_info = _validate_ai_uploader_criteria_or_413(tmp_path, filename, size_bytes=file_size_bytes)
        duration_sec = float(criteria_info.get("duration_seconds") or 0.0)
        stage_timings_ms["duration_probe_ms"] = round((time.time() - duration_stage_start) * 1000, 2)

        transcription_stage_start = time.time()
        if category_used == "Audio":
            transcript_res = mistral_transcribe(tmp_path) if use_mistral else transcribe_audio_file(tmp_path)
        else:
            transcript_res = transcribe_video_audio(tmp_path, transcriber=mistral_transcribe) if use_mistral else transcribe_video_audio(tmp_path)
        stage_timings_ms["transcription_ms"] = round((time.time() - transcription_stage_start) * 1000, 2)

        if not transcript_res.available:
            raise HTTPException(status_code=503, detail=transcript_res.rationale)
        if not transcript_res.text.strip():
            raise HTTPException(status_code=422, detail=transcript_res.rationale or "Media transcription produced no usable text.")

        llm_stage_start = time.time()
        if category_used == "Audio":
            from docint.llm.subcategory_classify import llm_classify_audio_subcategories_text

            llm_res = llm_classify_audio_subcategories_text(
                transcript_res.text,
                base_url=LLM_BASE_URL,
                api_key=LLM_API_KEY,
                model=LLM_MODEL,
                max_chars=max_chars,
                temperature=temperature,
            )
        else:
            from docint.llm.subcategory_classify import llm_classify_video_subcategories_text

            llm_res = llm_classify_video_subcategories_text(
                transcript_res.text,
                base_url=LLM_BASE_URL,
                api_key=LLM_API_KEY,
                model=LLM_MODEL,
                max_chars=max_chars,
                temperature=temperature,
            )
        stage_timings_ms["text_llm_ms"] = round((time.time() - llm_stage_start) * 1000, 2)

        candidates = _media_llm_candidates_from_result(llm_res, top_k_candidates=top_k_candidates)
        best_match = candidates[0] if candidates else None
        transcript_preview = transcript_res.text[:400].strip()
        if len(transcript_res.text) > 400:
            transcript_preview += "..."

        return MediaLlmOnlyResponse(
            category_used=category_used,
            best_match=best_match,
            all_candidates=candidates,
            text_llm={
                "subcategory_key": llm_res.subcategory_key,
                "subcategory_name": llm_res.subcategory_name,
                "confidence": llm_res.confidence,
                "model": LLM_MODEL,
                "rationale": llm_res.rationale,
            },
            transcript=MediaLlmTranscriptInfo(
                available=transcript_res.available,
                used=transcript_res.used,
                method=transcript_res.method,
                model=transcript_res.model,
                rationale=transcript_res.rationale,
                text_length=len(transcript_res.text),
                preview=transcript_preview,
                full_text=transcript_res.text if include_transcript else None,
            ),
            total_candidates=len(candidates),
            confidence_threshold_met=bool(best_match and best_match.confidence >= 0.35),
            document_info={
                "filename": filename,
                "asset_type": suffix.lstrip("."),
                "inferred_category": category_used,
                "source": "media_transcript",
                "text_length": len(transcript_res.text),
                "duration_seconds": round(duration_sec, 2) if duration_sec else None,
            },
            processing_info={
                "processing_time_ms": round(sum(stage_timings_ms.values()), 2),
                "sources_used": ["text_llm", "media_transcriber"],
                "llm_only": True,
                "transcript_first": True,
                "source_mode": "file",
                "include_transcript": include_transcript,
                "stage_timings_ms": stage_timings_ms,
                "transcriber": {
                    "enabled": MEDIA_TRANSCRIBER_ENABLED,
                    "configured": AUDIO_TRANSCRIPTION_CONFIGURED,
                    "model": transcript_res.model,
                    "method": transcript_res.method,
                },
            },
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Media LLM classification failed: {str(e)}")
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass


@app.post("/classify-url", response_model=ClassificationResponse)
async def classify_url_endpoint(
    body: UrlClassificationRequest,
    debug: bool = Query(False, description="If true, include full internal scoring/debug details in the response"),
    use_agri_gate: bool = Query(False, description="If true, send the submitted URL to Agri Gate before extraction"),
    require_agriculture: bool = Query(True, description="Skip subtype classification for URLs assessed as non-agriculture"),
    auto_route_models: bool = Query(True, description="Automatically decide whether text models should be used"),
    use_text_llm: bool = Query(True, description="Allow Text LLM (Qwen) for agriculture-related URL content"),
    heuristics_alpha: float = Query(
        0.4,
        ge=0.0,
        le=1.0,
        description="Weight for heuristics (0.4 = 40% heuristics, 60% LLM)",
    ),
    classification_confidence_threshold: float = Query(0.35, ge=0.0, le=1.0, description="Confidence threshold used to mark subtype classification as strong enough"),
    fusion_strategy: str = Query("adaptive", description="Fusion strategy: weighted, adaptive, agreement, cascade"),
    provider: ProviderChoice = Query(ProviderChoice.custom, description="Text LLM provider: 'custom' (self-hosted) or 'mistral'"),
):
    """Classify a public URL after Agri Gate screening and PageSense extraction."""
    if provider == ProviderChoice.mistral and not MISTRAL_CONFIGURED:
        raise HTTPException(status_code=503, detail="Mistral provider selected but MISTRAL_API_KEY is not configured.")
    endpoint_stage_timings_ms: Dict[str, float] = {}
    url = _validate_public_http_url(body.url)

    agri_gate_payload = {
        "enabled": use_agri_gate,
        "source": "url",
        "strict": AGRI_GATE_URL_STRICT,
        "skipped": not use_agri_gate,
    }
    if use_agri_gate:
        stage_start = time.time()
        agri_gate_payload = _agri_gate_or_raise(
            agrigate_scan_url(url),
            strict=AGRI_GATE_URL_STRICT,
            source_label="url",
        )
        endpoint_stage_timings_ms["agri_gate_ms"] = round((time.time() - stage_start) * 1000, 2)

    blocked_url_suffix = get_blocked_url_suffix(url)
    if blocked_url_suffix:
        raise HTTPException(
            status_code=415,
            detail=f"Blocked URL target '{blocked_url_suffix}'. Executable, installer, and script payloads are not allowed.",
        )
    archive_url_suffix = get_archive_url_suffix(url)
    if archive_url_suffix:
        raise HTTPException(
            status_code=415,
            detail=f"Archive URL target '{archive_url_suffix}' is not allowed in the current URL flow.",
        )

    stage_start = time.time()
    pagesense_cache_key = url.strip()
    pagesense_result = _cache_get(PAGESENSE_CACHE, pagesense_cache_key)
    pagesense_cache_hit = pagesense_result is not None
    if pagesense_result is None:
        pagesense_result = extract_url_text(url)
        if pagesense_result.ok:
            _cache_set(PAGESENSE_CACHE, pagesense_cache_key, pagesense_result, URL_EXTRACTION_CACHE_TTL_SEC)
    endpoint_stage_timings_ms["pagesense_ms"] = round((time.time() - stage_start) * 1000, 2)
    if not pagesense_result.ok:
        raise HTTPException(status_code=422, detail=pagesense_result.rationale)
    if len(pagesense_result.text) < EXTRACTOR_MIN_CHARS:
        raise HTTPException(
            status_code=422,
            detail=f"PageSense extracted too little usable text ({len(pagesense_result.text)} chars). Minimum required is {EXTRACTOR_MIN_CHARS}.",
        )

    if pagesense_result.content_kind in {"document", "pdf"} and pagesense_result.page_count and pagesense_result.page_count > MAX_DOCUMENT_UNITS:
        raise HTTPException(
            status_code=413,
            detail=(
                f"URL document too large ({pagesense_result.page_count} pages). "
                f"Maximum allowed is {MAX_DOCUMENT_UNITS} pages for synchronous classification."
            ),
        )

    if pagesense_result.content_kind in {"audio", "video"} and pagesense_result.duration_seconds and pagesense_result.duration_seconds > MAX_VIDEO_DURATION_SEC:
        raise HTTPException(
            status_code=413,
            detail=(
                f"URL media duration too long ({round(pagesense_result.duration_seconds, 1)} seconds). "
                f"Maximum allowed is {MAX_VIDEO_DURATION_SEC} seconds."
            ),
        )

    if pagesense_result.content_kind not in {"audio", "video"} and pagesense_result.size_bytes and pagesense_result.size_bytes > MAX_OTHER_UPLOAD_SIZE_MB * 1024 * 1024:
        raise HTTPException(
            status_code=413,
            detail=(
                f"URL content too large ({round(pagesense_result.size_bytes / (1024 * 1024), 2)} MB). "
                f"Maximum allowed is {MAX_OTHER_UPLOAD_SIZE_MB} MB for non-audio/video URL content."
            ),
        )

    result = classify_url_text(
        url=url,
        extracted_text=pagesense_result.text,
        title=pagesense_result.title,
        pagesense_meta={
            "service": "pagesense",
            "base_url": _masked_origin(URL_CONTENT_EXTRACTOR_BASE),
            "cache_hit": pagesense_cache_hit,
            "rationale": pagesense_result.rationale,
            "text_length": len(pagesense_result.text),
            "title": pagesense_result.title,
            "content_kind": pagesense_result.content_kind,
            "content_type": pagesense_result.content_type,
            "size_bytes": pagesense_result.size_bytes,
            "page_count": pagesense_result.page_count,
            "duration_seconds": pagesense_result.duration_seconds,
        },
        require_agriculture=require_agriculture,
        auto_route_models=auto_route_models,
        use_text_llm=use_text_llm,
        heuristics_alpha=heuristics_alpha,
        classification_confidence_threshold=classification_confidence_threshold,
        fusion_strategy=fusion_strategy,
        provider=provider,
    )
    result.processing_info.setdefault("stage_timings_ms", {}).update(endpoint_stage_timings_ms)
    result.processing_info["security_gate"] = agri_gate_payload
    result.processing_info["source_mode"] = "url"
    return _prepare_response(result, debug=debug)


@app.get("/subcategories")
async def list_subcategories(request: Request):
    """List all subcategory definitions."""
    from docint.rubrics.subcategories import get_all_detectable_features
    criteria = get_subcategory_criteria()

    subcats = {}
    for key, subcat in SUBCATEGORIES.items():
        subcats[key] = {
            "id": subcat.id,
            "name": subcat.name,
            "description": subcat.description,
            "parent_type": subcat.parent_type.value,
            "features": [f.name for f in subcat.detectable_features],
            "criteria": criteria.get(key),
        }
    
    return {
        "subcategories": subcats,
        "total": len(subcats),
        "all_features": get_all_detectable_features(),
        "supported_file_types": {
            "upload": SUPPORTED_FILE_TYPES_BY_CATEGORY,
            "url_suffix_hints": URL_SUFFIX_HINTS_BY_CATEGORY,
            "counts": {category: len(values) for category, values in SUPPORTED_FILE_TYPES_BY_CATEGORY.items()},
            "upload_total": sum(len(values) for values in SUPPORTED_FILE_TYPES_BY_CATEGORY.values()),
            "notes": {
                "category_binding": "Category is derived operationally from MIME type or URL/file signals; subcategory is derived from evidence in the asset.",
                "software_application": "Software Application currently has no dedicated upload extensions and is primarily inferred from URL text/metadata.",
                "xlsx": "XLSX is usually routed as Dataset, but may remain Document in lightweight spreadsheet cases.",
            },
        },
    }


@app.get("/intended-purposes")
async def list_intended_purposes(request: Request):
    """List the intended-purpose (user-intent) taxonomy used for classification.

    Useful for UI configuration and for understanding the `intended_purposes`
    block returned by `/classify`. Multi-label, capped at 3 per asset.
    """
    from docint.purposes.infer import load_purposes, PURPOSE_MAX_SELECTED

    purposes = load_purposes()
    by_category: Dict[str, List[Dict[str, str]]] = {}
    items = []
    for p in purposes:
        entry = {"key": p.key, "name": p.name, "category": p.category, "description": p.description}
        items.append(entry)
        by_category.setdefault(p.category or "Uncategorised", []).append(entry)

    return {
        "intended_purposes": items,
        "total": len(items),
        "by_category": by_category,
        "category_count": len(by_category),
        "max_selected_per_asset": PURPOSE_MAX_SELECTED,
        "version": "intended_purpose_v1",
    }


if __name__ == "__main__":
    import uvicorn
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host=host, port=port)
