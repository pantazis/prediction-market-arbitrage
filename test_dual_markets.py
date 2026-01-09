#!/usr/bin/env python3
"""Test data fetch from both Polymarket and Kalshi"""
from pathlib import Path
import sys
import os

sys.path.insert(0, str(Path(__file__).parent / 'src'))

print('=== DUAL MARKET DATA VERIFICATION ===')
print()

# Verify environment variables
print('Kalshi Credentials:')
key_id = os.getenv('KALSHI_API_KEY_ID', '')
private_key = os.getenv('KALSHI_PRIVATE_KEY_PEM', '')
api_host = os.getenv('KALSHI_API_HOST', '')

if key_id:
    print(f'  API Key ID: {key_id[:20]}...')
else:
    print('  API Key ID: NOT SET')

if private_key:
    print(f'  Private Key: Loaded ({len(private_key)} bytes)')
else:
    print('  Private Key: NOT SET')

if api_host:
    print(f'  API Host: {api_host}')
else:
    print('  API Host: NOT SET')
print()

# Test Polymarket
print('Testing Polymarket...')
from predarb.config import PolymarketConfig
from predarb.polymarket_client import PolymarketClient

poly_config = PolymarketConfig(enabled=True, host='https://gamma-api.polymarket.com')
poly_client = PolymarketClient(poly_config)
poly_markets = poly_client.fetch_markets()
print(f'✓ Polymarket: {len(poly_markets)} active markets')
if poly_markets:
    sample = poly_markets[0]
    print(f'  Sample: {sample.question[:50]}...')
    print(f'  Exchange: {sample.exchange}')
    if sample.outcomes:
        print(f'  Outcome: {sample.outcomes[0].label} = ${sample.outcomes[0].price:.4f}')
print()

# Test data integrity
print('Checking Polymarket data quality...')
valid = 0
for m in poly_markets[:50]:
    if m.question and m.outcomes:
        for o in m.outcomes:
            if 0 <= o.price <= 1:
                valid += 1
print(f'✓ Valid price data: {valid} outcomes checked')
print()

# Test Kalshi
if key_id and private_key and api_host:
    print('Testing Kalshi...')
    from predarb.config import KalshiConfig
    from predarb.kalshi_client import KalshiClient

    # The config will automatically load credentials from env vars
    kalshi_config = KalshiConfig(
        enabled=True,
        env='prod',
        min_liquidity_usd=500.0,
        min_days_to_expiry=1
    )
    
    print(f'  Config api_key_id: {kalshi_config.api_key_id[:20] if kalshi_config.api_key_id else "None"}...')
    print(f'  Config api_host: {kalshi_config.api_host}')
    
    try:
        kalshi_client = KalshiClient(
            api_key_id=kalshi_config.api_key_id,
            private_key_pem=kalshi_config.private_key_pem,
            api_host=kalshi_config.api_host,
            env=kalshi_config.env,
            min_liquidity_usd=kalshi_config.min_liquidity_usd,
            min_days_to_expiry=kalshi_config.min_days_to_expiry
        )
        kalshi_markets = kalshi_client.fetch_markets()
        print(f'✓ Kalshi: {len(kalshi_markets)} active markets')
        if kalshi_markets:
            sample = kalshi_markets[0]
            print(f'  Sample: {sample.question[:50]}...')
            print(f'  Exchange: {sample.exchange}')
            if sample.outcomes:
                print(f'  Outcome: {sample.outcomes[0].label} = ${sample.outcomes[0].price:.4f}')
        
        # Check data integrity
        print('\nChecking Kalshi data quality...')
        valid = 0
        for m in kalshi_markets[:50]:
            if m.question and m.outcomes:
                for o in m.outcomes:
                    if 0 <= o.price <= 1:
                        valid += 1
        print(f'✓ Valid price data: {valid} outcomes checked')
        print()
        
        print('=== RESULT ===')
        print(f'✅ BOTH MARKETS WORKING: {len(poly_markets)} Polymarket + {len(kalshi_markets)} Kalshi = {len(poly_markets) + len(kalshi_markets)} total markets')
    except Exception as e:
        print(f'✗ Kalshi error: {e}')
        print()
        print('=== RESULT ===')
        print(f'⚠️  Only Polymarket working: {len(poly_markets)} markets')
else:
    print('✗ Kalshi: Credentials not set')
    print()
    print('=== RESULT ===')
    print(f'⚠️  Only Polymarket working: {len(poly_markets)} markets')
