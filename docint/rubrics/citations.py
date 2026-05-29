# docint/rubrics/citations.py

from __future__ import annotations

from docint.features.citations import CitationSignals, evidence_intensity
from . import RubricResult


def score_citations(cites: CitationSignals, *, text_len: int) -> RubricResult:
    """
    Evidence / citation strength rubric.
    Normalises by document length and softly saturates to [0, 1].
    """
    intensity = evidence_intensity(cites, text_len=text_len)

    # Bonus if a References heading exists (if provided to CitationSignals)
    bonus = 0.08 if cites.has_references_heading else 0.0
    score = min(1.0, intensity + bonus)

    return RubricResult(
        score=round(score, 4),
        reasons={
            "cite_numeric": cites.cite_numeric,
            "cite_authoryear": cites.cite_authoryear,
            "doi_mentions": cites.doi_mentions,
            "url_mentions": cites.url_mentions,
            "has_references_heading": cites.has_references_heading,
            "intensity": intensity,
            "bonus": bonus,
            "text_len": text_len,
        },
    )
