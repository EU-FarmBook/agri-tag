from __future__ import annotations

from pathlib import Path

from docint.ingest.models import IngestedAsset


def ingest_text_file(file_path: str, filename: str) -> IngestedAsset:
    text = Path(file_path).read_text(encoding="utf-8", errors="replace").strip()
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return IngestedAsset(
        asset_type="txt",
        filename=filename,
        source_path=file_path,
        text=text,
        lines=lines,
        units=max(1, len(lines)),
        unit_label="lines",
        source="text_file",
        mime_type="text/plain",
        visual_candidate=False,
        ocr_supported=False,
        meta={"encoding": "utf-8", "line_count": len(lines)},
    )
