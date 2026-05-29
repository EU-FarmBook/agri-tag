from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List


@dataclass
class IngestedAsset:
    """Normalized extracted asset representation for downstream classification."""

    asset_type: str
    filename: str
    source_path: str
    text: str
    lines: List[str]
    units: int
    unit_label: str
    source: str
    mime_type: str
    visual_candidate: bool
    ocr_supported: bool
    meta: Dict[str, Any]
