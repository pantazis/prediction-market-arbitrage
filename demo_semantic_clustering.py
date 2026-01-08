"""
Demo script for semantic clustering scenario.
Shows how the scenario tests semantic similarity and all filters.
"""
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent / "src"))

from predarb.stress_scenarios import get_scenario

def main():
    print("=" * 80)
    print("SEMANTIC CLUSTERING SCENARIO DEMO")
    print("=" * 80)
    print()
    
    # Load scenario
    scenario = get_scenario("semantic_clustering", seed=42)
    markets = scenario.get_active_markets()
    
    print(f"Total markets generated: {len(markets)}")
    print()
    
    # Group 1: BTC semantic duplicates
    print("GROUP 1: Bitcoin Semantic Duplicates (5 markets)")
    print("-" * 80)
    btc_markets = [m for m in markets if m.id.startswith("btc_dup_")]
    for market in btc_markets:
        print(f"  {market.id}: {market.question}")
        print(f"    → Liquidity: ${market.liquidity:,.0f}, Volume: ${market.volume:,.0f}")
    print()
    
    # Group 2: Election semantic duplicates
    print("GROUP 2: Election Semantic Duplicates (4 markets)")
    print("-" * 80)
    election_markets = [m for m in markets if m.id.startswith("election_dup_")]
    for market in election_markets:
        print(f"  {market.id}: {market.question}")
        print(f"    → Liquidity: ${market.liquidity:,.0f}, Volume: ${market.volume:,.0f}")
    print()
    
    # Group 3: Filter violations
    print("GROUP 3: Filter Violations (10 markets)")
    print("-" * 80)
    
    # Wide spread
    wide_spread = [m for m in markets if m.id.startswith("wide_spread_")]
    print(f"\n  Wide Spread ({len(wide_spread)} markets):")
    for market in wide_spread:
        total_price = sum(o.price for o in market.outcomes)
        spread = 1.0 - total_price
        print(f"    {market.id}: Spread = {spread:.1%} (violates typical 3% max)")
    
    # Low volume
    low_volume = [m for m in markets if m.id.startswith("low_volume_")]
    print(f"\n  Low Volume ({len(low_volume)} markets):")
    for market in low_volume:
        print(f"    {market.id}: Volume = ${market.volume:,.0f} (below typical $10k min)")
    
    # Low liquidity
    low_liq = [m for m in markets if m.id.startswith("low_liq_")]
    print(f"\n  Low Liquidity ({len(low_liq)} markets):")
    for market in low_liq:
        print(f"    {market.id}: Liquidity = ${market.liquidity:,.0f} (below typical $25k min)")
    
    # Expiring soon
    expiring = [m for m in markets if m.id.startswith("expiring_")]
    print(f"\n  Expiring Soon ({len(expiring)} markets):")
    from datetime import datetime
    now = datetime.utcnow()
    for market in expiring:
        days = (market.end_date - now).days
        print(f"    {market.id}: Expires in {days} days (below typical 7 day min)")
    
    # Missing resolution source
    no_source = [m for m in markets if m.id.startswith("no_source_")]
    print(f"\n  No Resolution Source ({len(no_source)} markets):")
    for market in no_source:
        print(f"    {market.id}: resolution_source = '{market.resolution_source}' (empty)")
    
    print()
    
    # Group 4: Good arbitrage opportunities
    print("GROUP 4: Good Arbitrage Opportunities (3 markets)")
    print("-" * 80)
    good_arb = [m for m in markets if m.id.startswith("good_arb_")]
    for market in good_arb:
        total_price = sum(o.price for o in market.outcomes)
        edge = 1.0 - total_price
        print(f"  {market.id}: Edge = {edge:.2%}, Liquidity = ${market.liquidity:,.0f}")
    print()
    
    # Group 5: Distinct entities (should NOT cluster)
    print("GROUP 5: Distinct Entities (3 markets - should NOT cluster together)")
    print("-" * 80)
    distinct = [m for m in markets if m.id.startswith("distinct_")]
    for market in distinct:
        print(f"  {market.id}: {market.question}")
    print()
    
    print("=" * 80)
    print("USAGE:")
    print("  python -m predarb stress --scenario semantic_clustering")
    print("=" * 80)


if __name__ == "__main__":
    main()
