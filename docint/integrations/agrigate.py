from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

import httpx


@dataclass
class AgriGateScanResult:
    ok: bool
    allowed: bool
    status: str
    reason_code: Optional[str]
    reason: str
    details: Dict[str, Any]
    raw: Dict[str, Any]


def _normalized_base_url(url: str) -> str:
    return (url or "").rstrip("/")


def _headers(token: str) -> Dict[str, str]:
    token = (token or "").strip()
    if not token:
        return {}
    return {"Authorization": f"Bearer {token}"}


def _interpret_allowed(payload: Dict[str, Any]) -> bool:
    status = str(payload.get("status", "")).strip().lower()
    if status in {"allowed", "clean", "safe", "ok", "passed", "pass"}:
        return True
    if status in {"blocked", "unsafe", "rejected", "malicious", "deny", "denied"}:
        return False

    for key in ("allowed", "safe", "is_safe", "clean", "passed"):
        value = payload.get(key)
        if isinstance(value, bool):
            return value

    for key in ("blocked", "unsafe", "is_blocked", "malicious"):
        value = payload.get(key)
        if isinstance(value, bool):
            return not value

    return False


def _scan_result_from_payload(payload: Dict[str, Any]) -> AgriGateScanResult:
    return AgriGateScanResult(
        ok=True,
        allowed=_interpret_allowed(payload),
        status=str(payload.get("status", "")).strip() or "unknown",
        reason_code=(str(payload.get("reason_code", "")).strip() or None),
        reason=str(payload.get("reason", "")).strip() or "No reason provided",
        details=payload.get("details", {}) if isinstance(payload.get("details", {}), dict) else {},
        raw=payload,
    )


def scan_url(url: str) -> AgriGateScanResult:
    base_url = _normalized_base_url(os.getenv("AGRI_GATE_BASE_URL", ""))
    token = os.getenv("AGRI_GATE_API_TOKEN", "").strip()
    timeout = float(os.getenv("AGRI_GATE_TIMEOUT", "60"))

    if not base_url:
        return AgriGateScanResult(
            ok=False,
            allowed=False,
            status="not_configured",
            reason_code="agrigate_not_configured",
            reason="Agri Gate base URL is not configured",
            details={},
            raw={},
        )

    with httpx.Client(timeout=timeout) as client:
        response = client.post(
            f"{base_url}/v1/scan/url",
            headers={**_headers(token), "Content-Type": "application/json"},
            json={"url": url},
        )
        response.raise_for_status()
        payload = response.json()
    return _scan_result_from_payload(payload)


def scan_file(file_path: str, filename: Optional[str] = None) -> AgriGateScanResult:
    base_url = _normalized_base_url(os.getenv("AGRI_GATE_BASE_URL", ""))
    token = os.getenv("AGRI_GATE_API_TOKEN", "").strip()
    timeout = float(os.getenv("AGRI_GATE_TIMEOUT", "60"))

    if not base_url:
        return AgriGateScanResult(
            ok=False,
            allowed=False,
            status="not_configured",
            reason_code="agrigate_not_configured",
            reason="Agri Gate base URL is not configured",
            details={},
            raw={},
        )

    upload_name = filename or Path(file_path).name
    with open(file_path, "rb") as fh, httpx.Client(timeout=timeout) as client:
        response = client.post(
            f"{base_url}/v1/scan/file",
            headers=_headers(token),
            files={"file": (upload_name, fh)},
        )
        response.raise_for_status()
        payload = response.json()
    return _scan_result_from_payload(payload)
