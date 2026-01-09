"""
Composite Event Detector

Detects when composite (compound) events are mispriced relative to their component events.

Logical rules:
1. P(A AND B) ≤ min(P(A), P(B))  - Joint probability cannot exceed either component
2. P(A → B) ≤ P(A)               - Conditional outcome cannot exceed prerequisite
3. Hierarchical events: championship ≤ semifinal ≤ quarterfinal

Examples:
- "Team wins championship" requires "Team wins semifinal" → P(championship) ≤ P(semifinal)
- "Stock above $100k" requires "Stock above $90k" → P(>100k) ≤ P(>90k)
- "Candidate becomes president" requires "Candidate wins primary" → P(president) ≤ P(primary)
"""

from __future__ import annotations

import re
from typing import List, Optional, Tuple

from predarb.config import DetectorConfig
from predarb.models import Market, Opportunity, TradeAction


class CompositeDetector:
    """
    Detects composite event arbitrage opportunities.
    
    A composite event is one that logically requires another event as a prerequisite.
    If P(composite) > P(component), arbitrage exists.
    """
    
    # Keywords indicating hierarchical relationships
    HIERARCHY_KEYWORDS = {
        'championship': ['final', 'semifinal', 'championship', 'tournament'],
        'final': ['semifinal', 'final'],
        'semifinal': ['quarterfinal', 'semifinal'],
        'president': ['primary', 'election', 'president'],
        'elected': ['nominated', 'elected'],
        'win': ['reach', 'advance', 'qualify', 'win'],
    }
    
    # Composite patterns (more specific implies less specific)
    COMPOSITE_PATTERNS = [
        (r'win.*championship', r'win.*final'),
        (r'win.*championship', r'win.*semifinal'),
        (r'win.*final', r'win.*semifinal'),
        (r'win.*semifinal', r'win.*quarterfinal'),
        (r'become.*president', r'win.*primary'),
        (r'become.*president', r'win.*election'),
        (r'elected.*president', r'nominated'),
        (r'reach.*final', r'win.*semifinal'),
    ]
    
    def __init__(self, config: DetectorConfig):
        self.config = config
        # Use consistency tolerance for composite detection threshold
        self.min_violation = getattr(config, 'composite_tolerance', 0.02)
    
    def detect(self, markets: List[Market]) -> List[Opportunity]:
        """
        Detect composite event arbitrage across all markets.
        
        Returns:
            List of opportunities where P(composite) > P(component)
        """
        opps: List[Opportunity] = []
        
        # Check all market pairs for hierarchical relationships
        for i, m1 in enumerate(markets):
            for m2 in markets[i + 1:]:
                # Check if these markets have a hierarchical relationship
                relationship = self._find_hierarchy(m1, m2)
                if relationship:
                    composite_market, component_market, rel_type = relationship
                    
                    # Get probabilities (use YES outcome)
                    p_composite = self._get_yes_price(composite_market)
                    p_component = self._get_yes_price(component_market)
                    
                    if p_composite is None or p_component is None:
                        continue
                    
                    # Check for violation: P(composite) > P(component)
                    violation = p_composite - p_component
                    
                    if violation > self.min_violation:
                        # Arbitrage exists: sell composite, buy component
                        opps.append(
                            Opportunity(
                                type="COMPOSITE",
                                market_ids=[composite_market.id, component_market.id],
                                description=f"Composite violation: P({rel_type[0]})={p_composite:.3f} > P({rel_type[1]})={p_component:.3f}",
                                net_edge=violation,
                                actions=[
                                    # Sell the overpriced composite
                                    TradeAction(
                                        market_id=composite_market.id,
                                        outcome_id=composite_market.outcomes[0].id,
                                        side="SELL",
                                        amount=1.0,
                                        limit_price=p_composite
                                    ),
                                    # Buy the underpriced component
                                    TradeAction(
                                        market_id=component_market.id,
                                        outcome_id=component_market.outcomes[0].id,
                                        side="BUY",
                                        amount=1.0,
                                        limit_price=p_component
                                    ),
                                ],
                                metadata={
                                    "relationship": rel_type,
                                    "violation_size": violation,
                                    "composite_market": composite_market.id,
                                    "component_market": component_market.id,
                                }
                            )
                        )
        
        return opps
    
    def _find_hierarchy(
        self,
        m1: Market,
        m2: Market
    ) -> Optional[Tuple[Market, Market, Tuple[str, str]]]:
        """
        Determine if two markets have a hierarchical relationship.
        
        Returns:
            (composite_market, component_market, (composite_label, component_label))
            or None if no relationship found
        """
        q1 = m1.question.lower()
        q2 = m2.question.lower()
        
        # Check pattern-based matches
        for composite_pattern, component_pattern in self.COMPOSITE_PATTERNS:
            if re.search(composite_pattern, q1) and re.search(component_pattern, q2):
                return (m1, m2, (composite_pattern, component_pattern))
            if re.search(composite_pattern, q2) and re.search(component_pattern, q1):
                return (m2, m1, (composite_pattern, component_pattern))
        
        # Check keyword-based hierarchy
        for composite_keyword, hierarchy in self.HIERARCHY_KEYWORDS.items():
            if composite_keyword in q1:
                for component_keyword in hierarchy:
                    if component_keyword in q2 and component_keyword != composite_keyword:
                        # Verify component is less specific than composite
                        comp_idx = hierarchy.index(composite_keyword)
                        comp2_idx = hierarchy.index(component_keyword)
                        if comp_idx > comp2_idx:  # Higher index = more specific
                            return (m1, m2, (composite_keyword, component_keyword))
            
            if composite_keyword in q2:
                for component_keyword in hierarchy:
                    if component_keyword in q1 and component_keyword != composite_keyword:
                        comp_idx = hierarchy.index(composite_keyword)
                        comp2_idx = hierarchy.index(component_keyword)
                        if comp_idx > comp2_idx:
                            return (m2, m1, (composite_keyword, component_keyword))
        
        # Check for same entity with threshold hierarchy (handled by ladder detector)
        # Skip to avoid duplication
        
        return None
    
    def _get_yes_price(self, market: Market) -> Optional[float]:
        """Get the YES outcome price from a market."""
        yes_outcome = market.outcome_by_label("yes")
        if yes_outcome:
            return yes_outcome.price
        
        # Fallback to first outcome if no explicit YES
        if market.outcomes:
            return market.outcomes[0].price
        
        return None
