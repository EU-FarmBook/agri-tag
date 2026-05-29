from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

from docint.rubrics.subcategory_scorer import FeatureEvidence, SubcategoryScore


@dataclass(frozen=True)
class AudioSubtypeDefinition:
    key: str
    subcategory_id: str
    name: str
    description: str
    positive_terms: Tuple[str, ...]
    filename_terms: Tuple[str, ...] = ()


AUDIO_SUBTYPES: Dict[str, AudioSubtypeDefinition] = {
    "tutorial": AudioSubtypeDefinition(
        key="tutorial",
        subcategory_id="AUDIO_TUTORIAL",
        name="Tutorial",
        description="Instructional audio that teaches a task, workflow, or practice step by step",
        positive_terms=("step", "how to", "tutorial", "instructions", "demonstrate", "follow these", "procedure"),
        filename_terms=("tutorial", "howto", "how-to"),
    ),
    "educational_training_media": AudioSubtypeDefinition(
        key="educational_training_media",
        subcategory_id="AUDIO_EDUCATIONAL_TRAINING",
        name="Educational/Training Media",
        description="Audio learning content such as lectures, explainers, or training modules",
        positive_terms=("learning objectives", "lesson", "module", "training", "course", "lecture", "learning"),
        filename_terms=("training", "lecture", "lesson", "course"),
    ),
    "recorded_session": AudioSubtypeDefinition(
        key="recorded_session",
        subcategory_id="AUDIO_RECORDED_SESSION",
        name="Recorded Session",
        description="Recorded meeting, webinar, workshop, or session-style event audio",
        positive_terms=("webinar", "session", "workshop", "agenda", "speaker", "today we will", "welcome everyone"),
        filename_terms=("webinar", "session", "workshop", "meeting"),
    ),
    "interview": AudioSubtypeDefinition(
        key="interview",
        subcategory_id="AUDIO_INTERVIEW",
        name="Interview",
        description="Interview-style audio built around a structured exchange between host and guest",
        positive_terms=("interview", "guest", "host", "thanks for joining us", "can you tell us", "tell me about"),
        filename_terms=("interview", "podcast"),
    ),
    "qa_session": AudioSubtypeDefinition(
        key="qa_session",
        subcategory_id="AUDIO_QA_SESSION",
        name="Q&A Session",
        description="Audio whose primary structure is questions and answers",
        positive_terms=("question", "answer", "q&a", "questions", "asked", "let me answer"),
        filename_terms=("qa", "qanda", "q-and-a"),
    ),
    "audio_program": AudioSubtypeDefinition(
        key="audio_program",
        subcategory_id="AUDIO_PROGRAM",
        name="Audio Program",
        description="Program-style audio such as a radio segment, episode, or audio series entry",
        positive_terms=("episode", "program", "radio", "podcast", "segment", "welcome back"),
        filename_terms=("episode", "program", "podcast", "radio"),
    ),
}


def score_audio_subcategories(text: str, lines: List[str], filename: str = "") -> Tuple[SubcategoryScore, List[SubcategoryScore]]:
    text_lower = text.lower()
    filename_lower = filename.lower()
    scores: List[SubcategoryScore] = []

    for subtype in AUDIO_SUBTYPES.values():
        transcript_hits = [term for term in subtype.positive_terms if term in text_lower]
        transcript_score = min(1.0, len(transcript_hits) * 0.22)
        filename_hits = [term for term in subtype.filename_terms if term in filename_lower]
        filename_score = min(1.0, len(filename_hits) * 0.4)

        total_score = min(1.0, (0.8 * transcript_score) + (0.2 * filename_score))
        details = {
            "transcript_terms": FeatureEvidence(
                feature_name="audio_transcript_terms",
                detected=bool(transcript_hits),
                score=transcript_score,
                raw_value={"matches": transcript_hits[:8]},
                excerpts=transcript_hits[:3],
            ),
            "filename_terms": FeatureEvidence(
                feature_name="audio_filename_terms",
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
        rationale_detail = "; ".join(rationale_bits) if rationale_bits else "minimal audio-specific signals"

        scores.append(
            SubcategoryScore(
                subcategory_id=subtype.subcategory_id,
                subcategory_name=subtype.name,
                parent_type="audio",
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
