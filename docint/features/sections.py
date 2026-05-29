# docint/features/sections.py

from __future__ import annotations

import re

from dataclasses import dataclass
from typing import Dict, List, Pattern


@dataclass
class SectionSignals:
    """
    Signals derived from detecting common section headings.
    """
    counts: Dict[str, int]         # e.g. {"abstract": 1, "methods": 1, ...}
    present: Dict[str, bool]       # e.g. {"abstract": True, ...}
    matched_lines: Dict[str, List[str]]  # store examples for explainability


def _compile_section_patterns() -> Dict[str, Pattern]:
    """
    Patterns match a heading-like line (short-ish, standalone).
    Supports numbering like '1. Introduction' and variants like 'Materials and Methods'.
    """

    def heading_pat(name: str) -> Pattern:
        # Accept:
        # - optional numbering "1", "1.2", "2.3.1"
        # - optional separators ":" "-" "–"
        # - short trailing suffix text (e.g., "Introduction: context")
        #
        # Keep it conservative to avoid matching normal sentences.
        return re.compile(
            rf"^\s*(\d+(\.\d+)*)?\s*{name}\b\s*([:\-–]\s*.+)?\s*$",
            re.I,
        )

    return {
        "abstract": heading_pat("abstract"),
        "introduction": heading_pat("introduction"),
        "background": heading_pat("background"),
        "methods": heading_pat(r"(methods|methodology|materials and methods)"),
        "results": heading_pat("results"),
        "discussion": heading_pat("discussion"),
        "conclusion": heading_pat(r"(conclusion|conclusions)"),
        "references": heading_pat(r"(references|bibliography|literature)"),
        "acknowledgements": heading_pat(r"(acknowledg(e)?ments|acknowledgment(s)?)"),
        "appendix": heading_pat(r"(appendix|annex|annexes)"),
        "executive_summary": heading_pat(r"(executive summary|management summary)"),
    }


_SECTION_PATTERNS = _compile_section_patterns()


def count_sections(
    lines: List[str],
    *,
    max_heading_len: int = 120,
) -> SectionSignals:
    """
    Detect section headings by scanning line-level text.

    Args:
        lines: extracted lines (preferably stripped, non-empty)
        max_heading_len: ignore very long lines (likely paragraphs, not headings)

    Returns:
        SectionSignals
    """
    counts = {k: 0 for k in _SECTION_PATTERNS.keys()}
    matched_lines: Dict[str, List[str]] = {k: [] for k in _SECTION_PATTERNS.keys()}

    for ln in lines:
        if not ln:
            continue
        if len(ln) > max_heading_len:
            continue

        # Avoid matching paragraph-y lines that start with "Introduction" in prose.
        # (e.g., OCR weirdness can create long "headings")
        if len(ln.split()) > 16:
            continue

        for name, pat in _SECTION_PATTERNS.items():
            if pat.match(ln):
                counts[name] += 1
                if len(matched_lines[name]) < 5:
                    matched_lines[name].append(ln)
                break  # one line should match at most one canonical section

    present = {k: (v > 0) for k, v in counts.items()}
    return SectionSignals(counts=counts, present=present, matched_lines=matched_lines)


def imrad_presence(section_signals: SectionSignals) -> Dict[str, bool]:
    """
    Convenience helper: presence flags for canonical IMRaD + references.
    """
    keys = ["abstract", "introduction", "methods", "results", "discussion", "references"]
    return {k: bool(section_signals.present.get(k, False)) for k in keys}
