"""
Mistral AI provider adapters.

Kept deliberately separate from the OpenAI-compatible "custom LLM" flow so the
two paths do not get mixed up. This module owns:

- Mistral configuration (API key, endpoint, model names) read from the environment.
- OCR adapters (``mistral-ocr-latest``) that return the same ``ExtractedDoc`` the
  rest of the pipeline expects, so they are drop-in replacements for the local
  Tesseract OCR fallback.
- An audio/video transcription adapter (Voxtral) that returns the same
  ``AudioTranscriptionResult`` as the Whisper media-transcriber path.

Text and vision *classification* against Mistral is intentionally NOT
re-implemented here. Mistral exposes an OpenAI-compatible chat endpoint
(``MISTRAL_OPENAI_BASE_URL``), so the existing classification functions in
``docint.llm.subcategory_classify`` are reused unchanged, just pointed at
Mistral via ``MISTRAL_API_KEY`` / ``MISTRAL_TEXT_MODEL`` / ``MISTRAL_VISION_MODEL``.
The routing that selects this configuration lives in ``app.py``.

The ``mistralai`` SDK is imported lazily inside ``_client()`` so importing this
module never hard-fails when the package is absent; only the OCR/transcription
functions require it.
"""
from __future__ import annotations

import base64
import os
from pathlib import Path
from typing import Optional, Tuple

from docint.extract.pdf_text import ExtractedDoc
from docint.audio.transcribe import AudioTranscriptionResult

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY", "").strip()
# OpenAI-compatible chat endpoint, used by the reused classification functions.
MISTRAL_OPENAI_BASE_URL = os.getenv("MISTRAL_OPENAI_BASE_URL", "https://api.mistral.ai/v1").rstrip("/")
# Optional override of the native SDK server URL (OCR / transcription).
MISTRAL_SERVER_URL = os.getenv("MISTRAL_SERVER_URL", "").strip()

MISTRAL_TEXT_MODEL = os.getenv("MISTRAL_TEXT_MODEL", "mistral-small-latest").strip()
MISTRAL_VISION_MODEL = os.getenv("MISTRAL_VISION_MODEL", "mistral-medium-latest").strip()
MISTRAL_OCR_MODEL = os.getenv("MISTRAL_OCR_MODEL", "mistral-ocr-latest").strip()
MISTRAL_AUDIO_MODEL = os.getenv("MISTRAL_AUDIO_MODEL", "voxtral-mini-latest").strip()

MISTRAL_CONFIGURED = bool(MISTRAL_API_KEY)


def _client():
    """Build a native Mistral SDK client (lazy import)."""
    try:
        from mistralai import Mistral
    except ImportError as exc:  # pragma: no cover - depends on optional dep
        raise ImportError(
            "The 'mistralai' package is required for Mistral OCR/transcription. "
            "Install it with: pip install mistralai"
        ) from exc
    if not MISTRAL_API_KEY:
        raise RuntimeError("MISTRAL_API_KEY is not configured.")
    if MISTRAL_SERVER_URL:
        return Mistral(api_key=MISTRAL_API_KEY, server_url=MISTRAL_SERVER_URL)
    return Mistral(api_key=MISTRAL_API_KEY)


def _b64(path: str) -> str:
    return base64.b64encode(Path(path).read_bytes()).decode("utf-8")


# ---------------------------------------------------------------------------
# OCR  (mistral-ocr-latest)
# ---------------------------------------------------------------------------

def _ocr_pages_to_text(resp, *, max_pages: Optional[int] = None) -> Tuple[str, int]:
    """Flatten a Mistral OCR response into plain text + page count."""
    pages = getattr(resp, "pages", None)
    if pages is None and isinstance(resp, dict):
        pages = resp.get("pages")
    pages = pages or []
    total = len(pages)

    chunks = []
    for idx, pg in enumerate(pages):
        if max_pages is not None and idx >= max_pages:
            break
        markdown = getattr(pg, "markdown", None)
        if markdown is None and isinstance(pg, dict):
            markdown = pg.get("markdown")
        if markdown:
            chunks.append(markdown.strip())

    return "\n\n".join(chunks).strip(), total


def mistral_ocr_pdf(pdf_path: str, *, max_pages: Optional[int] = None) -> ExtractedDoc:
    """OCR a PDF via Mistral OCR, returning an ExtractedDoc (source='mistral_ocr')."""
    client = _client()
    document = {
        "type": "document_url",
        "document_url": f"data:application/pdf;base64,{_b64(pdf_path)}",
    }
    resp = client.ocr.process(
        model=MISTRAL_OCR_MODEL,
        document=document,
        include_image_base64=False,
    )
    text, total_pages = _ocr_pages_to_text(resp, max_pages=max_pages)
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return ExtractedDoc(
        text=text,
        lines=lines,
        pages=total_pages,
        source="mistral_ocr",
        meta={
            "ocr_provider": "mistral",
            "ocr_model": MISTRAL_OCR_MODEL,
            "pdf_path": pdf_path,
            "ocr_max_pages_kept": max_pages,
        },
    )


def mistral_ocr_image(image_path: str, **_ignored) -> ExtractedDoc:
    """OCR a single image via Mistral OCR, returning an ExtractedDoc.

    Accepts and ignores extra keyword arguments (e.g. ``lang``) so it is a drop-in
    replacement for the Tesseract ``ocr_image`` call site.
    """
    client = _client()
    suffix = Path(image_path).suffix.lower()
    mime = "image/png" if suffix == ".png" else "image/jpeg"
    document = {
        "type": "image_url",
        "image_url": f"data:{mime};base64,{_b64(image_path)}",
    }
    resp = client.ocr.process(
        model=MISTRAL_OCR_MODEL,
        document=document,
        include_image_base64=False,
    )
    text, total_pages = _ocr_pages_to_text(resp)
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return ExtractedDoc(
        text=text,
        lines=lines,
        pages=max(1, total_pages),
        source="mistral_ocr",
        meta={
            "ocr_provider": "mistral",
            "ocr_model": MISTRAL_OCR_MODEL,
            "image_path": image_path,
        },
    )


# ---------------------------------------------------------------------------
# Audio / video transcription  (Voxtral)
# ---------------------------------------------------------------------------

def mistral_transcribe(file_path: str, *, diarize: bool = False) -> AudioTranscriptionResult:
    """Transcribe an audio/video file via Mistral Voxtral.

    Returns the same AudioTranscriptionResult dataclass as the Whisper path so it
    is a drop-in replacement at the call site. Failure is fail-safe: it returns a
    result with ``available=False`` rather than raising.
    """
    if not MISTRAL_CONFIGURED:
        return AudioTranscriptionResult(
            available=False,
            used=False,
            text="",
            method="not_configured",
            model=MISTRAL_AUDIO_MODEL,
            rationale="Mistral API key not configured for transcription",
        )

    try:
        client = _client()
        with open(file_path, "rb") as fh:
            content = fh.read()
        kwargs = {
            "model": MISTRAL_AUDIO_MODEL,
            "file": {"file_name": os.path.basename(file_path), "content": content},
        }
        if diarize:
            kwargs["diarize"] = True
        transcription = client.audio.transcriptions.complete(**kwargs)
        text = (getattr(transcription, "text", "") or "").strip()
        return AudioTranscriptionResult(
            available=True,
            used=bool(text),
            text=text,
            method="mistral_voxtral",
            model=MISTRAL_AUDIO_MODEL,
            rationale=(
                "Transcribed via Mistral Voxtral"
                if text
                else "Mistral Voxtral returned an empty transcript"
            ),
        )
    except Exception as exc:  # fail-safe, mirrors the Whisper path's tolerance
        return AudioTranscriptionResult(
            available=False,
            used=False,
            text="",
            method="error",
            model=MISTRAL_AUDIO_MODEL,
            rationale=f"Mistral transcription failed: {exc}",
        )
