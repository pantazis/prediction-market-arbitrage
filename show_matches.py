#!/usr/bin/env python3
"""Show the cross-venue matches found."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from dotenv import load_dotenv
load_dotenv()

from predarb.config import KalshiConfig, PolymarketConfig
from predarb.kalshi_client import KalshiClient
from predarb.polymarket_client import PolymarketClient
from predarb.cross_venue_matcher import CrossVenueMatcher

print("=" * 80)
print("FINDING CROSS-VENUE ARBITRAGE MATCHES")
print("=" * 80)

# Fetch markets
print("\n[1/3] Fetching Kalshi markets...")
kalshi_config = KalshiConfig(enabled=True)
kalshi_client = KalshiClient(
    api_key_id=kalshi_config.api_key_id,
    private_key_pem=kalshi_config.private_key_pem,
    api_host=kalshi_config.api_host,
    env=kalshi_config.env
)
kalshi_markets = kalshi_client.fetch_markets()
print(f"✓ Kalshi: {len(kalshi_markets)} markets")

print("\n[2/3] Fetching Polymarket markets...")
poly_config = PolymarketConfig(enabled=True)
poly_client = PolymarketClient(poly_config)
poly_markets = poly_client.fetch_markets()
print(f"✓ Polymarket: {len(poly_markets)} markets")

# Find matches
print("\n[3/3] Finding semantic matches (similarity >= 0.45)...")
matcher = CrossVenueMatcher(
    min_similarity=0.45,
    max_hours_diff=24,
    batch_size=50,
    enabled=True
)

pairs = matcher.find_pairs(kalshi_markets, poly_markets)

print("\n" + "=" * 80)
print(f"FOUND {len(pairs)} CROSS-VENUE MATCHES")
print("=" * 80)

for i, (k_market, p_market, score) in enumerate(pairs, 1):
    print(f"\n{'='*80}")
    print(f"MATCH #{i} - Similarity: {score:.4f} ({score*100:.2f}%)")
    print(f"{'='*80}")
    
    print(f"\n📊 KALSHI:")
    print(f"  ID: {k_market.id}")
    print(f"  Question: {k_market.question}")
    print(f"  Description: {k_market.description[:150]}...")
    print(f"  Expiry: {k_market.expiry or k_market.end_date}")
    print(f"  Liquidity: ${k_market.liquidity:,.2f}")
    print(f"  Volume: ${k_market.volume:,.2f}")
    if k_market.outcomes:
        yes_price = k_market.outcomes[0].price
        no_price = k_market.outcomes[1].price if len(k_market.outcomes) > 1 else (1 - yes_price)
        print(f"  Prices: YES={yes_price:.4f} ({yes_price*100:.2f}¢) | NO={no_price:.4f} ({no_price*100:.2f}¢)")
    
    print(f"\n📊 POLYMARKET:")
    print(f"  ID: {p_market.id}")
    print(f"  Question: {p_market.question}")
    print(f"  Description: {p_market.description[:150]}...")
    print(f"  Expiry: {p_market.expiry or p_market.end_date}")
    print(f"  Liquidity: ${p_market.liquidity:,.2f}")
    print(f"  Volume: ${p_market.volume:,.2f}")
    if p_market.outcomes:
        yes_price = p_market.outcomes[0].price
        no_price = p_market.outcomes[1].price if len(p_market.outcomes) > 1 else (1 - yes_price)
        print(f"  Prices: YES={yes_price:.4f} ({yes_price*100:.2f}¢) | NO={no_price:.4f} ({no_price*100:.2f}¢)")
    
    # Calculate potential arbitrage
    if k_market.outcomes and p_market.outcomes:
        k_yes = k_market.outcomes[0].price
        p_yes = p_market.outcomes[0].price
        
        # Check if there's price divergence
        diff = abs(k_yes - p_yes)
        print(f"\n💰 ARBITRAGE POTENTIAL:")
        print(f"  Price difference: {diff:.4f} ({diff*100:.2f}¢)")
        
        if k_yes < p_yes:
            print(f"  Strategy: BUY YES on Kalshi @ {k_yes*100:.2f}¢, SELL YES on Polymarket @ {p_yes*100:.2f}¢")
            print(f"  Potential profit: {(p_yes - k_yes)*100:.2f}¢ per contract")
        elif p_yes < k_yes:
            print(f"  Strategy: BUY YES on Polymarket @ {p_yes*100:.2f}¢, SELL YES on Kalshi @ {k_yes*100:.2f}¢")
            print(f"  Potential profit: {(k_yes - p_yes)*100:.2f}¢ per contract")
        else:
            print(f"  No arbitrage: Prices are identical")
    
    print(f"\n⏱️  TIME DIFFERENCE:")
    k_date = k_market.expiry or k_market.end_date
    p_date = p_market.expiry or p_market.end_date
    if k_date and p_date:
        diff_hours = abs((k_date - p_date).total_seconds() / 3600)
        print(f"  {diff_hours:.1f} hours apart")
        if diff_hours > 0:
            print(f"  Kalshi: {k_date}")
            print(f"  Polymarket: {p_date}")

if len(pairs) == 0:
    print("\n⚠️  No matches found at similarity threshold 0.45")
    print("   Try lowering the threshold to 0.40 or 0.35 to find more potential matches.")

print("\n" + "=" * 80)
