#!/usr/bin/env python
"""
Demo: Live incremental reporting with deduplication.

Shows how the reporter:
1. Writes CSV on first iteration
2. Skips duplicate states
3. Appends only when data changes
4. Maintains restart-safe state
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from predarb.models import Market, Opportunity, Outcome
from predarb.reporter import LiveReporter


def create_market(market_id: str, liquidity: float = 1000.0) -> Market:
    """Create test market."""
    outcomes = [
        Outcome(id="yes", label="Yes", price=0.5),
        Outcome(id="no", label="No", price=0.5),
    ]
    return Market(
        id=market_id,
        question=f"Test {market_id}?",
        outcomes=outcomes,
        liquidity=liquidity,
        volume=500.0,
    )


def create_opportunity(opp_id: str, market_id: str) -> Opportunity:
    """Create test opportunity."""
    from predarb.models import TradeAction
    
    actions = [TradeAction(
        market_id=market_id,
        outcome_id="yes",
        side="BUY",
        amount=100.0,
        limit_price=0.5,
    )]
    
    return Opportunity(
        type="parity",
        market_ids=[market_id],
        description=f"Test {opp_id}",
        net_edge=0.05,
        actions=actions,
        metadata={"opp_id": opp_id},
    )


def demo():
    """Run demo showing reporter behavior."""
    print("\n" + "=" * 70)
    print("LIVE INCREMENTAL REPORTING DEMO")
    print("=" * 70 + "\n")
    
    # Create reporter (reports to ./reports)
    reporter = LiveReporter()
    
    print(f"📁 Reports directory: {reporter.reports_dir}")
    print(f"📄 State file: {reporter.state_file}")
    print(f"📊 CSV file: {reporter.summary_csv}\n")
    
    # Scenario 1: First run - should write
    print("─" * 70)
    print("ITERATION 1: First run with 2 markets, 1 opportunity")
    print("─" * 70)
    
    markets_1 = [create_market("m1"), create_market("m2")]
    opps_1 = [create_opportunity("o1", "m1")]
    
    wrote = reporter.report(
        iteration=1,
        all_markets=markets_1,
        detected_opportunities=opps_1,
        approved_opportunities=opps_1,
    )
    
    print(f"✓ Reported: {wrote}")
    print(f"  → Markets: 2 | Detected: 1 | Approved: 1")
    print(f"  → State hashes saved to disk")
    
    # Scenario 2: Same data - should skip
    print("\n" + "─" * 70)
    print("ITERATION 2: Same markets and opportunities")
    print("─" * 70)
    
    wrote = reporter.report(
        iteration=2,
        all_markets=markets_1,
        detected_opportunities=opps_1,
        approved_opportunities=opps_1,
    )
    
    print(f"✗ Reported: {wrote} (skipped - no change)")
    print(f"  → CSV remains 2 lines (header + 1 data row)")
    
    # Scenario 3: New market - should write
    print("\n" + "─" * 70)
    print("ITERATION 3: Added new market m3")
    print("─" * 70)
    
    markets_2 = [create_market("m1"), create_market("m2"), create_market("m3")]
    
    wrote = reporter.report(
        iteration=3,
        all_markets=markets_2,
        detected_opportunities=opps_1,
        approved_opportunities=opps_1,
    )
    
    print(f"✓ Reported: {wrote}")
    print(f"  → Markets: 3 | Detected: 1 | Approved: 1")
    print(f"  → Market hash changed → wrote new row")
    
    # Scenario 4: New opportunity - should write
    print("\n" + "─" * 70)
    print("ITERATION 4: Added new opportunity o2")
    print("─" * 70)
    
    opps_2 = [create_opportunity("o1", "m1"), create_opportunity("o2", "m2")]
    
    wrote = reporter.report(
        iteration=4,
        all_markets=markets_2,
        detected_opportunities=opps_2,
        approved_opportunities=opps_2,
    )
    
    print(f"✓ Reported: {wrote}")
    print(f"  → Markets: 3 | Detected: 2 | Approved: 2")
    print(f"  → Opportunity hash changed → wrote new row")
    
    # Scenario 5: Removed opportunity - should write
    print("\n" + "─" * 70)
    print("ITERATION 5: Removed opportunity o2")
    print("─" * 70)
    
    wrote = reporter.report(
        iteration=5,
        all_markets=markets_2,
        detected_opportunities=[create_opportunity("o1", "m1")],
        approved_opportunities=[create_opportunity("o1", "m1")],
    )
    
    print(f"✓ Reported: {wrote}")
    print(f"  → Markets: 3 | Detected: 1 | Approved: 1")
    print(f"  → Opportunity hash changed → wrote new row")
    
    # Show final CSV contents
    print("\n" + "=" * 70)
    print("FINAL CSV CONTENTS")
    print("=" * 70 + "\n")
    
    if reporter.summary_csv.exists():
        csv_content = reporter.summary_csv.read_text()
        lines = csv_content.strip().split("\n")
        
        print(f"Total rows: {len(lines)} (1 header + {len(lines) - 1} data rows)\n")
        
        for i, line in enumerate(lines):
            if i == 0:
                print("HEADER:")
                print(f"  {line}\n")
            else:
                parts = line.split(",")
                print(f"ROW {i}: Iteration={parts[1]}, Markets={parts[2]}, Detected={parts[3]}, Approved={parts[4]}")
    
    # Show state file
    print("\n" + "=" * 70)
    print("STATE FILE (for restart-safety)")
    print("=" * 70 + "\n")
    
    if reporter.state_file.exists():
        import json
        state = json.loads(reporter.state_file.read_text())
        print(f"market_ids_hash: {state['market_ids_hash'][:16]}...")
        print(f"approved_opp_ids_hash: {state['approved_opp_ids_hash'][:16]}...")
        print(f"last_updated: {state['last_updated']}")
    
    print("\n" + "=" * 70)
    print("✓ DEMO COMPLETE")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    demo()
