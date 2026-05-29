from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

from docint.rubrics.subcategory_scorer import FeatureEvidence, SubcategoryScore


@dataclass(frozen=True)
class DatasetSubtypeDefinition:
    key: str
    subcategory_id: str
    name: str
    description: str
    positive_terms: Tuple[str, ...]
    column_terms: Tuple[str, ...]
    file_terms: Tuple[str, ...] = ()


DATASET_SUBTYPES: Dict[str, DatasetSubtypeDefinition] = {
    "geospatial_data": DatasetSubtypeDefinition(
        key="geospatial_data",
        subcategory_id="DATASET_GEOSPATIAL",
        name="Geospatial Data",
        description="Datasets with coordinate fields, geometry, or GIS-style location records",
        positive_terms=("latitude", "longitude", "geometry", "geojson", "polygon", "coordinate", "spatial"),
        column_terms=("lat", "lon", "lng", "x", "y", "geometry", "wkt", "epsg", "bbox", "location"),
    ),
    "video_data": DatasetSubtypeDefinition(
        key="video_data",
        subcategory_id="DATASET_VIDEO",
        name="Video Data",
        description="Datasets centered on videos, clips, frames, or motion media assets",
        positive_terms=("video", "frame", "clip", "fps", "timestamp"),
        column_terms=("video", "clip", "frame", "duration", "fps"),
        file_terms=(".mp4", ".avi", ".mov", ".mkv", ".webm"),
    ),
    "audio_data": DatasetSubtypeDefinition(
        key="audio_data",
        subcategory_id="DATASET_AUDIO",
        name="Audio Data",
        description="Datasets centered on audio files, recordings, or speech assets",
        positive_terms=("audio", "speech", "transcript", "recording", "sample rate"),
        column_terms=("audio", "speaker", "transcript", "duration", "sample_rate"),
        file_terms=(".mp3", ".wav", ".m4a", ".flac"),
    ),
    "image_data": DatasetSubtypeDefinition(
        key="image_data",
        subcategory_id="DATASET_IMAGE",
        name="Image Data",
        description="Datasets centered on images, imagery, or computer-vision style assets",
        positive_terms=("image", "imagery", "pixel", "bounding box", "segmentation", "annotation"),
        column_terms=("image", "img", "filename", "path", "bbox", "mask", "label"),
        file_terms=(".jpg", ".jpeg", ".png", ".tif", ".tiff"),
    ),
    "text_data": DatasetSubtypeDefinition(
        key="text_data",
        subcategory_id="DATASET_TEXT",
        name="Text Data",
        description="Datasets centered on textual records, corpora, or document-level content fields",
        positive_terms=("text", "document", "corpus", "sentence", "paragraph", "token"),
        column_terms=("text", "content", "document", "sentence", "paragraph", "abstract", "title", "description"),
    ),
    "graph_network_data": DatasetSubtypeDefinition(
        key="graph_network_data",
        subcategory_id="DATASET_GRAPH_NETWORK",
        name="Graph/Network Data",
        description="Datasets representing nodes, edges, links, or relational graph structure",
        positive_terms=("graph", "network", "adjacency", "node", "edge", "link"),
        column_terms=("source", "target", "node", "edge", "from", "to", "weight"),
    ),
    "agricultural_production_data": DatasetSubtypeDefinition(
        key="agricultural_production_data",
        subcategory_id="DATASET_AGRICULTURAL_PRODUCTION",
        name="Agricultural Production Data",
        description="Datasets about crop, input, yield, livestock, or farm production variables",
        positive_terms=("crop", "yield", "fertilizer", "fertiliser", "farm", "livestock", "harvest", "manure", "field"),
        column_terms=("crop", "yield", "farm", "field", "fertilizer", "fertiliser", "harvest", "livestock", "manure"),
    ),
    "environmental_temporal_data": DatasetSubtypeDefinition(
        key="environmental_temporal_data",
        subcategory_id="DATASET_ENV_TEMPORAL",
        name="Environmental & Temporal Data",
        description="Datasets with weather, climate, environmental, or time-indexed measurements",
        positive_terms=("weather", "climate", "temperature", "rainfall", "humidity", "timeseries", "time series", "date"),
        column_terms=("date", "time", "timestamp", "temperature", "rainfall", "humidity", "climate", "weather"),
    ),
}


def _extract_tabular_signals(text: str, lines: List[str]) -> Dict[str, Any]:
    text_lower = text.lower()
    header_text = lines[0].lower() if lines else ""
    row_lines = [ln.lower() for ln in lines[1:10]]

    column_candidates: List[str] = []
    for line in lines[:4]:
        if line.lower().startswith("columns:"):
            column_candidates.extend([part.strip().lower() for part in line.split(":", 1)[1].split("|") if part.strip()])
        elif line.lower().startswith("row 1:") or line.lower().startswith("row 0:"):
            column_candidates.extend([part.strip().lower() for part in line.split(":", 1)[1].split("|") if part.strip()])

    return {
        "text_lower": text_lower,
        "header_text": header_text,
        "row_lines": row_lines,
        "columns": column_candidates,
    }


def _score_dataset_subtype(defn: DatasetSubtypeDefinition, signals: Dict[str, Any]) -> Tuple[float, Dict[str, FeatureEvidence], List[str], str]:
    text_lower = signals["text_lower"]
    columns: List[str] = signals["columns"]
    score = 0.0
    features_found: List[str] = []
    details: Dict[str, FeatureEvidence] = {}

    term_hits = [term for term in defn.positive_terms if term in text_lower]
    term_score = min(1.0, len(term_hits) * 0.22)
    details["domain_terms"] = FeatureEvidence(
        feature_name="dataset_domain_terms",
        detected=bool(term_hits),
        score=term_score,
        raw_value={"matches": term_hits[:8]},
        excerpts=term_hits[:3],
    )
    if term_hits:
        score += 0.45 * term_score
        features_found.append("domain_terms")

    column_hits = [col for col in columns if any(term == col or term in col for term in defn.column_terms)]
    column_score = min(1.0, len(column_hits) * 0.35)
    details["schema_markers"] = FeatureEvidence(
        feature_name="dataset_schema_markers",
        detected=bool(column_hits),
        score=column_score,
        raw_value={"matches": column_hits[:8], "columns_seen": columns[:12]},
        excerpts=column_hits[:3],
    )
    if column_hits:
        score += 0.4 * column_score
        features_found.append("schema_markers")

    file_hits = [ext for ext in defn.file_terms if ext in text_lower]
    file_score = min(1.0, len(file_hits) * 0.4)
    details["file_markers"] = FeatureEvidence(
        feature_name="dataset_file_markers",
        detected=bool(file_hits),
        score=file_score,
        raw_value={"matches": file_hits[:8]},
        excerpts=file_hits[:3],
    )
    if file_hits:
        score += 0.15 * file_score
        features_found.append("file_markers")

    score = min(1.0, score)
    rationale_bits = []
    if term_hits:
        rationale_bits.append(f"domain terms: {', '.join(term_hits[:3])}")
    if column_hits:
        rationale_bits.append(f"schema markers: {', '.join(column_hits[:3])}")
    if file_hits:
        rationale_bits.append(f"file markers: {', '.join(file_hits[:3])}")
    rationale = "; ".join(rationale_bits) if rationale_bits else "minimal dataset-specific signals"
    return score, details, features_found, rationale


def score_dataset_subcategories(text: str, lines: List[str]) -> Tuple[SubcategoryScore, List[SubcategoryScore]]:
    signals = _extract_tabular_signals(text, lines)
    scores: List[SubcategoryScore] = []

    for defn in DATASET_SUBTYPES.values():
        score, details, features_found, rationale_detail = _score_dataset_subtype(defn, signals)
        scores.append(
            SubcategoryScore(
                subcategory_id=defn.subcategory_id,
                subcategory_name=defn.name,
                parent_type="dataset",
                confidence=round(score, 4),
                evidence_score=round(score, 4),
                max_possible_evidence=1.0,
                features_found=features_found,
                feature_details=details,
                rationale=f"{defn.name} detected via {rationale_detail} (confidence: {score:.2f})",
            )
        )

    scores.sort(key=lambda item: item.confidence, reverse=True)
    best = scores[0]
    return best, scores
