from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

import httpx


@dataclass
class AudioTranscriptionResult:
    available: bool
    used: bool
    text: str
    method: str
    model: Optional[str]
    rationale: str


def _normalized_base_url(url: str) -> str:
    return (url or "").rstrip("/")


def transcribe_audio_file(file_path: str) -> AudioTranscriptionResult:
    enabled = os.getenv("MEDIA_TRANSCRIBER_ENABLED", "false").lower() == "true"
    base_url = _normalized_base_url(os.getenv("MEDIA_TRANSCRIBER_BASE_URL", ""))
    model = os.getenv("MEDIA_TRANSCRIBER_WHISPER_MODEL", "").strip()
    mode = os.getenv("MEDIA_TRANSCRIBER_MODE", "auto").strip() or "auto"
    api_key = os.getenv("MEDIA_TRANSCRIBER_API_KEY", "").strip()
    basic_user = os.getenv("MEDIA_TRANSCRIBER_BASIC_USER", "").strip()
    basic_pass = os.getenv("MEDIA_TRANSCRIBER_BASIC_PASS", "").strip()

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

    headers = {}
    if api_key:
        headers["x-api-key"] = api_key

    auth = (basic_user, basic_pass) if basic_user and basic_pass else None

    with open(file_path, "rb") as fh, httpx.Client(timeout=180.0, auth=auth) as client:
        resp = client.post(
            f"{base_url}/transcribe/upload",
            headers=headers,
            files={"file": (os.path.basename(file_path), fh)},
            data={"whisper_model": model, "mode": mode},
        )
        resp.raise_for_status()
        payload = resp.json()

    text = (
        payload.get("text")
        or payload.get("transcript")
        or payload.get("result", {}).get("text")
        or ""
    ).strip()
    if not text:
        return AudioTranscriptionResult(
            available=True,
            used=True,
            text="",
            method="media_transcriber_upload",
            model=model,
            rationale="Audio transcription returned no usable text",
        )

    return AudioTranscriptionResult(
        available=True,
        used=True,
        text=text,
        method="media_transcriber_upload",
        model=model,
        rationale="Audio successfully transcribed for downstream agriculture and subtype classification",
    )
