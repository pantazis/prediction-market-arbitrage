"""
Built-in stress test scenarios for DRY-RUN mode.

Each scenario is deterministic (seeded) and tests a specific aspect of the
arbitrage detection and execution pipeline.
"""
import random
from datetime import datetime, timedelta
from typing import List, Optional
from src.predarb.models import Market, Outcome


class StressScenario:
    """Base class for stress test scenarios."""
    
    def __init__(self, seed: Optional[int] = None):
        self.seed = seed or 42
        random.seed(self.seed)
    
    def get_active_markets(self) -> List[Market]:
        """Generate markets for this scenario."""
        raise NotImplementedError
    
    def fetch_markets(self) -> List[Market]:
        """Alias for get_active_markets() for Engine compatibility."""
        return self.get_active_markets()


class HighVolumeScenario(StressScenario):
    """
    High volume of markets (1000) with few opportunities.
    Tests market processing performance and filtering efficiency.
    """
    
    def get_active_markets(self) -> List[Market]:
        markets = []
        now = datetime.utcnow()
        end_date = now + timedelta(days=30)
        
        # 990 "normal" markets with fair pricing
        for i in range(990):
            yes_price = 0.48 + random.uniform(0, 0.04)
            no_price = 0.52 - random.uniform(0, 0.04)
            
            market = Market(
                id=f"norm_{i:04d}",
                question=f"Will normal event {i} occur?",
                outcomes=[
                    Outcome(id="yes", label="Yes", price=yes_price, liquidity=5000),
                    Outcome(id="no", label="No", price=no_price, liquidity=5000),
                ],
                end_date=end_date,
                liquidity=10000,
                volume=5000,
                tags=["yes/no"],
                resolution_source="source",
            )
            markets.append(market)
        
        # 10 markets with actual arbitrage opportunities
        for i in range(10):
            gross_cost = 0.92 + random.uniform(-0.03, 0.01)
            yes_price = gross_cost * 0.5
            no_price = gross_cost * 0.5
            
            market = Market(
                id=f"arb_{i:02d}",
                question=f"Will arbitrage event {i} occur?",
                outcomes=[
                    Outcome(id="yes", label="Yes", price=yes_price, liquidity=10000),
                    Outcome(id="no", label="No", price=no_price, liquidity=10000),
                ],
                end_date=end_date,
                liquidity=20000,
                volume=15000,
                tags=["yes/no", "arb"],
                resolution_source="source",
            )
            markets.append(market)
        
        return markets


class ManyRiskRejectionsScenario(StressScenario):
    """
    Many opportunities detected but most rejected by risk manager.
    Tests risk validation logic and rejection handling.
    """
    
    def get_active_markets(self) -> List[Market]:
        markets = []
        now = datetime.utcnow()
        end_date = now + timedelta(days=30)
        
        # 20 markets with low liquidity (rejected)
        for i in range(20):
            gross_cost = 0.93
            yes_price = gross_cost * 0.5
            no_price = gross_cost * 0.5
            
            market = Market(
                id=f"lowliq_{i:02d}",
                question=f"Low liquidity event {i}?",
                outcomes=[
                    Outcome(id="yes", label="Yes", price=yes_price, liquidity=50),
                    Outcome(id="no", label="No", price=no_price, liquidity=50),
                ],
                end_date=end_date,
                liquidity=100,  # Below min_liquidity
                volume=500,
                tags=["yes/no"],
                resolution_source="source",
            )
            markets.append(market)
        
        # 15 markets with tiny edge (fees eliminate profit)
        for i in range(15):
            gross_cost = 0.995  # ~0.5% edge, likely eliminated by fees
            yes_price = gross_cost * 0.5
            no_price = gross_cost * 0.5
            
            market = Market(
                id=f"lowedge_{i:02d}",
                question=f"Low edge event {i}?",
                outcomes=[
                    Outcome(id="yes", label="Yes", price=yes_price, liquidity=10000),
                    Outcome(id="no", label="No", price=no_price, liquidity=10000),
                ],
                end_date=end_date,
                liquidity=20000,
                volume=5000,
                tags=["yes/no"],
                resolution_source="source",
            )
            markets.append(market)
        
        # 5 markets that pass risk checks
        for i in range(5):
            gross_cost = 0.90
            yes_price = gross_cost * 0.5
            no_price = gross_cost * 0.5
            
            market = Market(
                id=f"good_{i:02d}",
                question=f"Good opportunity {i}?",
                outcomes=[
                    Outcome(id="yes", label="Yes", price=yes_price, liquidity=15000),
                    Outcome(id="no", label="No", price=no_price, liquidity=15000),
                ],
                end_date=end_date,
                liquidity=30000,
                volume=20000,
                tags=["yes/no"],
                resolution_source="source",
            )
            markets.append(market)
        
        return markets


class PartialFillScenario(StressScenario):
    """
    Insufficient orderbook depth on one leg → partial fill path.
    Tests hedge/cancel logic when execution fails.
    """
    
    def get_active_markets(self) -> List[Market]:
        markets = []
        now = datetime.utcnow()
        end_date = now + timedelta(days=30)
        
        # 10 markets with asymmetric liquidity (YES leg deep, NO leg shallow)
        for i in range(10):
            gross_cost = 0.92
            yes_price = gross_cost * 0.5
            no_price = gross_cost * 0.5
            
            market = Market(
                id=f"partial_{i:02d}",
                question=f"Partial fill scenario {i}?",
                outcomes=[
                    Outcome(id="yes", label="Yes", price=yes_price, liquidity=20000),
                    Outcome(id="no", label="No", price=no_price, liquidity=500),  # Shallow
                ],
                end_date=end_date,
                liquidity=20500,
                volume=10000,
                tags=["yes/no", "partial"],
                resolution_source="source",
            )
            markets.append(market)
        
        return markets


class HappyPathScenario(StressScenario):
    """
    Clean happy path: good opportunities, clean execution, realized PnL.
    Tests success case end-to-end.
    """
    
    def get_active_markets(self) -> List[Market]:
        markets = []
        now = datetime.utcnow()
        end_date = now + timedelta(days=30)
        
        # 15 markets with strong arbitrage opportunities
        for i in range(15):
            gross_cost = 0.88 + random.uniform(-0.03, 0.02)
            yes_price = gross_cost * random.uniform(0.45, 0.55)
            no_price = gross_cost - yes_price
            
            market = Market(
                id=f"happy_{i:02d}",
                question=f"Happy path event {i}?",
                outcomes=[
                    Outcome(id="yes", label="Yes", price=yes_price, liquidity=25000),
                    Outcome(id="no", label="No", price=no_price, liquidity=25000),
                ],
                end_date=end_date,
                liquidity=50000,
                volume=30000,
                tags=["yes/no", "arb"],
                resolution_source="source",
            )
            markets.append(market)
        
        return markets


class LatencyFreshnessScenario(StressScenario):
    """
    Markets with stale timestamps or expiry issues.
    Tests latency/freshness validation.
    """
    
    def get_active_markets(self) -> List[Market]:
        markets = []
        now = datetime.utcnow()
        
        # 10 markets expiring too soon (< 1 day)
        for i in range(10):
            end_date = now + timedelta(hours=12)  # Expires in 12 hours
            gross_cost = 0.92
            yes_price = gross_cost * 0.5
            no_price = gross_cost * 0.5
            
            market = Market(
                id=f"expiring_{i:02d}",
                question=f"Expiring soon event {i}?",
                outcomes=[
                    Outcome(id="yes", label="Yes", price=yes_price, liquidity=10000),
                    Outcome(id="no", label="No", price=no_price, liquidity=10000),
                ],
                end_date=end_date,
                liquidity=20000,
                volume=5000,
                tags=["yes/no"],
                resolution_source="source",
            )
            markets.append(market)
        
        # 5 markets with good expiry
        for i in range(5):
            end_date = now + timedelta(days=30)
            gross_cost = 0.90
            yes_price = gross_cost * 0.5
            no_price = gross_cost * 0.5
            
            market = Market(
                id=f"fresh_{i:02d}",
                question=f"Fresh event {i}?",
                outcomes=[
                    Outcome(id="yes", label="Yes", price=yes_price, liquidity=15000),
                    Outcome(id="no", label="No", price=no_price, liquidity=15000),
                ],
                end_date=end_date,
                liquidity=30000,
                volume=10000,
                tags=["yes/no"],
                resolution_source="source",
            )
            markets.append(market)
        
        return markets


class FeeSlippageScenario(StressScenario):
    """
    Opportunities where fees/slippage eliminate edge.
    Tests cost modeling and rejection.
    """
    
    def get_active_markets(self) -> List[Market]:
        markets = []
        now = datetime.utcnow()
        end_date = now + timedelta(days=30)
        
        # 20 markets with marginal edge (fees + slippage will kill it)
        for i in range(20):
            gross_cost = 0.97 + random.uniform(-0.01, 0.01)  # ~2-4% gross edge
            yes_price = gross_cost * 0.5
            no_price = gross_cost * 0.5
            
            market = Market(
                id=f"marginal_{i:02d}",
                question=f"Marginal edge event {i}?",
                outcomes=[
                    Outcome(id="yes", label="Yes", price=yes_price, liquidity=10000),
                    Outcome(id="no", label="No", price=no_price, liquidity=10000),
                ],
                end_date=end_date,
                liquidity=20000,
                volume=8000,
                tags=["yes/no"],
                resolution_source="source",
            )
            markets.append(market)
        
        return markets


class SemanticClusteringScenario(StressScenario):
    """
    Markets with semantic duplicates and various filter challenges.
    Tests semantic clustering (sentence-transformers), duplicate detection,
    and all market filter criteria (spread, volume, liquidity, expiry, etc.).
    """
    
    def get_active_markets(self) -> List[Market]:
        # Reset seed for deterministic generation on every call
        random.seed(self.seed)
        
        markets = []
        now = datetime.utcnow()
        
        # Group 1: Semantic duplicates - BTC price variations (5 markets)
        # Same semantic meaning, different phrasing
        btc_questions = [
            "Will Bitcoin exceed $100k by year end?",
            "Will BTC surpass $100,000 before 2027?",
            "Bitcoin to hit $100K this year?",
            "Will the price of Bitcoin reach 100000 USD?",
            "BTC > $100k by December 31st?",
        ]
        for i, question in enumerate(btc_questions):
            yes_price = 0.45 + random.uniform(0, 0.05)
            market = Market(
                id=f"btc_dup_{i}",
                question=question,
                outcomes=[
                    Outcome(id="yes", label="Yes", price=yes_price, liquidity=50000),
                    Outcome(id="no", label="No", price=1.0 - yes_price, liquidity=50000),
                ],
                end_date=now + timedelta(days=365),
                liquidity=100000,
                volume=50000,
                tags=["crypto", "bitcoin"],
                resolution_source="coinmarketcap",
            )
            markets.append(market)
        
        # Group 2: Semantic duplicates - Election outcomes (4 markets)
        election_questions = [
            "Will Democrats win the 2028 election?",
            "Democratic party victory in 2028 presidential race?",
            "Will the Democratic candidate win presidency in 2028?",
            "2028 US President: Will it be a Democrat?",
        ]
        for i, question in enumerate(election_questions):
            yes_price = 0.52 + random.uniform(0, 0.04)
            market = Market(
                id=f"election_dup_{i}",
                question=question,
                outcomes=[
                    Outcome(id="yes", label="Yes", price=yes_price, liquidity=75000),
                    Outcome(id="no", label="No", price=1.0 - yes_price, liquidity=75000),
                ],
                end_date=now + timedelta(days=1000),
                liquidity=150000,
                volume=80000,
                tags=["politics", "election"],
                resolution_source="official_results",
            )
            markets.append(market)
        
        # Group 3: Markets with FILTER VIOLATIONS
        
        # 3a: Excessive spread (2 markets) - should fail spread filter
        for i in range(2):
            yes_price = 0.40
            no_price = 0.50  # Spread = 10% (violates typical 3% max)
            market = Market(
                id=f"wide_spread_{i}",
                question=f"Wide spread market {i}?",
                outcomes=[
                    Outcome(id="yes", label="Yes", price=yes_price, liquidity=30000),
                    Outcome(id="no", label="No", price=no_price, liquidity=30000),
                ],
                end_date=now + timedelta(days=30),
                liquidity=60000,
                volume=25000,
                tags=["test"],
                resolution_source="oracle",
            )
            markets.append(market)
        
        # 3b: Low volume (2 markets) - should fail volume filter
        for i in range(2):
            yes_price = 0.48
            market = Market(
                id=f"low_volume_{i}",
                question=f"Low volume market {i}?",
                outcomes=[
                    Outcome(id="yes", label="Yes", price=yes_price, liquidity=30000),
                    Outcome(id="no", label="No", price=1.0 - yes_price, liquidity=30000),
                ],
                end_date=now + timedelta(days=30),
                liquidity=60000,
                volume=5000,  # Low volume (typical min: $10k)
                tags=["test"],
                resolution_source="oracle",
            )
            markets.append(market)
        
        # 3c: Low liquidity (2 markets) - should fail liquidity filter
        for i in range(2):
            yes_price = 0.47
            market = Market(
                id=f"low_liq_{i}",
                question=f"Low liquidity market {i}?",
                outcomes=[
                    Outcome(id="yes", label="Yes", price=yes_price, liquidity=5000),
                    Outcome(id="no", label="No", price=1.0 - yes_price, liquidity=5000),
                ],
                end_date=now + timedelta(days=30),
                liquidity=10000,  # Low liquidity (typical min: $25k)
                volume=15000,
                tags=["test"],
                resolution_source="oracle",
            )
            markets.append(market)
        
        # 3d: Expiring soon (2 markets) - should fail expiry filter
        for i in range(2):
            yes_price = 0.46
            market = Market(
                id=f"expiring_{i}",
                question=f"Expiring market {i}?",
                outcomes=[
                    Outcome(id="yes", label="Yes", price=yes_price, liquidity=40000),
                    Outcome(id="no", label="No", price=1.0 - yes_price, liquidity=40000),
                ],
                end_date=now + timedelta(days=3),  # Expires in 3 days (typical min: 7 days)
                liquidity=80000,
                volume=30000,
                tags=["test"],
                resolution_source="oracle",
            )
            markets.append(market)
        
        # 3e: Missing resolution source (2 markets) - should fail if require_resolution_source=True
        for i in range(2):
            yes_price = 0.45
            market = Market(
                id=f"no_source_{i}",
                question=f"No resolution source market {i}?",
                outcomes=[
                    Outcome(id="yes", label="Yes", price=yes_price, liquidity=35000),
                    Outcome(id="no", label="No", price=1.0 - yes_price, liquidity=35000),
                ],
                end_date=now + timedelta(days=30),
                liquidity=70000,
                volume=25000,
                tags=["test"],
                resolution_source="",  # Empty resolution source
            )
            markets.append(market)
        
        # Group 4: Good markets with arbitrage opportunities (3 markets)
        for i in range(3):
            yes_price = 0.42 + random.uniform(0, 0.02)
            no_price = 0.52 + random.uniform(0, 0.02)
            market = Market(
                id=f"good_arb_{i}",
                question=f"Good arbitrage opportunity {i}?",
                outcomes=[
                    Outcome(id="yes", label="Yes", price=yes_price, liquidity=80000),
                    Outcome(id="no", label="No", price=no_price, liquidity=80000),
                ],
                end_date=now + timedelta(days=60),
                liquidity=160000,
                volume=70000,
                tags=["quality"],
                resolution_source="verified_oracle",
            )
            markets.append(market)
        
        # Group 5: Related markets with different entities (should NOT cluster)
        # Tests that semantic clustering doesn't over-cluster unrelated markets
        distinct_questions = [
            "Will Apple stock exceed $200?",
            "Will Tesla stock exceed $200?",
            "Will Amazon stock exceed $200?",
        ]
        for i, question in enumerate(distinct_questions):
            yes_price = 0.50 + random.uniform(-0.03, 0.03)
            market = Market(
                id=f"distinct_{i}",
                question=question,
                outcomes=[
                    Outcome(id="yes", label="Yes", price=yes_price, liquidity=60000),
                    Outcome(id="no", label="No", price=1.0 - yes_price, liquidity=60000),
                ],
                end_date=now + timedelta(days=180),
                liquidity=120000,
                volume=55000,
                tags=["stocks"],
                resolution_source="market_data",
            )
            markets.append(market)
        
        # Group 6: LADDER opportunities - Sequential threshold markets with monotonicity violations
        # Tests LadderDetector for detecting price inconsistencies across related markets
        ladder_configs = [
            # BTC ladder: higher thresholds should have lower probabilities for ">"
            ("BTC", ">", [50000, 60000, 70000, 80000], [0.70, 0.55, 0.65, 0.30]),  # 0.65 violates monotonicity
            # ETH ladder: lower thresholds should have higher probabilities for "<"
            ("ETH", "<", [2000, 3000, 4000, 5000], [0.60, 0.45, 0.40, 0.50]),  # 0.50 violates monotonicity
        ]
        
        for asset, comparator, thresholds, probs in ladder_configs:
            for j, (threshold, prob) in enumerate(zip(thresholds, probs)):
                market = Market(
                    id=f"ladder_{asset.lower()}_{comparator}_{threshold}",
                    question=f"Will {asset} be {comparator} ${threshold:,}?",
                    outcomes=[
                        Outcome(id="yes", label="Yes", price=prob, liquidity=50000),
                        Outcome(id="no", label="No", price=1.0 - prob, liquidity=50000),
                    ],
                    end_date=now + timedelta(days=90),
                    liquidity=100000,
                    volume=40000,
                    tags=["crypto", asset.lower(), "ladder"],
                    resolution_source="price_feed",
                    asset=asset,
                    comparator=comparator,
                    threshold=float(threshold),
                )
                markets.append(market)
        
        # Group 7: EXCLUSIVE_SUM opportunities - Multi-outcome markets where sum ≠ 1.0
        # Tests ExclusiveSumDetector for markets with 3+ outcomes
        multi_outcome_configs = [
            # Winner of race with 4 candidates - prices sum to 0.92 (arb opportunity)
            ("race_winner", "Who will win the race?", ["Alice", "Bob", "Carol", "Dave"], [0.28, 0.25, 0.22, 0.17]),
            # Election with 5 outcomes - prices sum to 1.08 (reverse arb)
            ("election_winner", "Who will win the election?", ["Red", "Blue", "Green", "Yellow", "Purple"], [0.30, 0.28, 0.22, 0.18, 0.10]),
        ]
        
        for market_id, question, outcome_labels, prices in multi_outcome_configs:
            outcomes = []
            for k, (label, price) in enumerate(zip(outcome_labels, prices)):
                outcomes.append(
                    Outcome(
                        id=f"outcome_{k}",
                        label=label,
                        price=price,
                        liquidity=30000
                    )
                )
            
            market = Market(
                id=f"exclusive_sum_{market_id}",
                question=question,
                outcomes=outcomes,
                end_date=now + timedelta(days=60),
                liquidity=150000,
                volume=60000,
                tags=["multi-outcome", "exclusive"],
                resolution_source="official_results",
            )
            markets.append(market)
        
        # Group 8: CONSISTENCY opportunities - Complementary markets and monotonic violations
        # Tests ConsistencyDetector for logical inconsistencies
        
        # 8a: Complementary pairs (> vs <=) - should sum to 1.0 but don't
        consistency_pairs = [
            ("Gold", 2500, ">", 0.62, "<=", 0.45),  # Sum = 1.07 (inconsistent)
            ("Silver", 30, ">", 0.48, "<=", 0.58),   # Sum = 1.06 (inconsistent)
        ]
        
        for asset, threshold, comp1, prob1, comp2, prob2 in consistency_pairs:
            # First market: asset > threshold
            market1 = Market(
                id=f"consistency_{asset.lower()}_{comp1}_{threshold}",
                question=f"Will {asset} be {comp1} ${threshold}?",
                outcomes=[
                    Outcome(id="yes", label="Yes", price=prob1, liquidity=45000),
                    Outcome(id="no", label="No", price=1.0 - prob1, liquidity=45000),
                ],
                end_date=now + timedelta(days=75),
                liquidity=90000,
                volume=35000,
                tags=["commodities", asset.lower()],
                resolution_source="price_oracle",
                asset=asset,
                comparator=comp1,
                threshold=float(threshold),
            )
            markets.append(market1)
            
            # Second market: asset <= threshold (complementary)
            market2 = Market(
                id=f"consistency_{asset.lower()}_{comp2}_{threshold}",
                question=f"Will {asset} be {comp2} ${threshold}?",
                outcomes=[
                    Outcome(id="yes", label="Yes", price=prob2, liquidity=45000),
                    Outcome(id="no", label="No", price=1.0 - prob2, liquidity=45000),
                ],
                end_date=now + timedelta(days=75),
                liquidity=90000,
                volume=35000,
                tags=["commodities", asset.lower()],
                resolution_source="price_oracle",
                asset=asset,
                comparator=comp2,
                threshold=float(threshold),
            )
            markets.append(market2)
        
        # 8b: Monotonic dominance violations - P(X>60) > P(X>50) is inconsistent
        dominance_violation = Market(
            id="consistency_dominance_oil_50",
            question="Will Oil be > $50?",
            outcomes=[
                Outcome(id="yes", label="Yes", price=0.45, liquidity=40000),  # Lower prob
                Outcome(id="no", label="No", price=0.55, liquidity=40000),
            ],
            end_date=now + timedelta(days=80),
            liquidity=80000,
            volume=30000,
            tags=["commodities", "oil"],
            resolution_source="price_oracle",
            asset="Oil",
            comparator=">",
            threshold=50.0,
        )
        markets.append(dominance_violation)
        
        dominance_violation2 = Market(
            id="consistency_dominance_oil_60",
            question="Will Oil be > $60?",
            outcomes=[
                Outcome(id="yes", label="Yes", price=0.52, liquidity=40000),  # Higher prob (inconsistent!)
                Outcome(id="no", label="No", price=0.48, liquidity=40000),
            ],
            end_date=now + timedelta(days=80),
            liquidity=80000,
            volume=30000,
            tags=["commodities", "oil"],
            resolution_source="price_oracle",
            asset="Oil",
            comparator=">",
            threshold=60.0,
        )
        markets.append(dominance_violation2)
        
        # Group 9: Additional filter edge cases
        
        # 9a: Micro-price filter test - BUY price < $0.02 (dust liquidity)
        for i in range(2):
            market = Market(
                id=f"micro_price_{i}",
                question=f"Micro price event {i}?",
                outcomes=[
                    Outcome(id="yes", label="Yes", price=0.01, liquidity=20000),  # Below min_buy_price
                    Outcome(id="no", label="No", price=0.98, liquidity=20000),
                ],
                end_date=now + timedelta(days=40),
                liquidity=40000,
                volume=15000,
                tags=["edge_case"],
                resolution_source="oracle",
            )
            markets.append(market)
        
        # 9b: Expiry within min_expiry_hours (24h) - should be rejected by risk filter
        for i in range(2):
            yes_price = 0.44 + random.uniform(0, 0.02)
            market = Market(
                id=f"expiry_24h_{i}",
                question=f"Expiring in 12 hours event {i}?",
                outcomes=[
                    Outcome(id="yes", label="Yes", price=yes_price, liquidity=50000),
                    Outcome(id="no", label="No", price=1.0 - yes_price, liquidity=50000),
                ],
                end_date=now + timedelta(hours=12),  # Expires in 12 hours
                liquidity=100000,
                volume=40000,
                tags=["edge_case"],
                resolution_source="time_oracle",
            )
            markets.append(market)
        
        # 9c: Insufficient BUY-side depth - liquidity < 3x trade size
        for i in range(2):
            yes_price = 0.43 + random.uniform(0, 0.02)
            market = Market(
                id=f"shallow_depth_{i}",
                question=f"Shallow orderbook event {i}?",
                outcomes=[
                    Outcome(id="yes", label="Yes", price=yes_price, liquidity=1000),  # Too shallow
                    Outcome(id="no", label="No", price=1.0 - yes_price, liquidity=1000),
                ],
                end_date=now + timedelta(days=50),
                liquidity=2000,  # Total liquidity low
                volume=25000,
                tags=["edge_case"],
                resolution_source="oracle",
            )
            markets.append(market)
        
        # 9d: Entry spread > max_entry_spread_pct (10%)
        for i in range(2):
            market = Market(
                id=f"high_spread_{i}",
                question=f"High spread event {i}?",
                outcomes=[
                    Outcome(id="yes", label="Yes", price=0.35, liquidity=40000),
                    Outcome(id="no", label="No", price=0.55, liquidity=40000),  # Spread = 20%
                ],
                end_date=now + timedelta(days=45),
                liquidity=80000,
                volume=30000,
                tags=["edge_case"],
                resolution_source="oracle",
            )
            markets.append(market)
        
        # 9e: Marginal gross edge < min_gross_edge (5%)
        for i in range(2):
            yes_price = 0.475 + random.uniform(0, 0.005)
            no_price = 0.525 - random.uniform(0, 0.005)
            market = Market(
                id=f"low_gross_edge_{i}",
                question=f"Low edge event {i}?",
                outcomes=[
                    Outcome(id="yes", label="Yes", price=yes_price, liquidity=60000),
                    Outcome(id="no", label="No", price=no_price, liquidity=60000),
                ],
                end_date=now + timedelta(days=55),
                liquidity=120000,
                volume=50000,
                tags=["edge_case"],
                resolution_source="oracle",
            )
            markets.append(market)
        
        return markets


# Scenario registry
SCENARIOS = {
    "high_volume": HighVolumeScenario,
    "many_risk_rejections": ManyRiskRejectionsScenario,
    "partial_fill": PartialFillScenario,
    "happy_path": HappyPathScenario,
    "latency_freshness": LatencyFreshnessScenario,
    "fee_slippage": FeeSlippageScenario,
    "semantic_clustering": SemanticClusteringScenario,
}


def get_scenario(name: str, seed: Optional[int] = None) -> StressScenario:
    """
    Get a stress scenario by name.
    
    Args:
        name: Scenario name (see SCENARIOS dict)
        seed: Random seed for deterministic generation
        
    Returns:
        StressScenario instance
        
    Raises:
        ValueError: If scenario name not found
    """
    if name not in SCENARIOS:
        available = ", ".join(SCENARIOS.keys())
        raise ValueError(
            f"Unknown scenario: {name}\n"
            f"Available scenarios: {available}"
        )
    
    scenario_class = SCENARIOS[name]
    return scenario_class(seed=seed)


def list_scenarios() -> List[str]:
    """Return list of available scenario names."""
    return list(SCENARIOS.keys())
