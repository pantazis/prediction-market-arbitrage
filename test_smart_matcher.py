#!/usr/bin/env python3
"""
Test script for smart_matcher.py
Verifies the semantic matching pipeline with sample data.
"""

import json
from pathlib import Path
from datetime import datetime, timedelta

# Create sample test data
def create_test_data():
    """Create minimal test market data for both exchanges."""
    
    # Sample Kalshi markets
    kalshi_markets = [
        {
            "ticker": "PRES-TRUMP-2024",
            "title": "Will Donald Trump win the 2024 Presidential Election?",
            "subtitle": "Resolves YES if Trump wins",
            "status": "active",
            "market_type": "binary",
            "expiration_time": (datetime.now() + timedelta(days=300)).isoformat(),
            "yes_bid": 0.45,
            "no_bid": 0.53,
            "rules_primary": "Resolves based on official electoral college results"
        },
        {
            "ticker": "BITCOIN-100K",
            "title": "Will Bitcoin reach $100,000 by end of 2024?",
            "subtitle": "BTC price must hit 100K",
            "status": "active",
            "market_type": "binary",
            "expiration_time": (datetime.now() + timedelta(days=350)).isoformat(),
            "yes_bid": 0.30,
            "no_bid": 0.68
        }
    ]
    
    # Sample Polymarket markets
    poly_markets = [
        {
            "id": "poly-trump-2024",
            "question": "Trump to win 2024 US Presidential Election?",
            "description": "This market resolves YES if Donald Trump wins the 2024 election",
            "groupItemTitle": "US Presidential Election 2024",
            "active": True,
            "closed": False,
            "outcomes": ["Yes", "No"],
            "endDate": (datetime.now() + timedelta(days=301)).isoformat(),
            "clobTokenIds": ["0x123", "0x456"]
        },
        {
            "id": "poly-btc-100k",
            "question": "Bitcoin above $100,000 in 2024?",
            "description": "Will BTC price reach or exceed $100k before end of year?",
            "groupItemTitle": "Cryptocurrency Markets",
            "active": True,
            "closed": False,
            "outcomes": ["Yes", "No"],
            "endDate": (datetime.now() + timedelta(days=348)).isoformat(),
            "clobTokenIds": ["0xabc", "0xdef"]
        },
        {
            "id": "poly-unrelated",
            "question": "Will it rain in Tokyo tomorrow?",
            "description": "Weather prediction market",
            "groupItemTitle": "Weather",
            "active": True,
            "closed": False,
            "outcomes": ["Yes", "No"],
            "endDate": (datetime.now() + timedelta(days=1)).isoformat(),
            "clobTokenIds": ["0x789", "0x012"]
        }
    ]
    
    # Write to files
    Path("kalshi_markets.json").write_text(json.dumps(kalshi_markets, indent=2))
    Path("polymarket_markets.json").write_text(json.dumps(poly_markets, indent=2))
    
    print("✅ Created test market data:")
    print(f"  - kalshi_markets.json ({len(kalshi_markets)} markets)")
    print(f"  - polymarket_markets.json ({len(poly_markets)} markets)")

def run_test():
    """Run the smart matcher with test data."""
    print("\n" + "="*60)
    print("Testing smart_matcher.py")
    print("="*60 + "\n")
    
    # Import after data is created
    from smart_matcher import find_smart_pairs
    
    # Load test data
    k_data = json.loads(Path("kalshi_markets.json").read_text())
    p_data = json.loads(Path("polymarket_markets.json").read_text())
    
    print(f"Loaded {len(k_data)} Kalshi markets and {len(p_data)} Polymarket markets\n")
    
    # Run matcher with lower similarity threshold for testing
    pairs = find_smart_pairs(
        k_data, 
        p_data, 
        min_similarity=0.50,  # Lower threshold for test
        max_hours_diff=72     # Allow 3 days difference
    )
    
    # Display results
    print("\n" + "="*60)
    print(f"RESULTS: Found {len(pairs)} matching pairs")
    print("="*60 + "\n")
    
    for i, pair in enumerate(pairs, 1):
        print(f"Match {i}:")
        print(f"  Similarity: {pair['similarity_score']:.2%}")
        print(f"  Time Diff: {pair['time_diff_hours']:.1f} hours")
        print(f"  Kalshi:  {pair['kalshi']['title']}")
        print(f"  Poly:    {pair['polymarket']['question']}")
        print()
    
    # Verify expected matches
    assert len(pairs) >= 2, "Should find at least 2 matches (Trump + Bitcoin)"
    
    # Check Trump match exists
    trump_match = any(
        'trump' in pair['kalshi']['title'].lower() and 
        'trump' in pair['polymarket']['question'].lower()
        for pair in pairs
    )
    assert trump_match, "Should match Trump election markets"
    
    # Check Bitcoin match exists
    btc_match = any(
        'bitcoin' in pair['kalshi']['title'].lower() and 
        'bitcoin' in pair['polymarket']['question'].lower()
        for pair in pairs
    )
    assert btc_match, "Should match Bitcoin markets"
    
    print("✅ All assertions passed!")
    print(f"✅ Smart matcher working correctly!")
    
    # Save results
    Path("smart_pairs.json").write_text(json.dumps(pairs, indent=2))
    print(f"\n💾 Results saved to smart_pairs.json")

if __name__ == "__main__":
    try:
        create_test_data()
        run_test()
        
        print("\n" + "="*60)
        print("TEST PASSED ✅")
        print("="*60)
        
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
