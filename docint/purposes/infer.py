"""
Intended-purpose inference for knowledge objects.

`Intended purpose` is the **user-intent / functional** facet of a knowledge object
("what would a user come to this resource to do?") — e.g. *Access data*, *Ensure
compliance*, *Build professional networks*. It is orthogonal to both the
category/subcategory (genre/form) and the topics (subject matter), and it is
**multi-label, capped at 3** per object.

Because intent is pragmatic rather than lexical, the LLM is the quality path. The
module is staged like the agriculture/topics pipelines so it degrades gracefully:

  Stage 1 - embedding: a CPU-first multilingual embedding match against each
            purpose's "name + description" anchor (intfloat/multilingual-e5-small).
            Always available; used as the baseline / offline fallback.
  Stage 2 - LLM: when a text LLM is available, it ranks the purposes for the
            document and returns up to 3 with confidence + rationale. This is the
            primary signal when present.

The taxonomy is loaded from
``data_model/runtime/purposes/intended_purposes.json`` (a published list of
purposes with name/category/description). The module never hard-fails: if the
embedding model or the LLM is unavailable it returns whatever stage did run.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
PURPOSES_PATH = REPO_ROOT / "data_model" / "runtime" / "purposes" / "intended_purposes.json"

PURPOSE_EMBEDDING_MODEL = os.getenv(
    "PURPOSE_EMBEDDING_MODEL",
    os.getenv("AGRI_EMBEDDING_MODEL", "intfloat/multilingual-e5-small"),
).strip()
PURPOSE_ENABLE_EMBEDDING = os.getenv("PURPOSE_ENABLE_EMBEDDING", "true").strip().lower() in {"1", "true", "yes"}
EMBEDDING_TEXT_LIMIT = int(os.getenv("PURPOSE_EMBEDDING_TEXT_LIMIT", "3500"))
PURPOSE_MAX_SELECTED = int(os.getenv("PURPOSE_MAX_SELECTED", "3"))
# A purpose is emitted (embedding stage) when its normalised score clears this bar.
PURPOSE_SELECT_THRESHOLD = float(os.getenv("PURPOSE_SELECT_THRESHOLD", "0.5"))
# Max characters of document text sent to the LLM purpose classifier.
PURPOSE_LLM_MAX_CHARS = int(os.getenv("PURPOSE_LLM_MAX_CHARS", "9000"))


@dataclass(frozen=True)
class Purpose:
    key: str          # stable id from the taxonomy (_id)
    name: str
    category: str
    description: str


@dataclass
class PurposeScore:
    key: str
    name: str
    category: str
    score: float
    rationale: str = ""


@dataclass
class PurposeInferenceResult:
    purposes: List[PurposeScore] = field(default_factory=list)
    method: str = "none"
    stages_used: List[str] = field(default_factory=list)
    version: str = "intended_purpose_v1"
    rationale: str = ""


@lru_cache(maxsize=1)
def load_purposes() -> List[Purpose]:
    """Load and normalise the intended-purpose taxonomy (cached)."""
    try:
        raw = json.loads(PURPOSES_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []
    purposes: List[Purpose] = []
    for item in raw:
        name = (item.get("name") or "").strip()
        if not name:
            continue
        purposes.append(
            Purpose(
                key=str(item.get("_id") or name),
                name=name,
                category=(item.get("category") or "").strip(),
                description=(item.get("description") or "").strip(),
            )
        )
    return purposes


def _purpose_by_key() -> Dict[str, Purpose]:
    return {p.key: p for p in load_purposes()}


def _purpose_by_name() -> Dict[str, Purpose]:
    return {p.name.lower(): p for p in load_purposes()}


def _truncate(text: str) -> str:
    text = " ".join((text or "").split())
    return text[:EMBEDDING_TEXT_LIMIT]


# ---------------------------------------------------------------------------
# Stage 1 - embedding
# ---------------------------------------------------------------------------

def _embedding_available() -> bool:
    if not PURPOSE_ENABLE_EMBEDDING:
        return False
    try:
        import importlib.util

        return importlib.util.find_spec("sentence_transformers") is not None
    except Exception:
        return False


@lru_cache(maxsize=1)
def _model():
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(PURPOSE_EMBEDDING_MODEL, device="cpu")


@lru_cache(maxsize=1)
def _purpose_anchor_matrix():
    """Encode each purpose's 'name. description' anchor once (cached)."""
    purposes = load_purposes()
    if not purposes:
        return None, []
    model = _model()
    anchors = [f"passage: {p.name}. {p.description}" for p in purposes]
    vectors = model.encode(anchors, normalize_embeddings=True)
    return np.asarray(vectors), purposes


def _embedding_scores(text: str) -> Optional[Dict[str, float]]:
    if not _embedding_available():
        return None
    try:
        matrix, purposes = _purpose_anchor_matrix()
        if matrix is None:
            return None
        model = _model()
        doc = model.encode([f"query: {_truncate(text)}"], normalize_embeddings=True)
        sims = (np.asarray(doc) @ matrix.T)[0]  # cosine (normalised)
        # Min-max normalise across purposes so scores span [0, 1].
        lo, hi = float(sims.min()), float(sims.max())
        span = (hi - lo) or 1.0
        return {purposes[i].key: float((sims[i] - lo) / span) for i in range(len(purposes))}
    except Exception:
        return None


def _infer_embeddings(text: str, *, max_results: int) -> PurposeInferenceResult:
    scores = _embedding_scores(text)
    by_key = _purpose_by_key()
    if not scores:
        return PurposeInferenceResult(method="unavailable", stages_used=[], rationale="Embedding model unavailable")
    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    selected: List[PurposeScore] = []
    for key, score in ranked:
        if len(selected) >= max_results:
            break
        if score < PURPOSE_SELECT_THRESHOLD and selected:
            break
        p = by_key.get(key)
        if not p:
            continue
        selected.append(PurposeScore(key=p.key, name=p.name, category=p.category, score=round(score, 4),
                                     rationale=f"Embedding match to '{p.name}'"))
    return PurposeInferenceResult(
        purposes=selected,
        method="embedding",
        stages_used=["embedding"],
        rationale="Intended purposes: " + ", ".join(f"{p.name} ({p.score:.2f})" for p in selected) if selected else "No purpose cleared the threshold",
    )


# ---------------------------------------------------------------------------
# Stage 2 - LLM
# ---------------------------------------------------------------------------

def _build_llm_prompt(text: str) -> List[Dict[str, str]]:
    purposes = load_purposes()
    catalogue = "\n".join(f"- {p.name}: {p.description}" for p in purposes)
    system = (
        "You label a knowledge object with the USER INTENTS it serves - what a user "
        "would come to this resource to DO. This is different from its topic or its "
        "document type. Choose only from the provided list."
    )
    instructions = (
        "From the INTENDED PURPOSE OPTIONS below, select the 1 to 3 that best match the "
        "document. Prefer fewer when only one clearly applies. Use 'Other' only when none fit.\n\n"
        "Return STRICT JSON:\n"
        '{"purposes": [{"name": "<exact option name>", "confidence": 0.0-1.0, "reason": "<short>"}], '
        '"rationale": "<one sentence>"}\n\n'
        "INTENDED PURPOSE OPTIONS:\n" + catalogue
    )
    body = " ".join((text or "").split())[:PURPOSE_LLM_MAX_CHARS]
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": instructions + "\n\nDOCUMENT TEXT:\n" + body},
    ]


def _infer_llm(text: str, *, base_url: str, api_key: str, model: str, max_results: int, timeout: float = 60.0) -> Optional[PurposeInferenceResult]:
    try:
        from openai import OpenAI
        from docint.llm.subcategory_classify import _parse_llm_json_response
    except Exception:
        return None
    try:
        client = OpenAI(base_url=base_url, api_key=api_key, timeout=timeout)
        resp = client.chat.completions.create(
            model=model,
            messages=_build_llm_prompt(text),
            temperature=0.1,
        )
        raw = resp.choices[0].message.content or ""
        data = _parse_llm_json_response(raw, label="intended-purpose LLM")
    except Exception:
        return None

    by_name = _purpose_by_name()
    selected: List[PurposeScore] = []
    for item in (data.get("purposes") or []):
        name = str(item.get("name", "")).strip()
        p = by_name.get(name.lower())
        if not p:
            continue
        if any(s.key == p.key for s in selected):
            continue
        try:
            conf = float(item.get("confidence", 0.0))
        except (TypeError, ValueError):
            conf = 0.0
        selected.append(PurposeScore(key=p.key, name=p.name, category=p.category,
                                     score=round(max(0.0, min(1.0, conf)), 4),
                                     rationale=str(item.get("reason", "")).strip()))
        if len(selected) >= max_results:
            break
    if not selected:
        return None
    selected.sort(key=lambda s: s.score, reverse=True)
    return PurposeInferenceResult(
        purposes=selected,
        method="llm",
        stages_used=["llm"],
        rationale=str(data.get("rationale", "")).strip()
        or ("Intended purposes: " + ", ".join(p.name for p in selected)),
    )


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def infer_intended_purposes(
    text: str,
    *,
    max_results: int = PURPOSE_MAX_SELECTED,
    use_llm: bool = False,
    llm_config: Optional[Dict[str, str]] = None,
) -> PurposeInferenceResult:
    """Infer up to `max_results` intended purposes for a document.

    Uses the LLM stage when `use_llm` and `llm_config` are provided (primary),
    otherwise falls back to the embedding stage. If the LLM stage fails it falls
    back to embeddings as well, so a result is always returned (possibly empty).
    """
    max_results = max(1, min(max_results, PURPOSE_MAX_SELECTED))
    if not load_purposes():
        return PurposeInferenceResult(method="no_taxonomy", rationale="Intended-purpose taxonomy not loaded")

    if use_llm and llm_config and llm_config.get("base_url") and llm_config.get("model"):
        llm_result = _infer_llm(
            text,
            base_url=llm_config["base_url"],
            api_key=llm_config.get("api_key", ""),
            model=llm_config["model"],
            max_results=max_results,
        )
        if llm_result and llm_result.purposes:
            return llm_result

    return _infer_embeddings(text, max_results=max_results)
