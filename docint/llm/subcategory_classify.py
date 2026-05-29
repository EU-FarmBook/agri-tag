# docint/llm/subcategory_classify.py
"""
LLM classification for subcategories - aligns with evidence-based scoring.
Supports both text models (Qwen) and vision models (InternVL).
"""

from __future__ import annotations

import json
import os
import base64
import re
from dataclasses import dataclass
from typing import Dict, List, Any
from pathlib import Path

from openai import OpenAI

from docint.subtypes.unified import (
    allowed_unified_keys_for_category,
    load_category_profiles,
    load_unified_subtypes,
)


def _category_keys(category: str) -> List[str]:
    return list(allowed_unified_keys_for_category(category))


def _normalize_probs_for_category(probs: Dict[str, float], category: str) -> Dict[str, float]:
    keys = _category_keys(category)
    out = {k: float(probs.get(k, 0.0)) for k in keys}
    s = sum(out.values())
    if s <= 0:
        return {k: round(1.0 / len(keys), 4) for k in keys}
    return {k: round(v / s, 4) for k, v in out.items()}


def _parse_llm_json_response(raw: str, *, label: str) -> Dict[str, Any]:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise ValueError(f"Could not parse {label} response: {raw[:200]}")

        candidate = raw[start:end + 1]
        repairs = [
            candidate,
            re.sub(r",\s*([}\]])", r"\1", candidate),
            re.sub(r"(?<!\\\\)\n", " ", candidate),
        ]
        repairs.append(re.sub(r",\s*([}\]])", r"\1", repairs[-1]))

        for repaired in repairs:
            try:
                return json.loads(repaired)
            except json.JSONDecodeError:
                continue

        raise ValueError(f"Could not parse {label} response: {raw[:200]}")


def _salvage_partial_llm_payload(raw: str, *, category: str) -> Dict[str, Any]:
    keys = _category_keys(category)

    def _extract(pattern: str) -> str:
        match = re.search(pattern, raw, flags=re.IGNORECASE | re.DOTALL)
        return match.group(1).strip() if match else ""

    subcategory = _extract(r'"subcategory"\s*:\s*"([^"]+)"')
    profile_id = _extract(r'"profile_id"\s*:\s*"([^"]+)"')
    confidence_str = _extract(r'"confidence"\s*:\s*([0-9]*\.?[0-9]+)')
    rationale = _extract(r'"rationale"\s*:\s*"([^"]*)"')
    closest_alternative = _extract(r'"closest_alternative"\s*:\s*"([^"]+)"')

    if not subcategory or subcategory not in keys:
        raise ValueError("salvage failed: missing valid subcategory")

    try:
        confidence = float(confidence_str) if confidence_str else 0.75
    except ValueError:
        confidence = 0.75

    confidence = max(0.0, min(1.0, confidence))
    probs: Dict[str, float] = {key: 0.0 for key in keys}
    probs[subcategory] = confidence

    remainder_keys = [key for key in keys if key != subcategory]
    remainder = max(0.0, 1.0 - confidence)
    if remainder_keys:
        share = remainder / len(remainder_keys)
        for key in remainder_keys:
            probs[key] = share

    return {
        "subcategory": subcategory,
        "profile_id": profile_id or None,
        "confidence": confidence,
        "rationale": rationale or "Recovered from malformed LLM JSON output.",
        "matched_signals": [],
        "conflicting_signals": [],
        "closest_alternative": closest_alternative or (remainder_keys[0] if remainder_keys else subcategory),
        "probs": probs,
        "_salvaged": True,
    }


def _build_unified_category_prompt(
    category: str,
    *,
    include_agriculture_gate: bool = False,
    include_visual_evidence: bool = False,
) -> str:
    defs = load_unified_subtypes()
    keys = _category_keys(category)
    profiles = load_category_profiles(category)
    prompt_lines = [
        f"You are a {category.lower()} classifier for agricultural knowledge objects.",
        "Use the merged cross-modal subtype model.",
        "Score category-specific intermediate profiles first, then choose the best final unified subcategory.",
        "Ground your decision in observable evidence only.",
    ]
    if include_agriculture_gate:
        prompt_lines.append("First decide whether the asset is agriculture-related.")
    if include_visual_evidence:
        prompt_lines.append("Use both transcript/text evidence and visual evidence when available.")
    prompt_lines.extend([
        "",
        "Final unified subcategories for this category:",
    ])
    for key in keys:
        item = defs[key]
        prompt_lines.append(f"- {key} ({item.name})")
        prompt_lines.append(f"  definition: {item.definition}")
        prompt_lines.append(f"  scope_note: {item.scope_note}")
        prompt_lines.append("  detailed_features: " + "; ".join(item.detailed_features))
        prompt_lines.append("")

    prompt_lines.append("Category-specific intermediate profiles:")
    for profile in profiles:
        prompt_lines.append(f"- {profile['id']} ({profile['name']})")
        prompt_lines.append(f"  definition: {profile['definition']}")
        prompt_lines.append(f"  scope_note: {profile['scope_note']}")
        imports = []
        for item in profile.get("imports_to_unified", []):
            relation = item.get("relation", "primary")
            imports.append(f"{relation}:{item.get('unified_subcategory_id')}")
        prompt_lines.append("  maps_to_unified: " + ", ".join(imports))
        for feature_group in profile.get("feature_groups", []):
            prompt_lines.append(f"  feature_group: {feature_group['feature_id']}")
            prompt_lines.append(f"    measurement: {feature_group['measurement']}")
            prompt_lines.append(
                "    positive_indicators: " + ", ".join(feature_group.get("positive_indicators", [])[:8])
            )
            if feature_group.get("negative_indicators"):
                prompt_lines.append(
                    "    negative_indicators: " + ", ".join(feature_group.get("negative_indicators", [])[:8])
                )
        prompt_lines.append("")

    prompt_lines.extend([
        "Return ONLY valid JSON with:",
    ])
    if include_agriculture_gate:
        prompt_lines.extend([
            "1. 'is_agriculture_related': true or false",
            "2. 'agriculture_confidence': confidence 0.0-1.0 for agriculture relevance",
            "3. 'subcategory': the final unified subcategory key if agriculture-related, otherwise null",
            "4. 'profile_id': the best matching category profile id if agriculture-related, otherwise null",
            "5. 'confidence': subtype confidence 0.0-1.0",
            "6. 'rationale': brief explanation citing observable evidence",
            "7. 'matched_signals': short list of supporting signals",
            "8. 'conflicting_signals': short list of ambiguity signals",
            "9. 'closest_alternative': the next most plausible final unified subcategory key",
            "10. 'probs': object with probability for EACH final unified subcategory key",
        ])
    else:
        prompt_lines.extend([
            "1. 'subcategory': the final unified subcategory key",
            "2. 'profile_id': the best matching category profile id",
            "3. 'confidence': your confidence 0.0-1.0",
            "4. 'rationale': brief explanation citing observable evidence",
            "5. 'matched_signals': short list of supporting signals",
            "6. 'conflicting_signals': short list of ambiguity signals",
            "7. 'closest_alternative': the next most plausible final unified subcategory key",
            "8. 'probs': object with probability for EACH final unified subcategory key",
        ])
    prompt_lines.append("Be honest about uncertainty. Prefer measurable profile evidence over generic topical wording.")
    return "\n".join(prompt_lines)


def _build_unified_schema(category: str, *, include_agriculture_gate: bool = False) -> str:
    keys = _category_keys(category)
    probs_template = "\n".join([f'    "{k}": 0.0,' for k in keys])
    if include_agriculture_gate:
        return f"""Return ONLY valid JSON:
{{
  "is_agriculture_related": true,
  "agriculture_confidence": 0.0,
  "subcategory": "one_of_the_unified_keys_below_or_null",
  "profile_id": "one_of_the_profile_ids_below_or_null",
  "confidence": 0.0,
  "rationale": "explanation with evidence",
  "matched_signals": ["signal_1", "signal_2"],
  "conflicting_signals": ["signal_1"],
  "closest_alternative": "one_of_the_unified_keys_below",
  "probs": {{
{probs_template}
  }}
}}

Available unified subcategory keys:
""" + "\n".join([f"- {k}" for k in keys])
    return f"""Return ONLY valid JSON:
{{
  "subcategory": "one_of_the_unified_keys_below",
  "profile_id": "one_of_the_profile_ids_below",
  "confidence": 0.0,
  "rationale": "explanation with evidence",
  "matched_signals": ["signal_1", "signal_2"],
  "conflicting_signals": ["signal_1"],
  "closest_alternative": "one_of_the_unified_keys_below",
  "probs": {{
{probs_template}
  }}
}}

Available unified subcategory keys:
""" + "\n".join([f"- {k}" for k in keys])


DOCUMENT_UNIFIED_KEYS = _category_keys("Document")
DATASET_UNIFIED_KEYS = _category_keys("Dataset")
IMAGE_UNIFIED_KEYS = _category_keys("Image")
AUDIO_UNIFIED_KEYS = _category_keys("Audio")
VIDEO_UNIFIED_KEYS = _category_keys("Video")
SOFTWARE_UNIFIED_KEYS = _category_keys("Software Application")

SYSTEM_PROMPT = _build_unified_category_prompt("Document")
DATASET_SYSTEM_PROMPT = _build_unified_category_prompt("Dataset")
IMAGE_SYSTEM_PROMPT = _build_unified_category_prompt("Image", include_agriculture_gate=True)
AUDIO_SYSTEM_PROMPT = _build_unified_category_prompt("Audio")
VIDEO_SYSTEM_PROMPT = _build_unified_category_prompt("Video", include_agriculture_gate=True, include_visual_evidence=True)
SOFTWARE_SYSTEM_PROMPT = _build_unified_category_prompt("Software Application")


def build_schema() -> str:
    return _build_unified_schema("Document")


def build_dataset_schema() -> str:
    return _build_unified_schema("Dataset")


def build_image_schema() -> str:
    return _build_unified_schema("Image", include_agriculture_gate=True)


def build_audio_schema() -> str:
    return _build_unified_schema("Audio")


def build_video_schema() -> str:
    return _build_unified_schema("Video", include_agriculture_gate=True)


def build_software_schema() -> str:
    return _build_unified_schema("Software Application")


@dataclass
class SubcategoryLlmResult:
    """Result from LLM subcategory classification."""
    subcategory_key: str
    subcategory_name: str
    parent_type: str
    confidence: float
    rationale: str
    probs: Dict[str, float]  # Probabilities for all subcategories
    raw_json: Dict[str, Any]


def normalize_subcategory_probs(probs: Dict[str, float]) -> Dict[str, float]:
    return _normalize_probs_for_category(probs, "Document")


def normalize_dataset_probs(probs: Dict[str, float]) -> Dict[str, float]:
    return _normalize_probs_for_category(probs, "Dataset")


def normalize_audio_probs(probs: Dict[str, float]) -> Dict[str, float]:
    return _normalize_probs_for_category(probs, "Audio")


def normalize_video_probs(probs: Dict[str, float]) -> Dict[str, float]:
    return _normalize_probs_for_category(probs, "Video")


def normalize_software_probs(probs: Dict[str, float]) -> Dict[str, float]:
    return _normalize_probs_for_category(probs, "Software Application")


def llm_classify_subcategories_text(
    text: str,
    *,
    base_url: str,
    api_key: str,
    model: str,
    max_chars: int = 15000,
    temperature: float = 0.2,
    timeout: float = 60.0,
) -> SubcategoryLlmResult:
    """
    Classify document text into subcategories using text-based LLM.
    
    Args:
        text: Document text content
        base_url: vLLM/OpenAI compatible endpoint
        api_key: API key
        model: Model name
        max_chars: Max text length to send
        temperature: Sampling temperature
        timeout: Request timeout
    
    Returns:
        SubcategoryLlmResult with classification
    """
    client = OpenAI(base_url=base_url, api_key=api_key, timeout=timeout)
    
    # Truncate text if needed
    if len(text) > max_chars:
        head_len = int(max_chars * 0.7)
        tail_len = int(max_chars * 0.3)
        text = text[:head_len] + "\n\n[...TRUNCATED...]\n\n" + text[-tail_len:]
    
    schema = build_schema()
    
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": schema + "\n\nDOCUMENT TEXT:\n" + text},
    ]
    
    resp = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
    )
    
    raw = resp.choices[0].message.content or ""
    
    # Parse JSON response
    data = _parse_llm_json_response(raw, label="document LLM")
    
    # Extract and normalize
    subcat_key = data.get("subcategory", "")
    if subcat_key not in DOCUMENT_UNIFIED_KEYS:
        # Try to find closest match or use highest prob
        probs = data.get("probs", {})
        subcat_key = max(probs.items(), key=lambda x: x[1])[0] if probs else DOCUMENT_UNIFIED_KEYS[0]
    
    subcat_def = load_unified_subtypes()[subcat_key]
    probs = normalize_subcategory_probs(data.get("probs", {}))
    
    return SubcategoryLlmResult(
        subcategory_key=subcat_key,
        subcategory_name=subcat_def.name,
        parent_type="unified",
        confidence=float(data.get("confidence", probs.get(subcat_key, 0))),
        rationale=str(data.get("rationale", "")).strip(),
        probs=probs,
        raw_json=data,
    )


def llm_classify_dataset_subcategories_text(
    text: str,
    *,
    base_url: str,
    api_key: str,
    model: str,
    max_chars: int = 12000,
    temperature: float = 0.2,
    timeout: float = 60.0,
) -> SubcategoryLlmResult:
    client = OpenAI(base_url=base_url, api_key=api_key, timeout=timeout)

    if len(text) > max_chars:
        head_len = int(max_chars * 0.75)
        tail_len = int(max_chars * 0.25)
        text = text[:head_len] + "\n\n[...TRUNCATED...]\n\n" + text[-tail_len:]

    schema = build_dataset_schema()
    messages = [
        {"role": "system", "content": DATASET_SYSTEM_PROMPT},
        {"role": "user", "content": schema + "\n\nDATASET CONTENT PREVIEW:\n" + text},
    ]

    resp = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
    )

    raw = resp.choices[0].message.content or ""
    try:
        data = _parse_llm_json_response(raw, label="dataset LLM")
    except ValueError:
        data = _salvage_partial_llm_payload(raw, category="Dataset")

    subcat_key = data.get("subcategory", "")
    if subcat_key not in DATASET_UNIFIED_KEYS:
        probs = data.get("probs", {})
        subcat_key = max(probs.items(), key=lambda x: x[1])[0] if probs else DATASET_UNIFIED_KEYS[0]

    subtype = load_unified_subtypes()[subcat_key]
    probs = normalize_dataset_probs(data.get("probs", {}))

    return SubcategoryLlmResult(
        subcategory_key=subcat_key,
        subcategory_name=subtype.name,
        parent_type="unified",
        confidence=float(data.get("confidence", probs.get(subcat_key, 0))),
        rationale=str(data.get("rationale", "")).strip(),
        probs=probs,
        raw_json=data,
    )


def llm_classify_software_subcategories_text(
    text: str,
    *,
    base_url: str,
    api_key: str,
    model: str,
    max_chars: int = 12000,
    temperature: float = 0.2,
    timeout: float = 60.0,
) -> SubcategoryLlmResult:
    client = OpenAI(base_url=base_url, api_key=api_key, timeout=timeout)

    if len(text) > max_chars:
        head_len = int(max_chars * 0.75)
        tail_len = int(max_chars * 0.25)
        text = text[:head_len] + "\n\n[...TRUNCATED...]\n\n" + text[-tail_len:]

    schema = build_software_schema()
    messages = [
        {"role": "system", "content": SOFTWARE_SYSTEM_PROMPT},
        {"role": "user", "content": schema + "\n\nSOFTWARE OR TOOL DESCRIPTION:\n" + text},
    ]

    resp = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
    )

    raw = resp.choices[0].message.content or ""
    data = _parse_llm_json_response(raw, label="software LLM")

    subcat_key = data.get("subcategory", "")
    if subcat_key not in SOFTWARE_UNIFIED_KEYS:
        probs = data.get("probs", {})
        subcat_key = max(probs.items(), key=lambda x: x[1])[0] if probs else SOFTWARE_UNIFIED_KEYS[0]

    subtype = load_unified_subtypes()[subcat_key]
    probs = normalize_software_probs(data.get("probs", {}))

    return SubcategoryLlmResult(
        subcategory_key=subcat_key,
        subcategory_name=subtype.name,
        parent_type="unified",
        confidence=float(data.get("confidence", probs.get(subcat_key, 0))),
        rationale=str(data.get("rationale", "")).strip(),
        probs=probs,
        raw_json=data,
    )


def llm_classify_image_with_vision(
    image_path: str,
    *,
    base_url: str,
    api_key: str,
    model: str,
    temperature: float = 0.2,
    timeout: float = 120.0,
) -> Dict[str, Any]:
    client = OpenAI(base_url=base_url, api_key=api_key, timeout=timeout)
    img_path = Path(image_path)
    suffix = img_path.suffix.lower()
    mime = "image/png" if suffix == ".png" else "image/jpeg"
    img_base64 = base64.b64encode(img_path.read_bytes()).decode("utf-8")

    content = [
        {"type": "text", "text": IMAGE_SYSTEM_PROMPT + "\n\n" + build_image_schema()},
        {
            "type": "image_url",
            "image_url": {
                "url": f"data:{mime};base64,{img_base64}",
                "detail": "high",
            },
        },
    ]
    messages = [{"role": "user", "content": content}]

    resp = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=1200,
    )
    raw = resp.choices[0].message.content or ""
    data = _parse_llm_json_response(raw, label="image VLM")

    probs = _normalize_probs_for_category(data.get("probs", {}), "Image")
    data["probs"] = probs
    return data


def llm_classify_audio_subcategories_text(
    text: str,
    *,
    base_url: str,
    api_key: str,
    model: str,
    max_chars: int = 12000,
    temperature: float = 0.2,
    timeout: float = 60.0,
) -> SubcategoryLlmResult:
    client = OpenAI(base_url=base_url, api_key=api_key, timeout=timeout)

    if len(text) > max_chars:
        head_len = int(max_chars * 0.75)
        tail_len = int(max_chars * 0.25)
        text = text[:head_len] + "\n\n[...TRUNCATED...]\n\n" + text[-tail_len:]

    schema = build_audio_schema()
    messages = [
        {"role": "system", "content": AUDIO_SYSTEM_PROMPT},
        {"role": "user", "content": schema + "\n\nAUDIO TRANSCRIPT:\n" + text},
    ]

    resp = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
    )

    raw = resp.choices[0].message.content or ""
    data = _parse_llm_json_response(raw, label="audio LLM")

    subcat_key = data.get("subcategory", "")
    if subcat_key not in AUDIO_UNIFIED_KEYS:
        probs = data.get("probs", {})
        subcat_key = max(probs.items(), key=lambda x: x[1])[0] if probs else AUDIO_UNIFIED_KEYS[0]

    subtype = load_unified_subtypes()[subcat_key]
    probs = normalize_audio_probs(data.get("probs", {}))

    return SubcategoryLlmResult(
        subcategory_key=subcat_key,
        subcategory_name=subtype.name,
        parent_type="unified",
        confidence=float(data.get("confidence", probs.get(subcat_key, 0))),
        rationale=str(data.get("rationale", "")).strip(),
        probs=probs,
        raw_json=data,
    )


def llm_classify_video_subcategories_text(
    text: str,
    *,
    base_url: str,
    api_key: str,
    model: str,
    max_chars: int = 12000,
    temperature: float = 0.2,
    timeout: float = 60.0,
) -> SubcategoryLlmResult:
    client = OpenAI(base_url=base_url, api_key=api_key, timeout=timeout)

    if len(text) > max_chars:
        head_len = int(max_chars * 0.75)
        tail_len = int(max_chars * 0.25)
        text = text[:head_len] + "\n\n[...TRUNCATED...]\n\n" + text[-tail_len:]

    schema = build_video_schema()
    messages = [
        {"role": "system", "content": VIDEO_SYSTEM_PROMPT},
        {"role": "user", "content": schema + "\n\nVIDEO TRANSCRIPT:\n" + text},
    ]

    resp = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
    )

    raw = resp.choices[0].message.content or ""
    data = _parse_llm_json_response(raw, label="video text LLM")

    subcat_key = data.get("subcategory", "")
    if subcat_key not in VIDEO_UNIFIED_KEYS:
        probs = data.get("probs", {})
        subcat_key = max(probs.items(), key=lambda x: x[1])[0] if probs else VIDEO_UNIFIED_KEYS[0]

    subtype = load_unified_subtypes()[subcat_key]
    probs = normalize_video_probs(data.get("probs", {}))

    return SubcategoryLlmResult(
        subcategory_key=subcat_key,
        subcategory_name=subtype.name,
        parent_type="unified",
        confidence=float(data.get("confidence", probs.get(subcat_key, 0))),
        rationale=str(data.get("rationale", "")).strip(),
        probs=probs,
        raw_json=data,
    )


def llm_classify_video_with_vision(
    frame_paths: List[str],
    transcript_text: str,
    *,
    base_url: str,
    api_key: str,
    model: str,
    temperature: float = 0.2,
    timeout: float = 120.0,
) -> Dict[str, Any]:
    client = OpenAI(base_url=base_url, api_key=api_key, timeout=timeout)
    content: List[Dict[str, Any]] = [
        {"type": "text", "text": VIDEO_SYSTEM_PROMPT + "\n\n" + build_video_schema() + "\n\nTRANSCRIPT PREVIEW:\n" + (transcript_text[:6000] if transcript_text else "[No transcript available]")},
    ]

    for idx, frame_path in enumerate(frame_paths, start=1):
        img_path = Path(frame_path)
        img_base64 = base64.b64encode(img_path.read_bytes()).decode("utf-8")
        content.append({"type": "text", "text": f"\n[Sampled video frame {idx}]\n"})
        content.append(
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/png;base64,{img_base64}",
                    "detail": "high",
                },
            }
        )

    messages = [{"role": "user", "content": content}]
    resp = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=1600,
    )

    raw = resp.choices[0].message.content or ""
    data = _parse_llm_json_response(raw, label="video VLM")

    probs = normalize_video_probs(data.get("probs", {}))
    data["probs"] = probs
    data["sampled_frame_count"] = len(frame_paths)
    return data


def llm_classify_subcategories_vision_batch(
    pdf_path: str,
    page_numbers: List[int],
    *,
    base_url: str,
    api_key: str,
    model: str,
    temperature: float = 0.2,
    timeout: float = 120.0,
) -> SubcategoryLlmResult:
    """
    Classify specific pages of a PDF using vision-language model.
    
    Args:
        pdf_path: Path to PDF file
        page_numbers: List of page numbers to analyze (1-indexed)
        base_url: VLM endpoint
        api_key: API key
        model: VLM model name
        temperature: Sampling temperature
        timeout: Request timeout
    
    Returns:
        SubcategoryLlmResult with classification
    """
    try:
        from pdf2image import convert_from_path
    except ImportError:
        raise ImportError("pdf2image required for vision classification. Install: pip install pdf2image")
    
    # Convert specific pages to images
    images = convert_from_path(pdf_path, first_page=min(page_numbers), last_page=max(page_numbers))
    
    # Map images to page numbers
    page_images = {}
    for i, page_num in enumerate(range(min(page_numbers), max(page_numbers) + 1)):
        if page_num in page_numbers and i < len(images):
            page_images[page_num] = images[i]
    
    if not page_images:
        raise ValueError("Could not convert PDF pages to images")
    
    client = OpenAI(base_url=base_url, api_key=api_key, timeout=timeout)
    
    # Build message with images
    content = [
        {"type": "text", "text": SYSTEM_PROMPT + "\n\n" + build_schema()},
    ]
    
    # Add images in order with page labels
    for page_num in sorted(page_images.keys()):
        img = page_images[page_num]
        import io
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        img_base64 = base64.b64encode(buffer.getvalue()).decode("utf-8")
        
        content.append({
            "type": "text",
            "text": f"\n[Page {page_num}]\n"
        })
        content.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:image/png;base64,{img_base64}",
                "detail": "high"
            }
        })
    
    messages = [
        {"role": "user", "content": content}
    ]
    
    resp = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=2000,
    )
    
    raw = resp.choices[0].message.content or ""
    
    # Parse JSON
    data = _parse_llm_json_response(raw, label="document VLM")
    
    # Extract results
    subcat_key = data.get("subcategory", "")
    if subcat_key not in DOCUMENT_UNIFIED_KEYS:
        probs = data.get("probs", {})
        subcat_key = max(probs.items(), key=lambda x: x[1])[0] if probs else DOCUMENT_UNIFIED_KEYS[0]
    
    subcat_def = load_unified_subtypes()[subcat_key]
    probs = normalize_subcategory_probs(data.get("probs", {}))
    
    return SubcategoryLlmResult(
        subcategory_key=subcat_key,
        subcategory_name=subcat_def.name,
        parent_type="unified",
        confidence=float(data.get("confidence", probs.get(subcat_key, 0))),
        rationale=str(data.get("rationale", "")).strip(),
        probs=probs,
        raw_json={**data, "vision_model": True, "pages_analyzed": page_numbers},
    )


def _sample_vision_pages(total_pages: int, max_total_pages: int) -> List[int]:
    """Deterministically sample representative pages from the document."""
    pages_to_process = min(total_pages, max_total_pages)
    if pages_to_process <= 3:
        return list(range(1, pages_to_process + 1))

    if pages_to_process <= 6:
        return sorted(set([1, 2, pages_to_process // 2 or 1, pages_to_process - 1, pages_to_process]))

    sample_size = min(8, pages_to_process)
    if sample_size <= 1:
        return [1]

    positions = [0.0, 0.12, 0.28, 0.5, 0.72, 0.88, 1.0]
    if sample_size < len(positions):
        positions = positions[:sample_size]
        positions[-1] = 1.0

    sampled_pages = []
    for pos in positions:
        idx = round((pages_to_process - 1) * pos)
        sampled_pages.append(idx + 1)

    return sorted(set(max(1, min(pages_to_process, p)) for p in sampled_pages))


def llm_classify_subcategories_vision_sampled(
    pdf_path: str,
    *,
    base_url: str,
    api_key: str,
    model: str,
    max_total_pages: int = 8,
    temperature: float = 0.2,
) -> SubcategoryLlmResult:
    """
    Classify PDF using vision model on deterministic sampled pages.
    
    Args:
        pdf_path: Path to PDF file
        base_url: VLM endpoint
        api_key: API key
        model: VLM model name
        max_total_pages: Maximum sampled pages to process
        temperature: Sampling temperature
    
    Returns:
        SubcategoryLlmResult from sampled pages
    """
    from PyPDF2 import PdfReader
    
    reader = PdfReader(pdf_path)
    total_pages = len(reader.pages)
    page_numbers = _sample_vision_pages(total_pages, max_total_pages)
    result = llm_classify_subcategories_vision_batch(
        pdf_path,
        page_numbers,
        base_url=base_url,
        api_key=api_key,
        model=model,
        temperature=temperature,
    )
    result.raw_json = {
        **result.raw_json,
        "vision_sampling": "deterministic_stratified",
        "total_pages_in_document": total_pages,
        "sampled_page_count": len(page_numbers),
    }
    return result


# Alias for backward compatibility
llm_classify_subcategories_vision = llm_classify_subcategories_vision_sampled
