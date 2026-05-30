#!/usr/bin/env python3
"""
Offline smoke tests for the Agri-Tag API.

Runs in-process via FastAPI TestClient — no running server and no remote LLM calls
(text/vision LLMs are disabled in the classification test). The embedding model
(e5-small) is loaded locally for the agriculture/topics/purpose stages, so the
first run may download it once.

Run either way:
    pytest tests/test_smoke.py -v        # if pytest is installed
    python tests/test_smoke.py           # standalone, no pytest needed
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402
import app as appmod  # noqa: E402

client = TestClient(appmod.app)
_USER = os.getenv("DOCINT_AUTH_USERS", "").split(",")[0].strip()
_PW = os.getenv("DOCINT_AUTH_PASSWORD", "").strip()
AUTH = (_USER, _PW) if _USER and _PW else None
AUTH_ENABLED = AUTH is not None


def test_health_is_public():
    r = client.get("/health")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("status") == "ok"
    assert "models" in body


def test_root_requires_auth_when_enabled():
    if not AUTH_ENABLED:
        return  # auth not configured -> nothing to assert
    r = client.get("/")  # no creds
    assert r.status_code == 401


def test_subcategories_taxonomy():
    r = client.get("/subcategories", auth=AUTH)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("total", 0) > 0
    assert isinstance(body.get("subcategories"), dict)


def test_intended_purposes_taxonomy():
    r = client.get("/intended-purposes", auth=AUTH)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("total", 0) > 0
    assert body.get("max_selected_per_asset") == 3
    # every entry has the fields the classifier relies on
    for p in body["intended_purposes"]:
        assert p.get("key") and p.get("name")


def test_classify_text_empty_is_400():
    r = client.post("/classify-text", json={"text": "   "}, auth=AUTH)
    assert r.status_code == 400, r.text


def test_classify_text_oversize_is_413():
    r = client.post("/classify-text", json={"text": "word " * 5001}, auth=AUTH)
    assert r.status_code == 413, r.text


def test_provider_enum_rejects_invalid():
    # enum-validated query param -> FastAPI returns 422 for unknown values
    r = client.post("/classify-text?provider=banana", json={"text": "hello world"}, auth=AUTH)
    assert r.status_code == 422, r.text


def test_classify_text_basic_and_cardinality():
    # Offline: no text LLM, no agri gate -> heuristics + local embeddings only.
    text = (
        "This step-by-step guide explains how farmers can adopt precision irrigation "
        "with soil moisture sensors and scheduling to apply ready-to-use water-saving "
        "practices in the field. "
    ) * 6
    r = client.post(
        "/classify-text",
        params={"use_text_llm": "false", "auto_route_models": "false", "require_agriculture": "false"},
        json={"text": text},
        auth=AUTH,
    )
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["category_used"] == "Document"
    assert d.get("best_match") is not None
    # subcategory cardinality: best, plus a close runner-up only -> at most 2
    assert len(d.get("all_candidates", [])) <= 2
    assert d["processing_info"]["source_mode"] == "text"


def _run_standalone() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS  {t.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"FAIL  {t.__name__}: {e}")
            failed += 1
        except Exception as e:  # noqa: BLE001
            print(f"ERROR {t.__name__}: {type(e).__name__}: {e}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(_run_standalone())
