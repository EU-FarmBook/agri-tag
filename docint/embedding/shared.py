"""
Shared sentence-transformers model loader.

The agriculture, topics, and intended-purpose pipelines all use the same small
multilingual embedding model (``intfloat/multilingual-e5-small`` by default).
Previously each module loaded its own copy, which meant ~3x the RAM and three
separate (slow) cold-start loads. This module loads each distinct (model, device)
pair exactly once and shares the instance, so the first pipeline to touch it pays
the load cost and the others reuse it.

Loading is also guarded by a lock so concurrent first-requests can't trigger two
parallel downloads/loads of the same model.
"""
from __future__ import annotations

import os
import threading
from functools import lru_cache

# Quiet the noisy Hugging Face / transformers output (progress bars, advisory logs,
# tokenizer fork warnings). Set as defaults so an explicit env value still wins.
# These run before sentence-transformers/huggingface_hub are imported below.
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

_LOAD_LOCK = threading.Lock()


@lru_cache(maxsize=8)
def get_embedding_model(model_name: str, device: str = "cpu"):
    """Return a shared SentenceTransformer for (model_name, device), loaded once."""
    with _LOAD_LOCK:
        from sentence_transformers import SentenceTransformer

        return SentenceTransformer(model_name, device=device)


def prewarm_embedding_model(model_name: str, device: str = "cpu") -> bool:
    """Eagerly load (and tiny-encode) the model so the first request doesn't pay.

    Returns True on success, False if the model/deps are unavailable (fail-safe;
    never raises, so it is safe to call from a startup hook).
    """
    try:
        model = get_embedding_model(model_name, device=device)
        model.encode(["warmup"], normalize_embeddings=True)
        return True
    except Exception:
        return False
