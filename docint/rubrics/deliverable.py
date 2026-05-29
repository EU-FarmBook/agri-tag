# docint/rubrics/deliverable.py

from __future__ import annotations

from . import RubricResult
from docint.features.keywords import KeywordSignals, bucket_score
from docint.features.sections import SectionSignals


def score_deliverable(
    kw: KeywordSignals,
    sections: SectionSignals | None = None,
) -> RubricResult:
    """
    EU-style deliverable/report rubric.
    Uses deliverable keyword bucket + optional section cues (executive summary, appendix).
    """
    hits = kw.bucket_hits.get("deliverable_report", 0)
    base = bucket_score(hits, saturation=30)  # adjust saturation based on corpus characteristics

    # Small structural bonus for deliverable-ish sections
    bonus = 0.0
    if sections:
        if sections.present.get("executive_summary"):
            bonus += 0.07
        if sections.present.get("appendix"):
            bonus += 0.05

    score = min(1.0, base + bonus)

    return RubricResult(
        score=round(score, 4),
        reasons={
            "deliverable_hits": hits,
            "deliverable_terms": kw.term_hits.get("deliverable_report", {}),
            "base": base,
            "bonus": bonus,
            "executive_summary_present": bool(sections.present.get("executive_summary")) if sections else None,
            "appendix_present": bool(sections.present.get("appendix")) if sections else None,
        },
    )
