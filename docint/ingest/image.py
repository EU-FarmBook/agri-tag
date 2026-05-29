from __future__ import annotations

from docint.ingest.models import IngestedAsset


def ingest_image(file_path: str, filename: str, mime_type: str) -> IngestedAsset:
    return IngestedAsset(
        asset_type=mime_type.split("/")[-1].lower(),
        filename=filename,
        source_path=file_path,
        text="",
        lines=[],
        units=1,
        unit_label="images",
        source="image_file",
        mime_type=mime_type,
        visual_candidate=True,
        ocr_supported=True,
        meta={"image_path": file_path},
    )
