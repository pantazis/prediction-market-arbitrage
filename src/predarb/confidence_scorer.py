"""
Confidence scoring for market matches.

Computes match confidence based on structural vs semantic matching,
and determines if LLM verification is needed.

Requirements: 8.1, 8.2, 8.3, 8.4, 8.5
"""

from __future__ import annotations

from typing import Dict, TYPE_CHECKING

if TYPE_CHECKING:
    from predarb.match_pipeline import MatchCandidate


class ConfidenceScorer:
    """
    Computes match confidence based on structural vs semantic matching.
    
    Confidence scoring rules:
    - Full structural match (all fields): >= 0.95
    - Partial structural match: weighted combination
    - Semantic-only match: semantic_score * 0.7
    
    Requirements: 8.1, 8.2, 8.3, 8.4, 8.5
    """
    
    STRUCTURAL_WEIGHTS = {
        "asset": 0.25,
        "threshold": 0.30,
        "direction": 0.15,
        "date": 0.20,
        "category": 0.10,
    }
    
    # Confidence threshold for LLM verification
    LLM_VERIFICATION_THRESHOLD = 0.80
    
    def score(self, candidate: "MatchCandidate") -> float:
        """
        Compute confidence score (0.0-1.0) for a match candidate.
        
        Args:
            candidate: The MatchCandidate to score
            
        Returns:
            Confidence score between 0.0 and 1.0
        """
        structural_matches = candidate.structural_matches
        semantic_score = candidate.semantic_score
        
        # Count structural matches and compute weighted score
        matched_weight = 0.0
        total_weight = 0.0
        match_count = 0
        
        for field, weight in self.STRUCTURAL_WEIGHTS.items():
            if field in structural_matches:
                total_weight += weight
                if structural_matches[field]:
                    matched_weight += weight
                    match_count += 1
        
        # Determine scoring mode
        if total_weight > 0 and match_count == len(structural_matches) and match_count > 0:
            # Full structural match - high confidence
            return max(0.95, semantic_score)
        elif match_count > 0:
            # Partial structural match - weighted combination
            structural_ratio = matched_weight / total_weight if total_weight > 0 else 0
            return min(1.0, 0.7 + (0.25 * structural_ratio) + (0.05 * semantic_score))
        else:
            # Semantic-only match
            return semantic_score * 0.7
    
    def score_from_components(
        self, 
        structural_matches: Dict[str, bool], 
        semantic_score: float
    ) -> float:
        """
        Compute confidence score from raw components.
        
        Args:
            structural_matches: Dict of field -> matched boolean
            semantic_score: Semantic similarity score (0.0-1.0)
            
        Returns:
            Confidence score between 0.0 and 1.0
        """
        # Count structural matches and compute weighted score
        matched_weight = 0.0
        total_weight = 0.0
        match_count = 0
        
        for field, weight in self.STRUCTURAL_WEIGHTS.items():
            if field in structural_matches:
                total_weight += weight
                if structural_matches[field]:
                    matched_weight += weight
                    match_count += 1
        
        # Determine scoring mode
        if total_weight > 0 and match_count == len(structural_matches) and match_count > 0:
            # Full structural match - high confidence
            return max(0.95, semantic_score)
        elif match_count > 0:
            # Partial structural match - weighted combination
            structural_ratio = matched_weight / total_weight if total_weight > 0 else 0
            return min(1.0, 0.7 + (0.25 * structural_ratio) + (0.05 * semantic_score))
        else:
            # Semantic-only match
            return semantic_score * 0.7
    
    def needs_llm_verification(self, confidence: float) -> bool:
        """
        Check if a match needs LLM verification.
        
        Args:
            confidence: The confidence score to check
            
        Returns:
            True if confidence < 0.80, indicating LLM verification is needed
        """
        return confidence < self.LLM_VERIFICATION_THRESHOLD
