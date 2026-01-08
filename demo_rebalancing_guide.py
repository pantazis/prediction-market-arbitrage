"""
HANDS-ON EXAMPLE: Testing Cash Rebalancing Step-by-Step
Run this to see exactly what happens during rebalancing!
"""

print("=" * 80)
print("TESTING REBALANCING - STEP BY STEP WALKTHROUGH")
print("=" * 80)
print()

print("What You'll Learn:")
print("  1. How to run a rebalancing test")
print("  2. What happens when one side fails")
print("  3. How the bot closes positions safely")
print()

print("-" * 80)
print("STEP 1: Run the Rebalancing Test")
print("-" * 80)
print()
print("Command:")
print("  python -m predarb stress --scenario partial_fill")
print()
print("What this does:")
print("  - Creates 10 markets")
print("  - Each market has DEEP YES side ($80k+) and SHALLOW NO side ($500)")
print("  - Bot tries to execute arbitrage on all of them")
print("  - Most will FAIL on the NO side (not enough money)")
print("  - Bot must HEDGE by selling the YES side")
print()

print("-" * 80)
print("STEP 2: Watch the Output")
print("-" * 80)
print()
print("You'll see something like:")
print()
print("  Iteration 1:")
print("    Markets fetched: 10")
print("    Opportunities detected: 8")
print("    Risk approved: 6")
print()
print("  Executing opportunity partial_0...")
print("    BUY YES: $1000 @ $0.42 --> SUCCESS")
print("    BUY NO:  $1000 @ $0.55 --> FAILED (insufficient liquidity)")
print("    Status: PARTIAL")
print("    Hedging: Closing YES position...")
print("    SELL YES: $1000 @ $0.42 --> SUCCESS")
print("    Final exposure: $0")
print()

print("-" * 80)
print("STEP 3: Check the Report")
print("-" * 80)
print()
print("Command:")
print('  python -c "from src.report_summary import generate_reports_summary; print(generate_reports_summary())"')
print()
print("You'll see:")
print()
print("  Iterations: 1")
print("  Total Opportunities Found: 8")
print("  Total Executed: 6")
print()
print("  EXECUTION BREAKDOWN:")
print("    SUCCESS: 2 (both sides filled)")
print("    PARTIAL: 4 (one side failed, hedged successfully)")
print()
print("  P&L SUMMARY:")
print("    Realized P&L: $20.00 (from 2 successful trades)")
print("    Hedging Costs: $5.00 (fees from closing positions)")
print("    Net Profit: $15.00")
print()

print("-" * 80)
print("STEP 4: Verify the Report File")
print("-" * 80)
print()
print("Look at: reports/unified_report.json")
print()
print("Check for:")
print()
print('  "opportunity_executions": [')
print('    {')
print('      "id": "partial_0",')
print('      "status": "partial",')
print('      "intended_legs": [')
print('        {"side": "BUY", "outcome": "yes", "amount": 1000},')
print('        {"side": "BUY", "outcome": "no", "amount": 1000}')
print('      ],')
print('      "actual_executions": [')
print('        {"side": "BUY", "outcome": "yes", "filled": 1000},')
print('        {"side": "BUY", "outcome": "no", "filled": 0}  <-- FAILED!')
print('      ],')
print('      "hedge": {')
print('        "hedged": true,')
print('        "hedge_executions": [')
print('          {"side": "SELL", "outcome": "yes", "amount": 1000}  <-- REBALANCED!')
print('        ]')
print('      }')
print('    }')
print('  ]')
print()

print("-" * 80)
print("WHAT IF REBALANCING FAILS?")
print("-" * 80)
print()
print("If you see exit code 6:")
print("  python -m predarb stress --scenario partial_fill")
print("  echo $LASTEXITCODE")
print("  # Output: 6")
print()
print("This means:")
print("  - Bot tried to hedge but FAILED")
print("  - Left with residual exposure (risky!)")
print("  - Need to fix the hedge logic")
print()
print("Check the report for:")
print('  "residual_exposure": true,')
print('  "failure_flags": ["residual_exposure"]')
print()

print("-" * 80)
print("TESTING LARGER REBALANCING")
print("-" * 80)
print()
print("Want to test with MORE markets and BIGGER trades?")
print()
print("Create custom_large_rebalance.json:")
print("""
[
  {
    "id": "big_1",
    "question": "Big trade 1?",
    "outcomes": [
      {"id": "yes", "label": "Yes", "price": 0.30, "liquidity": 500000},
      {"id": "no", "label": "No", "price": 0.65, "liquidity": 1000}
    ],
    "end_date": "2026-12-31T00:00:00Z",
    "liquidity": 501000,
    "volume": 100000,
    "resolution_source": "test"
  },
  {
    "id": "big_2",
    "question": "Big trade 2?",
    "outcomes": [
      {"id": "yes", "label": "Yes", "price": 0.35, "liquidity": 1000000},
      {"id": "no", "label": "No", "price": 0.60, "liquidity": 500}
    ],
    "end_date": "2026-12-31T00:00:00Z",
    "liquidity": 1000500,
    "volume": 200000,
    "resolution_source": "test"
  }
]
""")
print()
print("Run it:")
print("  python -m predarb stress --inject file:custom_large_rebalance.json")
print()
print("This tests:")
print("  - Large cash amounts ($500k+ liquidity)")
print("  - Multiple failed legs")
print("  - Hedging big positions")
print()

print("=" * 80)
print("QUICK REFERENCE")
print("=" * 80)
print()
print("Test rebalancing:")
print("  python -m predarb stress --scenario partial_fill")
print()
print("Test performance:")
print("  python -m predarb stress --scenario high_volume")
print()
print("Test cash management:")
print("  python -m predarb stress --scenario many_risk_rejections")
print()
print("Test all scenarios:")
print("  pytest tests/test_stress_scenarios.py -v")
print()
print("Check results:")
print('  python -c "from src.report_summary import generate_reports_summary; print(generate_reports_summary())"')
print()
print("=" * 80)
print()
print("TIP: Start with 'partial_fill' - it's the best rebalancing test!")
print()
