import json
import sys

with open('reports/unified_report.json') as f:
    data = json.load(f)

print("=" * 70)
print("CONTINUOUS RUN ANALYSIS")
print("=" * 70)

iterations = data.get('iterations', [])
print(f"\nTotal iterations: {len(iterations)}")

if len(iterations) > 0:
    latest = iterations[-1]
    print(f"\nLatest iteration #{latest['iteration']}:")
    print(f"  Markets: {latest['markets']['count']}")
    print(f"  Detected: {latest['opportunities_detected']['count']}")
    print(f"  Approved: {latest['opportunities_approved']['count']}")
    print(f"  Approval rate: {latest['approval_rate_pct']:.1f}%")
    
    print(f"\n{'=' * 70}")
    print("LAST 5 ITERATIONS:")
    print("=" * 70)
    for it in iterations[-5:]:
        det = it['opportunities_detected']['count']
        app = it['opportunities_approved']['count']
        rate = it['approval_rate_pct']
        print(f"  Iter #{it['iteration']:2d}: {det:3d} detected, {app:3d} approved ({rate:5.1f}%)")
    
    # Check if all zeros
    all_approved = [it['opportunities_approved']['count'] for it in iterations]
    if sum(all_approved) == 0:
        print(f"\n❌ PROBLEM: Zero approvals across all {len(iterations)} iterations!")
        print("   This suggests:")
        print("   1. Markets don't meet quality thresholds")
        print("   2. Or mix ratio too low (only 10% injected stress markets)")
        print("   3. Or Polymarket API returning no/bad markets")
        
        all_detected = [it['opportunities_detected']['count'] for it in iterations]
        if sum(all_detected) > 0:
            print(f"\n   Detection working: {sum(all_detected)} total opportunities found")
            print("   But ALL rejected by risk manager!")
        else:
            print(f"\n   No opportunities even detected - market fetching issue?")

# Check mix ratio
print(f"\n{'=' * 70}")
print("MARKET MIX ANALYSIS:")
print("=" * 70)
if len(iterations) > 0:
    market_count = latest['markets']['count']
    # Original high_volume = 1000 markets, mix_ratio = 0.1 means ~100 injected
    # So 1100 total markets suggests correct mix
    print(f"  Total markets: {market_count}")
    if market_count > 1000:
        injected_estimate = market_count - 1000
        print(f"  Estimated injected: ~{injected_estimate} (10% mix ratio)")
        print(f"  Estimated Polymarket: ~1000")
    else:
        print(f"  ⚠️  Only {market_count} markets - expected ~1100 with mix")

