from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Tuple

from docint.rubrics.subcategory_scorer import FeatureEvidence, SubcategoryScore


BASE_DIR = Path(__file__).resolve().parents[2]
SUBCATEGORIES_DIR = BASE_DIR / "data_model" / "runtime" / "subcategories"
SIGNAL_SPECS_DIR = SUBCATEGORIES_DIR / "signal_specs"
V5_MODEL_PATH = SUBCATEGORIES_DIR / "subcategories_v5_full_model.json"
AUDIO_SIGNAL_SPEC_PATH = SIGNAL_SPECS_DIR / "audio_signal_spec.json"
DOCUMENT_SIGNAL_SPEC_PATH = SIGNAL_SPECS_DIR / "document_signal_spec.json"
DATASET_SIGNAL_SPEC_PATH = SIGNAL_SPECS_DIR / "dataset_signal_spec.json"
IMAGE_SIGNAL_SPEC_PATH = SIGNAL_SPECS_DIR / "image_signal_spec.json"
SOFTWARE_SIGNAL_SPEC_PATH = SIGNAL_SPECS_DIR / "software_signal_spec.json"
VIDEO_SIGNAL_SPEC_PATH = SIGNAL_SPECS_DIR / "video_signal_spec.json"


@dataclass(frozen=True)
class UnifiedSubtypeDefinition:
    key: str
    name: str
    definition: str
    scope_note: str
    user_label: str
    detailed_features: Tuple[str, ...]
    mapped_from_legacy: Tuple[str, ...]
    applicability_hints: Tuple[str, ...]


LEGACY_TO_UNIFIED: Dict[str, str] = {
    "journal_article": "technical_and_research_content",
    "Journal article": "technical_and_research_content",
    "article_in_conference_proceedings": "technical_and_research_content",
    "Article in conference proceedings": "technical_and_research_content",
    "chapter_in_edited_volume": "technical_and_research_content",
    "Chapter in edited volume": "technical_and_research_content",
    "book": "technical_and_research_content",
    "Book": "technical_and_research_content",
    "thesis": "technical_and_research_content",
    "Thesis": "technical_and_research_content",
    "technical_report": "technical_and_research_content",
    "Technical Report": "technical_and_research_content",
    "tutorial": "how_to_guides",
    "Tutorial": "how_to_guides",
    "guide_manual": "how_to_guides",
    "Guide/Manual": "how_to_guides",
    "presentation": "talks_and_lectures",
    "Presentation": "talks_and_lectures",
    "news_communication": "explainers",
    "News & Communication": "explainers",
    "informational_booklet": "explainers",
    "Informational Booklet": "explainers",
    "How-To / Instructional Documents": "how_to_guides",
    "Explanatory Documents": "explainers",
    "Technical & Scientific Documents": "technical_and_research_content",
    "Case Study / Practice Documents": "case_studies",
    "Project Reports": "technical_and_research_content",
    "Policy & Regulatory Documents": "technical_and_research_content",
    "Summaries & Factsheets": "explainers",
    "Templates & Reusable Documents": "templates",
    "Templates & Forms": "templates",
    "Presentation / Slide Documents": "talks_and_lectures",
    "educational_training_media": "explainers",
    "Educational/Training Media": "explainers",
    "recorded_session": "talks_and_lectures",
    "Recorded Session": "talks_and_lectures",
    "interview": "interviews",
    "Interview": "interviews",
    "qa_session": "q_and_a_sessions",
    "Q&A Session": "q_and_a_sessions",
    "audio_program": "talks_and_lectures",
    "Audio Program": "talks_and_lectures",
    "demonstration_field_recording": "field_demonstrations",
    "Demonstration/Field Recording": "field_demonstrations",
    "recorded_presentation_webinar": "talks_and_lectures",
    "Recorded presentation/webinar": "talks_and_lectures",
    "data_visualization": "charts_and_graphs",
    "Data Visualization": "charts_and_graphs",
    "figure_image": "photos",
    "Figure/Image": "photos",
    "map": "maps",
    "Map": "maps",
    "Chart/graph": "charts_and_graphs",
    "Infographic": "infographics",
    "Diagram/schematic": "diagrams",
    "Field/observational photograph": "field_demonstrations",
    "Diagnostic photograph": "diagnostic_images",
    "Equipment/infrastructure photograph": "photos",
    "Aerial/remote-sensing image": "maps",
    "geospatial_data": "maps",
    "Geospatial Data": "maps",
    "video_data": "datasets",
    "Video Data": "datasets",
    "audio_data": "datasets",
    "Audio Data": "datasets",
    "image_data": "datasets",
    "Image Data": "datasets",
    "text_data": "datasets",
    "Text Data": "datasets",
    "graph_network_data": "datasets",
    "Graph/Network Data": "datasets",
    "agricultural_production_data": "output_data",
    "Agricultural Production Data": "output_data",
    "environmental_temporal_data": "monitoring_data",
    "Environmental & Temporal Data": "monitoring_data",
    "Entity-focused dataset (Farm/Field Data)": "datasets",
    "Event/operations dataset (Activity Records)": "datasets",
    "Input-use dataset (Input Use Data)": "input_data",
    "Output/production dataset (Production Data)": "output_data",
    "Time-series dataset (Weather & Time Data)": "monitoring_data",
    "Geospatial dataset (Map-based or Geospatial Data)": "maps",
    "Analytical/derived dataset (Analysis & Insights Data)": "technical_and_research_content",
    "Survey/social dataset (Farmer & Survey Data)": "survey_data",
    "Machine/equipment dataset (Machinery & Sensor Data)": "monitoring_data",
    "Farm Management System (FMIS)": "software_tools",
    "Monitoring & Recording Tools": "software_tools",
    "Field Data Collection Apps": "software_tools",
    "Mapping & GIS Tools": "maps",
    "Data Analysis & Dashboard Tools": "software_tools",
    "Simulation & Forecasting Tools": "simulations",
    "Automation & Control Systems": "software_tools",
    "Training & Learning Applications": "how_to_guides",
    "Software Tools": "software_tools",
}


def _resolve_model_path() -> Path:
    # Runtime is v5-only. The legacy v4 / v4_improved fallback chain was retired
    # once the v5 full model became the committed source of truth.
    if not V5_MODEL_PATH.exists():
        raise FileNotFoundError(f"v5 subtype model is missing: {V5_MODEL_PATH}")
    return V5_MODEL_PATH


def _split_indicator_text(text: str) -> List[str]:
    if not text:
        return []
    return [
        item.strip(" .:-")
        for item in re.split(r"[;,]+", text)
        if item.strip(" .:-")
    ]


def _normalize_runtime_category(category: str) -> str:
    if category == "Software Application":
        return "Software"
    return category


def _strength_rank(strength: str) -> int:
    order = {"Strong": 3, "Partial": 2, "Weak/Partial": 1}
    return order.get(strength, 0)


def _strength_to_relation(strength: str, *, is_first: bool) -> str:
    if strength == "Strong" and is_first:
        return "primary"
    return "related"


@lru_cache(maxsize=1)
def load_audio_signal_spec() -> Dict[str, Any]:
    if not AUDIO_SIGNAL_SPEC_PATH.exists():
        return {}
    return json.loads(AUDIO_SIGNAL_SPEC_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def load_document_signal_spec() -> Dict[str, Any]:
    if not DOCUMENT_SIGNAL_SPEC_PATH.exists():
        return {}
    return json.loads(DOCUMENT_SIGNAL_SPEC_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def load_image_signal_spec() -> Dict[str, Any]:
    if not IMAGE_SIGNAL_SPEC_PATH.exists():
        return {}
    return json.loads(IMAGE_SIGNAL_SPEC_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def load_dataset_signal_spec() -> Dict[str, Any]:
    if not DATASET_SIGNAL_SPEC_PATH.exists():
        return {}
    return json.loads(DATASET_SIGNAL_SPEC_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def load_software_signal_spec() -> Dict[str, Any]:
    if not SOFTWARE_SIGNAL_SPEC_PATH.exists():
        return {}
    return json.loads(SOFTWARE_SIGNAL_SPEC_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def load_video_signal_spec() -> Dict[str, Any]:
    if not VIDEO_SIGNAL_SPEC_PATH.exists():
        return {}
    return json.loads(VIDEO_SIGNAL_SPEC_PATH.read_text(encoding="utf-8"))


def _calibrate_v5_profile_mappings(runtime_category: str, profile: Dict[str, Any]) -> List[Dict[str, Any]]:
    mappings = list(profile.get("unified_mappings", []))
    profile_id = str(profile.get("id", "")).strip()

    if runtime_category == "Dataset":
        overrides = load_dataset_signal_spec().get("profile_mapping_overrides", {})
        return overrides.get(profile_id, mappings)
    if runtime_category == "Software":
        overrides = load_software_signal_spec().get("profile_mapping_overrides", {})
        return overrides.get(profile_id, mappings)
    return mappings


def _build_feature_groups_from_v5_profile(profile: Dict[str, Any]) -> List[Dict[str, Any]]:
    groups: List[Dict[str, Any]] = []
    dominant_rule = str(profile.get("dominant_rule", ""))
    dominant_feature = ""
    match = re.search(r"Must:\s*([a-zA-Z0-9_]+)", dominant_rule)
    if match:
        dominant_feature = match.group(1)

    for item in profile.get("feature_catalog_matches", []):
        feature_id = str(item.get("feature_id", "")).strip()
        if not feature_id:
            continue
        positive_indicators: List[str] = []
        positive_indicators.extend(_split_indicator_text(item.get("definition", "")))
        positive_indicators.extend(_termify(feature_id))
        positive_indicators.extend(_termify(profile.get("name", "")))
        examples = profile.get("examples", "")
        if isinstance(examples, str):
            positive_indicators.extend(_termify(examples))
        weight = 1.0 if feature_id == dominant_feature else 0.78
        groups.append(
            {
                "feature_id": feature_id,
                "weight": weight,
                "definition": item.get("definition", ""),
                "measurement": dominant_rule if feature_id == dominant_feature and dominant_rule else f"Detect evidence for {feature_id}",
                "positive_indicators": list(dict.fromkeys([v for v in positive_indicators if v]))[:12],
                "negative_indicators": [],
            }
        )

    if not groups and profile.get("key_features_text"):
        indicators = _split_indicator_text(str(profile.get("key_features_text", "")))
        if indicators:
            groups.append(
                {
                    "feature_id": f"{profile.get('id', 'profile')}_key_features",
                    "weight": 0.82,
                    "definition": str(profile.get("key_features_text", "")),
                    "measurement": dominant_rule or "Detect document key-feature evidence",
                    "positive_indicators": indicators[:12],
                    "negative_indicators": [],
                }
            )
    return groups


def _runtime_payload_from_v5(payload: Dict[str, Any]) -> Dict[str, Any]:
    unified_subcategories = []
    categories: Dict[str, Dict[str, Any]] = {}

    for item in payload.get("unified_subcategories", []):
        unified_subcategories.append(
            {
                "id": item["id"],
                "name": item["name"],
                "definition": item.get("definition", ""),
                "scope_note": item.get("scope_note", ""),
                "user_label": item.get("user_label", ""),
                "detailed_features": item.get("feature_basis", []),
                "mapped_from_legacy": [],
                "applicability_hints": [
                    _normalize_runtime_category(value)
                    for value in item.get("applicable_categories", [])
                ],
                "imports_from_profiles": [
                    {
                        "source_profile_id": source.get("profile_id"),
                        "source_profile_name": source.get("profile_name"),
                        "source_modality": source.get("modality"),
                        "relation": "primary" if source.get("strength") == "Strong" else "related",
                        "why": source.get("rationale", ""),
                    }
                    for source in item.get("source_profiles", [])
                ],
            }
        )

    for category_name, category_payload in payload.get("source_modalities", {}).items():
        runtime_category = _normalize_runtime_category(category_name)
        profiles: List[Dict[str, Any]] = []
        for profile in category_payload.get("profiles", []):
            mappings = _calibrate_v5_profile_mappings(runtime_category, profile)
            mappings.sort(key=lambda row: _strength_rank(str(row.get("strength", ""))), reverse=True)
            imports_to_unified = [
                {
                    "unified_subcategory_id": mapping.get("unified_subcategory_id"),
                    "relation": _strength_to_relation(str(mapping.get("strength", "")), is_first=index == 0),
                    "why": f"{mapping.get('unified_subcategory_name', '')} via {mapping.get('strength', '')} mapping from v5 exhaustive model.",
                    "strength": mapping.get("strength"),
                }
                for index, mapping in enumerate(mappings)
            ]
            profiles.append(
                {
                    "id": profile.get("id"),
                    "name": profile.get("name"),
                    "definition": profile.get("definition", ""),
                    "scope_note": profile.get("scope_note", ""),
                    "examples": profile.get("examples", ""),
                    "feature_groups": _build_feature_groups_from_v5_profile(profile),
                    "imports_to_unified": imports_to_unified,
                }
            )
        categories[runtime_category] = {"profiles": profiles}

    present_ids = {item["id"] for item in unified_subcategories}
    synthetic_dataset_unified = load_dataset_signal_spec().get("synthetic_unified_subcategories", [])
    for item in synthetic_dataset_unified:
        if item["id"] not in present_ids:
            unified_subcategories.append(item)

    return {
        "unified_subcategories": unified_subcategories,
        "categories": categories,
    }


def _termify(text: str) -> List[str]:
    if not text:
        return []
    cleaned = re.sub(r"[\"'`]", "", text.lower())
    cleaned = cleaned.replace("->", " ").replace("_", " ")
    parts = [part.strip(" .:-") for part in re.split(r"[;,/()]+|\s{2,}", cleaned) if part.strip()]
    stop_terms = {
        "content",
        "data",
        "details",
        "topic",
        "format",
        "formats",
        "system",
        "systems",
        "application",
        "applications",
        "tool",
        "tools",
        "structure",
        "structured",
        "design",
        "process",
        "processes",
        "real-world",
        "real world",
    }
    terms: List[str] = []
    for part in parts:
        tokens = [part]
        if " " in part or "-" in part:
            tokens.extend(re.split(r"[\s-]+", part))
        for token in tokens:
            token = token.strip(" .:-")
            if len(token) < 4:
                continue
            if token in stop_terms:
                continue
            terms.append(token)
    return list(dict.fromkeys(terms))


def _match_terms(text_lower: str, terms: List[str], *, per_hit_weight: float) -> tuple[float, List[str]]:
    hits: List[str] = []
    for term in terms:
        if len(term) < 4:
            continue
        if " " in term or "-" in term or "/" in term:
            if term in text_lower:
                hits.append(term)
            continue
        pattern = rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])"
        if re.search(pattern, text_lower):
            hits.append(term)
    return min(1.0, len(hits) * per_hit_weight), hits[:12]


def _extract_prefixed_values(text: str, prefixes: Tuple[str, ...]) -> List[str]:
    values: List[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        lower = line.lower()
        for prefix in prefixes:
            if lower.startswith(prefix):
                _, _, rest = line.partition(":")
                if rest:
                    values.extend([part.strip().lower() for part in rest.split("|") if part.strip()])
                break
    return list(dict.fromkeys(values))


def _extract_dataset_context(text: str, filename: str) -> Dict[str, Any]:
    columns = _extract_prefixed_values(text, ("columns",))
    row_values = _extract_prefixed_values(text, tuple(f"row {idx}" for idx in range(0, 31)))
    text_lower = f"{filename}\n{text}".lower()
    numeric_value_count = 0
    prose_like_value_count = 0
    total_value_count = 0
    for value in row_values[:200]:
        total_value_count += 1
        if re.fullmatch(r"\s*[-+]?\d+(?:[\.,]\d+)?%?\s*", value):
            numeric_value_count += 1
        if len(value.split()) >= 12 or len(value) >= 120:
            prose_like_value_count += 1
    return {
        "text_lower": text_lower,
        "columns": columns,
        "row_values": row_values[:120],
        "has_tabular_preview": bool(columns),
        "sheet_mentions": text_lower.count("sheet:"),
        "row_mentions": len(re.findall(r"(?m)^row\s+\d+:", text_lower)),
        "numeric_value_count": numeric_value_count,
        "prose_like_value_count": prose_like_value_count,
        "total_value_count": total_value_count,
    }


def _extract_document_context(text: str, filename: str) -> Dict[str, Any]:
    text_lower = f"{filename}\n{text}".lower()
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    bullet_lines = [line for line in lines if re.match(r"^([-*•]|\d+[\.\)])\s+", line)]
    numbered_step_lines = [line for line in lines if re.match(r"^\d+[\.\)]\s+", line)]
    heading_lines = [
        line for line in lines
        if len(line) <= 90 and not re.match(r"^([-*•]|\d+[\.\)])\s+", line) and (line == line.title() or line.isupper())
    ]
    colon_lines = [line for line in lines if ":" in line[:60]]
    citation_hits = re.findall(r"\[(?:\d{1,3}|[A-Za-z][A-Za-z0-9_-]{1,20})\]|\([12]\d{3}\)|doi:|et al\.", text_lower)
    placeholder_hits = re.findall(r"\[[^\]]{2,40}\]|<[^>]{2,40}>|_{3,}|\.{3,}", text)
    imperative_hits = re.findall(r"\b(use|apply|install|mix|add|remove|check|measure|record|select|enter|choose|download|upload|follow|prepare)\b", text_lower)
    policy_hits = re.findall(r"\b(policy|regulation|directive|compliance|governance|framework|standard|guideline|recommendation|stakeholder)\b", text_lower)
    project_hits = re.findall(r"\b(project|deliverable|milestone|work package|task|objective|reporting|consortium)\b", text_lower)
    narrative_hits = re.findall(r"\b(challenge|problem|solution|outcome|result|lesson|implementation|case)\b", text_lower)
    return {
        "text_lower": text_lower,
        "lines": lines,
        "word_count": len(re.findall(r"\b\w+\b", text)),
        "bullet_count": len(bullet_lines),
        "numbered_step_count": len(numbered_step_lines),
        "heading_count": len(heading_lines),
        "colon_line_count": len(colon_lines),
        "citation_count": len(citation_hits),
        "placeholder_count": len(placeholder_hits),
        "imperative_count": len(imperative_hits),
        "policy_term_count": len(policy_hits),
        "project_term_count": len(project_hits),
        "narrative_term_count": len(narrative_hits),
    }


def _extract_image_context(text: str, filename: str) -> Dict[str, Any]:
    text_lower = f"{filename}\n{text}".lower()
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    numeric_tokens = re.findall(r"\b\d+(?:\.\d+)?%?\b", text_lower)
    orientation_terms = re.findall(r"\b(north|south|east|west|latitude|longitude|lat|lon|scale|legend)\b", text_lower)
    axis_terms = re.findall(r"\b(x-axis|y-axis|axis|axes|legend|series|bar|line|scatter|plot)\b", text_lower)
    callout_terms = re.findall(r"\b(step \d+|did you know|key message|tip|fact|summary)\b", text_lower)
    component_terms = re.findall(r"\b(component|process|system|input|output|arrow|flow|structure)\b", text_lower)
    diagnostic_terms = re.findall(r"\b(symptom|lesion|disease|damage|defect|inspection|close-up)\b", text_lower)
    field_terms = re.findall(r"\b(field|crop|animal|farm|plot|soil|grazing|orchard|pasture)\b", text_lower)
    equipment_terms = re.findall(r"\b(machine|equipment|tractor|implement|irrigation|control unit|sensor|device)\b", text_lower)
    remote_terms = re.findall(r"\b(ndvi|satellite|drone|remote sensing|thermal|multispectral|aerial)\b", text_lower)
    return {
        "text_lower": text_lower,
        "line_count": len(lines),
        "numeric_count": len(numeric_tokens),
        "orientation_count": len(orientation_terms),
        "axis_count": len(axis_terms),
        "callout_count": len(callout_terms),
        "component_count": len(component_terms),
        "diagnostic_count": len(diagnostic_terms),
        "field_count": len(field_terms),
        "equipment_count": len(equipment_terms),
        "remote_count": len(remote_terms),
    }


def _extract_media_transcript_context(text: str, filename: str) -> Dict[str, Any]:
    text_lower = f"{filename}\n{text}".lower()
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    question_count = len(re.findall(r"\?", text))
    question_phrase_count = len(re.findall(r"\b(question|q&a|q:|ask|asked)\b", text_lower))
    answer_phrase_count = len(re.findall(r"\b(answer|a:|respond|response)\b", text_lower))
    speaker_marker_count = len(re.findall(r"(?m)^(speaker\s*\d+|host|moderator|guest|interviewer|interviewee|farmer|expert)\s*[:\-]", text_lower))
    first_person_count = len(re.findall(r"\b(i|we|my|our|me|us)\b", text_lower))
    testimonial_count = len(re.findall(r"\b(in my experience|we found|on our farm|i think|i learned|we implemented)\b", text_lower))
    step_terms_count = len(re.findall(r"\b(step|first|next|then|finally|before|after)\b", text_lower))
    field_terms_count = len(re.findall(r"\b(field|farm|plot|crop|livestock|soil|orchard|pasture|in the field)\b", text_lower))
    slide_terms_count = len(re.findall(r"\b(slide|slides|screen|webinar|presentation|next slide)\b", text_lower))
    panel_terms_count = len(re.findall(r"\b(panel|moderator|audience|question from the audience)\b", text_lower))
    simulation_terms_count = len(re.findall(r"\b(simulation|model|animation|forecast|scenario|prediction)\b", text_lower))
    tool_terms_count = len(re.findall(r"\b(tool|app|software|machine|tractor|interface|dashboard|button|click|menu)\b", text_lower))
    return {
        "text_lower": text_lower,
        "line_count": len(lines),
        "question_count": question_count,
        "question_phrase_count": question_phrase_count,
        "answer_phrase_count": answer_phrase_count,
        "speaker_marker_count": speaker_marker_count,
        "first_person_count": first_person_count,
        "testimonial_count": testimonial_count,
        "step_terms_count": step_terms_count,
        "field_terms_count": field_terms_count,
        "slide_terms_count": slide_terms_count,
        "panel_terms_count": panel_terms_count,
        "simulation_terms_count": simulation_terms_count,
        "tool_terms_count": tool_terms_count,
    }


def _dataset_signal_strength_multiplier(strength: str) -> float:
    normalized = str(strength or "").strip().lower()
    if normalized == "strong":
        return 1.0
    if normalized == "partial":
        return 0.88
    if normalized in {"weak", "weak/partial"}:
        return 0.72
    return 1.0


def _signal_strength_multiplier(strength: str) -> float:
    normalized = str(strength or "").strip().lower()
    if normalized == "strong":
        return 1.0
    if normalized == "partial":
        return 0.88
    if normalized in {"weak", "weak/partial"}:
        return 0.72
    return 1.0


def _score_document_signal(text: str, filename: str, feature_id: str) -> tuple[float, List[str]]:
    context = _extract_document_context(text, filename)
    text_lower = context["text_lower"]
    spec = load_document_signal_spec().get("feature_signals", {}).get(feature_id, {})
    terms = list(spec.get("text_terms", []))
    score, hits = _match_terms(text_lower, terms, per_hit_weight=float(spec.get("per_hit_weight", 0.12) or 0.12))

    threshold_key = str(spec.get("structural_threshold_key", "")).strip()
    threshold_min = int(spec.get("structural_threshold_min", 0) or 0)
    threshold_bonus = float(spec.get("structural_bonus", 0.0) or 0.0)
    if threshold_key and threshold_min and int(context.get(threshold_key, 0) or 0) >= threshold_min:
        score = min(1.0, score + threshold_bonus)
        hits = list(dict.fromkeys(hits + [threshold_key]))[:10]

    required_keys_any = list(spec.get("required_context_keys_any", []))
    required_bonus = float(spec.get("required_context_bonus", 0.0) or 0.0)
    if required_keys_any and any(int(context.get(key, 0) or 0) > 0 for key in required_keys_any):
        score = min(1.0, score + required_bonus)
        hits = list(dict.fromkeys(hits + required_keys_any[:2]))[:10]

    bonus_terms = list(spec.get("bonus_terms", []))
    bonus = float(spec.get("bonus", 0.0) or 0.0)
    if bonus_terms and any(term in text_lower for term in bonus_terms):
        score = min(1.0, score + bonus)

    paired_terms_any = list(spec.get("paired_terms_any", []))
    pair_bonus = float(spec.get("pair_bonus", 0.0) or 0.0)
    for group in paired_terms_any:
        pair_terms = [str(term).strip().lower() for term in group if str(term).strip()]
        if pair_terms and all(term in text_lower for term in pair_terms):
            score = min(1.0, score + pair_bonus)
            hits = list(dict.fromkeys(hits + pair_terms))[:10]
            break

    negative_terms = list(spec.get("negative_terms", []))
    negative_penalty_scale = float(spec.get("negative_penalty_scale", 0.4) or 0.4)
    if negative_terms:
        neg_score, _ = _match_terms(
            text_lower,
            negative_terms,
            per_hit_weight=float(spec.get("negative_per_hit_weight", 0.08) or 0.08),
        )
        if neg_score > 0.0:
            score = max(0.0, score - min(0.36, neg_score * negative_penalty_scale))

    score = min(1.0, score * _signal_strength_multiplier(str(spec.get("signal_strength", "Strong"))))
    return score, hits[:10]


def _score_image_signal(text: str, filename: str, feature_id: str) -> tuple[float, List[str]]:
    context = _extract_image_context(text, filename)
    text_lower = context["text_lower"]
    spec = load_image_signal_spec().get("feature_signals", {}).get(feature_id, {})
    terms = list(spec.get("text_terms", []))
    score, hits = _match_terms(text_lower, terms, per_hit_weight=float(spec.get("per_hit_weight", 0.12) or 0.12))

    threshold_key = str(spec.get("structural_threshold_key", "")).strip()
    threshold_min = int(spec.get("structural_threshold_min", 0) or 0)
    threshold_bonus = float(spec.get("structural_bonus", 0.0) or 0.0)
    if threshold_key and threshold_min and int(context.get(threshold_key, 0) or 0) >= threshold_min:
        score = min(1.0, score + threshold_bonus)
        hits = list(dict.fromkeys(hits + [threshold_key]))[:10]

    required_keys_any = list(spec.get("required_context_keys_any", []))
    required_bonus = float(spec.get("required_context_bonus", 0.0) or 0.0)
    if required_keys_any and any(int(context.get(key, 0) or 0) > 0 for key in required_keys_any):
        score = min(1.0, score + required_bonus)
        hits = list(dict.fromkeys(hits + required_keys_any[:2]))[:10]

    bonus_terms = list(spec.get("bonus_terms", []))
    bonus = float(spec.get("bonus", 0.0) or 0.0)
    if bonus_terms and any(term in text_lower for term in bonus_terms):
        score = min(1.0, score + bonus)

    paired_terms_any = list(spec.get("paired_terms_any", []))
    pair_bonus = float(spec.get("pair_bonus", 0.0) or 0.0)
    for group in paired_terms_any:
        pair_terms = [str(term).strip().lower() for term in group if str(term).strip()]
        if pair_terms and all(term in text_lower for term in pair_terms):
            score = min(1.0, score + pair_bonus)
            hits = list(dict.fromkeys(hits + pair_terms))[:10]
            break

    negative_terms = list(spec.get("negative_terms", []))
    negative_penalty_scale = float(spec.get("negative_penalty_scale", 0.4) or 0.4)
    if negative_terms:
        neg_score, _ = _match_terms(
            text_lower,
            negative_terms,
            per_hit_weight=float(spec.get("negative_per_hit_weight", 0.08) or 0.08),
        )
        if neg_score > 0.0:
            score = max(0.0, score - min(0.36, neg_score * negative_penalty_scale))

    score = min(1.0, score * _signal_strength_multiplier(str(spec.get("signal_strength", "Strong"))))
    return score, hits[:10]


def _score_transcript_signal(context: Dict[str, Any], spec: Dict[str, Any]) -> tuple[float, List[str]]:
    text_lower = context["text_lower"]
    terms = list(spec.get("text_terms", []))
    score, hits = _match_terms(text_lower, terms, per_hit_weight=float(spec.get("per_hit_weight", 0.12) or 0.12))

    threshold_key = str(spec.get("structural_threshold_key", "")).strip()
    threshold_min = int(spec.get("structural_threshold_min", 0) or 0)
    threshold_bonus = float(spec.get("structural_bonus", 0.0) or 0.0)
    if threshold_key and threshold_min and int(context.get(threshold_key, 0) or 0) >= threshold_min:
        score = min(1.0, score + threshold_bonus)
        hits = list(dict.fromkeys(hits + [threshold_key]))[:10]

    required_keys_any = list(spec.get("required_context_keys_any", []))
    required_bonus = float(spec.get("required_context_bonus", 0.0) or 0.0)
    if required_keys_any and any(int(context.get(key, 0) or 0) > 0 for key in required_keys_any):
        score = min(1.0, score + required_bonus)
        hits = list(dict.fromkeys(hits + required_keys_any[:2]))[:10]

    bonus_terms = list(spec.get("bonus_terms", []))
    bonus = float(spec.get("bonus", 0.0) or 0.0)
    if bonus_terms and any(term in text_lower for term in bonus_terms):
        score = min(1.0, score + bonus)

    paired_terms_any = list(spec.get("paired_terms_any", []))
    pair_bonus = float(spec.get("pair_bonus", 0.0) or 0.0)
    for group in paired_terms_any:
        pair_terms = [str(term).strip().lower() for term in group if str(term).strip()]
        if pair_terms and all(term in text_lower for term in pair_terms):
            score = min(1.0, score + pair_bonus)
            hits = list(dict.fromkeys(hits + pair_terms))[:10]
            break

    negative_terms = list(spec.get("negative_terms", []))
    negative_penalty_scale = float(spec.get("negative_penalty_scale", 0.4) or 0.4)
    if negative_terms:
        neg_score, _ = _match_terms(
            text_lower,
            negative_terms,
            per_hit_weight=float(spec.get("negative_per_hit_weight", 0.08) or 0.08),
        )
        if neg_score > 0.0:
            score = max(0.0, score - min(0.36, neg_score * negative_penalty_scale))

    score = min(1.0, score * _signal_strength_multiplier(str(spec.get("signal_strength", "Strong"))))
    return score, hits[:10]


def _score_audio_signal(text: str, filename: str, feature_id: str) -> tuple[float, List[str]]:
    context = _extract_media_transcript_context(text, filename)
    spec = load_audio_signal_spec().get("feature_signals", {}).get(feature_id, {})
    return _score_transcript_signal(context, spec)


def _score_video_signal(text: str, filename: str, feature_id: str) -> tuple[float, List[str]]:
    context = _extract_media_transcript_context(text, filename)
    spec = load_video_signal_spec().get("feature_signals", {}).get(feature_id, {})
    return _score_transcript_signal(context, spec)


def _score_dataset_signal(context: Dict[str, Any], feature_id: str) -> tuple[float, List[str]]:
    text_lower = context["text_lower"]
    columns = context["columns"]
    row_values = context["row_values"]
    header_space = " ".join(columns)
    row_space = " ".join(row_values)

    def _hits(terms: List[str], *, in_columns_weight: float = 0.26, in_text_weight: float = 0.14) -> tuple[float, List[str]]:
        hits: List[str] = []
        score = 0.0
        for term in terms:
            matched = False
            if any(term == col or term in col for col in columns):
                hits.append(term)
                score += in_columns_weight
                matched = True
            elif term in header_space or term in row_space:
                hits.append(term)
                score += in_text_weight
                matched = True
            elif " " in term and term in text_lower:
                hits.append(term)
                score += in_text_weight
                matched = True
            elif re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", text_lower):
                hits.append(term)
                score += in_text_weight
                matched = True
            if matched and len(hits) >= 10:
                break
        return min(1.0, score), hits

    spec = load_dataset_signal_spec().get("feature_signals", {}).get(feature_id, {})
    terms = list(spec.get("column_terms", []))
    text_terms = list(spec.get("text_terms", terms))
    column_weight = float(spec.get("column_hit_weight", 0.26))
    text_weight = float(spec.get("text_hit_weight", 0.14))
    score, hits = _hits(terms, in_columns_weight=column_weight, in_text_weight=text_weight)
    extra_score, extra_hits = _hits(text_terms, in_columns_weight=0.0, in_text_weight=text_weight)
    score = max(score, extra_score)
    hits = list(dict.fromkeys(hits + extra_hits))[:10]

    row_count_min = int(spec.get("row_count_min", 0) or 0)
    row_count_bonus_terms = list(spec.get("row_count_bonus_terms", []))
    row_count_bonus = float(spec.get("row_count_bonus", 0.0) or 0.0)
    if row_count_min and context["row_mentions"] >= row_count_min:
        if not row_count_bonus_terms or any(term in text_lower for term in row_count_bonus_terms):
            score = min(1.0, score + row_count_bonus)

    required_columns_any = list(spec.get("required_columns_any", []))
    column_bonus = float(spec.get("bonus", spec.get("row_count_bonus", 0.0)) or 0.0)
    if required_columns_any and any(term in columns for term in required_columns_any):
        score = min(1.0, score + column_bonus)

    bonus_terms = list(spec.get("bonus_terms", []))
    bonus = float(spec.get("bonus", 0.0) or 0.0)
    if bonus_terms and any(term in text_lower for term in bonus_terms):
        score = min(1.0, score + bonus)

    paired_terms_any = list(spec.get("paired_terms_any", []))
    pair_bonus = float(spec.get("pair_bonus", 0.0) or 0.0)
    for group in paired_terms_any:
        terms = [str(term).strip().lower() for term in group if str(term).strip()]
        if terms and all(
            any(term == col or term in col for col in columns) or term in header_space or term in row_space or term in text_lower
            for term in terms
        ):
            score = min(1.0, score + pair_bonus)
            hits = list(dict.fromkeys(hits + terms))[:10]
            break

    negative_terms = list(spec.get("negative_terms", []))
    negative_scale = float(spec.get("negative_penalty_scale", 0.55) or 0.55)
    if negative_terms:
        neg_score, _ = _hits(
            negative_terms,
            in_columns_weight=float(spec.get("negative_column_hit_weight", 0.16) or 0.16),
            in_text_weight=float(spec.get("negative_text_hit_weight", 0.10) or 0.10),
        )
        if neg_score > 0.0:
            score = max(0.0, score - min(0.4, neg_score * negative_scale))

    if context["has_tabular_preview"] and spec:
        score = min(1.0, score + float(spec.get("tabular_bonus", 0.08) or 0.0))

    score = min(1.0, score * _signal_strength_multiplier(str(spec.get("signal_strength", "Strong"))))
    return score, hits[:10]


def _score_software_signal(text: str, filename: str, feature_id: str) -> tuple[float, List[str]]:
    text_lower = f"{filename}\n{text}".lower()
    spec = load_software_signal_spec().get("feature_signals", {}).get(feature_id, {})
    terms = list(spec.get("text_terms", []))
    score, hits = _match_terms(text_lower, terms, per_hit_weight=float(spec.get("per_hit_weight", 0.18) or 0.18))

    bonus_terms = list(spec.get("bonus_terms", []))
    bonus = float(spec.get("bonus", 0.0) or 0.0)
    if bonus_terms and any(term in text_lower for term in bonus_terms):
        score = min(1.0, score + bonus)

    paired_terms_any = list(spec.get("paired_terms_any", []))
    pair_bonus = float(spec.get("pair_bonus", 0.0) or 0.0)
    for group in paired_terms_any:
        pair_terms = [str(term).strip().lower() for term in group if str(term).strip()]
        if pair_terms and all(term in text_lower for term in pair_terms):
            score = min(1.0, score + pair_bonus)
            hits = list(dict.fromkeys(hits + pair_terms))[:10]
            break

    negative_terms = list(spec.get("negative_terms", []))
    negative_penalty_scale = float(spec.get("negative_penalty_scale", 0.5) or 0.5)
    if negative_terms:
        neg_score, _ = _match_terms(
            text_lower,
            negative_terms,
            per_hit_weight=float(spec.get("negative_per_hit_weight", 0.10) or 0.10),
        )
        if neg_score > 0.0:
            score = max(0.0, score - min(0.4, neg_score * negative_penalty_scale))

    score = min(1.0, score * _signal_strength_multiplier(str(spec.get("signal_strength", "Strong"))))
    return score, hits[:10]


def _dataset_extension(filename: str) -> str:
    suffix = Path(filename or "").suffix.lower().strip()
    return suffix if suffix.startswith(".") else ""


def _score_dataset_scope_confidence(text: str, filename: str) -> tuple[float, List[str]]:
    spec = load_dataset_signal_spec()
    format_spec = spec.get("file_format_baseline_signals", {})
    structural_spec = spec.get("structural_signals_universal", {})
    context = _extract_dataset_context(text, filename)
    suffix = _dataset_extension(filename)

    baseline_hits: List[str] = []
    baseline_bonus = 0.0
    for bucket_name, bucket in format_spec.items():
        if bucket_name.startswith("_") or not isinstance(bucket, dict):
            continue
        extensions = [str(item).lower() for item in bucket.get("extensions", [])]
        if suffix and suffix in extensions:
            baseline_bonus = max(baseline_bonus, float(bucket.get("dataset_confidence_bonus", 0.0) or 0.0))
            baseline_hits = [bucket_name, suffix]

    indicators = structural_spec.get("indicators", {})
    anti_indicators = structural_spec.get("anti_indicators", {})
    structural_bonus = 0.0
    structural_hits: List[str] = []

    min_columns = int(structural_spec.get("min_columns_for_dataset", 2) or 2)
    min_rows = int(structural_spec.get("min_rows_for_dataset", 2) or 2)
    has_tabular_shape = len(context["columns"]) >= min_columns and context["row_mentions"] >= min_rows
    if has_tabular_shape:
        structural_bonus += float(structural_spec.get("tabular_shape_bonus", 0.0) or 0.0)
        structural_hits.append("tabular_shape")

    if context["has_tabular_preview"] and "header_row_detected" in indicators:
        structural_bonus += float(indicators["header_row_detected"].get("bonus", 0.0) or 0.0)
        structural_hits.append("header_row_detected")

    if context["row_mentions"] >= 2 and "consistent_row_width" in indicators:
        structural_bonus += float(indicators["consistent_row_width"].get("bonus", 0.0) or 0.0)
        structural_hits.append("consistent_row_width")

    id_patterns = [str(item).lower() for item in indicators.get("id_column_present", {}).get("patterns_any", [])]
    if id_patterns and any(
        col == pattern or col.endswith(pattern) or pattern in col
        for col in context["columns"]
        for pattern in id_patterns
    ):
        structural_bonus += float(indicators["id_column_present"].get("bonus", 0.0) or 0.0)
        structural_hits.append("id_column_present")

    date_patterns = [str(item).lower() for item in indicators.get("date_column_present", {}).get("patterns_any", [])]
    if date_patterns and any(
        pattern in col
        for col in context["columns"]
        for pattern in date_patterns
    ):
        structural_bonus += float(indicators["date_column_present"].get("bonus", 0.0) or 0.0)
        structural_hits.append("date_column_present")

    total_value_count = max(1, int(context.get("total_value_count", 0) or 0))
    numeric_ratio = float(context.get("numeric_value_count", 0) or 0) / total_value_count
    if numeric_ratio >= 0.35 and "numeric_column_majority" in indicators:
        structural_bonus += float(indicators["numeric_column_majority"].get("bonus", 0.0) or 0.0)
        structural_hits.append("numeric_column_majority")

    penalty = 0.0
    prose_ratio = float(context.get("prose_like_value_count", 0) or 0) / total_value_count
    if prose_ratio >= 0.35 and "long_prose_columns" in anti_indicators:
        penalty += float(anti_indicators["long_prose_columns"].get("penalty", 0.0) or 0.0)
        structural_hits.append("long_prose_columns")
    if context["row_mentions"] <= 1 and "single_row_data" in anti_indicators:
        penalty += float(anti_indicators["single_row_data"].get("penalty", 0.0) or 0.0)
        structural_hits.append("single_row_data")

    raw_score = max(0.0, baseline_bonus + structural_bonus - penalty)
    runtime_bonus = min(0.18, raw_score * 0.45)
    return round(runtime_bonus, 4), list(dict.fromkeys(baseline_hits + structural_hits))[:8]


def _feature_specific_signal(text: str, filename: str, category: str, feature_id: str) -> tuple[float, List[str]]:
    runtime_category = _normalize_runtime_category(category)
    if runtime_category == "Audio":
        return _score_audio_signal(text, filename, feature_id)
    if runtime_category == "Document":
        return _score_document_signal(text, filename, feature_id)
    if runtime_category == "Image":
        return _score_image_signal(text, filename, feature_id)
    if runtime_category == "Dataset":
        return _score_dataset_signal(_extract_dataset_context(text, filename), feature_id)
    if runtime_category == "Software":
        return _score_software_signal(text, filename, feature_id)
    if runtime_category == "Video":
        return _score_video_signal(text, filename, feature_id)
    return 0.0, [] 


def _profile_name_terms(profile: Dict[str, Any]) -> List[str]:
    terms: List[str] = []
    for key in ("name", "definition", "scope_note"):
        terms.extend(_termify(str(profile.get(key, ""))))
    for item in profile.get("examples", []):
        terms.extend(_termify(str(item)))
    return list(dict.fromkeys(terms))


@lru_cache(maxsize=1)
def load_cross_modal_feature_model() -> Dict[str, Any]:
    payload = json.loads(_resolve_model_path().read_text(encoding="utf-8"))
    if payload.get("model_version") == "v5" and "source_modalities" in payload:
        return _runtime_payload_from_v5(payload)
    return payload


@lru_cache(maxsize=1)
def _load_profile_lookup() -> Dict[str, str]:
    payload = load_cross_modal_feature_model()
    lookup: Dict[str, str] = {}
    for category_payload in payload.get("categories", {}).values():
        for profile in category_payload.get("profiles", []):
            for link in profile.get("imports_to_unified", []):
                if link.get("relation") == "primary":
                    unified_id = link.get("unified_subcategory_id")
                    if unified_id:
                        lookup[profile.get("id", "")] = unified_id
                        lookup[profile.get("name", "")] = unified_id
    return lookup


@lru_cache(maxsize=1)
def load_unified_subtypes() -> Dict[str, UnifiedSubtypeDefinition]:
    payload = load_cross_modal_feature_model()
    result: Dict[str, UnifiedSubtypeDefinition] = {}
    for item in payload.get("unified_subcategories", []):
        result[item["id"]] = UnifiedSubtypeDefinition(
            key=item["id"],
            name=item["name"],
            definition=item["definition"],
            scope_note=item["scope_note"],
            user_label=item["user_label"],
            detailed_features=tuple(item.get("detailed_features", [])),
            mapped_from_legacy=tuple(item.get("mapped_from_legacy") or ()),
            applicability_hints=tuple(item.get("applicability_hints", [])),
        )
    return result


@lru_cache(maxsize=8)
def load_category_profiles(category: str) -> List[Dict[str, Any]]:
    payload = load_cross_modal_feature_model()
    category = _normalize_runtime_category(category)
    return list((payload.get("categories", {}).get(category) or {}).get("profiles", []))


@lru_cache(maxsize=8)
def allowed_unified_keys_for_category(category: str) -> Tuple[str, ...]:
    category = _normalize_runtime_category(category)
    defs = load_unified_subtypes()
    return tuple(
        key for key, subtype in defs.items()
        if not subtype.applicability_hints or category in subtype.applicability_hints
    )


@lru_cache(maxsize=1)
def load_unified_support_terms() -> Dict[str, Tuple[str, ...]]:
    payload = load_cross_modal_feature_model()
    support: Dict[str, List[str]] = {key: [] for key in load_unified_subtypes().keys()}
    for item in payload.get("unified_subcategories", []):
        subtype_id = item["id"]
        support[subtype_id].extend(_termify(item.get("name", "")))
        support[subtype_id].extend(_termify(item.get("user_label", "")))
        support[subtype_id].extend(_termify(item.get("definition", "")))
        support[subtype_id].extend(_termify(item.get("scope_note", "")))
        for feat in item.get("detailed_features", []):
            support[subtype_id].extend(_termify(str(feat)))
        for imported in item.get("imports_from_profiles", []):
            support[subtype_id].extend(_termify(str(imported.get("source_profile_name", ""))))
    for category_payload in payload.get("categories", {}).values():
        for profile in category_payload.get("profiles", []):
            for link in profile.get("imports_to_unified", []):
                unified_id = link.get("unified_subcategory_id")
                if unified_id not in support:
                    continue
                support[unified_id].extend(_profile_name_terms(profile))
                for feature_group in profile.get("feature_groups", []):
                    support[unified_id].extend(_termify(feature_group.get("definition", "")))
                    for indicator in feature_group.get("positive_indicators", []):
                        support[unified_id].extend(_termify(str(indicator)))
    return {key: tuple(dict.fromkeys(values)) for key, values in support.items()}


def _legacy_key_to_unified(key_or_name: str) -> str | None:
    if key_or_name in LEGACY_TO_UNIFIED:
        return LEGACY_TO_UNIFIED[key_or_name]
    return _load_profile_lookup().get(key_or_name)


def map_probs_to_unified(probs: Dict[str, float]) -> Dict[str, float]:
    aggregated: Dict[str, float] = {}
    for key, prob in probs.items():
        unified = _legacy_key_to_unified(key) or key
        aggregated[unified] = aggregated.get(unified, 0.0) + float(prob)
    total = sum(max(v, 0.0) for v in aggregated.values())
    if total > 0:
        return {k: v / total for k, v in aggregated.items()}
    return aggregated


def _score_profile_feature_group(text: str, text_lower: str, feature_group: Dict[str, Any], *, category: str, filename: str) -> tuple[float, float, List[str], List[str]]:
    weight = float(feature_group.get("weight", 0.0))
    positive_terms = [str(item).lower() for item in feature_group.get("positive_indicators", [])]
    negative_terms = [str(item).lower() for item in feature_group.get("negative_indicators", [])]
    pos_score, pos_hits = _match_terms(text_lower, positive_terms, per_hit_weight=0.22)
    feature_id = str(feature_group.get("feature_id", "")).strip()
    feature_score, feature_hits = _feature_specific_signal(text, filename, category, feature_id)
    if feature_score > pos_score:
        pos_score = feature_score
        pos_hits = list(dict.fromkeys(feature_hits + pos_hits))[:12]
    else:
        pos_hits = list(dict.fromkeys(pos_hits + feature_hits))[:12]
    neg_score, neg_hits = _match_terms(text_lower, negative_terms, per_hit_weight=0.12)
    if weight >= 0:
        contribution = max(0.0, pos_score - (0.55 * neg_score)) * weight
        penalty = 0.0
    else:
        contribution = 0.0
        penalty = pos_score * abs(weight)
    return contribution, penalty, pos_hits, neg_hits


def score_intermediate_profiles(*, category: str, text: str, filename: str = "") -> List[Dict[str, Any]]:
    category = _normalize_runtime_category(category)
    profiles = load_category_profiles(category)
    text_lower = f"{filename}\n{text}".lower()
    results: List[Dict[str, Any]] = []

    for profile in profiles:
        lexical_terms = _profile_name_terms(profile)
        lexical_score, lexical_hits = _match_terms(text_lower, lexical_terms, per_hit_weight=0.10)

        positive_weight_total = 0.0
        contribution_total = 0.0
        penalty_total = 0.0
        matched_signals: List[str] = list(lexical_hits)
        conflicting_signals: List[str] = []

        for feature_group in profile.get("feature_groups", []):
            weight = float(feature_group.get("weight", 0.0))
            contribution, penalty, pos_hits, neg_hits = _score_profile_feature_group(
                text,
                text_lower,
                feature_group,
                category=category,
                filename=filename,
            )
            if weight > 0:
                positive_weight_total += weight
                contribution_total += contribution
            penalty_total += penalty
            matched_signals.extend(pos_hits[:2])
            conflicting_signals.extend(neg_hits[:2])

        normalized_feature_score = (contribution_total / positive_weight_total) if positive_weight_total > 0 else 0.0
        profile_score = max(0.0, min(1.0, (0.62 * normalized_feature_score) + (0.38 * lexical_score) - min(0.42, penalty_total)))
        results.append(
            {
                "profile_id": profile.get("id"),
                "profile_name": profile.get("name"),
                "score": round(profile_score, 4),
                "matched_signals": list(dict.fromkeys(matched_signals))[:10],
                "conflicting_signals": list(dict.fromkeys(conflicting_signals))[:8],
                "imports_to_unified": profile.get("imports_to_unified", []),
            }
        )

    results.sort(key=lambda item: item["score"], reverse=True)
    return results


def score_unified_subcategories(
    *,
    text: str,
    category: str,
    legacy_probs: Dict[str, float] | None = None,
    filename: str = "",
) -> List[SubcategoryScore]:
    runtime_category = _normalize_runtime_category(category)
    defs = load_unified_subtypes()
    support_terms = load_unified_support_terms()
    profile_scores = score_intermediate_profiles(category=runtime_category, text=text, filename=filename)
    dataset_scope_bonus = 0.0
    dataset_scope_hits: List[str] = []
    if runtime_category == "Dataset":
        dataset_scope_bonus, dataset_scope_hits = _score_dataset_scope_confidence(text, filename)
    profile_by_unified: Dict[str, List[Dict[str, Any]]] = {}
    for profile in profile_scores:
        for link in profile.get("imports_to_unified", []):
            unified_id = link.get("unified_subcategory_id")
            if not unified_id:
                continue
            scaled = profile["score"] * (1.0 if link.get("relation") == "primary" else 0.62)
            profile_by_unified.setdefault(unified_id, []).append(
                {
                    "profile_id": profile["profile_id"],
                    "profile_name": profile["profile_name"],
                    "score": round(scaled, 4),
                    "base_score": profile["score"],
                    "relation": link.get("relation"),
                    "why": link.get("why"),
                    "matched_signals": profile.get("matched_signals", []),
                }
            )

    text_lower = f"{filename}\n{text}".lower()
    unified_prior = map_probs_to_unified(legacy_probs or {})
    scores: List[SubcategoryScore] = []

    for key, subtype in defs.items():
        lexical_terms: List[str] = []
        lexical_terms.extend(_termify(subtype.name))
        lexical_terms.extend(_termify(subtype.user_label))
        lexical_terms.extend(_termify(subtype.definition))
        lexical_terms.extend(_termify(subtype.scope_note))
        lexical_terms.extend(_termify(" ".join(subtype.detailed_features)))
        lexical_terms.extend(list(support_terms.get(key, ())))
        lexical_terms = list(dict.fromkeys(lexical_terms))
        direct_score, direct_hits = _match_terms(text_lower, lexical_terms, per_hit_weight=0.09)

        supporting_profiles = sorted(profile_by_unified.get(key, []), key=lambda item: item["score"], reverse=True)
        profile_score = supporting_profiles[0]["score"] if supporting_profiles else 0.0
        profile_names = [item["profile_name"] for item in supporting_profiles[:3]]
        profile_hits: List[str] = []
        for item in supporting_profiles[:2]:
            profile_hits.extend(item.get("matched_signals", [])[:2])
        profile_hits = list(dict.fromkeys(profile_hits))[:6]

        prior_score = float(unified_prior.get(key, 0.0))
        applicable = not subtype.applicability_hints or runtime_category in subtype.applicability_hints
        agreement_bonus = 0.08 if ((direct_score >= 0.14 and profile_score >= 0.20) or (profile_score >= 0.20 and prior_score >= 0.18)) else 0.0

        fused_core = max(direct_score, profile_score)
        total_score = (0.48 * fused_core) + (0.22 * profile_score) + (0.16 * prior_score) + agreement_bonus
        if runtime_category == "Dataset" and (direct_score > 0.0 or profile_score > 0.0 or prior_score > 0.0):
            total_score += dataset_scope_bonus
        if not applicable:
            total_score = 0.0
        elif fused_core < 0.08 and prior_score < 0.10:
            total_score = 0.0
        elif fused_core == 0.0:
            total_score = min(total_score, 0.32)
        total_score = min(1.0, max(0.0, total_score))

        details = {
            "unified_lexical_signals": FeatureEvidence(
                feature_name="unified_lexical_signals",
                detected=bool(direct_hits),
                score=round(direct_score, 4),
                raw_value={"matches": direct_hits[:8]},
                excerpts=direct_hits[:3],
            ),
            "intermediate_profile_support": FeatureEvidence(
                feature_name="intermediate_profile_support",
                detected=profile_score > 0.0,
                score=round(profile_score, 4),
                raw_value={
                    "top_profiles": [
                        {
                            "profile_id": item["profile_id"],
                            "profile_name": item["profile_name"],
                            "score": item["score"],
                            "relation": item["relation"],
                        }
                        for item in supporting_profiles[:3]
                    ]
                },
                excerpts=profile_names[:2],
            ),
            "category_type_prior": FeatureEvidence(
                feature_name="category_type_prior",
                detected=prior_score > 0.0,
                score=round(prior_score, 4),
                raw_value={"mapped_prior_probability": round(prior_score, 4)},
                excerpts=[],
            ),
            "category_applicability": FeatureEvidence(
                feature_name="category_applicability",
                detected=applicable,
                score=1.0 if applicable else 0.0,
                raw_value={"category": runtime_category, "applicability_hints": list(subtype.applicability_hints)},
                excerpts=[],
            ),
        }
        if runtime_category == "Dataset":
            details["dataset_scope_confidence"] = FeatureEvidence(
                feature_name="dataset_scope_confidence",
                detected=dataset_scope_bonus > 0.0,
                score=round(dataset_scope_bonus, 4),
                raw_value={"matches": dataset_scope_hits},
                excerpts=dataset_scope_hits[:3],
            )
        features_found = [name for name, ev in details.items() if ev.detected]
        rationale_bits: List[str] = []
        if direct_hits:
            rationale_bits.append(f"semantic cues: {', '.join(direct_hits[:3])}")
        if profile_names:
            rationale_bits.append(f"profile support: {', '.join(profile_names[:2])}")
        if profile_hits:
            rationale_bits.append(f"profile signals: {', '.join(profile_hits[:3])}")
        if prior_score > 0.0:
            rationale_bits.append(f"legacy prior: {prior_score:.2f}")
        if agreement_bonus > 0.0:
            rationale_bits.append("signal/profile agreement")
        if applicable and (direct_score > 0.0 or profile_score > 0.0 or prior_score > 0.0):
            rationale_bits.append(f"applicable to {runtime_category}")
        if runtime_category == "Dataset" and dataset_scope_hits:
            rationale_bits.append(f"dataset format/shape support: {', '.join(dataset_scope_hits[:3])}")
        rationale = "; ".join(rationale_bits) if rationale_bits else "minimal unified subtype evidence"

        scores.append(
            SubcategoryScore(
                subcategory_id=key,
                subcategory_name=subtype.name,
                parent_type="unified",
                confidence=round(total_score, 4),
                evidence_score=round(total_score, 4),
                max_possible_evidence=1.0,
                features_found=features_found,
                feature_details=details,
                rationale=f"{subtype.name} selected via {rationale} (confidence: {total_score:.2f})",
            )
        )

    if runtime_category == "Dataset":
        by_id = {item.subcategory_id: item for item in scores}
        fallback_rule = load_dataset_signal_spec().get("broad_fallback_rule", {})
        broad = by_id.get(str(fallback_rule.get("broad_subcategory_id", "structured_domain_datasets")))
        specific_ids = tuple(fallback_rule.get("specific_subcategory_ids", []))
        specific_scores = [by_id[item_id].confidence for item_id in specific_ids if item_id in by_id]
        strongest_specific = max(specific_scores, default=0.0)
        min_specific_score = float(fallback_rule.get("min_specific_score", 0.45) or 0.45)
        margin = float(fallback_rule.get("margin_below_specific", 0.02) or 0.02)
        if broad and strongest_specific >= min_specific_score and broad.confidence >= strongest_specific:
            capped = round(max(0.0, strongest_specific - margin), 4)
            broad.confidence = capped
            broad.evidence_score = capped
            broad.rationale += " Broad structured dataset label was down-weighted because a more specific dataset subtype had strong evidence."

    if runtime_category == "Software":
        by_id = {item.subcategory_id: item for item in scores}
        fallback_rule = load_software_signal_spec().get("broad_fallback_rule", {})
        broad = by_id.get(str(fallback_rule.get("broad_subcategory_id", "software_tools_and_applications")))
        specific_ids = tuple(fallback_rule.get("specific_subcategory_ids", []))
        specific_scores = [by_id[item_id].confidence for item_id in specific_ids if item_id in by_id]
        strongest_specific = max(specific_scores, default=0.0)
        min_specific_score = float(fallback_rule.get("min_specific_score", 0.40) or 0.40)
        margin = float(fallback_rule.get("margin_below_specific", 0.02) or 0.02)
        if broad and strongest_specific >= min_specific_score and broad.confidence >= strongest_specific:
            capped = round(max(0.0, strongest_specific - margin), 4)
            broad.confidence = capped
            broad.evidence_score = capped
            broad.rationale += " Broad software tool label was down-weighted because a more specific software subtype had strong evidence."

    if runtime_category == "Image":
        by_id = {item.subcategory_id: item for item in scores}
        fallback_rule = load_image_signal_spec().get("broad_fallback_rule", {})
        broad = by_id.get(str(fallback_rule.get("broad_subcategory_id", "photographs_and_field_images")))
        specific_ids = tuple(fallback_rule.get("specific_subcategory_ids", []))
        specific_scores = [by_id[item_id].confidence for item_id in specific_ids if item_id in by_id]
        strongest_specific = max(specific_scores, default=0.0)
        min_specific_score = float(fallback_rule.get("min_specific_score", 0.40) or 0.40)
        margin = float(fallback_rule.get("margin_below_specific", 0.02) or 0.02)
        if broad and strongest_specific >= min_specific_score and broad.confidence >= strongest_specific:
            capped = round(max(0.0, strongest_specific - margin), 4)
            broad.confidence = capped
            broad.evidence_score = capped
            broad.rationale += " Broad photograph label was down-weighted because a more specific image subtype had strong evidence."

    scores.sort(key=lambda item: item.confidence, reverse=True)
    return scores
