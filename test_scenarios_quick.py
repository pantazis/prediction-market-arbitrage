#!/usr/bin/env python3
"""Quick test of expanded scenarios."""
import sys
sys.path.insert(0, 'src')

from predarb.strict_ab_scenarios import get_strict_ab_scenario

poly, kalshi, meta = get_strict_ab_scenario(42)

print(f'Generated {len(poly)} Poly + {len(kalshi)} Kalshi markets')
print(f'Total scenarios: {len(meta)}')

valid = sum(1 for m in meta if m.expected_approval)
invalid = sum(1 for m in meta if not m.expected_approval)

print(f'  - Valid A+B: {valid}')
print(f'  - Invalid: {invalid}')

print('\nScenario breakdown:')
for i, m in enumerate(meta):
    status = "VALID" if m.expected_approval else "INVALID"
    print(f'  {i+1}. {m.name} ({m.arbitrage_type}) - {status}')
