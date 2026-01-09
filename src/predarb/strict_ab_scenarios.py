"""
Strict A+B Mode Test Scenarios

Generates comprehensive test data covering:
✅ VALID A+B arbitrage (should be detected and approved)
❌ INVALID arbitrage (should be rejected)

All scenarios are deterministic and network-free for testing.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from typing import List, Tuple, Dict, Any
from dataclasses import dataclass

from predarb.models import Market, Outcome


@dataclass
class ScenarioMetadata:
    """Metadata about a test scenario."""
    name: str
    expected_detection: bool  # Should detector find opportunity?
    expected_approval: bool  # Should pass strict A+B validation?
    rejection_reason: str = ""  # Expected rejection reason if any
    arbitrage_type: str = ""  # Type of arbitrage (PARITY, LADDER, etc.)
    description: str = ""


class StrictABScenarios:
    """
    Generator for strict A+B mode test scenarios.
    
    Creates markets that test ALL validation rules:
    1. Exactly 2 venues required
    2. At least one leg on venue A (Kalshi)
    3. At least one leg on venue B (Polymarket)
    4. No shorting on venue B
    5. Opportunity must require BOTH venues
    """
    
    def __init__(self, seed: int = 42):
        self.seed = seed
        random.seed(seed)
        self.now = datetime.now(timezone.utc).replace(tzinfo=None)
        self.expiry_7d = self.now + timedelta(days=7)
        self.expiry_30d = self.now + timedelta(days=30)
    
    def generate_all_scenarios(self) -> Tuple[List[Market], List[Market], List[ScenarioMetadata]]:
        """
        Generate comprehensive test suite.
        
        Returns:
            Tuple of (polymarket_markets, kalshi_markets, scenario_metadata)
        """
        poly_markets = []
        kalshi_markets = []
        metadata = []
        
        # ==================== VALID A+B ARBITRAGE (SHOULD DETECT) ==================== #
        
        # Scenario 1: Cross-venue parity (same event, mispriced across venues)
        p1, k1, m1 = self._scenario_cross_venue_parity()
        poly_markets.extend(p1)
        kalshi_markets.extend(k1)
        metadata.extend(m1)
        
        # Scenario 2: Cross-venue complement (YES on A, NO on B)
        p2, k2, m2 = self._scenario_cross_venue_complement()
        poly_markets.extend(p2)
        kalshi_markets.extend(k2)
        metadata.extend(m2)
        
        # Scenario 3: Cross-venue ladder (threshold markets across venues)
        p3, k3, m3 = self._scenario_cross_venue_ladder()
        poly_markets.extend(p3)
        kalshi_markets.extend(k3)
        metadata.extend(m3)
        
        # Scenario 4: Cross-venue with Kalshi short leg (requires venue A shorting)
        p4, k4, m4 = self._scenario_cross_venue_with_short()
        poly_markets.extend(p4)
        kalshi_markets.extend(k4)
        metadata.extend(m4)
        
        # Scenario 5: Cross-venue range replication (VALID - requires A short)
        p5, k5, m5 = self._scenario_range_replication_valid()
        poly_markets.extend(p5)
        kalshi_markets.extend(k5)
        metadata.extend(m5)
        
        # Scenario 6: Cross-venue multi-outcome additivity (VALID)
        p6, k6, m6 = self._scenario_multi_outcome_additivity_valid()
        poly_markets.extend(p6)
        kalshi_markets.extend(k6)
        metadata.extend(m6)
        
        # Scenario 7: Cross-venue composite vs components (VALID)
        p7, k7, m7 = self._scenario_composite_vs_components_valid()
        poly_markets.extend(p7)
        kalshi_markets.extend(k7)
        metadata.extend(m7)
        
        # Scenario 8: Cross-venue calendar basis (VALID - flagged)
        p8, k8, m8 = self._scenario_calendar_basis_valid()
        poly_markets.extend(p8)
        kalshi_markets.extend(k8)
        metadata.extend(m8)
        
        # ==================== INVALID ARBITRAGE (SHOULD REJECT) ==================== #
        
        # Scenario 5: Single-venue parity (Polymarket only)
        p5, k5, m5 = self._scenario_single_venue_parity_poly()
        poly_markets.extend(p5)
        kalshi_markets.extend(k5)
        metadata.extend(m5)
        
        # Scenario 6: Single-venue parity (Kalshi only)
        p6, k6, m6 = self._scenario_single_venue_parity_kalshi()
        poly_markets.extend(p6)
        kalshi_markets.extend(k6)
        metadata.extend(m6)
        
        # Scenario 7: Polymarket-only arbitrage (no Kalshi market)
        p7, k7, m7 = self._scenario_polymarket_only()
        poly_markets.extend(p7)
        kalshi_markets.extend(k7)
        metadata.extend(m7)
        
        # Scenario 8: Arbitrage requiring Polymarket shorting (FORBIDDEN)
        p8, k8, m8 = self._scenario_requires_polymarket_short()
        poly_markets.extend(p8)
        kalshi_markets.extend(k8)
        metadata.extend(m8)
        
        # Scenario 9: Theoretical arbitrage (arithmetic only, no venue constraint)
        p9, k9, m9 = self._scenario_theoretical_arithmetic()
        poly_markets.extend(p9)
        kalshi_markets.extend(k9)
        metadata.extend(m9)
        
        # Scenario 10: Edge-positive but execution-invalid (tiny liquidity)
        p10, k10, m10 = self._scenario_low_liquidity()
        poly_markets.extend(p10)
        kalshi_markets.extend(k10)
        metadata.extend(m10)
        
        # Scenario 11: Range replication INVALID (Polymarket-only, no cross-venue)
        p11, k11, m11 = self._scenario_range_replication_invalid()
        poly_markets.extend(p11)
        kalshi_markets.extend(k11)
        metadata.extend(m11)
        
        # Scenario 12: Multi-outcome INVALID (requires Polymarket short)
        p12, k12, m12 = self._scenario_multi_outcome_invalid()
        poly_markets.extend(p12)
        kalshi_markets.extend(k12)
        metadata.extend(m12)
        
        # Scenario 13: Composite INVALID (single venue only)
        p13, k13, m13 = self._scenario_composite_invalid()
        poly_markets.extend(p13)
        kalshi_markets.extend(k13)
        metadata.extend(m13)
        
        # Scenario 14: Calendar basis INVALID (insufficient time spread)
        p14, k14, m14 = self._scenario_calendar_basis_invalid()
        poly_markets.extend(p14)
        kalshi_markets.extend(k14)
        metadata.extend(m14)
        
        return poly_markets, kalshi_markets, metadata
    
    # ==================== VALID SCENARIOS ==================== #
    
    def _scenario_cross_venue_parity(self) -> Tuple[List[Market], List[Market], List[ScenarioMetadata]]:
        """Cross-venue parity: Same event priced differently on A and B."""
        poly = [Market(
            id="poly:cv_parity_1",
            question="Will BTC exceed $100k by year end?",
            outcomes=[
                Outcome(id="poly:cv_parity_1:yes", label="YES", price=0.40, liquidity=15000.0),
                Outcome(id="poly:cv_parity_1:no", label="NO", price=0.60, liquidity=15000.0),
            ],
            end_date=self.expiry_30d,
            expiry=self.expiry_30d,
            liquidity=30000.0,
            volume=100000.0,
            exchange="polymarket",
            tags=["crypto", "valid_ab"]
        )]
        
        kalshi = [Market(
            id="kalshi:BTC100K:BTC100K-T1",
            question="Will BTC exceed $100k by year end?",
            outcomes=[
                Outcome(id="kalshi:BTC100K:YES", label="YES", price=0.55, liquidity=12000.0),
                Outcome(id="kalshi:BTC100K:NO", label="NO", price=0.45, liquidity=12000.0),
            ],
            end_date=self.expiry_30d,
            expiry=self.expiry_30d,
            liquidity=24000.0,
            volume=80000.0,
            exchange="kalshi",
            tags=["crypto", "valid_ab"]
        )]
        
        metadata = [ScenarioMetadata(
            name="cross_venue_parity_btc",
            expected_detection=True,
            expected_approval=True,
            arbitrage_type="CROSS_VENUE_PARITY",
            description="Buy YES on Poly (0.40), Sell YES on Kalshi (0.55) = 0.15 edge"
        )]
        
        return poly, kalshi, metadata
    
    def _scenario_cross_venue_complement(self) -> Tuple[List[Market], List[Market], List[ScenarioMetadata]]:
        """Cross-venue complement: YES on A + NO on B < 1.0."""
        poly = [Market(
            id="poly:cv_complement_1",
            question="Will candidate win election?",
            outcomes=[
                Outcome(id="poly:cv_complement_1:yes", label="YES", price=0.48, liquidity=20000.0),
                Outcome(id="poly:cv_complement_1:no", label="NO", price=0.52, liquidity=20000.0),
            ],
            end_date=self.expiry_7d,
            expiry=self.expiry_7d,
            liquidity=40000.0,
            volume=150000.0,
            exchange="polymarket",
            tags=["politics", "valid_ab"]
        )]
        
        kalshi = [Market(
            id="kalshi:ELEC-WIN:ELEC-WIN-T1",
            question="Will candidate win election?",
            outcomes=[
                Outcome(id="kalshi:ELEC-WIN:YES", label="YES", price=0.46, liquidity=18000.0),
                Outcome(id="kalshi:ELEC-WIN:NO", label="NO", price=0.54, liquidity=18000.0),
            ],
            end_date=self.expiry_7d,
            expiry=self.expiry_7d,
            liquidity=36000.0,
            volume=120000.0,
            exchange="kalshi",
            tags=["politics", "valid_ab"]
        )]
        
        metadata = [ScenarioMetadata(
            name="cross_venue_complement_election",
            expected_detection=True,
            expected_approval=True,
            arbitrage_type="CROSS_VENUE_COMPLEMENT",
            description="Buy YES on Kalshi (0.46) + NO on Poly (0.52) = 0.98 < 1.0"
        )]
        
        return poly, kalshi, metadata
    
    def _scenario_cross_venue_ladder(self) -> Tuple[List[Market], List[Market], List[ScenarioMetadata]]:
        """Cross-venue ladder: Threshold markets with monotonicity violation."""
        poly = [
            Market(
                id="poly:cv_ladder_50k",
                question="Will stock index close above 50,000?",
                outcomes=[
                    Outcome(id="poly:cv_ladder_50k:yes", label="YES", price=0.70, liquidity=10000.0),
                    Outcome(id="poly:cv_ladder_50k:no", label="NO", price=0.30, liquidity=10000.0),
                ],
                end_date=self.expiry_7d,
                expiry=self.expiry_7d,
                liquidity=20000.0,
                volume=50000.0,
                exchange="polymarket",
                tags=["finance", "valid_ab", "ladder"],
                threshold=50000.0,
                comparator=">"
            ),
        ]
        
        kalshi = [
            Market(
                id="kalshi:INDEX60K:INDEX60K-T1",
                question="Will stock index close above 60,000?",
                outcomes=[
                    Outcome(id="kalshi:INDEX60K:YES", label="YES", price=0.75, liquidity=8000.0),
                    Outcome(id="kalshi:INDEX60K:NO", label="NO", price=0.25, liquidity=8000.0),
                ],
                end_date=self.expiry_7d,
                expiry=self.expiry_7d,
                liquidity=16000.0,
                volume=40000.0,
                exchange="kalshi",
                tags=["finance", "valid_ab", "ladder"],
                threshold=60000.0,
                comparator=">"
            ),
        ]
        
        metadata = [ScenarioMetadata(
            name="cross_venue_ladder_index",
            expected_detection=True,
            expected_approval=True,
            arbitrage_type="LADDER",
            description="P(>60k)=0.75 > P(>50k)=0.70 violates monotonicity (should be ≤)"
        )]
        
        return poly, kalshi, metadata
    
    def _scenario_cross_venue_with_short(self) -> Tuple[List[Market], List[Market], List[ScenarioMetadata]]:
        """Cross-venue arbitrage requiring short on Kalshi (venue A)."""
        poly = [Market(
            id="poly:cv_short_1",
            question="Will unemployment rate exceed 5%?",
            outcomes=[
                Outcome(id="poly:cv_short_1:yes", label="YES", price=0.35, liquidity=12000.0),
                Outcome(id="poly:cv_short_1:no", label="NO", price=0.65, liquidity=12000.0),
            ],
            end_date=self.expiry_7d,
            expiry=self.expiry_7d,
            liquidity=24000.0,
            volume=60000.0,
            exchange="polymarket",
            tags=["economics", "valid_ab"]
        )]
        
        kalshi = [Market(
            id="kalshi:UNEMP5:UNEMP5-T1",
            question="Will unemployment rate exceed 5%?",
            outcomes=[
                Outcome(id="kalshi:UNEMP5:YES", label="YES", price=0.25, liquidity=10000.0),
                Outcome(id="kalshi:UNEMP5:NO", label="NO", price=0.75, liquidity=10000.0),
            ],
            end_date=self.expiry_7d,
            expiry=self.expiry_7d,
            liquidity=20000.0,
            volume=50000.0,
            exchange="kalshi",
            tags=["economics", "valid_ab"]
        )]
        
        metadata = [ScenarioMetadata(
            name="cross_venue_with_kalshi_short",
            expected_detection=True,
            expected_approval=True,
            arbitrage_type="CROSS_VENUE_SHORT",
            description="Buy YES on Kalshi (0.25), Short YES on Polymarket (0.35) - requires Kalshi shorting"
        )]
        
        return poly, kalshi, metadata
    
    # ==================== INVALID SCENARIOS ==================== #
    
    def _scenario_single_venue_parity_poly(self) -> Tuple[List[Market], List[Market], List[ScenarioMetadata]]:
        """Single-venue parity on Polymarket only (SHOULD REJECT)."""
        poly = [Market(
            id="poly:single_parity_1",
            question="Will event X happen?",
            outcomes=[
                Outcome(id="poly:single_parity_1:yes", label="YES", price=0.45, liquidity=8000.0),
                Outcome(id="poly:single_parity_1:no", label="NO", price=0.50, liquidity=8000.0),
            ],
            end_date=self.expiry_7d,
            expiry=self.expiry_7d,
            liquidity=16000.0,
            volume=30000.0,
            exchange="polymarket",
            tags=["invalid", "single_venue"]
        )]
        
        kalshi = []  # No Kalshi market for this event
        
        metadata = [ScenarioMetadata(
            name="single_venue_parity_polymarket",
            expected_detection=True,  # Detector will find parity violation
            expected_approval=False,  # Validator will reject (single venue)
            rejection_reason="insufficient_venues",
            arbitrage_type="PARITY",
            description="YES+NO=0.95 on Polymarket only - executable on one venue alone"
        )]
        
        return poly, kalshi, metadata
    
    def _scenario_single_venue_parity_kalshi(self) -> Tuple[List[Market], List[Market], List[ScenarioMetadata]]:
        """Single-venue parity on Kalshi only (SHOULD REJECT)."""
        poly = []  # No Polymarket market
        
        kalshi = [Market(
            id="kalshi:SINGLE-PAR:SINGLE-PAR-T1",
            question="Will event Y happen?",
            outcomes=[
                Outcome(id="kalshi:SINGLE-PAR:YES", label="YES", price=0.44, liquidity=7000.0),
                Outcome(id="kalshi:SINGLE-PAR:NO", label="NO", price=0.51, liquidity=7000.0),
            ],
            end_date=self.expiry_7d,
            expiry=self.expiry_7d,
            liquidity=14000.0,
            volume=25000.0,
            exchange="kalshi",
            tags=["invalid", "single_venue"]
        )]
        
        metadata = [ScenarioMetadata(
            name="single_venue_parity_kalshi",
            expected_detection=True,
            expected_approval=False,
            rejection_reason="insufficient_venues",
            arbitrage_type="PARITY",
            description="YES+NO=0.95 on Kalshi only - executable on one venue alone"
        )]
        
        return poly, kalshi, metadata
    
    def _scenario_polymarket_only(self) -> Tuple[List[Market], List[Market], List[ScenarioMetadata]]:
        """Polymarket-only arbitrage (no corresponding Kalshi market)."""
        poly = [
            Market(
                id="poly:poly_only_1",
                question="Will obscure event happen?",
                outcomes=[
                    Outcome(id="poly:poly_only_1:yes", label="YES", price=0.42, liquidity=5000.0),
                    Outcome(id="poly:poly_only_1:no", label="NO", price=0.53, liquidity=5000.0),
                ],
                end_date=self.expiry_7d,
                expiry=self.expiry_7d,
                liquidity=10000.0,
                volume=20000.0,
                exchange="polymarket",
                tags=["invalid", "single_venue"]
            ),
        ]
        
        kalshi = []  # No Kalshi market
        
        metadata = [ScenarioMetadata(
            name="polymarket_only_arbitrage",
            expected_detection=True,
            expected_approval=False,
            rejection_reason="insufficient_venues",
            arbitrage_type="PARITY",
            description="Parity arbitrage on Polymarket with no Kalshi equivalent"
        )]
        
        return poly, kalshi, metadata
    
    def _scenario_requires_polymarket_short(self) -> Tuple[List[Market], List[Market], List[ScenarioMetadata]]:
        """Arbitrage that would require Polymarket shorting (FORBIDDEN)."""
        poly = [Market(
            id="poly:forbidden_short_1",
            question="Will GDP growth exceed 3%?",
            outcomes=[
                Outcome(id="poly:forbidden_short_1:yes", label="YES", price=0.65, liquidity=10000.0),
                Outcome(id="poly:forbidden_short_1:no", label="NO", price=0.35, liquidity=10000.0),
            ],
            end_date=self.expiry_7d,
            expiry=self.expiry_7d,
            liquidity=20000.0,
            volume=50000.0,
            exchange="polymarket",
            tags=["invalid", "forbidden_short"]
        )]
        
        kalshi = [Market(
            id="kalshi:GDP3:GDP3-T1",
            question="Will GDP growth exceed 3%?",
            outcomes=[
                Outcome(id="kalshi:GDP3:YES", label="YES", price=0.55, liquidity=8000.0),
                Outcome(id="kalshi:GDP3:NO", label="NO", price=0.45, liquidity=8000.0),
            ],
            end_date=self.expiry_7d,
            expiry=self.expiry_7d,
            liquidity=16000.0,
            volume=40000.0,
            exchange="kalshi",
            tags=["invalid", "forbidden_short"]
        )]
        
        metadata = [ScenarioMetadata(
            name="requires_polymarket_short",
            expected_detection=True,  # May detect price difference
            expected_approval=False,  # Will reject due to forbidden action
            rejection_reason="forbidden_action",
            arbitrage_type="DUPLICATE",
            description="Would require SHORT on Polymarket (sell YES at 0.65) - FORBIDDEN"
        )]
        
        return poly, kalshi, metadata
    
    def _scenario_theoretical_arithmetic(self) -> Tuple[List[Market], List[Market], List[ScenarioMetadata]]:
        """Theoretical arithmetic arbitrage without venue constraints."""
        poly = [Market(
            id="poly:theoretical_1",
            question="Will theoretical event occur?",
            outcomes=[
                Outcome(id="poly:theoretical_1:yes", label="YES", price=0.50, liquidity=5000.0),
                Outcome(id="poly:theoretical_1:no", label="NO", price=0.50, liquidity=5000.0),
            ],
            end_date=self.expiry_7d,
            expiry=self.expiry_7d,
            liquidity=10000.0,
            volume=15000.0,
            exchange="polymarket",
            tags=["invalid", "theoretical"]
        )]
        
        kalshi = [Market(
            id="kalshi:THEOR:THEOR-T1",
            question="Will theoretical event occur?",
            outcomes=[
                Outcome(id="kalshi:THEOR:YES", label="YES", price=0.50, liquidity=5000.0),
                Outcome(id="kalshi:THEOR:NO", label="NO", price=0.50, liquidity=5000.0),
            ],
            end_date=self.expiry_7d,
            expiry=self.expiry_7d,
            liquidity=10000.0,
            volume=15000.0,
            exchange="kalshi",
            tags=["invalid", "theoretical"]
        )]
        
        metadata = [ScenarioMetadata(
            name="theoretical_arithmetic",
            expected_detection=False,  # No edge detected
            expected_approval=False,
            rejection_reason="no_edge",
            arbitrage_type="NONE",
            description="No price discrepancy - theoretical test case"
        )]
        
        return poly, kalshi, metadata
    
    def _scenario_low_liquidity(self) -> Tuple[List[Market], List[Market], List[ScenarioMetadata]]:
        """Edge-positive but insufficient liquidity (should reject)."""
        poly = [Market(
            id="poly:low_liq_1",
            question="Will low-liquidity event happen?",
            outcomes=[
                Outcome(id="poly:low_liq_1:yes", label="YES", price=0.40, liquidity=100.0),  # Very low
                Outcome(id="poly:low_liq_1:no", label="NO", price=0.60, liquidity=100.0),
            ],
            end_date=self.expiry_7d,
            expiry=self.expiry_7d,
            liquidity=200.0,  # Below minimum threshold
            volume=500.0,
            exchange="polymarket",
            tags=["invalid", "low_liquidity"]
        )]
        
        kalshi = [Market(
            id="kalshi:LOWLIQ:LOWLIQ-T1",
            question="Will low-liquidity event happen?",
            outcomes=[
                Outcome(id="kalshi:LOWLIQ:YES", label="YES", price=0.55, liquidity=150.0),
                Outcome(id="kalshi:LOWLIQ:NO", label="NO", price=0.45, liquidity=150.0),
            ],
            end_date=self.expiry_7d,
            expiry=self.expiry_7d,
            liquidity=300.0,
            volume=600.0,
            exchange="kalshi",
            tags=["invalid", "low_liquidity"]
        )]
        
        metadata = [ScenarioMetadata(
            name="low_liquidity_rejection",
            expected_detection=True,  # Will detect edge
            expected_approval=False,  # Will reject due to low liquidity
            rejection_reason="insufficient_liquidity",
            arbitrage_type="CROSS_VENUE_PARITY",
            description="Valid edge (0.15) but liquidity < minimum threshold"
        )]
        
        return poly, kalshi, metadata
    
    # ==================== NEW VALID SCENARIOS ==================== #
    
    def _scenario_range_replication_valid(self) -> Tuple[List[Market], List[Market], List[ScenarioMetadata]]:
        """Cross-venue range replication: Replicate payoff range using short on venue A."""
        # Scenario: Replicate a 50-60k range using:
        # - BUY >50k on Polymarket (enters at lower bound)
        # - SHORT >60k on Kalshi (exits at upper bound)
        
        poly = [Market(
            id="poly:range_repl_50k",
            question="Will index close above 50,000?",
            outcomes=[
                Outcome(id="poly:range_50k:yes", label="YES", price=0.60, liquidity=15000.0),
                Outcome(id="poly:range_50k:no", label="NO", price=0.40, liquidity=15000.0),
            ],
            end_date=self.expiry_7d,
            expiry=self.expiry_7d,
            liquidity=30000.0,
            volume=80000.0,
            exchange="polymarket",
            tags=["finance", "valid_ab", "range_replication"],
            threshold=50000.0,
            comparator=">"
        )]
        
        kalshi = [Market(
            id="kalshi:RANGE60K:RANGE60K-T1",
            question="Will index close above 60,000?",
            outcomes=[
                Outcome(id="kalshi:RANGE60K:YES", label="YES", price=0.45, liquidity=12000.0),
                Outcome(id="kalshi:RANGE60K:NO", label="NO", price=0.55, liquidity=12000.0),
            ],
            end_date=self.expiry_7d,
            expiry=self.expiry_7d,
            liquidity=24000.0,
            volume=60000.0,
            exchange="kalshi",
            tags=["finance", "valid_ab", "range_replication"],
            threshold=60000.0,
            comparator=">"
        )]
        
        metadata = [ScenarioMetadata(
            name="cross_venue_range_replication",
            expected_detection=True,
            expected_approval=True,
            arbitrage_type="RANGE_REPLICATION",
            description="Replicate 50k-60k payoff range: BUY >50k@Poly(0.60) + SHORT >60k@Kalshi(0.45)"
        )]
        
        return poly, kalshi, metadata
    
    def _scenario_multi_outcome_additivity_valid(self) -> Tuple[List[Market], List[Market], List[ScenarioMetadata]]:
        """Cross-venue multi-outcome: Sum of outcomes across venues violates probability laws."""
        # Scenario: Election with 3 candidates across venues
        # Venue A prices sum to 1.05 (overpriced)
        # Venue B prices sum to 0.92 (underpriced)
        # Arbitrage: Sell overpriced on A, buy underpriced on B
        
        poly = [Market(
            id="poly:election_multi_3way",
            question="Who will win the election?",
            outcomes=[
                Outcome(id="poly:election:alice", label="Alice", price=0.30, liquidity=10000.0),
                Outcome(id="poly:election:bob", label="Bob", price=0.35, liquidity=10000.0),
                Outcome(id="poly:election:carol", label="Carol", price=0.27, liquidity=10000.0),
            ],
            end_date=self.expiry_30d,
            expiry=self.expiry_30d,
            liquidity=30000.0,
            volume=100000.0,
            exchange="polymarket",
            tags=["politics", "valid_ab", "multi_outcome"]
        )]
        
        kalshi = [Market(
            id="kalshi:ELECT3:ELECT3-T1",
            question="Who will win the election?",
            outcomes=[
                Outcome(id="kalshi:ELECT3:ALICE", label="Alice", price=0.35, liquidity=8000.0),
                Outcome(id="kalshi:ELECT3:BOB", label="Bob", price=0.40, liquidity=8000.0),
                Outcome(id="kalshi:ELECT3:CAROL", label="Carol", price=0.30, liquidity=8000.0),
            ],
            end_date=self.expiry_30d,
            expiry=self.expiry_30d,
            liquidity=24000.0,
            volume=80000.0,
            exchange="kalshi",
            tags=["politics", "valid_ab", "multi_outcome"]
        )]
        
        metadata = [ScenarioMetadata(
            name="cross_venue_multi_outcome_additivity",
            expected_detection=True,
            expected_approval=True,
            arbitrage_type="MULTI_OUTCOME",
            description="3-way election: Poly sum=0.92, Kalshi sum=1.05 - buy basket on Poly, short on Kalshi"
        )]
        
        return poly, kalshi, metadata
    
    def _scenario_composite_vs_components_valid(self) -> Tuple[List[Market], List[Market], List[ScenarioMetadata]]:
        """Cross-venue composite: Composite market mispriced vs component markets."""
        # Scenario: "Team wins championship" can be decomposed into "Team wins semifinal" AND "Team wins final"
        # P(wins championship) should ≤ P(wins semifinal)
        # If Kalshi prices championship higher than Poly prices semifinal, arbitrage exists
        
        poly = [Market(
            id="poly:composite_semifinal",
            question="Will Team X win the semifinal?",
            outcomes=[
                Outcome(id="poly:semi:yes", label="YES", price=0.70, liquidity=12000.0),
                Outcome(id="poly:semi:no", label="NO", price=0.30, liquidity=12000.0),
            ],
            end_date=self.expiry_7d,
            expiry=self.expiry_7d,
            liquidity=24000.0,
            volume=60000.0,
            exchange="polymarket",
            tags=["sports", "valid_ab", "composite"]
        )]
        
        kalshi = [Market(
            id="kalshi:CHAMP:CHAMP-T1",
            question="Will Team X win the championship?",
            outcomes=[
                Outcome(id="kalshi:CHAMP:YES", label="YES", price=0.75, liquidity=10000.0),
                Outcome(id="kalshi:CHAMP:NO", label="NO", price=0.25, liquidity=10000.0),
            ],
            end_date=self.expiry_30d,
            expiry=self.expiry_30d,
            liquidity=20000.0,
            volume=50000.0,
            exchange="kalshi",
            tags=["sports", "valid_ab", "composite"]
        )]
        
        metadata = [ScenarioMetadata(
            name="cross_venue_composite_vs_components",
            expected_detection=True,
            expected_approval=True,
            arbitrage_type="COMPOSITE",
            description="Championship(0.75@Kalshi) > Semifinal(0.70@Poly) violates P(A∩B) ≤ P(A)"
        )]
        
        return poly, kalshi, metadata
    
    def _scenario_calendar_basis_valid(self) -> Tuple[List[Market], List[Market], List[ScenarioMetadata]]:
        """Cross-venue calendar basis: Same event, different expiry dates."""
        # Scenario: BTC > 100k with different expiry dates
        # Near-term (7d) should be ≤ far-term (30d) for same strike
        # If near-term@Kalshi > far-term@Poly, calendar arbitrage exists
        
        poly = [Market(
            id="poly:btc100k_far",
            question="Will BTC exceed $100k by end of month?",
            outcomes=[
                Outcome(id="poly:btc_far:yes", label="YES", price=0.50, liquidity=15000.0),
                Outcome(id="poly:btc_far:no", label="NO", price=0.50, liquidity=15000.0),
            ],
            end_date=self.expiry_30d,
            expiry=self.expiry_30d,
            liquidity=30000.0,
            volume=100000.0,
            exchange="polymarket",
            tags=["crypto", "valid_ab", "calendar_basis"]
        )]
        
        kalshi = [Market(
            id="kalshi:BTC100K-NEAR:BTC100K-NEAR-T1",
            question="Will BTC exceed $100k this week?",
            outcomes=[
                Outcome(id="kalshi:BTC100K-NEAR:YES", label="YES", price=0.55, liquidity=12000.0),
                Outcome(id="kalshi:BTC100K-NEAR:NO", label="NO", price=0.45, liquidity=12000.0),
            ],
            end_date=self.expiry_7d,
            expiry=self.expiry_7d,
            liquidity=24000.0,
            volume=80000.0,
            exchange="kalshi",
            tags=["crypto", "valid_ab", "calendar_basis"]
        )]
        
        metadata = [ScenarioMetadata(
            name="cross_venue_calendar_basis",
            expected_detection=True,
            expected_approval=True,
            arbitrage_type="CALENDAR_BASIS",
            description="Near-term@Kalshi(0.55) > Far-term@Poly(0.50) violates time-value (flagged as special case)"
        )]
        
        return poly, kalshi, metadata
    
    # ==================== NEW INVALID SCENARIOS ==================== #
    
    def _scenario_range_replication_invalid(self) -> Tuple[List[Market], List[Market], List[ScenarioMetadata]]:
        """Range replication INVALID: Polymarket-only, no cross-venue component."""
        poly = [
            Market(
                id="poly:range_invalid_40k",
                question="Will index close above 40,000?",
                outcomes=[
                    Outcome(id="poly:range_inv_40k:yes", label="YES", price=0.75, liquidity=8000.0),
                    Outcome(id="poly:range_inv_40k:no", label="NO", price=0.25, liquidity=8000.0),
                ],
                end_date=self.expiry_7d,
                expiry=self.expiry_7d,
                liquidity=16000.0,
                volume=40000.0,
                exchange="polymarket",
                tags=["invalid", "single_venue"],
                threshold=40000.0,
                comparator=">"
            ),
            Market(
                id="poly:range_invalid_45k",
                question="Will index close above 45,000?",
                outcomes=[
                    Outcome(id="poly:range_inv_45k:yes", label="YES", price=0.68, liquidity=8000.0),
                    Outcome(id="poly:range_inv_45k:no", label="NO", price=0.32, liquidity=8000.0),
                ],
                end_date=self.expiry_7d,
                expiry=self.expiry_7d,
                liquidity=16000.0,
                volume=40000.0,
                exchange="polymarket",
                tags=["invalid", "single_venue"],
                threshold=45000.0,
                comparator=">"
            ),
        ]
        
        kalshi = []  # No Kalshi markets - single venue only
        
        metadata = [ScenarioMetadata(
            name="range_replication_polymarket_only",
            expected_detection=True,  # Ladder detector may find it
            expected_approval=False,  # Validator rejects (single venue)
            rejection_reason="insufficient_venues",
            arbitrage_type="LADDER",
            description="Range 40k-45k on Polymarket only - executable on one venue alone"
        )]
        
        return poly, kalshi, metadata
    
    def _scenario_multi_outcome_invalid(self) -> Tuple[List[Market], List[Market], List[ScenarioMetadata]]:
        """Multi-outcome INVALID: Would require Polymarket shorting."""
        # Scenario: Sum violation but would need to short multiple outcomes on Polymarket
        poly = [Market(
            id="poly:multi_invalid",
            question="Tournament winner (4 teams)?",
            outcomes=[
                Outcome(id="poly:multi_inv:team_a", label="Team A", price=0.28, liquidity=6000.0),
                Outcome(id="poly:multi_inv:team_b", label="Team B", price=0.29, liquidity=6000.0),
                Outcome(id="poly:multi_inv:team_c", label="Team C", price=0.22, liquidity=6000.0),
                Outcome(id="poly:multi_inv:team_d", label="Team D", price=0.26, liquidity=6000.0),
            ],
            end_date=self.expiry_7d,
            expiry=self.expiry_7d,
            liquidity=24000.0,
            volume=50000.0,
            exchange="polymarket",
            tags=["invalid", "forbidden_short"]
        )]
        
        kalshi = [Market(
            id="kalshi:TOURN4:TOURN4-T1",
            question="Tournament winner (4 teams)?",
            outcomes=[
                Outcome(id="kalshi:TOURN4:TEAM_A", label="Team A", price=0.24, liquidity=5000.0),
                Outcome(id="kalshi:TOURN4:TEAM_B", label="Team B", price=0.25, liquidity=5000.0),
                Outcome(id="kalshi:TOURN4:TEAM_C", label="Team C", price=0.26, liquidity=5000.0),
                Outcome(id="kalshi:TOURN4:TEAM_D", label="Team D", price=0.20, liquidity=5000.0),
            ],
            end_date=self.expiry_7d,
            expiry=self.expiry_7d,
            liquidity=20000.0,
            volume=40000.0,
            exchange="kalshi",
            tags=["invalid", "forbidden_short"]
        )]
        
        metadata = [ScenarioMetadata(
            name="multi_outcome_requires_polymarket_short",
            expected_detection=True,  # May detect sum violation
            expected_approval=False,  # Rejects (would need Poly short)
            rejection_reason="forbidden_action",
            arbitrage_type="EXCLUSIVE_SUM",
            description="Poly sum=1.05, Kalshi sum=0.95 but arbitrage requires shorting on Polymarket"
        )]
        
        return poly, kalshi, metadata
    
    def _scenario_composite_invalid(self) -> Tuple[List[Market], List[Market], List[ScenarioMetadata]]:
        """Composite INVALID: Single venue, no cross-venue component."""
        poly = [
            Market(
                id="poly:composite_invalid_final",
                question="Will Team Y reach the final?",
                outcomes=[
                    Outcome(id="poly:comp_inv:yes", label="YES", price=0.55, liquidity=8000.0),
                    Outcome(id="poly:comp_inv:no", label="NO", price=0.45, liquidity=8000.0),
                ],
                end_date=self.expiry_7d,
                expiry=self.expiry_7d,
                liquidity=16000.0,
                volume=40000.0,
                exchange="polymarket",
                tags=["invalid", "single_venue"]
            ),
            Market(
                id="poly:composite_invalid_win",
                question="Will Team Y win the final?",
                outcomes=[
                    Outcome(id="poly:comp_win:yes", label="YES", price=0.60, liquidity=8000.0),
                    Outcome(id="poly:comp_win:no", label="NO", price=0.40, liquidity=8000.0),
                ],
                end_date=self.expiry_7d,
                expiry=self.expiry_7d,
                liquidity=16000.0,
                volume=40000.0,
                exchange="polymarket",
                tags=["invalid", "single_venue"]
            ),
        ]
        
        kalshi = []  # No Kalshi component
        
        metadata = [ScenarioMetadata(
            name="composite_single_venue_only",
            expected_detection=True,  # Consistency detector may find logical violation
            expected_approval=False,  # Rejects (single venue)
            rejection_reason="insufficient_venues",
            arbitrage_type="CONSISTENCY",
            description="P(win final)=0.60 > P(reach final)=0.55 but only on Polymarket"
        )]
        
        return poly, kalshi, metadata
    
    def _scenario_calendar_basis_invalid(self) -> Tuple[List[Market], List[Market], List[ScenarioMetadata]]:
        """Calendar basis INVALID: Insufficient time spread or liquidity."""
        poly = [Market(
            id="poly:calendar_invalid_near",
            question="Will event occur within 24 hours?",
            outcomes=[
                Outcome(id="poly:cal_inv:yes", label="YES", price=0.48, liquidity=500.0),  # Low liquidity
                Outcome(id="poly:cal_inv:no", label="NO", price=0.52, liquidity=500.0),
            ],
            end_date=self.now + timedelta(hours=24),
            expiry=self.now + timedelta(hours=24),
            liquidity=1000.0,  # Below minimum
            volume=2000.0,
            exchange="polymarket",
            tags=["invalid", "low_liquidity"]
        )]
        
        kalshi = [Market(
            id="kalshi:CALINV:CALINV-T1",
            question="Will event occur within 24 hours?",
            outcomes=[
                Outcome(id="kalshi:CALINV:YES", label="YES", price=0.52, liquidity=600.0),
                Outcome(id="kalshi:CALINV:NO", label="NO", price=0.48, liquidity=600.0),
            ],
            end_date=self.now + timedelta(hours=24),
            expiry=self.now + timedelta(hours=24),
            liquidity=1200.0,  # Below minimum
            volume=2500.0,
            exchange="kalshi",
            tags=["invalid", "low_liquidity"]
        )]
        
        metadata = [ScenarioMetadata(
            name="calendar_basis_insufficient_liquidity",
            expected_detection=True,  # May detect price difference
            expected_approval=False,  # Rejects (low liquidity, near expiry)
            rejection_reason="insufficient_liquidity",
            arbitrage_type="TIMELAG",
            description="Calendar spread exists but liquidity < minimum and expiry < 48h"
        )]
        
        return poly, kalshi, metadata


def get_strict_ab_scenario(seed: int = 42) -> Tuple[List[Market], List[Market], List[ScenarioMetadata]]:
    """
    Convenience function to generate all strict A+B scenarios.
    
    Returns:
        Tuple of (polymarket_markets, kalshi_markets, scenario_metadata)
    """
    generator = StrictABScenarios(seed=seed)
    return generator.generate_all_scenarios()
