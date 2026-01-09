"""
Comprehensive cross-venue arbitrage scenario generator.

Creates coordinated market fixtures across TWO venues (Polymarket + Kalshi) that plant
specific arbitrage opportunities and edge cases for deterministic stress testing.
"""
import random
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Dict, Any, Tuple
from src.predarb.models import Market, Outcome


class CrossVenueArbitrageScenarios:
    """
    Generator for comprehensive cross-venue arbitrage test scenarios.
    
    Creates markets across both venues with planted opportunities for every arbitrage type:
    - Cross-venue duplicate arbitrage (same event, different prices)
    - Parity violations (YES+NO != 1.0)
    - Ladder monotonicity violations
    - Exclusive-sum constraint violations
    - Time-lag / stale quote arbitrage
    - Cross-market consistency violations
    
    Plus negative cases and edge cases for each type.
    """
    
    def __init__(self, seed: int = 42):
        self.seed = seed
        random.seed(seed)
        # Use timezone-aware datetime consistently
        self.now = datetime.now(timezone.utc).replace(tzinfo=None)  # Strip timezone for compatibility
    
    def generate_all_scenarios(self) -> Tuple[List[Market], List[Market]]:
        """
        Generate comprehensive test suite covering ALL arbitrage types.
        
        Returns:
            Tuple of (polymarket_markets, kalshi_markets)
        """
        poly_markets = []
        kalshi_markets = []
        
        # A. Cross-venue duplicate arbitrage
        poly_a, kalshi_a = self._generate_duplicate_arbitrage()
        poly_markets.extend(poly_a)
        kalshi_markets.extend(kalshi_a)
        
        # B. Parity violations (within single venue)
        poly_b, kalshi_b = self._generate_parity_violations()
        poly_markets.extend(poly_b)
        kalshi_markets.extend(kalshi_b)
        
        # C. Ladder monotonicity violations
        poly_c, kalshi_c = self._generate_ladder_violations()
        poly_markets.extend(poly_c)
        kalshi_markets.extend(kalshi_c)
        
        # D. Exclusive-sum constraint violations
        poly_d, kalshi_d = self._generate_exclusive_sum_violations()
        poly_markets.extend(poly_d)
        kalshi_markets.extend(kalshi_d)
        
        # E. Time-lag / stale quote arbitrage
        poly_e, kalshi_e = self._generate_timelag_arbitrage()
        poly_markets.extend(poly_e)
        kalshi_markets.extend(kalshi_e)
        
        # F. Consistency / cross-market violations
        poly_f, kalshi_f = self._generate_consistency_violations()
        poly_markets.extend(poly_f)
        kalshi_markets.extend(kalshi_f)
        
        # G. Operational edge cases
        poly_g, kalshi_g = self._generate_operational_edge_cases()
        poly_markets.extend(poly_g)
        kalshi_markets.extend(kalshi_g)
        
        return poly_markets, kalshi_markets
    
    def _generate_duplicate_arbitrage(self) -> Tuple[List[Market], List[Market]]:
        """
        Generate cross-venue duplicate arbitrage scenarios.
        
        Cases:
        1. Profitable duplicate (clear price difference)
        2. Near-zero edge (should be filtered out)
        3. Edge disappears after fees (negative after costs)
        4. Reverse direction (B->A instead of A->B)
        """
        poly = []
        kalshi = []
        expiry = self.now + timedelta(days=7)
        
        # Case 1: Profitable duplicate (Poly YES=0.45, Kalshi YES=0.60)
        poly.append(Market(
            id="poly:dup_profit_1",
            question="Will candidate win the election?",
            outcomes=[
                Outcome(id="poly:dup_profit_1:yes", label="YES", price=0.45, liquidity=10000.0),
                Outcome(id="poly:dup_profit_1:no", label="NO", price=0.55, liquidity=10000.0),
            ],
            end_date=expiry,
            expiry=expiry,
            liquidity=20000.0,
            volume=50000.0,
            tags=["politics", "duplicate"],
            exchange="polymarket",
        ))
        kalshi.append(Market(
            id="kalshi:ELEC-WIN:ELEC-WIN-T1",
            question="Will candidate win the election?",
            outcomes=[
                Outcome(id="kalshi:ELEC-WIN:YES", label="YES", price=0.60, liquidity=8000.0),
                Outcome(id="kalshi:ELEC-WIN:NO", label="NO", price=0.40, liquidity=8000.0),
            ],
            end_date=expiry,
            expiry=expiry,
            liquidity=16000.0,
            volume=30000.0,
            tags=["politics", "duplicate"],
            exchange="kalshi",
        ))
        
        # Case 2: Near-zero edge (Poly=0.495, Kalshi=0.505 -> 1% gross, <0% after fees)
        poly.append(Market(
            id="poly:dup_tiny_edge",
            question="Will stock index close above threshold?",
            outcomes=[
                Outcome(id="poly:dup_tiny:yes", label="YES", price=0.495, liquidity=5000.0),
                Outcome(id="poly:dup_tiny:no", label="NO", price=0.505, liquidity=5000.0),
            ],
            end_date=expiry,
            expiry=expiry,
            liquidity=10000.0,
            volume=20000.0,
            tags=["finance"],
            exchange="polymarket",
        ))
        kalshi.append(Market(
            id="kalshi:INDEX-THR:INDEX-THR-T1",
            question="Will stock index close above threshold?",
            outcomes=[
                Outcome(id="kalshi:INDEX:YES", label="YES", price=0.505, liquidity=5000.0),
                Outcome(id="kalshi:INDEX:NO", label="NO", price=0.495, liquidity=5000.0),
            ],
            end_date=expiry,
            expiry=expiry,
            liquidity=10000.0,
            volume=15000.0,
            tags=["finance"],
            exchange="kalshi",
        ))
        
        # Case 3: Edge disappears after fees (Poly=0.47, Kalshi=0.52 -> 5% gross but high fees)
        # With 0.5% fee each side = 1% total, plus slippage, may eliminate profit
        poly.append(Market(
            id="poly:dup_fee_killer",
            question="Will crypto price reach target by deadline?",
            outcomes=[
                Outcome(id="poly:dup_fee:yes", label="YES", price=0.47, liquidity=3000.0),
                Outcome(id="poly:dup_fee:no", label="NO", price=0.53, liquidity=3000.0),
            ],
            end_date=expiry,
            expiry=expiry,
            liquidity=6000.0,
            volume=10000.0,
            tags=["crypto"],
            exchange="polymarket",
        ))
        kalshi.append(Market(
            id="kalshi:CRYPTO-PRICE:CRYPTO-T1",
            question="Will crypto price reach target by deadline?",
            outcomes=[
                Outcome(id="kalshi:CRYPTO:YES", label="YES", price=0.52, liquidity=3000.0),
                Outcome(id="kalshi:CRYPTO:NO", label="NO", price=0.48, liquidity=3000.0),
            ],
            end_date=expiry,
            expiry=expiry,
            liquidity=6000.0,
            volume=8000.0,
            tags=["crypto"],
            exchange="kalshi",
        ))
        
        # Case 4: Reverse direction (Kalshi cheaper than Poly)
        poly.append(Market(
            id="poly:dup_reverse",
            question="Will tech stock beat earnings?",
            outcomes=[
                Outcome(id="poly:dup_rev:yes", label="YES", price=0.68, liquidity=12000.0),
                Outcome(id="poly:dup_rev:no", label="NO", price=0.32, liquidity=12000.0),
            ],
            end_date=expiry,
            expiry=expiry,
            liquidity=24000.0,
            volume=40000.0,
            tags=["tech", "earnings"],
            exchange="polymarket",
        ))
        kalshi.append(Market(
            id="kalshi:TECH-EARN:TECH-EARN-T1",
            question="Will tech stock beat earnings?",
            outcomes=[
                Outcome(id="kalshi:TECH:YES", label="YES", price=0.55, liquidity=10000.0),
                Outcome(id="kalshi:TECH:NO", label="NO", price=0.45, liquidity=10000.0),
            ],
            end_date=expiry,
            expiry=expiry,
            liquidity=20000.0,
            volume=35000.0,
            tags=["tech", "earnings"],
            exchange="kalshi",
        ))
        
        return poly, kalshi
    
    def _generate_parity_violations(self) -> Tuple[List[Market], List[Market]]:
        """
        Generate parity violation scenarios (YES+NO != 1.0 within single venue).
        
        Cases:
        1. Clear profitable parity (YES+NO = 0.90)
        2. Borderline parity (YES+NO = 0.98, marginal after fees)
        3. Rejected after slippage (YES+NO = 0.985, not enough edge)
        4. Multi-outcome parity violation
        """
        poly = []
        kalshi = []
        expiry = self.now + timedelta(days=10)
        
        # Case 1: Clear profitable parity on Polymarket
        poly.append(Market(
            id="poly:parity_profit",
            question="Will referendum pass?",
            outcomes=[
                Outcome(id="poly:parity_prof:yes", label="YES", price=0.44, liquidity=15000.0),
                Outcome(id="poly:parity_prof:no", label="NO", price=0.46, liquidity=15000.0),
            ],
            end_date=expiry,
            expiry=expiry,
            liquidity=30000.0,
            volume=60000.0,
            tags=["politics", "parity"],
            exchange="polymarket",
        ))
        
        # Case 2: Borderline parity on Kalshi (YES+NO = 0.98)
        kalshi.append(Market(
            id="kalshi:PARITY-BORD:PARITY-T1",
            question="Will unemployment rate drop?",
            outcomes=[
                Outcome(id="kalshi:PARITY:YES", label="YES", price=0.49, liquidity=8000.0),
                Outcome(id="kalshi:PARITY:NO", label="NO", price=0.49, liquidity=8000.0),
            ],
            end_date=expiry,
            expiry=expiry,
            liquidity=16000.0,
            volume=25000.0,
            tags=["economics", "parity"],
            exchange="kalshi",
        ))
        
        # Case 3: Rejected after slippage (YES+NO = 0.985)
        poly.append(Market(
            id="poly:parity_reject",
            question="Will team win championship?",
            outcomes=[
                Outcome(id="poly:parity_rej:yes", label="YES", price=0.492, liquidity=5000.0),
                Outcome(id="poly:parity_rej:no", label="NO", price=0.493, liquidity=5000.0),
            ],
            end_date=expiry,
            expiry=expiry,
            liquidity=10000.0,
            volume=15000.0,
            tags=["sports", "parity"],
            exchange="polymarket",
        ))
        
        # Case 4: Multi-outcome parity violation (3 outcomes, sum < 1.0)
        kalshi.append(Market(
            id="kalshi:MULTI-PAR:MULTI-T1",
            question="Which party will control senate?",
            outcomes=[
                Outcome(id="kalshi:MULTI:DEM", label="Democrat", price=0.30, liquidity=7000.0),
                Outcome(id="kalshi:MULTI:REP", label="Republican", price=0.30, liquidity=7000.0),
                Outcome(id="kalshi:MULTI:IND", label="Independent", price=0.30, liquidity=7000.0),
            ],
            end_date=expiry,
            expiry=expiry,
            liquidity=21000.0,
            volume=40000.0,
            tags=["politics", "multi-outcome"],
            exchange="kalshi",
        ))
        
        return poly, kalshi
    
    def _generate_ladder_violations(self) -> Tuple[List[Market], List[Market]]:
        """
        Generate ladder monotonicity violation scenarios.
        
        Cases:
        1. Strict violation (price goes UP for worse outcome)
        2. Tiny violation (below threshold)
        3. Equal-threshold edge case (prices exactly equal)
        """
        poly = []
        kalshi = []
        expiry = self.now + timedelta(days=14)
        
        # Case 1: Strict ladder violation on Polymarket
        # Temperature thresholds: >30°C should be MORE likely than >35°C but isn't
        poly.append(Market(
            id="poly:ladder_strict_30",
            question="Will temperature exceed 30°C?",
            outcomes=[
                Outcome(id="poly:ladder_30:yes", label="YES", price=0.40, liquidity=8000.0),
                Outcome(id="poly:ladder_30:no", label="NO", price=0.60, liquidity=8000.0),
            ],
            end_date=expiry,
            expiry=expiry,
            liquidity=16000.0,
            volume=20000.0,
            tags=["weather", "ladder"],
            exchange="polymarket",
        ))
        poly.append(Market(
            id="poly:ladder_strict_35",
            question="Will temperature exceed 35°C?",
            outcomes=[
                Outcome(id="poly:ladder_35:yes", label="YES", price=0.55, liquidity=8000.0),  # VIOLATION: Higher than 30°C!
                Outcome(id="poly:ladder_35:no", label="NO", price=0.45, liquidity=8000.0),
            ],
            end_date=expiry,
            expiry=expiry,
            liquidity=16000.0,
            volume=18000.0,
            tags=["weather", "ladder"],
            exchange="polymarket",
        ))
        
        # Case 2: Tiny violation on Kalshi (below threshold)
        kalshi.append(Market(
            id="kalshi:LADDER-TINY-100:T1",
            question="Will stock close above $100?",
            outcomes=[
                Outcome(id="kalshi:L100:YES", label="YES", price=0.50, liquidity=5000.0),
                Outcome(id="kalshi:L100:NO", label="NO", price=0.50, liquidity=5000.0),
            ],
            end_date=expiry,
            expiry=expiry,
            liquidity=10000.0,
            volume=15000.0,
            tags=["finance", "ladder"],
            exchange="kalshi",
        ))
        kalshi.append(Market(
            id="kalshi:LADDER-TINY-105:T1",
            question="Will stock close above $105?",
            outcomes=[
                Outcome(id="kalshi:L105:YES", label="YES", price=0.505, liquidity=5000.0),  # Only 0.5% higher
                Outcome(id="kalshi:L105:NO", label="NO", price=0.495, liquidity=5000.0),
            ],
            end_date=expiry,
            expiry=expiry,
            liquidity=10000.0,
            volume=14000.0,
            tags=["finance", "ladder"],
            exchange="kalshi",
        ))
        
        # Case 3: Equal-threshold edge case
        poly.append(Market(
            id="poly:ladder_equal_50",
            question="Will score be at least 50 points?",
            outcomes=[
                Outcome(id="poly:leq_50:yes", label="YES", price=0.60, liquidity=6000.0),
                Outcome(id="poly:leq_50:no", label="NO", price=0.40, liquidity=6000.0),
            ],
            end_date=expiry,
            expiry=expiry,
            liquidity=12000.0,
            volume=25000.0,
            tags=["sports", "ladder"],
            exchange="polymarket",
        ))
        poly.append(Market(
            id="poly:ladder_equal_60",
            question="Will score be at least 60 points?",
            outcomes=[
                Outcome(id="poly:leq_60:yes", label="YES", price=0.60, liquidity=6000.0),  # Exactly equal!
                Outcome(id="poly:leq_60:no", label="NO", price=0.40, liquidity=6000.0),
            ],
            end_date=expiry,
            expiry=expiry,
            liquidity=12000.0,
            volume=24000.0,
            tags=["sports", "ladder"],
            exchange="polymarket",
        ))
        
        return poly, kalshi
    
    def _generate_exclusive_sum_violations(self) -> Tuple[List[Market], List[Market]]:
        """
        Generate exclusive-sum constraint violation scenarios.
        
        Cases:
        1. Profitable correction (mutually exclusive outcomes sum > 1.0)
        2. Rejected due to insufficient depth
        """
        poly = []
        kalshi = []
        expiry = self.now + timedelta(days=20)
        
        # Case 1: Profitable exclusive-sum violation
        # Three candidates, only one can win, but probabilities sum to 1.20
        poly.append(Market(
            id="poly:excl_cand_a",
            question="Will Candidate A win primary?",
            outcomes=[
                Outcome(id="poly:excl_a:yes", label="YES", price=0.45, liquidity=10000.0),
                Outcome(id="poly:excl_a:no", label="NO", price=0.55, liquidity=10000.0),
            ],
            end_date=expiry,
            expiry=expiry,
            liquidity=20000.0,
            volume=30000.0,
            tags=["politics", "exclusive"],
            exchange="polymarket",
        ))
        poly.append(Market(
            id="poly:excl_cand_b",
            question="Will Candidate B win primary?",
            outcomes=[
                Outcome(id="poly:excl_b:yes", label="YES", price=0.40, liquidity=10000.0),
                Outcome(id="poly:excl_b:no", label="NO", price=0.60, liquidity=10000.0),
            ],
            end_date=expiry,
            expiry=expiry,
            liquidity=20000.0,
            volume=28000.0,
            tags=["politics", "exclusive"],
            exchange="polymarket",
        ))
        poly.append(Market(
            id="poly:excl_cand_c",
            question="Will Candidate C win primary?",
            outcomes=[
                Outcome(id="poly:excl_c:yes", label="YES", price=0.35, liquidity=10000.0),
                Outcome(id="poly:excl_c:no", label="NO", price=0.65, liquidity=10000.0),
            ],
            end_date=expiry,
            expiry=expiry,
            liquidity=20000.0,
            volume=25000.0,
            tags=["politics", "exclusive"],
            exchange="polymarket",
        ))
        
        # Case 2: Exclusive-sum violation but insufficient depth (should reject)
        kalshi.append(Market(
            id="kalshi:EXCL-DEPTH-A:T1",
            question="Which team wins tournament?",
            outcomes=[
                Outcome(id="kalshi:EXCL_A:YES", label="Team A", price=0.60, liquidity=500.0),  # Low liquidity
                Outcome(id="kalshi:EXCL_A:NO", label="NOT Team A", price=0.40, liquidity=500.0),
            ],
            end_date=expiry,
            expiry=expiry,
            liquidity=1000.0,
            volume=2000.0,
            tags=["sports", "exclusive"],
            exchange="kalshi",
        ))
        kalshi.append(Market(
            id="kalshi:EXCL-DEPTH-B:T1",
            question="Which team wins tournament?",
            outcomes=[
                Outcome(id="kalshi:EXCL_B:YES", label="Team B", price=0.55, liquidity=500.0),
                Outcome(id="kalshi:EXCL_B:NO", label="NOT Team B", price=0.45, liquidity=500.0),
            ],
            end_date=expiry,
            expiry=expiry,
            liquidity=1000.0,
            volume=1800.0,
            tags=["sports", "exclusive"],
            exchange="kalshi",
        ))
        
        return poly, kalshi
    
    def _generate_timelag_arbitrage(self) -> Tuple[List[Market], List[Market]]:
        """
        Generate time-lag / stale quote arbitrage scenarios.
        
        Cases:
        1. Stale timestamp on one venue (within acceptable lag)
        2. Max-staleness rejection (timestamp too old)
        """
        poly = []
        kalshi = []
        expiry = self.now + timedelta(days=5)
        
        # Case 1: Acceptable time lag (5 minutes stale, price divergence)
        stale_time = self.now - timedelta(minutes=5)
        poly.append(Market(
            id="poly:timelag_fresh",
            question="Will breaking news event occur?",
            outcomes=[
                Outcome(
                    id="poly:timelag:yes",
                    label="YES",
                    price=0.70,
                    liquidity=8000.0,
                    last_updated=self.now,  # Fresh
                ),
                Outcome(
                    id="poly:timelag:no",
                    label="NO",
                    price=0.30,
                    liquidity=8000.0,
                    last_updated=self.now,
                ),
            ],
            end_date=expiry,
            expiry=expiry,
            liquidity=16000.0,
            volume=20000.0,
            tags=["news", "timelag"],
            updated_at=self.now,
            exchange="polymarket",
        ))
        kalshi.append(Market(
            id="kalshi:TIMELAG-STALE:T1",
            question="Will breaking news event occur?",
            outcomes=[
                Outcome(
                    id="kalshi:TL:YES",
                    label="YES",
                    price=0.50,  # Stale price, not updated
                    liquidity=6000.0,
                    last_updated=stale_time,
                ),
                Outcome(
                    id="kalshi:TL:NO",
                    label="NO",
                    price=0.50,
                    liquidity=6000.0,
                    last_updated=stale_time,
                ),
            ],
            end_date=expiry,
            expiry=expiry,
            liquidity=12000.0,
            volume=15000.0,
            tags=["news", "timelag"],
            updated_at=stale_time,
            exchange="kalshi",
        ))
        
        # Case 2: Max-staleness rejection (60 minutes old, should reject)
        very_stale = self.now - timedelta(minutes=60)
        poly.append(Market(
            id="poly:timelag_reject_fresh",
            question="Will scheduled announcement happen?",
            outcomes=[
                Outcome(
                    id="poly:tlr:yes",
                    label="YES",
                    price=0.65,
                    liquidity=5000.0,
                    last_updated=self.now,
                ),
                Outcome(
                    id="poly:tlr:no",
                    label="NO",
                    price=0.35,
                    liquidity=5000.0,
                    last_updated=self.now,
                ),
            ],
            end_date=expiry,
            expiry=expiry,
            liquidity=10000.0,
            volume=12000.0,
            tags=["news"],
            updated_at=self.now,
            exchange="polymarket",
        ))
        kalshi.append(Market(
            id="kalshi:TIMELAG-VERYSTALE:T1",
            question="Will scheduled announcement happen?",
            outcomes=[
                Outcome(
                    id="kalshi:TVS:YES",
                    label="YES",
                    price=0.45,
                    liquidity=4000.0,
                    last_updated=very_stale,  # 60 min old
                ),
                Outcome(
                    id="kalshi:TVS:NO",
                    label="NO",
                    price=0.55,
                    liquidity=4000.0,
                    last_updated=very_stale,
                ),
            ],
            end_date=expiry,
            expiry=expiry,
            liquidity=8000.0,
            volume=10000.0,
            tags=["news"],
            updated_at=very_stale,
            exchange="kalshi",
        ))
        
        return poly, kalshi
    
    def _generate_consistency_violations(self) -> Tuple[List[Market], List[Market]]:
        """
        Generate cross-market consistency violation scenarios.
        
        Cases:
        1. True positive (logical contradiction between markets)
        2. False positive guard (ambiguous mapping, should reject)
        """
        poly = []
        kalshi = []
        expiry = self.now + timedelta(days=12)
        
        # Case 1: True consistency violation
        # Market A: "Team wins championship" = 70%
        # Market B: "Team reaches finals" = 50%
        # Violation: Can't win without reaching finals!
        poly.append(Market(
            id="poly:consist_champ",
            question="Will team win championship?",
            outcomes=[
                Outcome(id="poly:cons_ch:yes", label="YES", price=0.70, liquidity=12000.0),
                Outcome(id="poly:cons_ch:no", label="NO", price=0.30, liquidity=12000.0),
            ],
            end_date=expiry,
            expiry=expiry,
            liquidity=24000.0,
            volume=40000.0,
            tags=["sports", "consistency"],
            exchange="polymarket",
        ))
        poly.append(Market(
            id="poly:consist_finals",
            question="Will team reach finals?",
            outcomes=[
                Outcome(id="poly:cons_fi:yes", label="YES", price=0.50, liquidity=10000.0),  # Inconsistent!
                Outcome(id="poly:cons_fi:no", label="NO", price=0.50, liquidity=10000.0),
            ],
            end_date=expiry,
            expiry=expiry,
            liquidity=20000.0,
            volume=35000.0,
            tags=["sports", "consistency"],
            exchange="polymarket",
        ))
        
        # Case 2: Ambiguous mapping (false positive guard)
        # Two similar but different events - should NOT be matched
        kalshi.append(Market(
            id="kalshi:AMBIG-GDP-Q1:T1",
            question="Will Q1 GDP growth exceed 2.5%?",
            outcomes=[
                Outcome(id="kalshi:AMB1:YES", label="YES", price=0.55, liquidity=8000.0),
                Outcome(id="kalshi:AMB1:NO", label="NO", price=0.45, liquidity=8000.0),
            ],
            end_date=expiry,
            expiry=expiry,
            liquidity=16000.0,
            volume=25000.0,
            tags=["economics"],
            description="Q1 GDP growth threshold",
            exchange="kalshi",
        ))
        kalshi.append(Market(
            id="kalshi:AMBIG-GDP-Q2:T1",
            question="Will Q2 GDP growth exceed 2.5%?",  # DIFFERENT quarter!
            outcomes=[
                Outcome(id="kalshi:AMB2:YES", label="YES", price=0.60, liquidity=8000.0),
                Outcome(id="kalshi:AMB2:NO", label="NO", price=0.40, liquidity=8000.0),
            ],
            end_date=expiry + timedelta(days=90),  # Different expiry
            expiry=expiry + timedelta(days=90),
            liquidity=16000.0,
            volume=23000.0,
            tags=["economics"],
            description="Q2 GDP growth threshold",
            exchange="kalshi",
        ))
        
        return poly, kalshi
    
    def _generate_operational_edge_cases(self) -> Tuple[List[Market], List[Market]]:
        """
        Generate operational edge cases.
        
        Cases:
        - Partial fills (asymmetric liquidity)
        - Insufficient orderbook depth
        - Min order size violations
        - Max exposure limits
        - Fee schedule mismatches
        - Tick size rounding edge cases
        - Market paused/closed flags
        - Mismatched resolution dates
        """
        poly = []
        kalshi = []
        expiry = self.now + timedelta(days=3)
        far_expiry = self.now + timedelta(days=90)
        
        # Partial fill scenario (one leg has low liquidity)
        poly.append(Market(
            id="poly:partial_fill",
            question="Will event with asymmetric depth occur?",
            outcomes=[
                Outcome(id="poly:pf:yes", label="YES", price=0.45, liquidity=20000.0),  # Deep
                Outcome(id="poly:pf:no", label="NO", price=0.55, liquidity=500.0),  # Shallow!
            ],
            end_date=expiry,
            expiry=expiry,
            liquidity=20500.0,
            volume=30000.0,
            tags=["edge-case", "partial"],
            exchange="polymarket",
        ))
        
        # Insufficient depth (both legs too thin)
        kalshi.append(Market(
            id="kalshi:INSUF-DEPTH:T1",
            question="Will low-liquidity event occur?",
            outcomes=[
                Outcome(id="kalshi:ID:YES", label="YES", price=0.40, liquidity=200.0),
                Outcome(id="kalshi:ID:NO", label="NO", price=0.60, liquidity=200.0),
            ],
            end_date=expiry,
            expiry=expiry,
            liquidity=400.0,  # Below minimum
            volume=800.0,
            tags=["edge-case"],
            exchange="kalshi",
        ))
        
        # Fee schedule mismatch (marginal opportunity)
        poly.append(Market(
            id="poly:fee_mismatch",
            question="Will marginal fee-sensitive event occur?",
            outcomes=[
                Outcome(id="poly:fm:yes", label="YES", price=0.48, liquidity=8000.0),
                Outcome(id="poly:fm:no", label="NO", price=0.51, liquidity=8000.0),
            ],
            end_date=expiry,
            expiry=expiry,
            liquidity=16000.0,
            volume=20000.0,
            tags=["edge-case", "fees"],
            exchange="polymarket",
        ))
        
        # Tick size rounding edge case (prices at weird increments)
        kalshi.append(Market(
            id="kalshi:TICK-ROUND:T1",
            question="Will tick-size test event occur?",
            outcomes=[
                Outcome(id="kalshi:TR:YES", label="YES", price=0.4999, liquidity=5000.0),
                Outcome(id="kalshi:TR:NO", label="NO", price=0.5001, liquidity=5000.0),
            ],
            end_date=expiry,
            expiry=expiry,
            liquidity=10000.0,
            volume=15000.0,
            tags=["edge-case", "rounding"],
            exchange="kalshi",
        ))
        
        # Mismatched resolution dates (same event, different expiries - should not match)
        poly.append(Market(
            id="poly:mismatch_date_near",
            question="Will annual target be hit?",
            outcomes=[
                Outcome(id="poly:md:yes", label="YES", price=0.60, liquidity=7000.0),
                Outcome(id="poly:md:no", label="NO", price=0.40, liquidity=7000.0),
            ],
            end_date=expiry,  # 3 days
            expiry=expiry,
            liquidity=14000.0,
            volume=18000.0,
            tags=["edge-case", "expiry"],
            exchange="polymarket",
        ))
        kalshi.append(Market(
            id="kalshi:MISMATCH-DATE-FAR:T1",
            question="Will annual target be hit?",
            outcomes=[
                Outcome(id="kalshi:MDF:YES", label="YES", price=0.55, liquidity=7000.0),
                Outcome(id="kalshi:MDF:NO", label="NO", price=0.45, liquidity=7000.0),
            ],
            end_date=far_expiry,  # 90 days - DIFFERENT!
            expiry=far_expiry,
            liquidity=14000.0,
            volume=17000.0,
            tags=["edge-case", "expiry"],
            exchange="kalshi",
        ))
        
        return poly, kalshi


def get_cross_venue_scenario(seed: int = 42) -> Tuple[List[Market], List[Market]]:
    """
    Get comprehensive cross-venue arbitrage test scenario.
    
    Args:
        seed: Random seed for reproducibility
        
    Returns:
        Tuple of (polymarket_markets, kalshi_markets)
    """
    generator = CrossVenueArbitrageScenarios(seed=seed)
    return generator.generate_all_scenarios()
