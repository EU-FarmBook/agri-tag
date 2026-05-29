from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class KoEligibilityResult:
    is_eligible: bool
    confidence: float
    exclusion_type: Optional[str]
    rationale: str
    matched_signals: List[str]
    score: float
    method: str


_EXCLUSION_PATTERNS: Dict[str, List[tuple[str, str]]] = {
    "job_vacancy": [
        ("\\bphd position\\b", "phd position"),
        ("\\bphd vacancy\\b", "phd vacancy"),
        ("\\bvacancy\\b", "vacancy"),
        ("\\bjob opening\\b", "job opening"),
        ("\\bwe are seeking\\b", "we are seeking"),
        ("\\brequirements\\b", "requirements"),
        ("\\bsalary and conditions\\b", "salary and conditions"),
        ("\\bplease send your application\\b", "send your application"),
        ("\\bapplications\\b", "applications"),
        ("\\bcover letter\\b", "cover letter"),
        ("\\breferees\\b", "referees"),
        ("\\bstart date\\b", "start date"),
        ("\\bequal opportunities employer\\b", "equal opportunities employer"),
        ("\\bcv\\b", "cv"),
    ],
    "call_for_applications": [
        ("\\bcall for applications\\b", "call for applications"),
        ("\\bcall for candidates\\b", "call for candidates"),
        ("\\bapply now\\b", "apply now"),
        ("\\bapplication deadline\\b", "application deadline"),
        ("\\bdeadline\\b", "deadline"),
        ("\\bfellowship\\b", "fellowship"),
        ("\\binternship\\b", "internship"),
        ("\\bscholarship\\b", "scholarship"),
    ],
    "event_announcement": [
        ("\\bregister now\\b", "register now"),
        ("\\bwebinar\\b", "webinar"),
        ("\\bconference\\b", "conference"),
        ("\\bworkshop\\b", "workshop"),
        ("\\bevent\\b", "event"),
        ("\\bjoin us\\b", "join us"),
        ("\\bsave the date\\b", "save the date"),
    ],
    "procurement_notice": [
        ("\\btender\\b", "tender"),
        ("\\brequest for proposal\\b", "request for proposal"),
        ("\\brequest for quotation\\b", "request for quotation"),
        ("\\bprocurement\\b", "procurement"),
        ("\\bbid submission\\b", "bid submission"),
    ],
}


def _normalize(text: str) -> str:
    return " ".join((text or "").lower().split())


def assess_ko_eligibility(text: str) -> KoEligibilityResult:
    normalized = _normalize(text)
    scores: Dict[str, int] = {}
    matched: Dict[str, List[str]] = {}

    for label, rules in _EXCLUSION_PATTERNS.items():
        hits: List[str] = []
        for pattern, signal in rules:
            if re.search(pattern, normalized, re.I):
                hits.append(signal)
        matched[label] = hits
        scores[label] = len(hits)

    best_label = max(scores, key=scores.get) if scores else None
    best_score = scores.get(best_label, 0) if best_label else 0
    best_hits = matched.get(best_label, []) if best_label else []

    if best_label == "job_vacancy":
        strong = best_score >= 3 or ("phd position" in best_hits and "applications" in best_hits)
    else:
        strong = best_score >= 3

    if strong:
        return KoEligibilityResult(
            is_eligible=False,
            confidence=min(0.98, 0.55 + (best_score * 0.1)),
            exclusion_type=best_label,
            rationale=f"Content looks like {best_label.replace('_', ' ')} based on: {', '.join(best_hits[:6])}",
            matched_signals=best_hits[:10],
            score=float(best_score),
            method="heuristic_exclusion_gate",
        )

    if best_score == 0:
        return KoEligibilityResult(
            is_eligible=True,
            confidence=0.85,
            exclusion_type=None,
            rationale="No strong non-KO exclusion patterns detected",
            matched_signals=[],
            score=0.0,
            method="heuristic_exclusion_gate",
        )

    return KoEligibilityResult(
        is_eligible=True,
        confidence=0.45,
        exclusion_type=best_label,
        rationale=f"Weak exclusion signals detected for {best_label.replace('_', ' ')}, but not enough to reject",
        matched_signals=best_hits[:10],
        score=float(best_score),
        method="heuristic_exclusion_gate",
    )
