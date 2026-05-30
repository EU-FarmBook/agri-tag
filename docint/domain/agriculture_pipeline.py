from __future__ import annotations

import importlib.util
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

from docint.domain.agriculture import assess_agriculture_relevance


@dataclass
class AgricultureStageResult:
    stage: str
    available: bool
    used: bool
    is_agriculture_related: Optional[bool]
    confidence: Optional[float]
    rationale: str
    details: Dict[str, Any]


@dataclass
class AgriculturePipelineResult:
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
    stages_used: List[str]
    stage_results: List[AgricultureStageResult]
    # True when stages 1-2 were inconclusive and the Stage-3 LLM was *deferred*
    # (defer_llm=True) so the caller can make a single combined agri+subtype call.
    needs_llm_decision: bool = False


AGRI_EMBEDDING_MODEL = os.getenv("AGRI_EMBEDDING_MODEL", "intfloat/multilingual-e5-small").strip()
AGRI_ENABLE_EMBEDDING = os.getenv("AGRI_ENABLE_EMBEDDING", "true").strip().lower() in {"1", "true", "yes"}
AGRI_ENABLE_LLM_FALLBACK = os.getenv("AGRI_ENABLE_LLM_FALLBACK", "true").strip().lower() in {"1", "true", "yes"}
EMBEDDING_TEXT_LIMIT = int(os.getenv("AGRI_EMBEDDING_TEXT_LIMIT", "3500"))
EMBEDDING_OVERRIDE_THRESHOLD = float(os.getenv("AGRI_EMBEDDING_OVERRIDE_THRESHOLD", "0.74"))
EMBEDDING_BLEND_WEIGHT = float(os.getenv("AGRI_EMBEDDING_BLEND_WEIGHT", "0.45"))
# Stage-3 agriculture LLM only fires when the lexicon+embedding result is genuinely
# ambiguous. These bounds are configurable so the (expensive) LLM call can be trimmed:
#  - inside [LOW, HIGH] = genuinely uncertain -> ask the LLM
#  - in [FLOOR, LOW) with substantive text   = weak-but-possible -> ask the LLM (rescue)
#  - below FLOOR                             = confidently non-agriculture -> DO NOT ask
# Raising FLOOR cuts LLM calls on clearly non-agri docs (faster) at some recall risk;
# tune against the eval set. (Previously FLOOR was effectively 0 -> the LLM fired on
# almost every substantive document.)
AGRI_LLM_CONF_LOW = float(os.getenv("AGRI_LLM_CONF_LOW", "0.3"))
AGRI_LLM_CONF_HIGH = float(os.getenv("AGRI_LLM_CONF_HIGH", "0.7"))
AGRI_LLM_LOWCONF_FLOOR = float(os.getenv("AGRI_LLM_LOWCONF_FLOOR", "0.1"))
REPO_ROOT = Path(__file__).resolve().parents[2]
AGRICULTURE_RUNTIME_DIR = REPO_ROOT / "data_model" / "runtime" / "agriculture"
BUCKET_CENTROID_PATH = AGRICULTURE_RUNTIME_DIR / "bucket_centroids.npz"
BUCKET_CENTROID_META_PATH = AGRICULTURE_RUNTIME_DIR / "bucket_centroids.meta.json"
NON_AGRICULTURE_PROTOTYPES = [
    "query: generic software products corporate administration mobile applications SaaS tooling account management and login workflows",
    "query: urban mobility finance legal compliance media entertainment consumer marketing and generic web publishing",
    "query: pure computing infrastructure general chemistry physics mathematics and unrelated industrial operations",
]


def _embedding_available() -> bool:
    return bool(AGRI_EMBEDDING_MODEL and importlib.util.find_spec("sentence_transformers"))


def _load_embedding_model():
    from docint.embedding.shared import get_embedding_model

    return get_embedding_model(AGRI_EMBEDDING_MODEL, device="cpu")


def _truncate_text(text: str) -> str:
    compact = " ".join(text.split())
    return compact[:EMBEDDING_TEXT_LIMIT]


@lru_cache(maxsize=1)
def _load_bucket_centroids() -> tuple[Dict[str, np.ndarray], Dict[str, Any]]:
    if not BUCKET_CENTROID_PATH.exists():
        return {}, {}

    arrs = np.load(BUCKET_CENTROID_PATH)
    centroids: Dict[str, np.ndarray] = {}
    for key in arrs.files:
        if key.startswith("bucket::"):
            centroids[key.removeprefix("bucket::")] = arrs[key]

    meta: Dict[str, Any] = {}
    if BUCKET_CENTROID_META_PATH.exists():
        import json

        meta = json.loads(BUCKET_CENTROID_META_PATH.read_text(encoding="utf-8"))
    return centroids, meta


def _embedding_stage(text: str) -> AgricultureStageResult:
    if not _embedding_available():
        return AgricultureStageResult(
            stage="embedding",
            available=False,
            used=False,
            is_agriculture_related=None,
            confidence=None,
            rationale="Embedding stage unavailable: sentence-transformers dependency or model is not configured locally",
            details={"model": AGRI_EMBEDDING_MODEL},
        )

    try:
        model = _load_embedding_model()
        text_for_embedding = _truncate_text(text)
        doc_emb = model.encode([f"query: {text_for_embedding}"], normalize_embeddings=True)
        bucket_centroids, bucket_meta = _load_bucket_centroids()
        use_bucket_centroids = bool(bucket_centroids)
        bucket_scores: Dict[str, float] = {}

        if use_bucket_centroids:
            bucket_scores = {
                bucket: float((doc_emb @ centroid.reshape(-1, 1))[0][0])
                for bucket, centroid in bucket_centroids.items()
                if bucket != "__all__"
            }
            max_bucket_score = float(max(bucket_scores.values())) if bucket_scores else 0.0
            global_centroid = bucket_centroids.get("__all__")
            global_score = (
                float((doc_emb @ global_centroid.reshape(-1, 1))[0][0])
                if global_centroid is not None
                else 0.0
            )
            agri_score = max(max_bucket_score, global_score)
        else:
            prototypes = {
                "agriculture": [
                    "query: agriculture farming crops livestock manure fertiliser soil irrigation nutrient recovery food systems",
                    "query: agricultural production farm sustainability agronomy field trials fertilisers digestate biostimulants pollination beekeeping pesticide crop protection",
                    "query: landbouw landbouwsystemen mest gewas bodem irrigatie landbouwproductie bestuiving bijenteelt pesticiden",
                    "query: agriculture cultures elevage fumier sol irrigation engrais pollinisation apiculture pesticide",
                    "query: georgia ktinotrophia lipasmata edafos ardrefsi agrodiatrofiko systima melissokomia epikoniasi",
                ],
            }
            agri_embs = model.encode(prototypes["agriculture"], normalize_embeddings=True)
            agri_score = float(max((doc_emb @ agri_embs.T)[0]))

        non_embs = model.encode(NON_AGRICULTURE_PROTOTYPES, normalize_embeddings=True)
    except Exception as exc:
        return AgricultureStageResult(
            stage="embedding",
            available=False,
            used=False,
            is_agriculture_related=None,
            confidence=None,
            rationale=f"Embedding stage unavailable: {exc}",
            details={"model": AGRI_EMBEDDING_MODEL},
        )

    non_score = float(max((doc_emb @ non_embs.T)[0]))
    margin = agri_score - non_score
    confidence = max(0.0, min(1.0, 0.5 + (margin * 1.75)))
    is_related = agri_score > non_score

    return AgricultureStageResult(
        stage="embedding",
        available=True,
        used=True,
        is_agriculture_related=is_related,
        confidence=round(confidence, 4),
        rationale=f"Embedding similarity agriculture={agri_score:.3f}, non_agriculture={non_score:.3f}",
        details={
            "model": AGRI_EMBEDDING_MODEL,
            "mode": "bucket_centroids" if use_bucket_centroids else "prototype_queries",
            "text_chars_used": min(len(text_for_embedding), EMBEDDING_TEXT_LIMIT),
            "agriculture_similarity": round(agri_score, 4),
            "non_agriculture_similarity": round(non_score, 4),
            "margin": round(margin, 4),
            "bucket_similarities": {k: round(v, 4) for k, v in sorted(bucket_scores.items(), key=lambda item: item[1], reverse=True)[:5]},
            "bucket_meta": bucket_meta if use_bucket_centroids else {},
        },
    )


def assess_agriculture_relevance_staged(
    text: str,
    *,
    lines: List[str] | None = None,
    allow_llm_fallback: bool = False,
    llm_config: Optional[Dict[str, str]] = None,
    defer_llm: bool = False,
) -> AgriculturePipelineResult:
    """
    Three-stage agriculture pipeline:
    1. AGROVOC-style multilingual lexicon matcher
    2. small local multilingual embedding model for ambiguous cases
    3. optional text LLM fallback only when still uncertain

    When ``defer_llm`` is True, Stage 3 is *not* called even if it would have
    fired; instead the result is flagged ``needs_llm_decision=True`` with the
    provisional Stage 1-2 verdict, so the caller can resolve it with a single
    combined agriculture+subtype LLM call (avoiding a second round-trip).
    """
    lex = assess_agriculture_relevance(text, lines=lines)
    stage_results: List[AgricultureStageResult] = [
        AgricultureStageResult(
            stage="lexicon",
            available=True,
            used=True,
            is_agriculture_related=lex.is_agriculture_related,
            confidence=lex.confidence,
            rationale=lex.rationale,
            details={
                "lexicon_version": lex.lexicon_version,
                "matched_buckets": lex.matched_buckets,
                "matched_concepts": lex.matched_concepts,
            },
        )
    ]
    stages_used = ["lexicon"]

    final_is_related = lex.is_agriculture_related
    final_confidence = lex.confidence
    final_method = lex.method
    final_rationale = lex.rationale

    substantive_text = len((text or "").split()) >= 80 or len(text or "") >= 600
    ambiguous = 0.2 <= lex.score <= 0.75
    should_try_embedding = AGRI_ENABLE_EMBEDDING and (ambiguous or (lex.score < 0.2 and substantive_text))
    if should_try_embedding:
        emb = _embedding_stage(text)
        stage_results.append(emb)
        if emb.used:
            stages_used.append("embedding")
            if emb.confidence is not None:
                if emb.confidence >= EMBEDDING_OVERRIDE_THRESHOLD:
                    final_is_related = bool(emb.is_agriculture_related)
                    final_confidence = emb.confidence
                    final_method = "embedding_stage_cpu"
                    final_rationale = emb.rationale
                else:
                    blended = max(
                        0.0,
                        min(1.0, (lex.confidence * (1.0 - EMBEDDING_BLEND_WEIGHT)) + (emb.confidence * EMBEDDING_BLEND_WEIGHT)),
                    )
                    final_confidence = round(blended, 4)
                    if lex.confidence >= emb.confidence:
                        final_is_related = lex.is_agriculture_related
                    else:
                        final_is_related = bool(emb.is_agriculture_related)
                    final_method = "lexicon_embedding_hybrid"
                    final_rationale = f"{lex.rationale} | {emb.rationale}"
        else:
            stage_results.append(
                AgricultureStageResult(
                    stage="embedding_notice",
                    available=True,
                    used=False,
                    is_agriculture_related=None,
                    confidence=None,
                    rationale="Embedding stage was enabled but could not be used; falling back to lexicon result",
                    details={"model": AGRI_EMBEDDING_MODEL},
                )
            )

    still_ambiguous = (
        (AGRI_LLM_CONF_LOW <= final_confidence <= AGRI_LLM_CONF_HIGH)
        or (AGRI_LLM_LOWCONF_FLOOR <= final_confidence < AGRI_LLM_CONF_LOW and substantive_text)
    )
    needs_llm_decision = False
    if still_ambiguous and allow_llm_fallback and AGRI_ENABLE_LLM_FALLBACK and llm_config and defer_llm:
        # Defer Stage 3: the caller will run one combined agri+subtype LLM call.
        needs_llm_decision = True
    elif still_ambiguous and allow_llm_fallback and AGRI_ENABLE_LLM_FALLBACK and llm_config:
        try:
            from docint.llm.agriculture_classify import llm_classify_agriculture_text

            llm_res = llm_classify_agriculture_text(
                text,
                base_url=llm_config["base_url"],
                api_key=llm_config["api_key"],
                model=llm_config["model"],
            )
            stage_results.append(
                AgricultureStageResult(
                    stage="llm",
                    available=True,
                    used=True,
                    is_agriculture_related=llm_res.is_agriculture_related,
                    confidence=llm_res.confidence,
                    rationale=llm_res.rationale,
                    details=llm_res.raw_json,
                )
            )
            stages_used.append("llm")
            final_is_related = llm_res.is_agriculture_related
            final_confidence = llm_res.confidence
            final_method = "llm_fallback"
            final_rationale = llm_res.rationale
        except Exception as exc:
            stage_results.append(
                AgricultureStageResult(
                    stage="llm",
                    available=bool(llm_config),
                    used=False,
                    is_agriculture_related=None,
                    confidence=None,
                    rationale=f"LLM fallback unavailable: {exc}",
                    details={},
                )
            )

    return AgriculturePipelineResult(
        is_agriculture_related=final_is_related,
        confidence=round(final_confidence, 4),
        score=round(final_confidence, 4),
        method=final_method,
        lexicon_version=lex.lexicon_version,
        matched_terms=lex.matched_terms,
        matched_buckets=lex.matched_buckets,
        matched_concepts=lex.matched_concepts,
        bucket_scores=lex.bucket_scores,
        rationale=final_rationale,
        stages_used=stages_used,
        stage_results=stage_results,
        needs_llm_decision=needs_llm_decision,
    )
