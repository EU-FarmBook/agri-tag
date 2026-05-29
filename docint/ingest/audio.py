from __future__ import annotations

from pathlib import Path

from docint.ingest.models import IngestedAsset


def ingest_audio(file_path: str, filename: str, mime_type: str) -> IngestedAsset:
    return IngestedAsset(
        asset_type=Path(filename).suffix.lower().lstrip("."),
        filename=filename,
        source_path=file_path,
        text="",
        lines=[],
        units=1,
        unit_label="track",
        source="audio_file",
        mime_type=mime_type,
        visual_candidate=False,
        ocr_supported=False,
        meta={},
    )
