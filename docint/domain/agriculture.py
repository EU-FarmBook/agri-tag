from __future__ import annotations

import json
import re
import unicodedata

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Dict, List


@dataclass
class AgricultureRelevanceResult:
    """Fast CPU-friendly agriculture relevance assessment."""
    is_agriculture_related: bool
    confidence: float
    score: float
    method: str
    lexicon_version: str
    matched_terms: List[str]
    matched_buckets: List[str]
    matched_concepts: List[str]
    bucket_scores: Dict[str, float]
    rationale: str


@dataclass
class AgricultureLexiconEntry:
    concept_id: str
    bucket: str
    preferred_label: str
    preferred_language: str
    strong_anchor: bool
    labels: List[Dict[str, str]]


REPO_ROOT = Path(__file__).resolve().parents[2]
LEXICON_PATH = REPO_ROOT / "data_model" / "runtime" / "agriculture" / "lexicon.json"


def _normalize_text(text: str) -> str:
    lowered = (text or "").lower()
    folded = unicodedata.normalize("NFKD", lowered)
    return "".join(ch for ch in folded if not unicodedata.combining(ch))


def _compile_term_pattern(term: str) -> re.Pattern[str]:
    escaped = re.escape(term)
    escaped = escaped.replace(r"\ ", r"[\s\-]+")
    return re.compile(r"\b" + escaped + r"\b", re.I)


def _bucket_score(total_hits: int, unique_hits: int, saturation: int = 6) -> float:
    raw = min(1.0, total_hits / float(max(1, saturation)))
    diversity = min(1.0, unique_hits / 3.0)
    return round(min(1.0, (raw * 0.7) + (diversity * 0.3)), 4)


@lru_cache(maxsize=1)
def load_agriculture_lexicon() -> tuple[str, List[AgricultureLexiconEntry]]:
    raw = json.loads(LEXICON_PATH.read_text(encoding="utf-8"))
    version = str(raw.get("version", "unknown"))
    concepts = raw.get("concepts", [])

    entries: List[AgricultureLexiconEntry] = []
    for concept in concepts:
        preferred = concept["preferred_label"]
        labels = [preferred, *concept.get("alt_labels", [])]
        normalized_labels = []
        for item in labels:
            label = _normalize_text(str(item["label"]).strip())
            if not label:
                continue
            normalized_labels.append(
                {
                    "language": str(item["language"]).strip().lower(),
                    "label": label,
                    "pattern": _compile_term_pattern(label),
                }
            )

        entries.append(
            AgricultureLexiconEntry(
                concept_id=str(concept["concept_id"]),
                bucket=str(concept["bucket"]),
                preferred_label=_normalize_text(str(preferred["label"]).strip()),
                preferred_language=str(preferred["language"]).strip().lower(),
                strong_anchor=bool(concept.get("strong_anchor", False)),
                labels=normalized_labels,
            )
        )

    return version, entries


def assess_agriculture_relevance(text: str, *, lines: List[str] | None = None) -> AgricultureRelevanceResult:
    """
    Fast multilingual agriculture relevance scorer.

    Stage 1 of the planned pipeline:
    - external multilingual lexicon matcher
    - CPU friendly
    - explainable

    Future stages can add:
    - small multilingual embedding model for ambiguous cases
    - optional LLM fallback
    """
    lexicon_version, entries = load_agriculture_lexicon()
    normalized = _normalize_text(text)
    top_text = _normalize_text("\n".join((lines or [])[:20])) if lines else normalized[:1200]

    bucket_scores: Dict[str, float] = {}
    bucket_hits: Dict[str, int] = {}
    bucket_unique: Dict[str, int] = {}
    matched_terms_by_bucket: Dict[str, List[str]] = {}
    matched_concepts: List[str] = []
    strong_anchor_hits = 0

    for entry in entries:
        total_concept_hits = 0
        matched_labels: List[str] = []

        for label_info in entry.labels:
            count = len(label_info["pattern"].findall(normalized))
            if count:
                total_concept_hits += count
                matched_labels.append(label_info["label"])

        if not total_concept_hits:
            continue

        bucket = entry.bucket
        bucket_hits[bucket] = bucket_hits.get(bucket, 0) + total_concept_hits
        bucket_unique[bucket] = bucket_unique.get(bucket, 0) + 1
        matched_terms_by_bucket.setdefault(bucket, [])
        for label in matched_labels:
            if label not in matched_terms_by_bucket[bucket]:
                matched_terms_by_bucket[bucket].append(label)
        matched_concepts.append(entry.concept_id)

        if entry.strong_anchor:
            strong_anchor_hits += total_concept_hits

    all_buckets = sorted({entry.bucket for entry in entries})
    for bucket in all_buckets:
        bucket_scores[bucket] = _bucket_score(
            bucket_hits.get(bucket, 0),
            bucket_unique.get(bucket, 0),
        )

    weights = {
        "farming_systems": 0.25,
        "crops_plants": 0.2,
        "livestock_manure": 0.2,
        "soil_water_nutrients": 0.25,
        "agri_bioeconomy": 0.1,
    }
    weighted = sum(bucket_scores.get(bucket, 0.0) * weight for bucket, weight in weights.items())
    active_buckets = [bucket for bucket, score in bucket_scores.items() if score >= 0.18]

    coverage_bonus = 0.0
    if len(active_buckets) >= 2:
        coverage_bonus += 0.08
    if len(active_buckets) >= 3:
        coverage_bonus += 0.08

    top_hits = 0
    for entry in entries:
        if not entry.strong_anchor:
            continue
        for label_info in entry.labels:
            top_hits += len(label_info["pattern"].findall(top_text))
    title_boost = 0.08 if top_hits >= 2 else 0.0

    score = min(1.0, round(weighted + coverage_bonus + title_boost, 4))
    if strong_anchor_hits == 0:
        score = min(score, 0.24)

    is_related = score >= 0.35 or (strong_anchor_hits >= 2 and score >= 0.25)

    matched_terms: List[str] = []
    for bucket in all_buckets:
        matched_terms.extend(matched_terms_by_bucket.get(bucket, []))
    matched_terms = matched_terms[:12]
    matched_buckets = [bucket for bucket in all_buckets if bucket_scores.get(bucket, 0.0) >= 0.18]
    matched_concepts = matched_concepts[:12]

    if matched_terms:
        rationale = (
            f"Agriculture relevance assessed via multilingual lexicon {lexicon_version} "
            f"with matches in {', '.join(matched_buckets[:3])}: "
            f"{', '.join(matched_terms[:6])}"
        )
    else:
        rationale = (
            f"No strong agriculture-specific lexicon matches found using {lexicon_version}"
        )

    return AgricultureRelevanceResult(
        is_agriculture_related=is_related,
        confidence=score,
        score=score,
        method="agrovoc_lexicon_v0_cpu",
        lexicon_version=lexicon_version,
        matched_terms=matched_terms,
        matched_buckets=matched_buckets,
        matched_concepts=matched_concepts,
        bucket_scores=bucket_scores,
        rationale=rationale,
    )
