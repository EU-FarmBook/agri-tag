from __future__ import annotations

from dataclasses import dataclass
import math
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import fitz
from PIL import Image

from docint.video.extract import media_duration_seconds


MAX_BYTES = int(os.getenv("EUF_AI_MAX_BYTES", str(1024 * 1024 * 1024)))
MEDIA_MAX_DURATION_SECONDS = max(60, int(os.getenv("EUF_AI_MEDIA_MAX_DURATION_SECONDS", "3000")))
PDF_MAX_PAGES = max(1, int(os.getenv("EUF_AI_PDF_MAX_PAGES", "100")))
OFFICE_MAX_PAGES = max(1, int(os.getenv("EUF_AI_OFFICE_MAX_PAGES", "100")))
TEXT_MAX_BYTES = max(1, int(os.getenv("EUF_AI_TEXT_MAX_BYTES", str(5 * 1024 * 1024))))
TEXT_MAX_CHARS = max(1, int(os.getenv("EUF_AI_TEXT_MAX_CHARS", "500000")))
IMAGE_MAX_SIDE_PX = max(1, int(os.getenv("EUF_AI_IMAGE_MAX_SIDE_PX", "10000")))

DOCUMENT_EXTS = {".pdf", ".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx"}
OFFICE_EXTS = {".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx"}
TEXT_EXTS = {".txt", ".csv", ".tsv", ".json"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png"}
AUDIO_EXTS = {".mp3", ".wav", ".m4a"}
VIDEO_EXTS = {
    ".mp4",
    ".avi",
    ".mov",
    ".wmv",
    ".mpeg",
    ".mpg",
    ".mkv",
    ".flv",
    ".webm",
    ".3gp",
    ".mts",
    ".m2ts",
    ".vob",
    ".rmvb",
}
MEDIA_EXTS = AUDIO_EXTS | VIDEO_EXTS


@dataclass(slots=True)
class CriteriaResult:
    ok: bool = True
    code: str = "ok"
    message: str = ""
    details: dict | None = None


class CriteriaViolation(ValueError):
    def __init__(self, status_code: int, message: str, *, code: str, details: dict | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.message = message
        self.code = code
        self.details = details or {}


def suffix_of(filename: str) -> str:
    return Path(filename or "").suffix.lower()


def validate_upload_size(size_bytes: int) -> CriteriaResult:
    if size_bytes > MAX_BYTES:
        return CriteriaResult(
            ok=False,
            code="file_too_large",
            message="File is too large for AI-assisted ingestion. Maximum allowed size is 1 GB.",
            details={"size_bytes": size_bytes, "max_bytes": MAX_BYTES},
        )
    return CriteriaResult(details={"size_bytes": size_bytes, "max_bytes": MAX_BYTES})


def _raise_if_failed(result: CriteriaResult, status_code: int = 413) -> None:
    if not result.ok:
        raise CriteriaViolation(status_code, result.message, code=result.code, details=result.details)


def pdf_page_count(file_path: str) -> int:
    with fitz.open(file_path) as doc:
        return int(doc.page_count or 0)


def _soffice_binary() -> str:
    soffice = shutil.which("libreoffice") or shutil.which("soffice")
    if not soffice:
        raise CriteriaViolation(
            422,
            "Office document page inspection requires LibreOffice/soffice on PATH.",
            code="office_page_inspection_unavailable",
        )
    return soffice


def office_document_page_count(file_path: str) -> int:
    soffice = _soffice_binary()
    source_path = Path(file_path)
    with tempfile.TemporaryDirectory(prefix="agritag-office-pages-") as td:
        work_dir = Path(td)
        output_dir = work_dir / "converted"
        output_dir.mkdir(parents=True, exist_ok=True)
        profile_dir = work_dir / "libreoffice-profile"
        profile_dir.mkdir(parents=True, exist_ok=True)

        result = subprocess.run(
            [
                soffice,
                f"-env:UserInstallation=file://{profile_dir}",
                "--headless",
                "--convert-to",
                "pdf",
                "--outdir",
                str(output_dir),
                str(source_path),
            ],
            cwd=str(work_dir),
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
        if result.returncode != 0:
            stderr = (result.stderr or result.stdout or "").strip()
            raise CriteriaViolation(
                422,
                f"Office document page inspection failed: {stderr or 'unknown LibreOffice error'}",
                code="office_page_inspection_failed",
            )

        pdf_path = output_dir / f"{source_path.stem}.pdf"
        if not pdf_path.exists():
            pdfs = sorted(output_dir.glob("*.pdf"))
            if len(pdfs) == 1:
                pdf_path = pdfs[0]
        if not pdf_path.exists():
            raise CriteriaViolation(
                422,
                "Office document page inspection produced no PDF output.",
                code="office_page_inspection_failed",
            )

        return pdf_page_count(str(pdf_path))


def text_stats(file_path: str) -> tuple[int, int]:
    total_bytes = 0
    total_chars = 0
    decoder_buffer = b""
    with Path(file_path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            total_bytes += len(chunk)
            if total_bytes > TEXT_MAX_BYTES:
                return total_bytes, total_chars
            decoder_buffer += chunk
            try:
                text = decoder_buffer.decode("utf-8")
                decoder_buffer = b""
            except UnicodeDecodeError:
                keep = min(len(decoder_buffer), 4)
                text = decoder_buffer[:-keep].decode("utf-8", errors="replace") if len(decoder_buffer) > keep else ""
                decoder_buffer = decoder_buffer[-keep:]
            total_chars += len(text)
            if total_chars > TEXT_MAX_CHARS:
                return total_bytes, total_chars
    if decoder_buffer:
        total_chars += len(decoder_buffer.decode("utf-8", errors="replace"))
    return total_bytes, total_chars


def estimated_text_pages(file_path: str) -> int:
    text = Path(file_path).read_text(encoding="utf-8", errors="replace")
    lines = [line for line in text.splitlines() if line.strip()]
    return max(1, math.ceil(len(lines) / 40))


def image_dimensions(file_path: str) -> tuple[int, int]:
    with Image.open(file_path) as image:
        return int(image.width or 0), int(image.height or 0)


def validate_asset_against_ai_uploader_criteria(file_path: str, filename: str, *, size_bytes: int | None = None) -> dict:
    suffix = suffix_of(filename)
    if size_bytes is None:
        size_bytes = Path(file_path).stat().st_size

    _raise_if_failed(validate_upload_size(size_bytes))

    if suffix in MEDIA_EXTS:
        duration_seconds = media_duration_seconds(file_path) or 0.0
        if duration_seconds > MEDIA_MAX_DURATION_SECONDS:
            label = "Audio" if suffix in AUDIO_EXTS else "Video"
            max_minutes = int(MEDIA_MAX_DURATION_SECONDS // 60)
            raise CriteriaViolation(
                413,
                f"{label} is too long for AI-assisted ingestion. Maximum allowed duration is {max_minutes} minutes.",
                code="media_too_long",
                details={"duration_seconds": duration_seconds, "max_duration_seconds": MEDIA_MAX_DURATION_SECONDS},
            )
        return {"duration_seconds": duration_seconds, "size_bytes": size_bytes}

    if suffix == ".pdf":
        pages = pdf_page_count(file_path)
        if pages > PDF_MAX_PAGES:
            raise CriteriaViolation(
                413,
                (
                    f"PDF is too long for AI-assisted ingestion. Maximum allowed length is {PDF_MAX_PAGES} pages; "
                    f"this file has {pages} pages."
                ),
                code="pdf_too_long",
                details={"page_count": pages, "max_pages": PDF_MAX_PAGES},
            )
        return {"page_count": pages, "unit_label": "pages", "size_bytes": size_bytes}

    if suffix in OFFICE_EXTS:
        pages = office_document_page_count(file_path)
        if pages > OFFICE_MAX_PAGES:
            raise CriteriaViolation(
                413,
                (
                    f"Office document is too long for AI-assisted ingestion. Maximum allowed converted length is "
                    f"{OFFICE_MAX_PAGES} pages/slides; this file converts to {pages}."
                ),
                code="office_too_long",
                details={"page_count": pages, "max_pages": OFFICE_MAX_PAGES},
            )
        return {"page_count": pages, "unit_label": "pages", "size_bytes": size_bytes}

    if suffix in TEXT_EXTS:
        total_bytes, total_chars = text_stats(file_path)
        if total_bytes > TEXT_MAX_BYTES:
            raise CriteriaViolation(
                413,
                f"Text file is too large for AI-assisted ingestion. Maximum allowed raw size is {TEXT_MAX_BYTES // (1024 * 1024)} MB.",
                code="text_too_large_bytes",
                details={"size_bytes": total_bytes, "max_bytes": TEXT_MAX_BYTES, "char_count": total_chars},
            )
        if total_chars > TEXT_MAX_CHARS:
            raise CriteriaViolation(
                413,
                f"Text file is too large for AI-assisted ingestion. Maximum allowed extracted text length is {TEXT_MAX_CHARS} characters.",
                code="text_too_large_chars",
                details={"size_bytes": total_bytes, "char_count": total_chars, "max_chars": TEXT_MAX_CHARS},
            )
        return {
            "size_bytes": total_bytes,
            "char_count": total_chars,
            "estimated_pages": estimated_text_pages(file_path),
            "unit_label": "estimated_pages",
        }

    if suffix in IMAGE_EXTS:
        width, height = image_dimensions(file_path)
        if max(width, height) > IMAGE_MAX_SIDE_PX:
            raise CriteriaViolation(
                413,
                f"Image is too large for AI-assisted ingestion. Maximum allowed width or height is {IMAGE_MAX_SIDE_PX}px.",
                code="image_too_large",
                details={"width": width, "height": height, "max_side_px": IMAGE_MAX_SIDE_PX},
            )
        return {"width": width, "height": height, "size_bytes": size_bytes}

    return {"size_bytes": size_bytes}
