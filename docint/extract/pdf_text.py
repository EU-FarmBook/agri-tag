# docint/extract/pdf_text.py

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Dict, Any

import fitz  # PyMuPDF


@dataclass
class ExtractedDoc:
    """
    Standard container for extracted document text + minimal metadata.
    Keeping this consistent makes downstream steps (features/rubrics/LLM) simpler.
    """
    text: str
    lines: List[str]
    pages: int
    source: str  # "pdf_text" or "ocr"
    meta: Dict[str, Any]


def extract_pdf_text(
    pdf_path: str,
    *,
    max_pages: Optional[int] = None,
    join_pages_with: str = "\n\n",
) -> ExtractedDoc:
    """
    Extract text from a PDF using PyMuPDF.

    Notes:
    - This is fast and preserves a reasonable reading order for many PDFs.
    - For scanned PDFs (images), this often returns very little text; use OCR fallback.

    Args:
        pdf_path: path to PDF
        max_pages: if set, only extract from the first N pages (speed for quick classification)
        join_pages_with: separator between pages (useful to keep page boundaries visible)

    Returns:
        ExtractedDoc
    """
    doc = fitz.open(pdf_path)
    total_pages = doc.page_count

    n = total_pages if max_pages is None else min(max_pages, total_pages)

    page_texts: List[str] = []
    all_lines: List[str] = []

    for i in range(n):
        page = doc.load_page(i)
        # "text" gives a simple linearised output. We may later switch to "blocks" if needed.
        t = page.get_text("text") or ""
        page_texts.append(t)

        # Keep line boundaries for heading detection and section counting
        for ln in t.splitlines():
            ln = ln.strip()
            if ln:
                all_lines.append(ln)

    full_text = join_pages_with.join(page_texts).strip()

    return ExtractedDoc(
        text=full_text,
        lines=all_lines,
        pages=total_pages,
        source="pdf_text",
        meta={
            "pdf_path": pdf_path,
            "extracted_pages": n,
            "total_pages": total_pages,
            "engine": "pymupdf",
        },
    )
