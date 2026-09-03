from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, Optional

import httpx


@dataclass
class PageSenseResult:
    ok: bool
    text: str
    title: Optional[str]
    content_kind: Optional[str]
    content_type: Optional[str]
    size_bytes: Optional[int]
    page_count: Optional[int]
    duration_seconds: Optional[float]
    raw: Dict[str, Any]
    rationale: str


def _normalized_base_url(url: str) -> str:
    return (url or "").rstrip("/")


def _extractor_auth() -> Optional[tuple[str, str]]:
    """Basic-auth credentials for PageSense, or None when unset.

    PageSense's /api/extract has no authentication of its own; the deployment
    gates it with HTTP basic auth at the ingress, so an unauthenticated call
    comes back as 401 with no useful body. Left unset (as in a local run
    against an ungated instance) the request is sent without credentials.
    """
    user = os.getenv("URL_CONTENT_EXTRACTOR_USER", "").strip()
    password = os.getenv("URL_CONTENT_EXTRACTOR_PASSWORD", "")
    return (user, password) if user else None


def extract_url_text(url: str) -> PageSenseResult:
    base_url = _normalized_base_url(os.getenv("URL_CONTENT_EXTRACTOR_BASE", ""))
    timeout = float(os.getenv("EXTRACTOR_TIMEOUT", "60"))

    if not base_url:
        return PageSenseResult(
            ok=False,
            text="",
            title=None,
            content_kind=None,
            content_type=None,
            size_bytes=None,
            page_count=None,
            duration_seconds=None,
            raw={},
            rationale="PageSense base URL is not configured",
        )

    with httpx.Client(timeout=timeout, auth=_extractor_auth()) as client:
        try:
            response = client.post(
                f"{base_url}/api/extract",
                headers={"Content-Type": "application/json"},
                json={"url": url},
            )
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPStatusError as exc:
            response = exc.response
            try:
                payload = response.json()
            except Exception:
                payload = {}
            detail = (
                payload.get("detail")
                or payload.get("error")
                or payload.get("message")
                or response.text.strip()
                or f"PageSense returned HTTP {response.status_code}"
            )
            return PageSenseResult(
                ok=False,
                text="",
                title=None,
                content_kind=None,
                content_type=None,
                size_bytes=None,
                page_count=None,
                duration_seconds=None,
                raw=payload if isinstance(payload, dict) else {},
                rationale=f"PageSense rejected the URL: {detail}",
            )
        except httpx.HTTPError as exc:
            return PageSenseResult(
                ok=False,
                text="",
                title=None,
                content_kind=None,
                content_type=None,
                size_bytes=None,
                page_count=None,
                duration_seconds=None,
                raw={},
                rationale=f"PageSense request failed: {str(exc)}",
            )

    text = (
        payload.get("text")
        or payload.get("content")
        or payload.get("raw_text")
        or payload.get("result", {}).get("text")
        or ""
    )
    text = text.strip()
    title = (
        payload.get("title")
        or payload.get("meta", {}).get("title")
        or payload.get("result", {}).get("title")
    )
    meta = payload.get("meta", {}) if isinstance(payload.get("meta", {}), dict) else {}
    result_meta = payload.get("result", {}) if isinstance(payload.get("result", {}), dict) else {}

    def _as_int(value: Any) -> Optional[int]:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _as_float(value: Any) -> Optional[float]:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    content_kind = (
        payload.get("content_kind")
        or meta.get("content_kind")
        or result_meta.get("content_kind")
    )
    content_type = (
        payload.get("content_type")
        or meta.get("content_type")
        or result_meta.get("content_type")
    )
    size_bytes = _as_int(
        payload.get("size_bytes")
        or payload.get("size")
        or meta.get("size_bytes")
        or meta.get("size")
        or result_meta.get("size_bytes")
        or result_meta.get("size")
    )
    page_count = _as_int(
        payload.get("page_count")
        or meta.get("page_count")
        or result_meta.get("page_count")
    )
    duration_seconds = _as_float(
        payload.get("duration_seconds")
        or meta.get("duration_seconds")
        or result_meta.get("duration_seconds")
    )

    return PageSenseResult(
        ok=bool(text),
        text=text,
        title=title.strip() if isinstance(title, str) and title.strip() else None,
        content_kind=str(content_kind).strip() if isinstance(content_kind, str) and content_kind.strip() else None,
        content_type=str(content_type).strip() if isinstance(content_type, str) and content_type.strip() else None,
        size_bytes=size_bytes,
        page_count=page_count,
        duration_seconds=duration_seconds,
        raw=payload,
        rationale="Extracted raw readable text via PageSense" if text else "PageSense returned no usable text",
    )
