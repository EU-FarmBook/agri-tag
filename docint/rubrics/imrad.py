# docint/rubrics/imrad.py

from __future__ import annotations

from docint.features.sections import SectionSignals, imrad_presence
from . import RubricResult


def score_imrad(sections: SectionSignals) -> RubricResult:
    """
    IMRaD-ish structure scoring.
    Measures presence of canonical research sections.
    """
    present = imrad_presence(sections)

    # Weight methods + references higher (inspectability anchors)
    weights = {
        "abstract": 1.0,
        "introduction": 1.0,
        "methods": 2.0,
        "results": 1.0,
        "discussion": 1.0,
        "references": 2.0,
    }

    total = sum(weights.values())
    got = sum(weights[k] for k, ok in present.items() if ok)

    score = got / total if total else 0.0

    return RubricResult(
        score=round(score, 4),
        reasons={
            "present": present,
            "counts": sections.counts,
            "matched_lines": {k: sections.matched_lines.get(k, []) for k in present.keys()},
            "weights": weights,
        },
    )
