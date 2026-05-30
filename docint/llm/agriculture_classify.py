from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict

from openai import OpenAI


SYSTEM_PROMPT = """You are an agriculture relevance classifier for knowledge objects
(documents, datasets, transcripts). Decide whether the content is agriculture-related.

The text may be written in ANY language (e.g. English, Dutch, German, French, Greek,
Bulgarian, Spanish, Italian, Polish, ...). Classify by MEANING, not language; never
treat non-English text as less relevant, and judge column names / abbreviations
(e.g. "rainfall_mm", "temperature_c", "ndvi", "parcel_id") on what they represent.

Return ONLY valid JSON with:
{
  "is_agriculture_related": true,
  "confidence": 0.0,
  "matched_signals": ["signal_1"],
  "conflicting_signals": ["signal_1"],
  "rationale": "short evidence-based explanation"
}

Guidance:
- Treat agriculture broadly: farming systems, crops, livestock, manure, fertilizers,
  soil, irrigation, farm sustainability, nutrient recovery, bio-based fertilisers,
  food systems, forestry, rural development, and related agri-bioeconomy topics.
- INCLUDE environmental, climate, weather, agro-meteorological, and temporal data when
  it is the kind used in agriculture/land/rural contexts — e.g. weather station series
  (temperature, rainfall, humidity, solar radiation, wind), soil moisture, growing-season
  or agro-climatic conditions, and remote-sensing/geospatial parcel data. These are core
  agricultural environmental data, not "general water science".
- Only exclude content with no plausible agricultural connection (e.g. consumer banking,
  unrelated industrial manufacturing, general entertainment).
- When a dataset or document plausibly supports farming or land/rural decision-making,
  classify it as agriculture-related.
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
