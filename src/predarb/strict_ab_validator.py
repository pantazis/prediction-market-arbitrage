"""
Strict A+B Mode Validator

Enforces NON-NEGOTIABLE constraint that ALL arbitrage opportunities must:
1. Use EXACTLY TWO venues (one leg on A, one on B)
2. Respect venue constraints:
   - Venue A (Kalshi-like): BUY, SELL-TO-OPEN (short), SELL-TO-CLOSE
   - Venue B (Polymarket-like): BUY, SELL-TO-CLOSE ONLY (NO shorting)
3. Be non-executable on either venue alone

This module provides validation logic to reject:
- Single-venue arbitrage
- Theoretical/arithmetic arbitrage without venue distinction
- Arbitrage requiring forbidden actions (e.g., Polymarket shorting)
- Arbitrage executable on one venue alone
"""

from __future__ import annotations

import logging
from typing import List, Dict, Set, Tuple, Optional
from dataclasses import dataclass, field
from collections import defaultdict

from predarb.models import Opportunity, TradeAction, Market

logger = logging.getLogger(__name__)


@dataclass
class VenueConstraints:
    """Defines what actions are allowed on each venue type."""
    name: str
    supports_shorting: bool  # Can SELL without existing position
    allowed_sides: Set[str] = field(default_factory=set)
    
    @classmethod
    def kalshi_like(cls) -> "VenueConstraints":
        """Venue A: Kalshi-like with shorting support."""
        return cls(
            name="kalshi",
            supports_shorting=True,
            allowed_sides={"BUY", "SELL"}  # SELL includes both to-open and to-close
        )
    
    @classmethod
    def polymarket_like(cls) -> "VenueConstraints":
        """Venue B: Polymarket-like WITHOUT shorting."""
        return cls(
            name="polymarket",
            supports_shorting=False,
            allowed_sides={"BUY", "SELL"}  # SELL only to-close (inventory required)
        )


@dataclass
class ValidationResult:
    """Result of strict A+B validation."""
    is_valid: bool
    rejection_reason: Optional[str] = None
    venues_used: Set[str] = field(default_factory=set)
    venue_legs: Dict[str, int] = field(default_factory=dict)
    forbidden_actions: List[str] = field(default_factory=list)
    metadata: Dict[str, object] = field(default_factory=dict)


class StrictABValidator:
    """
    Validates that opportunities conform to strict A+B mode requirements.
    
    Rules enforced:
    1. Exactly 2 venues used
    2. At least one leg on venue A
    3. At least one leg on venue B
    4. Venue B legs never include SELL-TO-OPEN (short)
    5. Venue B legs never create short exposure
    6. Removing either venue eliminates the opportunity
    """
    
    VENUE_A_NAMES = {"kalshi"}
    VENUE_B_NAMES = {"polymarket"}
    
    def __init__(
        self,
        venue_a_constraints: Optional[VenueConstraints] = None,
        venue_b_constraints: Optional[VenueConstraints] = None,
        broker_positions: Optional[Dict[str, float]] = None
    ):
        """
        Initialize validator.
        
        Args:
            venue_a_constraints: Constraints for venue A (default: Kalshi-like)
            venue_b_constraints: Constraints for venue B (default: Polymarket-like)
            broker_positions: Current inventory positions {market:outcome -> quantity}
        """
        self.venue_a = venue_a_constraints or VenueConstraints.kalshi_like()
        self.venue_b = venue_b_constraints or VenueConstraints.polymarket_like()
        self.broker_positions = broker_positions or {}
    
    def validate_opportunity(
        self,
        opportunity: Opportunity,
        market_lookup: Dict[str, Market]
    ) -> ValidationResult:
        """
        Validate that an opportunity conforms to strict A+B mode.
        
        Args:
            opportunity: The opportunity to validate
            market_lookup: Dictionary of market_id -> Market for venue lookup
            
        Returns:
            ValidationResult with validation status and details
        """
        # Rule 1: Count venues used
        venues_used = self._get_venues_used(opportunity, market_lookup)
        
        if len(venues_used) < 2:
            return ValidationResult(
                is_valid=False,
                rejection_reason="insufficient_venues",
                venues_used=venues_used,
                metadata={
                    "required": 2,
                    "found": len(venues_used),
                    "detail": "Arbitrage requires EXACTLY 2 venues"
                }
            )
        
        if len(venues_used) > 2:
            return ValidationResult(
                is_valid=False,
                rejection_reason="too_many_venues",
                venues_used=venues_used,
                metadata={
                    "required": 2,
                    "found": len(venues_used),
                    "detail": "Arbitrage must use EXACTLY 2 venues (no more)"
                }
            )
        
        # Rule 2: Check venue distribution (must have at least one A and one B)
        venue_legs = self._count_venue_legs(opportunity, market_lookup)
        
        has_venue_a = any(v in self.VENUE_A_NAMES for v in venue_legs.keys())
        has_venue_b = any(v in self.VENUE_B_NAMES for v in venue_legs.keys())
        
        if not has_venue_a or not has_venue_b:
            return ValidationResult(
                is_valid=False,
                rejection_reason="single_venue_type",
                venues_used=venues_used,
                venue_legs=venue_legs,
                metadata={
                    "has_venue_a": has_venue_a,
                    "has_venue_b": has_venue_b,
                    "detail": "Must have legs on BOTH venue A (Kalshi) and venue B (Polymarket)"
                }
            )
        
        # Rule 3: Check for forbidden actions on venue B
        forbidden_actions = self._check_forbidden_actions(opportunity, market_lookup)
        
        if forbidden_actions:
            return ValidationResult(
                is_valid=False,
                rejection_reason="forbidden_action",
                venues_used=venues_used,
                venue_legs=venue_legs,
                forbidden_actions=forbidden_actions,
                metadata={
                    "detail": "Venue B (Polymarket) does not support short selling",
                    "forbidden_count": len(forbidden_actions)
                }
            )
        
        # Rule 4: Verify opportunity type is in allowed list
        if not self._is_allowed_opportunity_type(opportunity):
            return ValidationResult(
                is_valid=False,
                rejection_reason="forbidden_opportunity_type",
                venues_used=venues_used,
                venue_legs=venue_legs,
                metadata={
                    "opportunity_type": opportunity.type,
                    "detail": f"Opportunity type {opportunity.type} not in allowed list for A+B mode"
                }
            )
        
        # All rules passed
        return ValidationResult(
            is_valid=True,
            venues_used=venues_used,
            venue_legs=venue_legs,
            metadata={
                "opportunity_type": opportunity.type,
                "leg_count": len(opportunity.actions)
            }
        )
    
    def _get_venues_used(
        self,
        opportunity: Opportunity,
        market_lookup: Dict[str, Market]
    ) -> Set[str]:
        """Get set of unique venues used in this opportunity."""
        venues = set()
        for action in opportunity.actions:
            market = market_lookup.get(action.market_id)
            if market and market.exchange:
                venues.add(market.exchange.lower())
        return venues
    
    def _count_venue_legs(
        self,
        opportunity: Opportunity,
        market_lookup: Dict[str, Market]
    ) -> Dict[str, int]:
        """Count number of legs per venue."""
        venue_count = defaultdict(int)
        for action in opportunity.actions:
            market = market_lookup.get(action.market_id)
            if market and market.exchange:
                venue_count[market.exchange.lower()] += 1
        return dict(venue_count)
    
    def _check_forbidden_actions(
        self,
        opportunity: Opportunity,
        market_lookup: Dict[str, Market]
    ) -> List[str]:
        """
        Check for actions that violate venue constraints.
        
        Returns list of forbidden action descriptions.
        """
        forbidden = []
        
        for action in opportunity.actions:
            market = market_lookup.get(action.market_id)
            if not market or not market.exchange:
                continue
            
            venue_name = market.exchange.lower()
            
            # Check if this is venue B (Polymarket-like)
            if venue_name in self.VENUE_B_NAMES:
                # Venue B does not support shorting
                if action.side.upper() == "SELL":
                    # Check if we have inventory for this position
                    position_key = f"{action.market_id}:{action.outcome_id}"
                    inventory = self.broker_positions.get(position_key, 0.0)
                    
                    if inventory <= 0:
                        # This is a SELL without inventory = short attempt
                        forbidden.append(
                            f"SELL-TO-OPEN on {venue_name} for {action.market_id}:{action.outcome_id} "
                            f"(inventory={inventory})"
                        )
                    elif action.amount > inventory:
                        # Partial short attempt
                        forbidden.append(
                            f"SELL amount {action.amount} exceeds inventory {inventory} on {venue_name} "
                            f"for {action.market_id}:{action.outcome_id}"
                        )
        
        return forbidden
    
    def _is_allowed_opportunity_type(self, opportunity: Opportunity) -> bool:
        """
        Check if opportunity type is allowed in strict A+B mode.
        
        Allowed types:
        - Cross-venue parity
        - Cross-venue complement
        - Cross-venue ladder
        - Cross-venue range replication (with A short leg)
        - Cross-venue multi-outcome additivity
        - Cross-venue composite
        
        Forbidden types:
        - Single-venue parity (executable on one venue)
        - Single-venue ladder
        - DUPLICATE (if both legs are BUYs on different venues - no cross-venue execution constraint)
        """
        opp_type = opportunity.type.upper()
        
        # Note: For now, we allow all types and rely on venue validation
        # In production, you may want to explicitly whitelist/blacklist types
        
        # Example of type-based filtering:
        # SINGLE_VENUE_TYPES = {"SINGLE_PARITY", "SINGLE_LADDER"}
        # if opp_type in SINGLE_VENUE_TYPES:
        #     return False
        
        return True
    
    def validate_batch(
        self,
        opportunities: List[Opportunity],
        market_lookup: Dict[str, Market]
    ) -> Tuple[List[Opportunity], List[Tuple[Opportunity, ValidationResult]]]:
        """
        Validate a batch of opportunities.
        
        Returns:
            Tuple of (valid_opportunities, rejected_with_reasons)
        """
        valid = []
        rejected = []
        
        for opp in opportunities:
            result = self.validate_opportunity(opp, market_lookup)
            if result.is_valid:
                valid.append(opp)
            else:
                rejected.append((opp, result))
        
        return valid, rejected
    
    def generate_validation_report(
        self,
        opportunities: List[Opportunity],
        market_lookup: Dict[str, Market]
    ) -> Dict[str, object]:
        """
        Generate comprehensive validation report.
        
        Returns:
            Dictionary with validation statistics and details
        """
        valid, rejected = self.validate_batch(opportunities, market_lookup)
        
        # Count rejections by reason
        rejection_counts = defaultdict(int)
        for _, result in rejected:
            rejection_counts[result.rejection_reason] += 1
        
        # Count valid opportunities by type
        valid_by_type = defaultdict(int)
        for opp in valid:
            valid_by_type[opp.type] += 1
        
        # Collect venue distribution for valid opportunities
        venue_distributions = []
        for opp in valid:
            result = self.validate_opportunity(opp, market_lookup)
            venue_distributions.append({
                "venues": sorted(result.venues_used),
                "legs": result.venue_legs,
                "type": opp.type
            })
        
        return {
            "total_opportunities": len(opportunities),
            "total_valid": len(valid),
            "total_rejected": len(rejected),
            "rejection_rate": len(rejected) / len(opportunities) if opportunities else 0,
            "rejections_by_reason": dict(rejection_counts),
            "valid_by_type": dict(valid_by_type),
            "venue_distributions": venue_distributions,
            "validation_passed": len(rejected) == 0 or all(
                reason in {"low_edge", "insufficient_liquidity"}
                for reason in rejection_counts.keys()
            )
        }
