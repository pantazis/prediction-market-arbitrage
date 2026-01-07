#!/usr/bin/env python
"""Quick demo of unified reporting system."""

import sys
import tempfile
from pathlib import Path
from datetime import datetime

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.predarb.unified_reporter import UnifiedReporter
from src.predarb.models import Market, Opportunity, Trade, TradeAction, Outcome
from src.report_summary import generate_reports_summary, export_legacy_csv

def demo_unified_reporter():
    """Demonstrate the unified reporting system."""
    
    # Use temp directory for demo
    with tempfile.TemporaryDirectory() as tmpdir:
        reports_dir = Path(tmpdir)
        
        print("=" * 80)
        print("UNIFIED REPORTER DEMO")
        print("=" * 80)
        print()
        
        # Create reporter
        reporter = UnifiedReporter(reports_dir)
        print(f"[OK] Initialized reporter in {reports_dir}")
        print()
        
        # Create sample data
        markets = [
            Market(
                id="market1",
                question="Will it rain?",
                liquidity=1000.0,
                volume=500.0,
                outcomes=[
                    Outcome(id="yes", label="Yes", price=0.60),
                    Outcome(id="no", label="No", price=0.41)
                ]
            ),
            Market(
                id="market2",
                question="Will it snow?",
                liquidity=800.0,
                volume=400.0,
                outcomes=[
                    Outcome(id="yes", label="Yes", price=0.30),
                    Outcome(id="no", label="No", price=0.71)
                ]
            )
        ]
        
        opportunity = Opportunity(
            type="parity",
            market_ids=["market1", "market2"],
            description="Parity arbitrage between rain and snow markets",
            net_edge=5.0,
            actions=[
                TradeAction(
                    market_id="market1",
                    outcome_id="yes",
                    side="BUY",
                    amount=100.0,
                    limit_price=0.60
                ),
                TradeAction(
                    market_id="market2",
                    outcome_id="no",
                    side="SELL",
                    amount=100.0,
                    limit_price=0.71
                )
            ]
        )
        
        trades = [
            Trade(
                id="trade1",
                timestamp=datetime.utcnow(),
                market_id="market1",
                outcome_id="yes",
                side="BUY",
                amount=100.0,
                price=0.60,
                fees=0.60,
                slippage=0.30,
                realized_pnl=-60.90
            ),
            Trade(
                id="trade2",
                timestamp=datetime.utcnow(),
                market_id="market2",
                outcome_id="no",
                side="SELL",
                amount=100.0,
                price=0.71,
                fees=0.71,
                slippage=0.36,
                realized_pnl=69.93
            )
        ]
        
        # Report iteration
        print("Recording iteration 1...")
        reporter.report_iteration(
            iteration=1,
            all_markets=markets,
            detected_opportunities=[opportunity],
            approved_opportunities=[opportunity]
        )
        print("[OK] Iteration recorded")
        print()
        
        # Log opportunity execution
        print("Logging opportunity execution...")
        trace_id = reporter.log_opportunity_execution(
            opportunity=opportunity,
            detector_name="ParityDetector",
            prices_before={"yes": 0.60, "no": 0.71},
            intended_actions=[
                {"market_id": "market1", "outcome_id": "yes", "side": "BUY", "amount": 100.0, "price": 0.60},
                {"market_id": "market2", "outcome_id": "no", "side": "SELL", "amount": 100.0, "price": 0.71}
            ],
            risk_approval={"approved": True, "reason": "passed"},
            executions=trades,
            hedge={"action": "none", "performed": False, "decision": "continue", "reason": "none", "hedge_executions": []},
            status="success",
            realized_pnl=9.03,
            latency_ms=42
        )
        print(f"[OK] Execution logged with trace_id: {trace_id[:16]}...")
        print()
        
        # Log trades
        print("Logging trades...")
        reporter.log_trades(trades)
        print(f"[OK] {len(trades)} trades logged")
        print()
        
        # Add second iteration (no change)
        print("Recording iteration 2 (no changes)...")
        changed = reporter.report_iteration(
            iteration=2,
            all_markets=markets,
            detected_opportunities=[opportunity],
            approved_opportunities=[opportunity]
        )
        print(f"[OK] Iteration 2: {'recorded' if changed else 'skipped (no changes)'}")
        print()
        
        # Add third iteration (with change)
        print("Recording iteration 3 (new market)...")
        markets_expanded = markets + [
            Market(
                id="market3",
                question="Will it be sunny?",
                liquidity=1200.0,
                volume=600.0,
                outcomes=[
                    Outcome(id="yes", label="Yes", price=0.75),
                    Outcome(id="no", label="No", price=0.26)
                ]
            )
        ]
        reporter.report_iteration(
            iteration=3,
            all_markets=markets_expanded,
            detected_opportunities=[opportunity],
            approved_opportunities=[opportunity]
        )
        print("[OK] Iteration 3 recorded (market count changed)")
        print()
        
        # Display summary
        print("=" * 80)
        print("GENERATED SUMMARY")
        print("=" * 80)
        summary = generate_reports_summary(reports_dir)
        print(summary)
        print()
        
        # Export to legacy format
        print("=" * 80)
        print("EXPORTING TO LEGACY FORMAT")
        print("=" * 80)
        export_legacy_csv(reports_dir, reports_dir)
        print()
        
        # List generated files
        print("Generated files:")
        for file in sorted(reports_dir.glob("*")):
            size = file.stat().st_size
            print(f"  {file.name:30s} ({size:,} bytes)")
        print()
        
        print("=" * 80)
        print("DEMO COMPLETE")
        print("=" * 80)
        print()
        print("Key benefits of unified reporting:")
        print("  • Single JSON file instead of 3 separate files")
        print("  • Atomic updates (safer concurrent access)")
        print("  • Easy programmatic querying")
        print("  • Built-in deduplication and change detection")
        print("  • Backward compatible via export_legacy_csv()")
        print()

if __name__ == "__main__":
    demo_unified_reporter()
