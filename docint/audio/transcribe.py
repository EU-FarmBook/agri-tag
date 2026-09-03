from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from openai import OpenAI


@dataclass
class AudioTranscriptionResult:
    available: bool
    used: bool
    text: str
    method: str
    model: Optional[str]
    rationale: str


def _normalized_base_url(url: str) -> str:
    """Bare host or a /v1 root both work, matching the LLM settings."""
    normalized = (url or "").rstrip("/")
    if normalized and not normalized.endswith("/v1"):
        normalized += "/v1"
    return normalized


def transcribe_audio_file(file_path: str) -> AudioTranscriptionResult:
    enabled = os.getenv("MEDIA_TRANSCRIBER_ENABLED", "false").lower() == "true"
    base_url = _normalized_base_url(os.getenv("MEDIA_TRANSCRIBER_BASE_URL", ""))
    model = os.getenv("MEDIA_TRANSCRIBER_WHISPER_MODEL", "").strip()
    api_key = os.getenv("MEDIA_TRANSCRIBER_API_KEY", "").strip()

    if not enabled:
        return AudioTranscriptionResult(
            available=False,
            used=False,
            text="",
            method="disabled",
            model=model or None,
            rationale="Audio transcription disabled by configuration",
        )

    if not (base_url and model):
        return AudioTranscriptionResult(
            available=False,
            used=False,
            text="",
            method="not_configured",
            model=model or None,
            rationale="Audio transcription backend not configured",
        )

    # OpenAI-compatible speech-to-text: POST {base_url}/audio/transcriptions,
    # multipart `file` plus a `model` field, answering {"text": ...}. This is
    # what Scaleway's whisper-large-v3 serves. The previous backend was a
    # self-hosted service with its own /transcribe/upload route, a
    # `whisper_model` field and a `mode` field that has no equivalent here.
    client = OpenAI(base_url=base_url, api_key=api_key, timeout=180.0)
    with open(file_path, "rb") as fh:
        resp = client.audio.transcriptions.create(
            model=model,
            file=(os.path.basename(file_path), fh),
        )

    text = (getattr(resp, "text", "") or "").strip()
    if not text:
        return AudioTranscriptionResult(
            available=True,
            used=True,
            text="",
            method="openai_audio_transcriptions",
            model=model,
            rationale="Audio transcription returned no usable text",
        )

    return AudioTranscriptionResult(
        available=True,
        used=True,
        text=text,
        method="openai_audio_transcriptions",
        model=model,
        rationale="Audio successfully transcribed for downstream agriculture and subtype classification",
    )
