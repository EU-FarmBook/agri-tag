from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

from docint.rubrics.subcategory_scorer import FeatureEvidence, SubcategoryScore


@dataclass(frozen=True)
class VideoSubtypeDefinition:
    key: str
    subcategory_id: str
    name: str
    description: str
    positive_terms: Tuple[str, ...]
    filename_terms: Tuple[str, ...] = ()


VIDEO_SUBTYPES: Dict[str, VideoSubtypeDefinition] = {
    "tutorial": VideoSubtypeDefinition(
        key="tutorial",
        subcategory_id="VIDEO_TUTORIAL",
        name="Tutorial",
        description="Instructional video that teaches a task or workflow step by step",
        positive_terms=("step", "how to", "tutorial", "instructions", "demonstrate", "follow these", "procedure"),
        filename_terms=("tutorial", "howto", "how-to"),
    ),
    "educational_training_media": VideoSubtypeDefinition(
        key="educational_training_media",
        subcategory_id="VIDEO_EDUCATIONAL_TRAINING",
        name="Educational/Training Media",
        description="Lesson, lecture, explainer, or other training-oriented video",
        positive_terms=("learning objectives", "lesson", "module", "training", "course", "lecture", "learning"),
        filename_terms=("training", "lecture", "lesson", "course"),
    ),
    "recorded_session": VideoSubtypeDefinition(
        key="recorded_session",
        subcategory_id="VIDEO_RECORDED_SESSION",
        name="Recorded Session",
        description="Recorded webinar, meeting, workshop, panel, or session-style event video",
        positive_terms=("webinar", "session", "workshop", "agenda", "speaker", "today we will", "welcome everyone"),
        filename_terms=("webinar", "session", "workshop", "meeting"),
    ),
    "interview": VideoSubtypeDefinition(
        key="interview",
        subcategory_id="VIDEO_INTERVIEW",
        name="Interview",
        description="Interview-style video centered on host and guest exchange",
        positive_terms=("interview", "guest", "host", "thanks for joining us", "can you tell us", "tell me about"),
        filename_terms=("interview", "podcast"),
    ),
    "qa_session": VideoSubtypeDefinition(
        key="qa_session",
        subcategory_id="VIDEO_QA_SESSION",
        name="Q&A Session",
        description="Video whose primary structure is questions and answers",
        positive_terms=("question", "answer", "q&a", "questions", "asked", "let me answer"),
        filename_terms=("qa", "qanda", "q-and-a"),
    ),
    "demonstration_field_recording": VideoSubtypeDefinition(
        key="demonstration_field_recording",
        subcategory_id="VIDEO_DEMONSTRATION_FIELD",
        name="Demonstration/Field Recording",
        description="Demonstration, field recording, or practice-oriented observational video",
        positive_terms=("demonstration", "field", "onsite", "equipment", "showing", "in the field", "operation"),
        filename_terms=("demo", "field", "onsite", "recording"),
    ),
}


def score_video_subcategories(text: str, lines: List[str], filename: str = "") -> Tuple[SubcategoryScore, List[SubcategoryScore]]:
    text_lower = text.lower()
    filename_lower = filename.lower()
    scores: List[SubcategoryScore] = []

    for subtype in VIDEO_SUBTYPES.values():
        transcript_hits = [term for term in subtype.positive_terms if term in text_lower]
        transcript_score = min(1.0, len(transcript_hits) * 0.22)
        filename_hits = [term for term in subtype.filename_terms if term in filename_lower]
        filename_score = min(1.0, len(filename_hits) * 0.4)

        total_score = min(1.0, (0.8 * transcript_score) + (0.2 * filename_score))
        details = {
            "transcript_terms": FeatureEvidence(
                feature_name="video_transcript_terms",
                detected=bool(transcript_hits),
                score=transcript_score,
                raw_value={"matches": transcript_hits[:8]},
                excerpts=transcript_hits[:3],
            ),
            "filename_terms": FeatureEvidence(
                feature_name="video_filename_terms",
                detected=bool(filename_hits),
                score=filename_score,
                raw_value={"matches": filename_hits[:8]},
                excerpts=filename_hits[:3],
            ),
        }
        features_found: List[str] = []
        if transcript_hits:
            features_found.append("transcript_terms")
        if filename_hits:
            features_found.append("filename_terms")

        rationale_bits: List[str] = []
        if transcript_hits:
            rationale_bits.append(f"transcript cues: {', '.join(transcript_hits[:3])}")
        if filename_hits:
            rationale_bits.append(f"filename cues: {', '.join(filename_hits[:2])}")
        rationale_detail = "; ".join(rationale_bits) if rationale_bits else "minimal video-specific signals"

        scores.append(
            SubcategoryScore(
                subcategory_id=subtype.subcategory_id,
                subcategory_name=subtype.name,
                parent_type="video",
                confidence=round(total_score, 4),
                evidence_score=round(total_score, 4),
                max_possible_evidence=1.0,
                features_found=features_found,
                feature_details=details,
                rationale=f"{subtype.name} detected via {rationale_detail} (confidence: {total_score:.2f})",
            )
        )

    scores.sort(key=lambda item: item.confidence, reverse=True)
    return scores[0], scores
