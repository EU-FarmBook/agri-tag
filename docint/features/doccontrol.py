# docint/features/doccontrol.py

from __future__ import annotations

import re
from dataclasses import dataclass

@dataclass
class DocControlSignals:
    ga_number: int
    deliverable_code: int   # D2.5, D1.1 etc.
    dissemination_level: int
    revision_history: int
    work_package: int

_GA_RE = re.compile(r"\bgrant\s+agreement\s*(no\.|number)?\s*[:#]?\s*\d{4,10}\b", re.I)
_DCODE_RE = re.compile(r"\bD\d+(\.\d+)+\b", re.I)
_DISSEM_RE = re.compile(r"\bdissemination\s+level\b", re.I)
_REV_RE = re.compile(r"\brevision\s+history\b|\bversion\s+history\b|\bdocument\s+history\b", re.I)
_WP_RE = re.compile(r"\bwork\s+package\b|\bWP\d+\b", re.I)

def detect_doccontrol(text: str) -> DocControlSignals:
    t = text or ""
    return DocControlSignals(
        ga_number=len(_GA_RE.findall(t)),
        deliverable_code=len(_DCODE_RE.findall(t)),
        dissemination_level=len(_DISSEM_RE.findall(t)),
        revision_history=len(_REV_RE.findall(t)),
        work_package=len(_WP_RE.findall(t)),
    )
