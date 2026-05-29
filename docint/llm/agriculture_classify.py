from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict

from openai import OpenAI


SYSTEM_PROMPT = """You are an agriculture relevance classifier for PDF text.
Decide whether the document is agriculture-related.

Return ONLY valid JSON with:
{
  "is_agriculture_related": true,
  "confidence": 0.0,
  "matched_signals": ["signal_1"],
  "conflicting_signals": ["signal_1"],
  "rationale": "short evidence-based explanation"
}

Guidance:
- Treat agriculture broadly: farming systems, crops, livestock, manure, fertilizers, soil, irrigation, farm sustainability, nutrient recovery, bio-based fertilisers, food systems, and related agri-bioeconomy topics.
- Do not classify general water science, generic packaging, or unrelated industrial topics as agriculture-related unless the document clearly connects them to farming, agricultural inputs, food systems, or farm-level production.
- Be conservative when evidence is weak.
"""


@dataclass
class AgricultureLlmResult:
    is_agriculture_related: bool
    confidence: float
    rationale: str
    raw_json: Dict[str, Any]


def llm_classify_agriculture_text(
    text: str,
    *,
    base_url: str,
    api_key: str,
    model: str,
    max_chars: int = 12000,
    temperature: float = 0.0,
    timeout: float = 45.0,
) -> AgricultureLlmResult:
    client = OpenAI(base_url=base_url, api_key=api_key, timeout=timeout)

    if len(text) > max_chars:
        head_len = int(max_chars * 0.7)
        tail_len = int(max_chars * 0.3)
        text = text[:head_len] + "\n\n[...TRUNCATED...]\n\n" + text[-tail_len:]

    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": "DOCUMENT TEXT:\n" + text},
        ],
        temperature=temperature,
    )

    raw = resp.choices[0].message.content or ""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start != -1 and end != -1 and end > start:
            data = json.loads(raw[start:end + 1])
        else:
            raise ValueError(f"Could not parse agriculture LLM response: {raw[:200]}")

    return AgricultureLlmResult(
        is_agriculture_related=bool(data.get("is_agriculture_related", False)),
        confidence=float(data.get("confidence", 0.0)),
        rationale=str(data.get("rationale", "")).strip(),
        raw_json=data,
    )
