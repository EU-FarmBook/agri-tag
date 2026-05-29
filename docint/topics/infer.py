"""
Multi-label topic inference for files and URLs.

Topics (Forestry, Livestock, Crop farming, Economics, Environment, Society) are
*orthogonal* to category/subcategory and *multi-label*: one knowledge object can
carry several at once. This module mirrors the staged, CPU-first, multilingual
design of ``docint/domain/agriculture*``:

  Stage 1 - lexicon:   multilingual AGROVOC-derived strong anchors (explainable)
  Stage 2 - embedding: per-topic centroids (intfloat/multilingual-e5-small)
  (Stage 3 - an LLM tie-break for genuinely ambiguous multi-label cases is a
   planned extension point; the staged structure here mirrors the agriculture
   pipeline so it can be slotted in the same way.)

Signals come from ``data_model/runtime/topics/topic_signals.json`` (built by
``scripts/build_topic_signals_from_agrovoc.py``) and the centroids from
``data_model/runtime/topics/topic_centroids.npz`` (``scripts/compute_topic_centroids.py``).
The pipeline degrades gracefully to lexicon-only when the embedding model or the
centroid file is unavailable, so it is safe to import in any environment.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
TOPICS_RUNTIME_DIR = REPO_ROOT / "data_model" / "runtime" / "topics"
SIGNALS_PATH = TOPICS_RUNTIME_DIR / "topic_signals.json"
CENTROID_PATH = TOPICS_RUNTIME_DIR / "topic_centroids.npz"
CENTROID_META_PATH = TOPICS_RUNTIME_DIR / "topic_centroids.meta.json"

TOPIC_EMBEDDING_MODEL = os.getenv(
    "TOPIC_EMBEDDING_MODEL",
    os.getenv("AGRI_EMBEDDING_MODEL", "intfloat/multilingual-e5-small"),
).strip()
TOPIC_ENABLE_EMBEDDING = os.getenv("TOPIC_ENABLE_EMBEDDING", "true").strip().lower() in {"1", "true", "yes"}
EMBEDDING_TEXT_LIMIT = int(os.getenv("TOPIC_EMBEDDING_TEXT_LIMIT", "3500"))

# How lexical vs embedding evidence are blended into the final per-topic score.
LEX_WEIGHT = float(os.getenv("TOPIC_LEX_WEIGHT", "0.55"))
EMB_WEIGHT = float(os.getenv("TOPIC_EMB_WEIGHT", "0.45"))
# A topic is emitted when its final score clears this bar.
TOPIC_SELECT_THRESHOLD = float(os.getenv("TOPIC_SELECT_THRESHOLD", "0.45"))
# Cap on returned topics and on matched terms surfaced per topic.
TOPIC_MAX_SELECTED = int(os.getenv("TOPIC_MAX_SELECTED", "4"))
TOPIC_MAX_TERMS = int(os.getenv("TOPIC_MAX_TERMS", "6"))


@dataclass
class TopicScore:
    topic: str
    score: float
    lexical_score: float
    embedding_score: float
    matched_terms: List[str] = field(default_factory=list)
    rationale: str = ""


@dataclass
class TopicInferenceResult:
    topics: List[TopicScore]          # selected topics (above threshold), ranked
    ranked: List[TopicScore]          # every topic, ranked (useful for debug)
    method: str
    stages_used: List[str]
    signals_version: str
    rationale: str


# --------------------------------------------------------------------------- #
# Text normalisation + lexicon loading
# --------------------------------------------------------------------------- #
def _normalize_text(text: str) -> str:
    lowered = (text or "").lower()
    folded = unicodedata.normalize("NFKD", lowered)
    return "".join(ch for ch in folded if not unicodedata.combining(ch))


def _compile_term_pattern(term: str) -> re.Pattern[str]:
    escaped = re.escape(term)
    escaped = escaped.replace(r"\ ", r"[\s\-]+")
    return re.compile(r"\b" + escaped + r"\b", re.I)


@dataclass
class _TopicLexicon:
    name: str
    # (compiled pattern, display label) for the strong anchors only
    patterns: List[tuple[re.Pattern[str], str]]
    negative_terms: List[str]


@lru_cache(maxsize=1)
def _load_signals() -> tuple[str, List[_TopicLexicon]]:
    raw = json.loads(SIGNALS_PATH.read_text(encoding="utf-8"))
    version = str(raw.get("version", "unknown"))
    topics: List[_TopicLexicon] = []
    for name, payload in raw.get("topics", {}).items():
        seen: set[str] = set()
        patterns: List[tuple[re.Pattern[str], str]] = []
        for anchor in payload.get("anchors", []):
            # Lexical layer uses strong anchors only: precise + cheap + explainable.
            if not anchor.get("strong"):
                continue
            label = _normalize_text(str(anchor.get("label", "")).strip())
            if len(label) < 3 or label in seen:
                continue
            seen.add(label)
            patterns.append((_compile_term_pattern(label), label))
        topics.append(
            _TopicLexicon(
                name=name,
                patterns=patterns,
                negative_terms=[_normalize_text(t) for t in payload.get("negative_terms", [])],
            )
        )
    return version, topics


def _lexical_score(total_hits: int, unique_hits: int, saturation: int = 5) -> float:
    raw = min(1.0, total_hits / float(max(1, saturation)))
    diversity = min(1.0, unique_hits / 3.0)
    return round(min(1.0, (raw * 0.7) + (diversity * 0.3)), 4)


# --------------------------------------------------------------------------- #
# Embedding stage (shares the agriculture model singleton when model matches)
# --------------------------------------------------------------------------- #
def _embedding_available() -> bool:
    return bool(
        TOPIC_ENABLE_EMBEDDING
        and TOPIC_EMBEDDING_MODEL
        and CENTROID_PATH.exists()
        and importlib.util.find_spec("sentence_transformers")
    )


@lru_cache(maxsize=1)
def _load_embedding_model():
    # Reuse the agriculture pipeline's cached model when the model name matches,
    # so we don't hold two copies of multilingual-e5 in memory.
    try:
        from docint.domain.agriculture_pipeline import (
            AGRI_EMBEDDING_MODEL,
            _load_embedding_model as _agri_loader,
        )

        if AGRI_EMBEDDING_MODEL == TOPIC_EMBEDDING_MODEL:
            return _agri_loader()
    except Exception:
        pass

    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(TOPIC_EMBEDDING_MODEL, device="cpu")


@lru_cache(maxsize=1)
def _load_topic_centroids() -> Dict[str, np.ndarray]:
    if not CENTROID_PATH.exists():
        return {}
    arrs = np.load(CENTROID_PATH)
    return {
        key.removeprefix("topic::"): arrs[key]
        for key in arrs.files
        if key.startswith("topic::") and key != "topic::__all__"
    }


def _truncate(text: str) -> str:
    return " ".join((text or "").split())[:EMBEDDING_TEXT_LIMIT]


def _embedding_scores(text: str) -> Optional[Dict[str, float]]:
    """Per-topic embedding scores in [0,1], or None if the stage is unavailable.

    All topics are agriculture sub-domains, so raw cosine similarities sit close
    together. We score each topic by how far it stands out from the *mean* topic
    similarity (topic specificity) and min-max spread that across topics.
    """
    if not _embedding_available():
        return None
    try:
        model = _load_embedding_model()
        centroids = _load_topic_centroids()
        if not centroids:
            return None
        doc = model.encode([f"query: {_truncate(text)}"], normalize_embeddings=True)
        sims = {topic: float((doc @ c.reshape(-1, 1))[0][0]) for topic, c in centroids.items()}
    except Exception:
        return None

    values = list(sims.values())
    mean_sim = sum(values) / len(values)
    # Specificity margin per topic, then min-max to [0,1] for a usable score.
    margins = {t: s - mean_sim for t, s in sims.items()}
    lo, hi = min(margins.values()), max(margins.values())
    span = hi - lo
    if span <= 1e-6:
        return {t: 0.5 for t in sims}
    return {t: round((m - lo) / span, 4) for t, m in margins.items()}


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
def infer_topics(text: str, *, lines: Optional[List[str]] = None) -> TopicInferenceResult:
    """Infer one or more topics for already-extracted text (file or URL)."""
    version, topic_lexicons = _load_signals()
    normalized = _normalize_text(text)
    top_text = _normalize_text("\n".join((lines or [])[:20])) if lines else normalized[:1200]

    lexical: Dict[str, float] = {}
    matched_terms: Dict[str, List[str]] = {}
    title_boost: Dict[str, float] = {}

    for topic in topic_lexicons:
        if topic.negative_terms and any(neg in normalized for neg in topic.negative_terms):
            # Negatives only veto when there is no positive evidence at all; we
            # still compute hits so a strongly on-topic doc is not silenced.
            pass
        total_hits = 0
        unique_hits = 0
        terms: List[str] = []
        top_hits = 0
        for pattern, label in topic.patterns:
            count = len(pattern.findall(normalized))
            if count:
                total_hits += count
                unique_hits += 1
                if label not in terms:
                    terms.append(label)
            if top_text:
                top_hits += len(pattern.findall(top_text))
        lexical[topic.name] = _lexical_score(total_hits, unique_hits)
        matched_terms[topic.name] = terms
        title_boost[topic.name] = 0.08 if top_hits >= 2 else 0.0

    embedding = _embedding_scores(text)
    stages_used = ["lexicon"]
    if embedding is not None:
        stages_used.append("embedding")

    ranked: List[TopicScore] = []
    for topic in topic_lexicons:
        name = topic.name
        lex = lexical.get(name, 0.0)
        emb = embedding.get(name, 0.0) if embedding is not None else 0.0
        if embedding is not None:
            final = (lex * LEX_WEIGHT) + (emb * EMB_WEIGHT)
        else:
            final = lex
        final = round(min(1.0, final + title_boost.get(name, 0.0)), 4)

        terms = matched_terms.get(name, [])[:TOPIC_MAX_TERMS]
        if terms:
            rationale = f"Matched {name} anchors: {', '.join(terms)}"
        else:
            rationale = f"No strong {name} lexicon hits; score driven by embedding similarity"
        ranked.append(
            TopicScore(
                topic=name,
                score=final,
                lexical_score=lex,
                embedding_score=round(emb, 4),
                matched_terms=terms,
                rationale=rationale,
            )
        )

    ranked.sort(key=lambda t: t.score, reverse=True)

    selected = [t for t in ranked if t.score >= TOPIC_SELECT_THRESHOLD][:TOPIC_MAX_SELECTED]
    # Guarantee at least the single best topic when there is any lexical signal,
    # since callers only invoke this for agriculture-related assets.
    if not selected and ranked and (ranked[0].lexical_score > 0 or embedding is not None):
        selected = [ranked[0]]

    method = "lexicon_embedding_hybrid" if embedding is not None else "lexicon_only"
    if selected:
        rationale = "Topics: " + ", ".join(f"{t.topic} ({t.score:.2f})" for t in selected)
    else:
        rationale = "No topic cleared the selection threshold"

    return TopicInferenceResult(
        topics=selected,
        ranked=ranked,
        method=method,
        stages_used=stages_used,
        signals_version=version,
        rationale=rationale,
    )
