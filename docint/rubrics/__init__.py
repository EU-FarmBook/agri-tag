# docint/rubrics/__init__.py

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Any


@dataclass
class RubricResult:
    score: float
    reasons: Dict[str, Any]
