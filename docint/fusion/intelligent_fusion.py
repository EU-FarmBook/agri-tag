# docint/fusion/intelligent_fusion.py
"""
Intelligent fusion of evidence-based and LLM classification results.

This module provides algorithms to combine multiple classification sources
(heuristics, vision LLM, text LLM) into a single consensus result.

The fusion considers:
- Confidence scores from each source
- Evidence strength
- Agreement between sources
- Source reliability
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Any
from enum import Enum


class FusionStrategy(str, Enum):
    """Available fusion strategies."""
    WEIGHTED = "weighted"           # Static weights (alpha-based)
    CONFIDENCE_ADAPTIVE = "adaptive"  # Dynamic based on confidence
    AGREEMENT_BASED = "agreement"   # Weight by agreement with others
    CASCADE = "cascade"            # Heuristics first, LLM fallback


@dataclass
class SourceResult:
    """Classification result from a single source."""
    source_name: str  # "heuristics", "vision_llm", "text_llm"
    subcategory_key: str
    confidence: float  # 0.0 - 1.0
    probs: Dict[str, float]  # Probabilities for all subcategories
    evidence_score: Optional[float] = None  # For heuristics
    rationale: Optional[str] = None


@dataclass
class FusionResult:
    """Result of fusing multiple sources."""
    subcategory_key: str
    confidence: float
    probs: Dict[str, float]
    sources_used: List[str]
    fusion_strategy: str
    weights: Dict[str, float]  # Weight given to each source
    agreement_score: float  # How much sources agree (0-1)
    rationale: str


def calculate_agreement(
    results: List[SourceResult],
    top_k: int = 3
) -> float:
    """
    Calculate agreement score between multiple sources.
    
    Args:
        results: List of source results
        top_k: Consider top-k predictions for agreement
    
    Returns:
        Agreement score 0.0 - 1.0
    """
    if len(results) < 2:
        return 1.0  # Single source has perfect agreement
    
    # Get top-k predictions for each source
    top_preds = []
    for r in results:
        sorted_probs = sorted(r.probs.items(), key=lambda x: x[1], reverse=True)
        top_preds.append(set([k for k, _ in sorted_probs[:top_k]]))
    
    # Calculate pairwise Jaccard similarity
    agreements = []
    for i in range(len(top_preds)):
        for j in range(i + 1, len(top_preds)):
            intersection = len(top_preds[i] & top_preds[j])
            union = len(top_preds[i] | top_preds[j])
            if union > 0:
                agreements.append(intersection / union)
    
    return sum(agreements) / len(agreements) if agreements else 0.0


def weighted_fusion(
    results: List[SourceResult],
    weights: Dict[str, float],
) -> FusionResult:
    """
    Fuse results using static weights.
    
    Args:
        results: List of source results
        weights: Weight for each source (e.g., {"heuristics": 0.4, "text_llm": 0.6})
    
    Returns:
        FusionResult
    """
    if not results:
        raise ValueError("No results to fuse")
    
    # Get all subcategory keys
    all_keys = set()
    for r in results:
        all_keys.update(r.probs.keys())
    
    # Weighted sum of probabilities
    fused_probs = {}
    for key in all_keys:
        prob_sum = 0.0
        weight_sum = 0.0
        
        for r in results:
            weight = weights.get(r.source_name, 0.0)
            prob_sum += r.probs.get(key, 0.0) * weight
            weight_sum += weight
        
        fused_probs[key] = prob_sum / weight_sum if weight_sum > 0 else 0.0
    
    # Normalize
    total = sum(fused_probs.values())
    if total > 0:
        fused_probs = {k: round(v / total, 4) for k, v in fused_probs.items()}
    
    # Best match
    best_key = max(fused_probs.items(), key=lambda x: x[1])[0]
    best_confidence = fused_probs[best_key]
    
    # Calculate agreement
    agreement = calculate_agreement(results)
    
    # Build rationale
    source_info = [f"{r.source_name}({r.subcategory_key}:{r.confidence:.2f})" for r in results]
    rationale = f"Fused from {len(results)} sources: {', '.join(source_info)}. Agreement: {agreement:.2f}"
    
    return FusionResult(
        subcategory_key=best_key,
        confidence=round(best_confidence, 4),
        probs=fused_probs,
        sources_used=[r.source_name for r in results],
        fusion_strategy="weighted",
        weights=weights,
        agreement_score=round(agreement, 4),
        rationale=rationale
    )


def confidence_adaptive_fusion(
    results: List[SourceResult],
    base_weights: Dict[str, float],
    min_confidence_threshold: float = 0.3,
) -> FusionResult:
    """
    Fuse results with dynamic weights based on confidence.
    
    Higher confidence sources get higher weight.
    Low confidence sources (below threshold) get reduced weight.
    
    Args:
        results: List of source results
        base_weights: Base weight for each source
        min_confidence_threshold: Minimum confidence to use full weight
    
    Returns:
        FusionResult
    """
    if not results:
        raise ValueError("No results to fuse")
    
    # Adjust weights based on confidence
    adjusted_weights = {}
    for r in results:
        base_weight = base_weights.get(r.source_name, 0.33)
        confidence = r.confidence
        
        # Reduce weight if confidence is low
        if confidence < min_confidence_threshold:
            confidence_factor = confidence / min_confidence_threshold
        else:
            confidence_factor = 1.0 + (confidence - min_confidence_threshold) * 0.5
        
        adjusted_weights[r.source_name] = base_weight * confidence_factor
    
    # Normalize weights
    total_weight = sum(adjusted_weights.values())
    if total_weight > 0:
        adjusted_weights = {k: v / total_weight for k, v in adjusted_weights.items()}
    
    # Use weighted fusion with adjusted weights, but preserve the selected strategy label.
    result = weighted_fusion(results, adjusted_weights)
    result.fusion_strategy = "adaptive"
    return result


def agreement_based_fusion(
    results: List[SourceResult],
    base_weights: Dict[str, float],
) -> FusionResult:
    """
    Fuse results giving higher weight to sources that agree with majority.
    
    Args:
        results: List of source results
        base_weights: Base weight for each source
    
    Returns:
        FusionResult
    """
    if len(results) < 2:
        # Just use weighted fusion for single source
        return weighted_fusion(results, base_weights)
    
    # Calculate agreement for each source with others
    agreement_scores = {}
    for i, r1 in enumerate(results):
        agreements = []
        for j, r2 in enumerate(results):
            if i != j:
                # Check if top predictions match
                if r1.subcategory_key == r2.subcategory_key:
                    agreements.append(1.0)
                else:
                    agreements.append(0.0)
        agreement_scores[r1.source_name] = sum(agreements) / len(agreements) if agreements else 0.0
    
    # Adjust weights by agreement
    adjusted_weights = {}
    for r in results:
        base_weight = base_weights.get(r.source_name, 0.33)
        agreement_bonus = 0.5 + (0.5 * agreement_scores[r.source_name])  # 0.5 to 1.0
        adjusted_weights[r.source_name] = base_weight * agreement_bonus
    
    # Normalize
    total_weight = sum(adjusted_weights.values())
    if total_weight > 0:
        adjusted_weights = {k: v / total_weight for k, v in adjusted_weights.items()}
    
    result = weighted_fusion(results, adjusted_weights)
    result.fusion_strategy = "agreement_based"
    return result


def intelligent_fusion(
    heuristics_result: Optional[SourceResult] = None,
    vision_result: Optional[SourceResult] = None,
    text_result: Optional[SourceResult] = None,
    strategy: FusionStrategy = FusionStrategy.CONFIDENCE_ADAPTIVE,
    heuristics_alpha: float = 0.4,  # Weight for heuristics (if all sources available)
    llm_alpha: float = 0.6,  # Weight for LLM (split between vision/text)
) -> FusionResult:
    """
    Intelligently fuse results from multiple classification sources.
    
    This is the main entry point for fusion. It selects the appropriate
    strategy based on available sources and configuration.
    
    Args:
        heuristics_result: Evidence-based classification result
        vision_result: Vision LLM classification result
        text_result: Text LLM classification result
        strategy: Fusion strategy to use
        heuristics_alpha: Base weight for heuristics (0.0 - 1.0)
        llm_alpha: Base weight for LLM sources (0.0 - 1.0)
    
    Returns:
        FusionResult with consensus classification
    """
    # Collect available results
    results = []
    if heuristics_result:
        results.append(heuristics_result)
    if vision_result:
        results.append(vision_result)
    if text_result:
        results.append(text_result)
    
    if not results:
        raise ValueError("At least one classification result required")
    
    if len(results) == 1:
        # Only one source, no fusion needed
        r = results[0]
        return FusionResult(
            subcategory_key=r.subcategory_key,
            confidence=r.confidence,
            probs=r.probs,
            sources_used=[r.source_name],
            fusion_strategy="single_source",
            weights={r.source_name: 1.0},
            agreement_score=1.0,
            rationale=f"Single source: {r.source_name}"
        )
    
    # Build base weights
    base_weights = {}
    
    # Heuristics weight
    if heuristics_result:
        base_weights["heuristics"] = heuristics_alpha
    
    # LLM weights (split between vision and text)
    llm_results = []
    if vision_result:
        llm_results.append("vision_llm")
    if text_result:
        llm_results.append("text_llm")
    
    if llm_results:
        llm_weight_each = llm_alpha / len(llm_results)
        for name in llm_results:
            base_weights[name] = llm_weight_each
    
    # Apply selected strategy
    if strategy == FusionStrategy.WEIGHTED:
        return weighted_fusion(results, base_weights)
    
    elif strategy == FusionStrategy.CONFIDENCE_ADAPTIVE:
        return confidence_adaptive_fusion(results, base_weights)
    
    elif strategy == FusionStrategy.AGREEMENT_BASED:
        return agreement_based_fusion(results, base_weights)
    
    elif strategy == FusionStrategy.CASCADE:
        # Use heuristics if confident, otherwise LLM
        if heuristics_result and heuristics_result.confidence >= 0.6:
            return weighted_fusion([heuristics_result], {"heuristics": 1.0})
        elif llm_results:
            llm_res = vision_result or text_result
            return weighted_fusion([llm_res], {llm_res.source_name: 1.0})
        else:
            return weighted_fusion(results, base_weights)
    
    else:
        raise ValueError(f"Unknown fusion strategy: {strategy}")


def convert_to_source_result(
    subcategory_key: str,
    confidence: float,
    probs: Dict[str, float],
    source_name: str,
    evidence_score: Optional[float] = None,
    rationale: Optional[str] = None,
) -> SourceResult:
    """Helper to create SourceResult from classification output."""
    return SourceResult(
        source_name=source_name,
        subcategory_key=subcategory_key,
        confidence=confidence,
        probs=probs,
        evidence_score=evidence_score,
        rationale=rationale,
    )
