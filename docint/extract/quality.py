# docint/extract/quality.py

from __future__ import annotations

import re

from dataclasses import dataclass
from typing import Dict, Any


@dataclass
class TextQuality:
    ok: bool
    reason: str
    metrics: Dict[str, Any]


def text_quality_ok(
    text: str,
    *,
    min_chars: int = 800,
    min_letter_ratio: float = 0.25,
) -> TextQuality:
    """
    Decide whether extracted text is good enough to skip OCR.

    Heuristics:
    - Minimum character count: very short text suggests scanned PDF or extraction failure
    - Letter ratio: if text is mostly symbols/whitespace, extraction is likely poor

    Returns:
        TextQuality (ok + reason + metrics)
    """
    if not text:
        return TextQuality(ok=False, reason="empty_text", metrics={"chars": 0, "letter_ratio": 0.0})

    chars = len(text)
    if chars < min_chars:
        letters = len(re.findall(r"[A-Za-z]", text))
        ratio = letters / max(1, chars)
        return TextQuality(
            ok=False,
            reason="too_short",
            metrics={"chars": chars, "letters": letters, "letter_ratio": ratio, "min_chars": min_chars},
        )

    letters = len(re.findall(r"[A-Za-z]", text))
    ratio = letters / max(1, chars)

    if ratio < min_letter_ratio:
        return TextQuality(
            ok=False,
            reason="low_letter_ratio",
            metrics={"chars": chars, "letters": letters, "letter_ratio": ratio, "min_letter_ratio": min_letter_ratio},
        )

    return TextQuality(ok=True, reason="ok", metrics={"chars": chars, "letters": letters, "letter_ratio": ratio})
