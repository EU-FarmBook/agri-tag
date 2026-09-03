from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, Optional

from openai import OpenAI

from ._tuning import reasoning_kwargs


SYSTEM_PROMPT = """You are a knowledge-object eligibility classifier.
The text may be in ANY language; judge by meaning, not language.
Your job is NOT to decide whether the text is agriculture-related.
Your job is to decide whether the content is an eligible knowledge object for content classification,
or whether it should be excluded because it is mainly one of these:
- job vacancy / recruitment ad
- call for applications / fellowship / internship notice
- event announcement / registration page
- procurement / tender notice
- generic administrative notice

Return ONLY valid JSON:
{
  "is_eligible": true,
  "confidence": 0.0,
  "exclusion_type": null,
  "matched_signals": ["signal_1"],
  "rationale": "short evidence-based explanation"
}

Guidance:
- A document can be agriculture-related but still be ineligible if it is mainly a vacancy, application call, or event notice.
- Be conservative about rejection, but reject clearly when the document is mainly a recruitment or announcement artifact rather than substantive knowledge content.
"""


@dataclass
class KoEligibilityLlmResult:
    is_eligible: bool
    confidence: float
    exclusion_type: Optional[str]
    rationale: str
    raw_json: Dict[str, Any]


def llm_classify_ko_eligibility_text(
    text: str,
    *,
    base_url: str,
    api_key: str,
    model: str,
    max_chars: int = 8000,
    temperature: float = 0.0,
    timeout: float = 45.0,
) -> KoEligibilityLlmResult:
    client = OpenAI(base_url=base_url, api_key=api_key, timeout=timeout)

    if len(text) > max_chars:
        head_len = int(max_chars * 0.6)
        tail_len = int(max_chars * 0.2)
        mid_len = max_chars - head_len - tail_len - 20
        mid_start = max(0, (len(text) // 2) - (mid_len // 2))
        mid_end = min(len(text), mid_start + mid_len)
        text = text[:head_len] + "\n\n[...]\n\n" + text[mid_start:mid_end] + "\n\n[...]\n\n" + text[-tail_len:]

    resp = client.chat.completions.create(
        **reasoning_kwargs(),
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
            raise ValueError(f"Could not parse KO eligibility LLM response: {raw[:200]}")

    exclusion_type = data.get("exclusion_type")
    if exclusion_type in {"", "null"}:
        exclusion_type = None

    return KoEligibilityLlmResult(
        is_eligible=bool(data.get("is_eligible", True)),
        confidence=float(data.get("confidence", 0.0)),
        exclusion_type=str(exclusion_type).strip() if exclusion_type is not None else None,
        rationale=str(data.get("rationale", "")).strip(),
        raw_json=data,
    )
