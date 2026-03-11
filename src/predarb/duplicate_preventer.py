"""
Duplicate prevention for market matching.

Ensures one-to-one matching between venues by selecting the best match
when multiple Kalshi markets match the same Polymarket market.

Requirements: 9.1, 9.2, 9.3, 9.4, 9.5
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Set, TYPE_CHECKING

if TYPE_CHECKING:
    from predarb.match_pipeline import MatchCandidate

logger = logging.getLogger(__name__)


class DuplicatePreventer:
    """
    Ensures one-to-one matching between Kalshi and Polymarket markets.
    
    When multiple Kalshi markets match the same Polymarket market,
    selects the highest confidence match, preferring higher liquidity on ties.
    
    Requirements: 9.1, 9.2, 9.3, 9.4, 9.5
    """
    
    def __init__(self):
        """Initialize the DuplicatePreventer."""
        self.matched_polymarket_ids: Set[str] = set()
        self.duplicate_log: List[Dict] = []
    
    def reset(self) -> None:
        """Reset state for a new matching run."""
        self.matched_polymarket_ids = set()
        self.duplicate_log = []
    
    def select_best_match(
        self, 
        candidates: List["MatchCandidate"], 
        polymarket_id: str
    ) -> Optional["MatchCandidate"]:
        """
        Select the best match for a Polymarket market from multiple candidates.
        
        Selection criteria:
        1. Highest confidence score
        2. On ties, prefer higher Kalshi market liquidity
        
        Args:
            candidates: List of candidates matching the same Polymarket market
            polymarket_id: The Polymarket market ID
            
        Returns:
            The best MatchCandidate, or None if no candidates
        """
        if not candidates:
            return None
        
        if len(candidates) == 1:
            return candidates[0]
        
        # Sort by confidence (desc), then by Kalshi liquidity (desc)
        def sort_key(c: "MatchCandidate") -> tuple:
            liquidity = getattr(c.kalshi_market, "liquidity", 0) or 0
            return (-c.confidence, -liquidity)
        
        sorted_candidates = sorted(candidates, key=sort_key)
        best = sorted_candidates[0]
        
        # Log duplicate detection
        rejected_ids = [c.kalshi_market.id for c in sorted_candidates[1:]]
        self.duplicate_log.append({
            "polymarket_id": polymarket_id,
            "selected_kalshi_id": best.kalshi_market.id,
            "selected_confidence": best.confidence,
            "rejected_kalshi_ids": rejected_ids,
            "rejected_count": len(rejected_ids),
        })
        
        logger.debug(
            f"Duplicate detected for {polymarket_id}: "
            f"selected {best.kalshi_market.id} (conf={best.confidence:.3f}), "
            f"rejected {len(rejected_ids)} others"
        )
        
        return best
    
    def deduplicate(
        self, 
        candidates: List["MatchCandidate"]
    ) -> List["MatchCandidate"]:
        """
        Remove duplicate matches, keeping the best for each Polymarket market.
        
        Args:
            candidates: List of all match candidates
            
        Returns:
            Deduplicated list with at most one Kalshi market per Polymarket market
        """
        self.reset()
        
        # Group candidates by Polymarket ID
        by_poly_id: Dict[str, List["MatchCandidate"]] = {}
        for candidate in candidates:
            poly_id = candidate.polymarket_market.id
            if poly_id not in by_poly_id:
                by_poly_id[poly_id] = []
            by_poly_id[poly_id].append(candidate)
        
        # Select best match for each Polymarket market
        result: List["MatchCandidate"] = []
        for poly_id, group in by_poly_id.items():
            best = self.select_best_match(group, poly_id)
            if best:
                result.append(best)
                self.matched_polymarket_ids.add(poly_id)
        
        duplicates_found = sum(1 for g in by_poly_id.values() if len(g) > 1)
        if duplicates_found > 0:
            logger.info(
                f"Deduplicated {len(candidates)} candidates to {len(result)} matches "
                f"({duplicates_found} Polymarket markets had multiple Kalshi matches)"
            )
        
        return result
    
    def get_duplicate_summary(self) -> Dict:
        """Get summary of duplicate handling."""
        return {
            "total_duplicates_resolved": len(self.duplicate_log),
            "polymarket_ids_matched": len(self.matched_polymarket_ids),
            "details": self.duplicate_log,
        }
