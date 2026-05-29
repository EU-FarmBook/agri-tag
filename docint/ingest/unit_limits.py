from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import math
import zipfile
import xml.etree.ElementTree as ET

import fitz
from pptx import Presentation


@dataclass
class DocumentUnitInfo:
    units: int | None
    unit_label: str
    available: bool
    rationale: str


def _read_docx_app_pages(file_path: str) -> int | None:
    try:
        with zipfile.ZipFile(file_path) as zf:
            with zf.open("docProps/app.xml") as fh:
                root = ET.parse(fh).getroot()
        for elem in root.iter():
            if elem.tag.endswith("Pages"):
                value = (elem.text or "").strip()
                if value.isdigit():
                    return int(value)
    except Exception:
        return None
    return None


def inspect_document_units(file_path: str, filename: str) -> DocumentUnitInfo:
    suffix = Path(filename).suffix.lower()

    if suffix == ".pdf":
        doc = fitz.open(file_path)
        return DocumentUnitInfo(
            units=doc.page_count,
            unit_label="pages",
            available=True,
            rationale="Exact PDF page count from PyMuPDF",
        )

    if suffix == ".pptx":
        pres = Presentation(file_path)
        return DocumentUnitInfo(
            units=len(pres.slides),
            unit_label="slides",
            available=True,
            rationale="Exact PPTX slide count from presentation metadata",
        )

    if suffix == ".docx":
        pages = _read_docx_app_pages(file_path)
        if pages is not None:
            return DocumentUnitInfo(
                units=pages,
                unit_label="pages",
                available=True,
                rationale="DOCX page count from Office extended properties",
            )
        return DocumentUnitInfo(
            units=None,
            unit_label="pages",
            available=False,
            rationale="DOCX page count metadata unavailable",
        )

    if suffix == ".txt":
        try:
            text = Path(file_path).read_text(encoding="utf-8", errors="replace")
            lines = [line for line in text.splitlines() if line.strip()]
            estimated_pages = max(1, math.ceil(len(lines) / 40))
            return DocumentUnitInfo(
                units=estimated_pages,
                unit_label="estimated_pages",
                available=True,
                rationale="Estimated TXT page count using 40 non-empty lines per page",
            )
        except Exception:
            return DocumentUnitInfo(
                units=None,
                unit_label="estimated_pages",
                available=False,
                rationale="TXT page estimate unavailable",
            )

    return DocumentUnitInfo(
        units=None,
        unit_label="units",
        available=False,
        rationale="Early document unit inspection not implemented for this file type",
    )
