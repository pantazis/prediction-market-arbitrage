#!/usr/bin/env python3
"""Check what fields are populated from Kalshi vs Polymarket APIs."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from dotenv import load_dotenv
load_dotenv()

from predarb.config import KalshiConfig, PolymarketConfig
from predarb.kalshi_client import KalshiClient
from predarb.polymarket_client import PolymarketClient

print("=" * 80)
print("CHECKING MARKET FIELDS FROM BOTH APIs")
print("=" * 80)

# Fetch one market from each exchange
print("\n[1/2] Fetching Kalshi markets...")
kalshi_config = KalshiConfig(enabled=True)
kalshi_client = KalshiClient(
    api_key_id=kalshi_config.api_key_id,
    private_key_pem=kalshi_config.private_key_pem,
    api_host=kalshi_config.api_host,
    env=kalshi_config.env
)
kalshi_markets = kalshi_client.fetch_markets()[:3]  # Just get 3 samples

print("\n[2/2] Fetching Polymarket markets...")
poly_config = PolymarketConfig(enabled=True)
poly_client = PolymarketClient(poly_config)
poly_markets = poly_client.fetch_markets()[:3]  # Just get 3 samples

# Show Kalshi market structure
print("\n" + "=" * 80)
print("KALSHI MARKET SAMPLE")
print("=" * 80)
if kalshi_markets:
    k = kalshi_markets[0]
    print(f"\nID: {k.id}")
    print(f"Question: {k.question}")
    print(f"Description: {k.description[:100] if k.description else 'NONE'}...")
    print(f"Category: {getattr(k, 'category', 'NONE')}")
    print(f"Tags: {k.tags}")
    print(f"Expiry: {k.expiry or k.end_date}")
    print(f"Exchange: {k.exchange}")
    print(f"Outcomes: {[o.label for o in k.outcomes] if k.outcomes else []}")
    
    # Show what _get_text_blob would extract
    from predarb.cross_venue_matcher import _get_text_blob
    blob = _get_text_blob(k)
    print(f"\nText blob for matching (first 200 chars):")
    print(f"  '{blob[:200]}...'")

# Show Polymarket market structure
print("\n" + "=" * 80)
print("POLYMARKET MARKET SAMPLE")
print("=" * 80)
if poly_markets:
    p = poly_markets[0]
    print(f"\nID: {p.id}")
    print(f"Question: {p.question}")
    print(f"Description: {p.description[:100] if p.description else 'NONE'}...")
    print(f"Category: {getattr(p, 'category', 'NONE')}")
    print(f"Tags: {p.tags}")
    print(f"Expiry: {p.expiry or p.end_date}")
    print(f"Exchange: {p.exchange}")
    print(f"Outcomes: {[o.label for o in p.outcomes] if p.outcomes else []}")
    
    # Show what _get_text_blob would extract
    from predarb.cross_venue_matcher import _get_text_blob
    blob = _get_text_blob(p)
    print(f"\nText blob for matching (first 200 chars):")
    print(f"  '{blob[:200]}...'")

print("\n" + "=" * 80)
print("COMPARISON")
print("=" * 80)
print("\nFields used for semantic matching:")
print("  ✓ question (title)")
print("  ✓ description")
print("  ? category (may not be populated)")
print("\nKalshi question samples:")
for i, k in enumerate(kalshi_markets[:3], 1):
    print(f"  {i}. {k.question[:70]}")

print("\nPolymarket question samples:")
for i, p in enumerate(poly_markets[:3], 1):
    print(f"  {i}. {p.question[:70]}")

print("\n" + "=" * 80)
