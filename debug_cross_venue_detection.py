#!/usr/bin/env python3
"""
Step-by-step debug tool for cross-venue arbitrage detection.
Shows exactly how markets from Polymarket and Kalshi are compared.

Usage:
    export KALSHI_API_KEY_ID=<your_key>
    export KALSHI_PRIVATE_KEY_PEM=<your_pem>
    export KALSHI_API_HOST=https://api.elections.kalshi.com
    python debug_cross_venue_detection.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

import os
from typing import List
from predarb.config import AppConfig, PolymarketConfig, KalshiConfig
from predarb.polymarket_client import PolymarketClient
from predarb.kalshi_client import KalshiClient
from predarb.models import Market
from predarb.matchers import cluster_duplicates, fingerprint, similarity
from predarb.detectors.duplicates import DuplicateDetector
from predarb.config import DetectorConfig

def print_header(title: str):
    print("\n" + "=" * 80)
    print(title.center(80))
    print("=" * 80)

def print_step(step: int, description: str):
    print(f"\n📍 STEP {step}: {description}")
    print("-" * 80)

def main():
    print_header("CROSS-VENUE ARBITRAGE DETECTION DEBUGGER")
    
    # ========== STEP 1: FETCH MARKETS FROM BOTH APIS ==========
    print_step(1, "FETCH MARKETS FROM POLYMARKET")
    
    poly_config = PolymarketConfig(enabled=True, host='https://gamma-api.polymarket.com')
    poly_client = PolymarketClient(poly_config)
    
    print("Connecting to Polymarket API...")
    poly_markets = poly_client.fetch_markets()
    print(f"✓ Fetched {len(poly_markets)} markets from Polymarket")
    
    # Show sample Polymarket market
    if poly_markets:
        sample = poly_markets[0]
        print(f"\n📊 Sample Polymarket Market:")
        print(f"   ID: {sample.id}")
        print(f"   Exchange: {sample.exchange}")
        print(f"   Question: {sample.question[:70]}...")
        print(f"   Outcomes: {len(sample.outcomes)}")
        if sample.outcomes:
            print(f"   First outcome: {sample.outcomes[0].label} @ ${sample.outcomes[0].price:.4f}")
    
    # ========== STEP 2: FETCH KALSHI MARKETS ==========
    print_step(2, "FETCH MARKETS FROM KALSHI")
    
    # Check credentials
    key_id = os.getenv('KALSHI_API_KEY_ID')
    private_key = os.getenv('KALSHI_PRIVATE_KEY_PEM')
    api_host = os.getenv('KALSHI_API_HOST', 'https://api.elections.kalshi.com')
    
    if not key_id or not private_key:
        print("⚠️  Kalshi credentials not found!")
        print("   Set KALSHI_API_KEY_ID and KALSHI_PRIVATE_KEY_PEM environment variables")
        print("   Proceeding with Polymarket only...\n")
        kalshi_markets = []
    else:
        print(f"Credentials found: {key_id[:20]}...")
        print(f"Connecting to Kalshi API: {api_host}")
        
        kalshi_client = KalshiClient(
            api_key_id=key_id,
            private_key_pem=private_key,
            api_host=api_host,
            min_liquidity_usd=500,
            min_days_to_expiry=1
        )
        
        kalshi_markets = kalshi_client.fetch_markets()
        print(f"✓ Fetched {len(kalshi_markets)} markets from Kalshi (after filtering)")
        
        # Show sample Kalshi market
        if kalshi_markets:
            sample = kalshi_markets[0]
            print(f"\n📊 Sample Kalshi Market:")
            print(f"   ID: {sample.id}")
            print(f"   Exchange: {sample.exchange}")
            print(f"   Question: {sample.question[:70]}...")
            print(f"   Outcomes: {len(sample.outcomes)}")
            if sample.outcomes:
                print(f"   First outcome: {sample.outcomes[0].label} @ ${sample.outcomes[0].price:.4f}")
    
    # ========== STEP 3: MERGE MARKETS ==========
    print_step(3, "MERGE MARKETS FROM BOTH EXCHANGES")
    
    all_markets = poly_markets + kalshi_markets
    print(f"Total markets in merged pool: {len(all_markets)}")
    print(f"   Polymarket: {len(poly_markets)}")
    print(f"   Kalshi: {len(kalshi_markets)}")
    
    # Show exchange distribution
    exchanges = {}
    for m in all_markets:
        exchanges[m.exchange] = exchanges.get(m.exchange, 0) + 1
    
    print(f"\nExchange distribution:")
    for exchange, count in exchanges.items():
        print(f"   {exchange}: {count} markets")
    
    # ========== STEP 4: FIND DUPLICATE MARKETS (SAME EVENT) ==========
    print_step(4, "FIND DUPLICATE MARKETS ACROSS EXCHANGES")
    
    print("Running cluster_duplicates() to find same events...")
    pairs = cluster_duplicates(all_markets, title_threshold=0.8)
    
    print(f"✓ Found {len(pairs)} duplicate market pairs")
    
    # Analyze pairs
    cross_venue_pairs = []
    same_venue_pairs = []
    
    for m1, m2 in pairs:
        if m1.exchange != m2.exchange:
            cross_venue_pairs.append((m1, m2))
        else:
            same_venue_pairs.append((m1, m2))
    
    print(f"\n📊 Pair Analysis:")
    print(f"   Cross-venue pairs (different exchanges): {len(cross_venue_pairs)}")
    print(f"   Same-venue pairs (same exchange): {len(same_venue_pairs)}")
    
    # ========== STEP 5: SHOW CROSS-VENUE MATCHES IN DETAIL ==========
    if cross_venue_pairs:
        print_step(5, "CROSS-VENUE MARKET MATCHES (Same Event, Different Prices)")
        
        print(f"\nShowing first {min(5, len(cross_venue_pairs))} cross-venue pairs:\n")
        
        for idx, (m1, m2) in enumerate(cross_venue_pairs[:5], 1):
            fp1 = fingerprint(m1)
            fp2 = fingerprint(m2)
            title_sim = similarity(fp1["key"], fp2["key"])
            
            print(f"PAIR {idx}:")
            print(f"   Market 1 ({m1.exchange}):")
            print(f"      ID: {m1.id}")
            print(f"      Question: {m1.question[:60]}...")
            print(f"      Normalized: {fp1['key'][:60]}...")
            if m1.outcomes:
                print(f"      Price: ${m1.outcomes[0].price:.4f} ({m1.outcomes[0].label})")
            
            print(f"\n   Market 2 ({m2.exchange}):")
            print(f"      ID: {m2.id}")
            print(f"      Question: {m2.question[:60]}...")
            print(f"      Normalized: {fp2['key'][:60]}...")
            if m2.outcomes:
                print(f"      Price: ${m2.outcomes[0].price:.4f} ({m2.outcomes[0].label})")
            
            print(f"\n   Match Quality:")
            print(f"      Title similarity: {title_sim:.2%}")
            
            # Calculate price difference
            if m1.outcomes and m2.outcomes:
                price_diff = abs(m1.outcomes[0].price - m2.outcomes[0].price)
                print(f"      Price difference: ${price_diff:.4f} ({price_diff*100:.2f}%)")
                print(f"      Arbitrage potential: ${price_diff * 100:.2f} per $100 invested")
            
            print()
    else:
        print_step(5, "NO CROSS-VENUE MATCHES FOUND")
        print("This could mean:")
        print("   • The exchanges don't have overlapping markets right now")
        print("   • Title/question formatting is too different to match")
        print("   • Kalshi filtering removed all potential matches")
    
    # ========== STEP 6: RUN DUPLICATE DETECTOR ==========
    print_step(6, "RUN DUPLICATE DETECTOR")
    
    detector_config = DetectorConfig(
        duplicate_price_diff_threshold=0.01  # 1% minimum price difference
    )
    detector = DuplicateDetector(detector_config)
    
    print(f"Running DuplicateDetector with threshold: {detector_config.duplicate_price_diff_threshold:.2%}")
    opportunities = detector.detect(all_markets)
    
    print(f"✓ Detected {len(opportunities)} arbitrage opportunities")
    
    if opportunities:
        print(f"\n📊 Opportunities Found:\n")
        for idx, opp in enumerate(opportunities[:10], 1):
            print(f"Opportunity {idx}:")
            print(f"   Type: {opp.type}")
            print(f"   Description: {opp.description}")
            print(f"   Net edge: {opp.net_edge*100:.2f}%")
            print(f"   Markets involved: {len(opp.market_ids)}")
            print(f"   Actions: {len(opp.actions)}")
            for action in opp.actions:
                print(f"      • {action.side} {action.amount} @ ${action.limit_price:.4f}")
            print()
    else:
        print("   No opportunities met the price difference threshold")
    
    # ========== STEP 7: SUMMARY ==========
    print_header("SUMMARY")
    print(f"Total markets fetched: {len(all_markets)}")
    print(f"   • Polymarket: {len(poly_markets)}")
    print(f"   • Kalshi: {len(kalshi_markets)}")
    print(f"\nDuplicate pairs found: {len(pairs)}")
    print(f"   • Cross-venue: {len(cross_venue_pairs)}")
    print(f"   • Same-venue: {len(same_venue_pairs)}")
    print(f"\nArbitrage opportunities: {len(opportunities)}")
    
    if opportunities:
        total_edge = sum(o.net_edge for o in opportunities)
        print(f"   • Total potential edge: {total_edge*100:.2f}%")
        print(f"   • Average edge per opportunity: {total_edge/len(opportunities)*100:.2f}%")
    
    print("\n" + "=" * 80)
    print("Debug session complete!")
    print("=" * 80)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nDebug session interrupted by user.")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
