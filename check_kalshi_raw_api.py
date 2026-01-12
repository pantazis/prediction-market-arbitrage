#!/usr/bin/env python3
"""Check raw Kalshi API response to see available fields."""

import sys
from pathlib import Path
import json
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from dotenv import load_dotenv
load_dotenv()

import requests
from predarb.config import KalshiConfig
from predarb.kalshi_client import KalshiClient

print("=" * 80)
print("CHECKING RAW KALSHI API RESPONSE")
print("=" * 80)

kalshi_config = KalshiConfig(enabled=True)
kalshi_client = KalshiClient(
    api_key_id=kalshi_config.api_key_id,
    private_key_pem=kalshi_config.private_key_pem,
    api_host=kalshi_config.api_host,
    env=kalshi_config.env
)

# Get first series from Politics
print("\n[1/2] Getting a Politics series...")
series_resp = kalshi_client._make_request("GET", "/trade-api/v2/series", params={
    "category": "Politics",
    "limit": 1
})
if not series_resp or "series" not in series_resp or not series_resp["series"]:
    print("ERROR: No series found")
    sys.exit(1)

series_ticker = series_resp["series"][0]["ticker"]
print(f"✓ Got series: {series_ticker}")

# Get markets for this series
print(f"\n[2/2] Getting markets for series {series_ticker}...")
markets_resp = kalshi_client._make_request("GET", "/trade-api/v2/markets", params={
    "series_ticker": series_ticker,
    "limit": 10
})

if not markets_resp or "markets" not in markets_resp or not markets_resp["markets"]:
    print(f"WARNING: No markets for {series_ticker}, trying different series...")
    
    # Try to get a different series with active markets
    for i in range(10):
        series_resp = kalshi_client._make_request("GET", "/trade-api/v2/series", params={
            "category": "Politics",
            "limit": 10,
            "cursor": str(i * 10)
        })
        if series_resp and "series" in series_resp:
            for series in series_resp["series"]:
                series_ticker = series["ticker"]
                markets_resp = kalshi_client._make_request("GET", "/trade-api/v2/markets", params={
                    "series_ticker": series_ticker,
                    "limit": 1
                })
                if markets_resp and "markets" in markets_resp and markets_resp["markets"]:
                    print(f"✓ Found markets in series: {series_ticker}")
                    break
            if markets_resp and "markets" in markets_resp and markets_resp["markets"]:
                break

if not markets_resp or "markets" not in markets_resp or not markets_resp["markets"]:
    print("ERROR: No markets found")
    sys.exit(1)

raw_market = markets_resp["markets"][0]

print("\n" + "=" * 80)
print("RAW KALSHI MARKET JSON")
print("=" * 80)
print(json.dumps(raw_market, indent=2))

print("\n" + "=" * 80)
print("AVAILABLE TEXT FIELDS")
print("=" * 80)
print(f"title: {raw_market.get('title', 'MISSING')}")
print(f"subtitle: {raw_market.get('subtitle', 'MISSING')}")
print(f"category: {raw_market.get('category', 'MISSING')}")
print(f"description: {raw_market.get('description', 'MISSING')}")
print(f"rules_primary: {raw_market.get('rules_primary', 'MISSING')}")
print(f"rules_secondary: {raw_market.get('rules_secondary', 'MISSING')}")

print("\n" + "=" * 80)
