# docint/features/keywords.py

from __future__ import annotations

import re

from dataclasses import dataclass
from typing import Dict, List


@dataclass
class KeywordSignals:
    """
    Keyword counts for different intent buckets.
    """
    bucket_hits: Dict[str, int]          # total hits per bucket
    term_hits: Dict[str, Dict[str, int]] # per-bucket per-term counts


# Curated cue-phrases. Keep them short + high-signal.
# These keywords may need adjustment based on the specific corpus.
KEYWORD_BUCKETS: Dict[str, List[str]] = {
    "deliverable_report": [
        "deliverable", "work package", "grant agreement", "ga number",
        "dissemination level", "task ", "milestone", "version", "revision history",
        "horizon europe", "h2020", "project acronym",
    ],
    "educational": [
        "learning objectives", "by the end of", "you will be able to",
        "prerequisites", "lesson", "module", "exercise", "quiz", "assignment",
        "self-check", "glossary",
    ],
    "practice_oriented": [
        "step 1", "step 2", "step 3", "procedure", "materials", "tools",
        "instructions", "do not", "ensure", "checklist", "safety", "warning", "caution",
    ],
    "policy_guidance": [
        "shall", "must", "should", "compliance", "regulation", "directive",
        "guidelines", "policy", "governance", "risk assessment", "legal",
    ],
}


def count_keywords(text: str, *, buckets: Dict[str, List[str]] = KEYWORD_BUCKETS) -> KeywordSignals:
    """
    Count keyword/phrase hits by bucket.

    Notes:
    - Uses simple substring counts (case-insensitive).
    - This is deterministic and fast.
    - Token/regex matching can be implemented later for improved precision.

    Returns:
        KeywordSignals
    """
    t = (text or "").lower()

    bucket_hits: Dict[str, int] = {}
    term_hits: Dict[str, Dict[str, int]] = {}

    for bucket, terms in buckets.items():
        term_hits[bucket] = {}
        total = 0
        for term in terms:
            # For multi-word phrases, match on flexible whitespace.
            # For single words, use word boundaries to avoid substrings.
            term_l = term.lower()

            if " " in term_l:
                pat = re.compile(r"\b" + re.escape(term_l).replace(r"\ ", r"\s+") + r"\b", re.I)
            else:
                pat = re.compile(r"\b" + re.escape(term_l) + r"\b", re.I)

            c = len(pat.findall(t))
            if c:
                term_hits[bucket][term] = c
                total += c

        bucket_hits[bucket] = total

    return KeywordSignals(bucket_hits=bucket_hits, term_hits=term_hits)


def bucket_score(hits: int, *, saturation: int) -> float:
    """
    Convert raw hit counts into a [0, 1] score using saturation.
    Example: saturation=30 means 30+ hits ~ score 1.0
    """
    return min(1.0, hits / float(max(1, saturation)))
