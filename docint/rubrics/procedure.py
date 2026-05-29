# docint/rubrics/procedure.py

from __future__ import annotations

from . import RubricResult
from docint.features.keywords import KeywordSignals, bucket_score


def score_procedure(kw: KeywordSignals) -> RubricResult:
    """
    Practice-oriented / SOP / how-to rubric.
    Detects step-by-step procedural cues and safety warnings.
    """
    hits = kw.bucket_hits.get("practice_oriented", 0)
    base = bucket_score(hits, saturation=25)

    terms = kw.term_hits.get("practice_oriented", {})

    # Bonus for explicit step sequences + safety language
    has_steps = any(k in terms for k in ["step 1", "step 2", "step 3", "procedure"])
    has_safety = any(k in terms for k in ["warning", "caution", "safety", "do not"])

    bonus = 0.0
    if has_steps:
        bonus += 0.10
    if has_safety:
        bonus += 0.08

    score = min(1.0, base + bonus)

    return RubricResult(
        score=round(score, 4),
        reasons={
            "procedure_hits": hits,
            "procedure_terms": terms,
            "base": base,
            "bonus": bonus,
            "has_step_cues": has_steps,
            "has_safety_cues": has_safety,
        },
    )
