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
