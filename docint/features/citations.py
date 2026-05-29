# docint/features/citations.py

from __future__ import annotations

import re

from dataclasses import dataclass


@dataclass
class CitationSignals:
    """
    Detects common citation patterns and DOI mentions.
    These are signals, not proof of quality.
    """
    cite_numeric: int       # [12], [3, 7], [1-5]
    cite_authoryear: int    # (Smith, 2020), (Smith et al., 2020)
    doi_mentions: int
    url_mentions: int
    has_references_heading: bool  # optional, from sections feature


_NUMERIC_CITE_RE = re.compile(r"\[\s*\d+(\s*[-–,]\s*\d+)*\s*\]")
# A fairly tolerant author-year pattern. Not perfect (names are messy), but useful.
_AUTHOR_YEAR_RE = re.compile(r"\(\s*[A-Z][A-Za-z'’-]+( et al\.)?,\s*\d{4}[a-z]?\s*\)")
_DOI_RE = re.compile(r"\b10\.\d{4,9}/\S+\b")
_URL_RE = re.compile(r"\bhttps?://\S+\b")


def detect_citations(text: str, *, has_references_heading: bool = False) -> CitationSignals:
    """
    Extract citation-like signals from plain text.

    Args:
        text: extracted text
        has_references_heading: whether a References section was detected

    Returns:
        CitationSignals
    """
    if not text:
        return CitationSignals(
            cite_numeric=0,
            cite_authoryear=0,
            doi_mentions=0,
            url_mentions=0,
            has_references_heading=has_references_heading,
        )

    cite_numeric = len(_NUMERIC_CITE_RE.findall(text))
    cite_authoryear = len(_AUTHOR_YEAR_RE.findall(text))
    doi_mentions = len(_DOI_RE.findall(text))
    url_mentions = len(_URL_RE.findall(text))

    return CitationSignals(
        cite_numeric=cite_numeric,
        cite_authoryear=cite_authoryear,
        doi_mentions=doi_mentions,
        url_mentions=url_mentions,
        has_references_heading=has_references_heading,
    )


def evidence_intensity(sig: CitationSignals, *, text_len: int) -> float:
    """
    A rough normalised score for 'evidence density'.
    Useful as a feature; do not interpret as truthfulness.

    Returns a value in [0, 1] using a soft saturation.
    """
    # Weighted: DOI and citations count more than URLs
    raw = (sig.cite_numeric * 1.0) + (sig.cite_authoryear * 1.0) + (sig.doi_mentions * 2.0) + (sig.url_mentions * 0.2)
    # Scale by text length (avoid rewarding giant documents unfairly)
    per_10k_chars = raw / max(1.0, (text_len / 10000.0))

    # Soft cap: 0..1
    return min(1.0, per_10k_chars / 25.0)
