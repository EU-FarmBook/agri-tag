# docint/extract/ocr.py

from __future__ import annotations

import re

from typing import List, Optional

import pytesseract

from pdf2image import convert_from_path
from PIL import Image

from .pdf_text import ExtractedDoc


def _clean_ocr_text(s: str) -> str:
    """
    OCR text tends to contain:
    - hyphenation at line breaks
    - uneven spacing
    Clean it lightly but avoid destroying structure.
    """
    # Join hyphenated words split across lines: "inter-\nnational" -> "international"
    s = re.sub(r"-\n(\w)", r"\1", s)

    # Normalise spaces (keep newlines)
    s = re.sub(r"[ \t]+", " ", s)

    # Collapse excessive blank lines
    s = re.sub(r"\n{3,}", "\n\n", s)

    return s.strip()


def ocr_pdf(
    pdf_path: str,
    *,
    dpi: int = 220,
    lang: str = "eng",
    max_pages: Optional[int] = None,
    poppler_path: Optional[str] = None,
    tesseract_cmd: Optional[str] = None,
) -> ExtractedDoc:
    """
    OCR a PDF by converting pages to images and running Tesseract.

    Kubuntu prerequisites:
      sudo apt-get install -y tesseract-ocr poppler-utils
      pip install pytesseract pdf2image pillow

    Args:
        pdf_path: path to PDF
        dpi: raster DPI (200–300 recommended; higher = slower)
        lang: Tesseract languages, e.g. "eng" or "eng+nld"
        max_pages: OCR only first N pages (often enough to classify)
        poppler_path: optional path to poppler binaries (usually not needed on Kubuntu)
        tesseract_cmd: optional explicit tesseract binary path

    Returns:
        ExtractedDoc (source="ocr")
    """
    if tesseract_cmd:
        # Useful when tesseract is not on PATH
        pytesseract.pytesseract.tesseract_cmd = tesseract_cmd

    images_all = convert_from_path(pdf_path, dpi=dpi, poppler_path=poppler_path)
    pdf_total_pages = len(images_all)  # true total pages *from pdf2image conversion*
    images = images_all if max_pages is None else images_all[:max_pages]

    page_texts: List[str] = []
    lines: List[str] = []

    # psm 6 = Assume a uniform block of text (good default for reports)
    # psm 4 may be tried for multi-column sometimes.
    tesseract_config = "--psm 6"

    for img in images:
        t = pytesseract.image_to_string(img, lang=lang, config=tesseract_config) or ""
        t = _clean_ocr_text(t)
        page_texts.append(t)

        for ln in t.splitlines():
            ln = ln.strip()
            if ln:
                lines.append(ln)

    full_text = "\n\n".join(page_texts).strip()

    return ExtractedDoc(
        text=full_text,
        lines=lines,
        pages=pdf_total_pages,
        source="ocr",
        meta={
            "pdf_path": pdf_path,
            "ocr_pages": len(images),
            "pdf_total_pages": pdf_total_pages,
            "dpi": dpi,
            "lang": lang,
            "engine": "tesseract",
            "tesseract_config": tesseract_config,
        },
    )


def ocr_image(
    image_path: str,
    *,
    lang: str = "eng",
    tesseract_cmd: Optional[str] = None,
) -> ExtractedDoc:
    """OCR a single image file."""
    if tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = tesseract_cmd

    img = Image.open(image_path)
    tesseract_config = "--psm 6"
    text = pytesseract.image_to_string(img, lang=lang, config=tesseract_config) or ""
    text = _clean_ocr_text(text)
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]

    return ExtractedDoc(
        text=text,
        lines=lines,
        pages=1,
        source="ocr",
        meta={
            "image_path": image_path,
            "lang": lang,
            "engine": "tesseract",
            "tesseract_config": tesseract_config,
        },
    )
