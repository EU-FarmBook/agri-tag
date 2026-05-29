from __future__ import annotations

from docint.extract.pdf_text import extract_pdf_text
from docint.ingest.models import IngestedAsset


def ingest_pdf(pdf_path: str, filename: str) -> IngestedAsset:
    doc = extract_pdf_text(pdf_path, max_pages=None)
    return IngestedAsset(
        asset_type="pdf",
        filename=filename,
        source_path=pdf_path,
        text=doc.text,
        lines=doc.lines,
        units=doc.pages,
        unit_label="pages",
        source=doc.source,
        mime_type="application/pdf",
        visual_candidate=True,
        ocr_supported=True,
        meta=doc.meta,
    )
