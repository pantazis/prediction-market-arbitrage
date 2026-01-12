#!/usr/bin/env python3
"""Test different similarity thresholds to find matches."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from dotenv import load_dotenv
load_dotenv()

from predarb.config import KalshiConfig, PolymarketConfig
from predarb.kalshi_client import KalshiClient
from predarb.polymarket_client import PolymarketClient
from predarb.cross_venue_matcher import CrossVenueMatcher

print("=" * 70)
print("TESTING SIMILARITY THRESHOLDS")
print("=" * 70)

# Fetch markets
print("\n[1/3] Fetching Kalshi markets...")
kalshi_config = KalshiConfig(enabled=True)
kalshi_client = KalshiClient(
    api_key_id=kalshi_config.api_key_id,
    private_key_pem=kalshi_config.private_key_pem,
    api_host=kalshi_config.api_host,
    env=kalshi_config.env,
    min_liquidity_usd=0.0,
    min_days_to_expiry=0
)
kalshi_markets = kalshi_client.fetch_markets()
print(f"✓ Kalshi: {len(kalshi_markets)} markets")

print("\n[2/3] Fetching Polymarket markets...")
poly_config = PolymarketConfig(enabled=True)
poly_client = PolymarketClient(poly_config)
poly_markets = poly_client.fetch_markets()
print(f"✓ Polymarket: {len(poly_markets)} markets")

# Test different thresholds
thresholds = [0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60]

print("\n[3/3] Testing similarity thresholds...")
print("=" * 70)

for threshold in thresholds:
    matcher = CrossVenueMatcher(
        min_similarity=threshold,
        max_hours_diff=24,
        batch_size=50,
        enabled=True
    )
    
    pairs = matcher.find_pairs(kalshi_markets, poly_markets)
    
    print(f"\nThreshold {threshold:.2f}: {len(pairs)} matches")
    
    if pairs and len(pairs) <= 5:
        # Show details for first few matches
        for k_market, p_market, score in pairs[:3]:
            print(f"  • [{score:.3f}] {k_market.question[:50]}...")
            print(f"           vs {p_market.question[:50]}...")

print("\n" + "=" * 70)
print("DONE")
print("=" * 70)
