#!/usr/bin/env python3
"""Quick test to see what opportunities are found"""
import sys
import json
import logging
sys.path.insert(0, 'src')

# Enable logging to see what's happening
logging.basicConfig(level=logging.INFO, format='%(name)s - %(levelname)s - %(message)s')

from predarb.engine import Engine
from predarb.config import load_config
from predarb.testing.fake_client import FakePolymarketClient
from predarb.llm_verifier import LLMVerifier, LLMVerifierConfig

# Load config
config = load_config('config.yml')

# Disable telegram to avoid rate limiting
config.telegram.enabled = False

# Use fake client with test data
client = FakePolymarketClient(num_markets=25, seed=42)

# Create engine with mock notifier (no Telegram calls)
engine = Engine(config, client)
# Initialize LLM verifier with mock provider (no API calls)
llm_config = LLMVerifierConfig(
    enabled=True,
    provider="mock",
    fail_mode="fail_open"
)
llm_verifier = LLMVerifier(llm_config)
# Run once to find opportunities
print("Running engine with ALL markets (no pre-filtering)...")
markets = client.fetch_markets()
print(f"Total markets in client: {len(markets)}")

executed = engine.run_once()

print(f"\nFound {len(executed)} executed opportunities\n")

# Get markets for title lookup
markets = client.fetch_markets()
market_map = {m.id: m for m in markets}

# Group PARITY opportunities by event (similar events with same timing)
parity_opps = [opp for opp in executed if opp.type == "PARITY"]
duplicate_opps = [opp for opp in executed if opp.type == "DUPLICATE"]

print(f"=== PARITY OPPORTUNITIES (Mispriced YES+NO) ===\n")
for i, opp in enumerate(parity_opps, 1):
    print(f"{i}. Market: {', '.join(opp.market_ids)}")
    
    for mid in opp.market_ids:
        market = market_map.get(mid)
        if market:
            print(f"   Title: {market.title}")
            print(f"   End Date: {market.end_date}")
            # Show YES and NO prices
            for outcome in market.outcomes:
                print(f"      {outcome.label}: {outcome.price:.4f}")
    
    print(f"   Edge: {opp.net_edge:.4f} ({opp.net_edge*100:.2f}%)")
    print(f"   Description: {opp.description}")
    print()

# Check if multiple PARITY opportunities exist on similar events
if len(parity_opps) > 1:
    print(f"\n=== LLM VERIFICATION: Similar Events with Same Timing ===\n")
    print("Checking if PARITY markets resolve on same events (more likely to diverge)...\n")
    
    parity_markets = [market_map[mid] for opp in parity_opps for mid in opp.market_ids if mid in market_map]
    
    # Verify pairs of PARITY markets
    verified_pairs = []
    for i, market_a in enumerate(parity_markets):
        for market_b in parity_markets[i+1:]:
            # Only check if same end date (timing)
            if market_a.end_date == market_b.end_date:
                result = llm_verifier.verify_pair(market_a, market_b)
                if result.same_event:
                    verified_pairs.append((market_a, market_b, result.confidence))
                    print(f"SIMILAR: {market_a.id} <-> {market_b.id}")
                    print(f"  A: {market_a.title}")
                    print(f"  B: {market_b.title}")
                    print(f"  Confidence: {result.confidence:.2%}\n")
    
    if not verified_pairs:
        print("No similar event pairs found (different events or timing).\n")

print(f"\n=== DUPLICATE OPPORTUNITIES (Similar events, different prices) ===\n")
# Group duplicates by market pair
dup_groups = {}
for opp in duplicate_opps:
    key = tuple(sorted(opp.market_ids))
    if key not in dup_groups:
        dup_groups[key] = opp

for i, (market_ids, opp) in enumerate(sorted(dup_groups.items()), 1):
    print(f"{i}. Markets: {', '.join(market_ids)}")
    
    for mid in market_ids:
        market = market_map.get(mid)
        if market:
            print(f"   {mid}: {market.title}")
            # Show prices for first outcome (YES)
            yes_outcome = next((o for o in market.outcomes if o.label.upper() == "YES"), None)
            if yes_outcome:
                print(f"      Price: {yes_outcome.price:.4f}")
    
    print(f"   Edge: {opp.net_edge:.4f} ({opp.net_edge*100:.2f}%)")
    print(f"   Description: {opp.description}")
    print()
