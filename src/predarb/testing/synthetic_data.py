"""Synthetic market data generation for testing and simulation."""

import random
from datetime import datetime, timedelta
from typing import List, Dict, Tuple

from predarb.models import Market, Outcome


def generate_synthetic_markets(
    num_markets: int = 30,
    days: int = 2,
    seed: int = 42,
) -> List[Market]:
    """Generate deterministic synthetic markets for simulation.
    
    Creates 2 days of minute-by-minute market evolution with:
      - 20-50 markets with various opportunity types
      - Parity violations (outcome sum != 1)
      - Ladder markets (sequential outcome buckets)
      - Duplicate/clone markets with price divergence
      - Multi-outcome exclusive sum violations
      - Time-lag divergence between related markets
      - Illiquid/wide-spread rejection cases
    
    Args:
        num_markets: Number of unique markets to generate (default 30)
        days: Number of days to simulate (default 2)
        seed: Random seed for deterministic generation
    
    Returns:
        List of Market objects representing initial state
    """
    random.seed(seed)
    now = datetime.utcnow()
    end_date = now + timedelta(days=days + 30)  # 30 days in future
    
    markets = []
    market_id = 1
    
    # Distribute num_markets across opportunity types
    # We'll generate proportional amounts of each type
    total_weights = 5 + 4 + 3 + 3 + 2 + 3  # Sum of items below
    
    parity_count = max(1, int(num_markets * 5 / total_weights))
    ladder_count = max(1, int(num_markets * 4 / total_weights))
    dup_count = max(1, int(num_markets * 3 / total_weights))
    multiout_count = max(1, int(num_markets * 3 / total_weights))
    timelag_count = max(1, int(num_markets * 2 / total_weights))
    reject_count = max(1, int(num_markets * 3 / total_weights))
    
    # === YES/NO PARITY MARKETS ===
    for i in range(parity_count):
        gross_cost = 0.94 + random.uniform(-0.05, 0.02)  # Sum < 1 = arbitrage
        yes_price = gross_cost * random.uniform(0.4, 0.6)
        no_price = gross_cost - yes_price
        
        market = Market(
            id=f"market_{market_id:03d}",
            question=f"Will event {i} occur by {end_date.date()}?",
            outcomes=[
                Outcome(id="yes", label="Yes", price=yes_price, liquidity=5000),
                Outcome(id="no", label="No", price=no_price, liquidity=5000),
            ],
            end_date=end_date,
            liquidity=10000 + random.uniform(0, 5000),
            volume=random.uniform(1000, 50000),
            tags=["yes/no", "simple"],
            resolution_source="source",
        )
        markets.append(market)
        market_id += 1
    
    # === LADDER MARKETS (bucket/range markets) ===
    for i in range(ladder_count):
        base = random.uniform(0.15, 0.30)
        outcomes = [
            Outcome(id=f"outcome_{j}", label=f"${100 + j*100}", price=base, liquidity=3000)
            for j in range(4)
        ]
        
        market = Market(
            id=f"market_{market_id:03d}",
            question=f"Price range for metric {i} on {end_date.date()}?",
            outcomes=outcomes,
            end_date=end_date,
            liquidity=12000 + random.uniform(0, 3000),
            volume=random.uniform(500, 20000),
            tags=["ladder", "numeric"],
            resolution_source="source",
        )
        markets.append(market)
        market_id += 1
    
    # === DUPLICATE MARKETS (clones with price differences) ===
    for i in range(dup_count):
        base_yes_price = random.uniform(0.35, 0.65)
        base_no_price = 1.0 - base_yes_price
        
        # Market A (reference)
        market_a = Market(
            id=f"market_{market_id:03d}",
            question=f"Event clone set {i} - original phrasing",
            outcomes=[
                Outcome(id="yes", label="Yes", price=base_yes_price, liquidity=4000),
                Outcome(id="no", label="No", price=base_no_price, liquidity=4000),
            ],
            end_date=end_date,
            liquidity=8000 + random.uniform(0, 2000),
            volume=random.uniform(500, 15000),
            tags=["duplicate", "yes/no"],
            resolution_source="source",
        )
        markets.append(market_a)
        market_id += 1
        
        # Market B (clone with price divergence)
        yes_diff = random.uniform(0.02, 0.08)
        market_b = Market(
            id=f"market_{market_id:03d}",
            question=f"Event clone set {i} - alternative phrasing",
            outcomes=[
                Outcome(id="yes", label="Yes", price=base_yes_price + yes_diff, liquidity=4000),
                Outcome(id="no", label="No", price=base_no_price - yes_diff, liquidity=4000),
            ],
            end_date=end_date,
            liquidity=8000 + random.uniform(0, 2000),
            volume=random.uniform(500, 15000),
            tags=["duplicate", "yes/no"],
            resolution_source="source",
        )
        markets.append(market_b)
        market_id += 1
    
    # === MULTI-OUTCOME EXCLUSIVE SUM VIOLATIONS ===
    for i in range(multiout_count):
        # Sum != 1 with more outcomes
        outcome_count = random.randint(3, 5)
        prices = []
        target_sum = random.uniform(0.92, 0.98)  # Intentionally off
        
        for j in range(outcome_count - 1):
            p = random.uniform(0.1, 0.4)
            prices.append(p)
        
        remaining = target_sum - sum(prices)
        remaining = max(0.01, min(0.95, remaining))  # Clamp to valid range
        prices.append(remaining)
        
        # Ensure prices list matches outcome_count
        prices = prices[:outcome_count]
        while len(prices) < outcome_count:
            prices.append(random.uniform(0.05, 0.15))
        
        outcomes = [
            Outcome(id=f"outcome_{j}", label=f"Option {chr(65+j)}", price=max(0, prices[j]), liquidity=2000)
            for j in range(outcome_count)
        ]
        
        market = Market(
            id=f"market_{market_id:03d}",
            question=f"Multi-outcome market {i} on {end_date.date()}?",
            outcomes=outcomes,
            end_date=end_date,
            liquidity=6000 + random.uniform(0, 2000),
            volume=random.uniform(200, 10000),
            tags=["exclusive_sum", "multioutcome"],
            resolution_source="source",
        )
        markets.append(market)
        market_id += 1
    
    # === TIME-LAG MARKETS (related markets with stale pricing) ===
    for i in range(timelag_count):
        base_price = random.uniform(0.3, 0.7)
        
        # Market 1 (fresh)
        market_1 = Market(
            id=f"market_{market_id:03d}",
            question=f"Related market {i} set - market 1",
            outcomes=[
                Outcome(id="yes", label="Yes", price=base_price, liquidity=3500),
                Outcome(id="no", label="No", price=1 - base_price, liquidity=3500),
            ],
            end_date=end_date,
            liquidity=7000 + random.uniform(0, 1500),
            volume=random.uniform(300, 12000),
            tags=["timelag", "yes/no"],
            resolution_source="source",
        )
        markets.append(market_1)
        market_id += 1
        
        # Market 2 (stale pricing - diverge by >5%)
        old_price = base_price + random.uniform(0.08, 0.15)
        old_price = min(0.95, max(0.05, old_price))
        market_2 = Market(
            id=f"market_{market_id:03d}",
            question=f"Related market {i} set - market 2",
            outcomes=[
                Outcome(id="yes", label="Yes", price=old_price, liquidity=3500),
                Outcome(id="no", label="No", price=1 - old_price, liquidity=3500),
            ],
            end_date=end_date,
            liquidity=7000 + random.uniform(0, 1500),
            volume=random.uniform(300, 12000),
            tags=["timelag", "yes/no"],
            resolution_source="source",
        )
        markets.append(market_2)
        market_id += 1
    
    # === REJECTION CASES (illiquid, wide spread, no resolution source) ===
    for i in range(reject_count):
        if i % 2 == 0:
            # Illiquid case
            market = Market(
                id=f"market_{market_id:03d}",
                question=f"Illiquid market {i} - should be filtered",
                outcomes=[
                    Outcome(id="yes", label="Yes", price=0.5, liquidity=100),
                    Outcome(id="no", label="No", price=0.5, liquidity=100),
                ],
                end_date=end_date,
                liquidity=200,  # Too low
                volume=10,  # Too low
                tags=["illiquid"],
                resolution_source=None,  # Missing resolution
            )
        else:
            # Wide spread case
            market = Market(
                id=f"market_{market_id:03d}",
                question=f"Wide spread market {i} - should be filtered",
                outcomes=[
                    Outcome(id="yes", label="Yes", price=0.2, liquidity=500),
                    Outcome(id="no", label="No", price=0.7, liquidity=500),
                ],
                end_date=end_date,
                liquidity=1000,
                volume=100,
                tags=["wide_spread"],
                resolution_source="source",
            )
        
        markets.append(market)
        market_id += 1
    
    return markets


def evolve_markets_minute_by_minute(
    initial_markets: List[Market],
    days: int = 2,
    seed: int = 42,
) -> Dict[int, List[Market]]:
    """Evolve markets minute-by-minute over N days.
    
    Args:
        initial_markets: Starting market snapshots
        days: Number of days to simulate
        seed: Random seed for deterministic evolution
    
    Returns:
        Dict mapping minute (0..2880) to market list at that minute
    """
    random.seed(seed + 1000)  # Different seed for evolution
    total_minutes = days * 24 * 60
    
    evolution = {0: initial_markets}
    
    for minute in range(1, total_minutes):
        prev_markets = evolution[minute - 1]
        new_markets = []
        
        for market in prev_markets:
            # Shallow copy outcomes and evolve prices slightly
            new_outcomes = []
            for outcome in market.outcomes:
                # Random walk on price (±1-3%)
                drift = random.uniform(-0.03, 0.03)
                new_price = max(0.01, min(0.99, outcome.price + drift))
                
                new_outcome = Outcome(
                    id=outcome.id,
                    label=outcome.label,
                    price=new_price,
                    liquidity=outcome.liquidity * random.uniform(0.95, 1.05),
                    last_updated=datetime.utcnow(),
                )
                new_outcomes.append(new_outcome)
            
            # Evolve volume and liquidity
            new_market = Market(
                id=market.id,
                question=market.question,
                outcomes=new_outcomes,
                end_date=market.end_date,
                liquidity=market.liquidity * random.uniform(0.98, 1.02),
                volume=market.volume * random.uniform(0.99, 1.01),
                tags=market.tags,
                resolution_source=market.resolution_source,
                description=market.description,
                best_bid=market.best_bid,
                best_ask=market.best_ask,
            )
            new_markets.append(new_market)
        
        evolution[minute] = new_markets
    
    return evolution


__all__ = ["generate_synthetic_markets", "evolve_markets_minute_by_minute"]
