from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import fitz
from PIL import Image

from docint.ingest import ai_uploader_criteria as criteria


def _raises_criteria_violation(fn):
    try:
        fn()
    except criteria.CriteriaViolation as exc:
        return exc
    raise AssertionError("Expected CriteriaViolation")


def test_global_size_limit_rejects_without_large_file():
    result = criteria.validate_upload_size(criteria.MAX_BYTES + 1)

    assert result.ok is False
    assert result.code == "file_too_large"


def test_text_limits_match_ai_uploader(tmp_path: Path):
    path = tmp_path / "oversize.txt"
    path.write_bytes(b"a" * (criteria.TEXT_MAX_BYTES + 1))

    exc = _raises_criteria_violation(
        lambda: criteria.validate_asset_against_ai_uploader_criteria(str(path), "oversize.txt")
    )

    assert exc.status_code == 413
    assert exc.code in {"text_too_large_bytes", "text_too_large_chars"}


def test_image_side_limit_matches_ai_uploader(tmp_path: Path):
    path = tmp_path / "wide.png"
    Image.new("RGB", (criteria.IMAGE_MAX_SIDE_PX + 1, 1), "white").save(path)

    exc = _raises_criteria_violation(
        lambda: criteria.validate_asset_against_ai_uploader_criteria(str(path), "wide.png")
    )

    assert exc.status_code == 413
    assert exc.code == "image_too_large"


def test_pdf_page_limit_matches_ai_uploader(tmp_path: Path):
    path = tmp_path / "long.pdf"
    doc = fitz.open()
    for _ in range(criteria.PDF_MAX_PAGES + 1):
        doc.new_page()
    doc.save(path)
    doc.close()

    exc = _raises_criteria_violation(
        lambda: criteria.validate_asset_against_ai_uploader_criteria(str(path), "long.pdf")
    )

    assert exc.status_code == 413
    assert exc.code == "pdf_too_long"


def _run_standalone() -> int:
    import tempfile

    tests = [
        test_global_size_limit_rejects_without_large_file,
        test_text_limits_match_ai_uploader,
        test_image_side_limit_matches_ai_uploader,
        test_pdf_page_limit_matches_ai_uploader,
    ]
    failed = 0
    for test in tests:
        try:
            if "tmp_path" in test.__code__.co_varnames:
                with tempfile.TemporaryDirectory() as td:
                    test(Path(td))
            else:
                test()
            print(f"PASS  {test.__name__}")
        except Exception as exc:
            failed += 1
            print(f"FAIL  {test.__name__}: {type(exc).__name__}: {exc}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(_run_standalone())
