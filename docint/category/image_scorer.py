from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

from docint.rubrics.subcategory_scorer import FeatureEvidence, SubcategoryScore


@dataclass(frozen=True)
class ImageSubtypeDefinition:
    key: str
    subcategory_id: str
    name: str
    description: str
    positive_terms: Tuple[str, ...]


IMAGE_SUBTYPES: Dict[str, ImageSubtypeDefinition] = {
    "data_visualization": ImageSubtypeDefinition(
        key="data_visualization",
        subcategory_id="IMAGE_DATA_VIZ",
        name="Data Visualization",
        description="Visual artifact whose primary purpose is to communicate data, patterns, or summarized information",
        positive_terms=("chart", "graph", "axis", "legend", "bar", "line", "pie", "percent", "infographic", "value"),
    ),
    "figure_image": ImageSubtypeDefinition(
        key="figure_image",
        subcategory_id="IMAGE_FIGURE",
        name="Figure/Image",
        description="Standalone image or figure used to illustrate or explain content",
        positive_terms=("figure", "image", "photo", "photograph", "diagram", "illustration", "caption"),
    ),
    "map": ImageSubtypeDefinition(
        key="map",
        subcategory_id="IMAGE_MAP",
        name="Map",
        description="Map-based visual representation of a whole area or part of an area",
        positive_terms=("map", "region", "legend", "scale", "boundary", "latitude", "longitude", "location"),
    ),
}


def score_image_subcategories_from_text(text: str, lines: List[str]) -> Tuple[SubcategoryScore, List[SubcategoryScore]]:
    text_lower = text.lower()
    scores: List[SubcategoryScore] = []
    for subtype in IMAGE_SUBTYPES.values():
        hits = [term for term in subtype.positive_terms if term in text_lower]
        score = min(1.0, len(hits) * 0.2)
        details = {
            "ocr_terms": FeatureEvidence(
                feature_name="image_ocr_terms",
                detected=bool(hits),
                score=score,
                raw_value={"matches": hits[:8]},
                excerpts=hits[:3],
            )
        }
        scores.append(
            SubcategoryScore(
                subcategory_id=subtype.subcategory_id,
                subcategory_name=subtype.name,
                parent_type="image",
                confidence=round(score, 4),
                evidence_score=round(score, 4),
                max_possible_evidence=1.0,
                features_found=["ocr_terms"] if hits else [],
                feature_details=details,
                rationale=f"{subtype.name} detected via OCR/image text cues (confidence: {score:.2f})" if hits else f"{subtype.name} has minimal OCR cues (confidence: {score:.2f})",
            )
        )

    if all(score.confidence == 0 for score in scores):
        for score in scores:
            if score.subcategory_name == "Figure/Image":
                score.confidence = 0.45
                score.evidence_score = 0.45
                score.rationale = "Defaulted to Figure/Image due to minimal OCR cues (confidence: 0.45)"
                break

    scores.sort(key=lambda item: item.confidence, reverse=True)
    return scores[0], scores
