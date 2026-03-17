#!/usr/bin/env python3
"""
Quick scan to show price spreads on matched cross-venue pairs.
NOT part of the main app - just a diagnostic script.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from dotenv import load_dotenv
load_dotenv()

from predarb.polymarket_client import PolymarketClient
from predarb.kalshi_client import KalshiClient
from predarb.config import PolymarketConfig
from predarb.cross_venue_matcher import CrossVenueMatcher

def main():
    print("Fetching markets from both venues...")
    
    # Initialize clients
    poly_config = PolymarketConfig(
        host="https://gamma-api.polymarket.com",
        clob_host="https://clob.polymarket.com",
        limit=500
    )
    poly_client = PolymarketClient(poly_config)
    kalshi_client = KalshiClient()
    
    # Fetch markets
    print("\n[1/4] Fetching Polymarket...")
    poly_markets = poly_client.fetch_markets()
    print(f"  -> {len(poly_markets)} markets")
    
    print("\n[2/4] Fetching Kalshi...")
    kalshi_markets = kalshi_client.fetch_markets()
    print(f"  -> {len(kalshi_markets)} markets")
    
    # Match
    print("\n[3/4] Finding cross-venue matches...")
    matcher = CrossVenueMatcher(similarity_threshold=0.90)
    pairs = matcher.find_pairs(kalshi_markets, poly_markets)
    print(f"  -> {len(pairs)} matched pairs")
    
    # Show spreads
    print("\n[4/4] Price Spreads (sorted by spread size):\n")
    print(f"{'Kalshi Market':<50} {'Poly Market':<50} {'K-YES':>7} {'P-YES':>7} {'Spread':>8} {'Signal':<10}")
    print("-" * 140)
    
    results = []
    for pair in pairs:
        k_market = pair.kalshi_market
        p_market = pair.poly_market
        
        # Get YES prices
        k_yes = next((o.price for o in k_market.outcomes if o.label.upper() == "YES"), None)
        p_yes = next((o.price for o in p_market.outcomes if o.label.upper() == "YES"), None)
        
        if k_yes is not None and p_yes is not None:
            spread = abs(k_yes - p_yes)
            signal = ""
            if spread > 0.05:
                if k_yes < p_yes:
                    signal = "BUY Kalshi"
                else:
                    signal = "BUY Poly"
            results.append((k_market.question[:48], p_market.question[:48], k_yes, p_yes, spread, signal))
    
    # Sort by spread descending
    results.sort(key=lambda x: x[4], reverse=True)
    
    for k_q, p_q, k_yes, p_yes, spread, signal in results[:20]:
        spread_pct = spread * 100
        print(f"{k_q:<50} {p_q:<50} {k_yes:>7.2%} {p_yes:>7.2%} {spread_pct:>7.1f}% {signal:<10}")
    
    # Summary
    actionable = [r for r in results if r[4] > 0.05]
    print(f"\n{'='*140}")
    print(f"Total pairs: {len(results)} | Actionable (>5% spread): {len(actionable)}")
    
    if actionable:
        print("\nActionable opportunities (spread > 5%):")
        for k_q, p_q, k_yes, p_yes, spread, signal in actionable[:5]:
            print(f"  • {signal}: {k_q[:60]}... (spread: {spread*100:.1f}%)")

if __name__ == "__main__":
    main()
