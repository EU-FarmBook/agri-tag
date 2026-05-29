# docint/rubrics/pedagogy.py

from __future__ import annotations

from . import RubricResult
from docint.features.keywords import KeywordSignals, bucket_score


def score_pedagogy(kw: KeywordSignals) -> RubricResult:
    """
    Educational material rubric.
    Looks for learning objectives, modules/lessons, exercises, etc.
    """
    hits = kw.bucket_hits.get("educational", 0)
    base = bucket_score(hits, saturation=25)

    # Bonus if we see both objective-ish and assessment-ish cues
    terms = kw.term_hits.get("educational", {})
    has_objective = any(k in terms for k in ["learning objectives", "by the end of", "you will be able to"])
    has_assessment = any(k in terms for k in ["exercise", "quiz", "assignment", "self-check"])

    bonus = 0.0
    if has_objective:
        bonus += 0.08
    if has_assessment:
        bonus += 0.08

    score = min(1.0, base + bonus)

    return RubricResult(
        score=round(score, 4),
        reasons={
            "educational_hits": hits,
            "educational_terms": terms,
            "base": base,
            "bonus": bonus,
            "has_objective_cues": has_objective,
            "has_assessment_cues": has_assessment,
        },
    )
