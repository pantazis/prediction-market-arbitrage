#!/usr/bin/env python
"""Direct test runner for reporter tests (avoiding conftest issues)."""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

import tempfile
import csv
from predarb.models import Market, Opportunity, Outcome, TradeAction
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


def test_reporter_initialization():
    """Test reporter initializes correctly."""
    with tempfile.TemporaryDirectory() as tmpdir:
        reporter = LiveReporter(Path(tmpdir))
        assert reporter.reports_dir == Path(tmpdir)
        assert reporter.state_file == Path(tmpdir) / ".last_report_state.json"
        assert reporter.summary_csv == Path(tmpdir) / "live_summary.csv"
        assert reporter.last_state["market_ids_hash"] is None
        assert reporter.last_state["approved_opp_ids_hash"] is None
    print("✓ test_reporter_initialization")


def test_reporter_first_report_writes_csv():
    """Test first report creates CSV with header and row."""
    with tempfile.TemporaryDirectory() as tmpdir:
        reporter = LiveReporter(Path(tmpdir))
        
        markets = [create_market("m1"), create_market("m2")]
        opps_detected = [create_opportunity("o1", "m1"), create_opportunity("o2", "m1")]
        opps_approved = [create_opportunity("o1", "m1")]
        
        result = reporter.report(
            iteration=1,
            all_markets=markets,
            detected_opportunities=opps_detected,
            approved_opportunities=opps_approved,
        )
        
        assert result is True
        assert reporter.summary_csv.exists()
        
        lines = reporter.summary_csv.read_text().strip().split("\n")
        # Reporter writes two header rows, then data
        assert len(lines) == 3
        # Validate the data row values by parsing CSV
        rows = list(csv.reader(lines))
        data = rows[-1]
        # Columns: TIMESTAMP, READABLE_TIME, ITERATION, MARKETS, ..., DETECTED, ..., APPROVED, ...
        assert int(data[2]) == 1  # ITERATION
        assert int(data[3]) == 2  # MARKETS count
        assert int(data[5]) == 2  # DETECTED count
        assert int(data[7]) == 1  # APPROVED count
    print("✓ test_reporter_first_report_writes_csv")


def test_reporter_deduplicates_same_markets():
    """Test reporter skips writing if markets and opportunities haven't changed."""
    with tempfile.TemporaryDirectory() as tmpdir:
        reporter = LiveReporter(Path(tmpdir))
        
        markets = [create_market("m1"), create_market("m2")]
        opps_detected = [create_opportunity("o1", "m1")]
        opps_approved = [create_opportunity("o1", "m1")]
        
        result1 = reporter.report(
            iteration=1,
            all_markets=markets,
            detected_opportunities=opps_detected,
            approved_opportunities=opps_approved,
        )
        assert result1 is True
        
        result2 = reporter.report(
            iteration=2,
            all_markets=markets,
            detected_opportunities=opps_detected,
            approved_opportunities=opps_approved,
        )
        assert result2 is False
        
        lines = reporter.summary_csv.read_text().strip().split("\n")
        assert len(lines) == 3
    print("✓ test_reporter_deduplicates_same_markets")


def test_reporter_writes_on_market_change():
    """Test reporter writes new row when markets change."""
    with tempfile.TemporaryDirectory() as tmpdir:
        reporter = LiveReporter(Path(tmpdir))
        
        markets1 = [create_market("m1")]
        markets2 = [create_market("m1"), create_market("m2")]
        opps = [create_opportunity("o1", "m1")]
        
        result1 = reporter.report(
            iteration=1,
            all_markets=markets1,
            detected_opportunities=opps,
            approved_opportunities=opps,
        )
        assert result1 is True
        
        result2 = reporter.report(
            iteration=2,
            all_markets=markets2,
            detected_opportunities=opps,
            approved_opportunities=opps,
        )
        assert result2 is True
        
        lines = reporter.summary_csv.read_text().strip().split("\n")
        # Two header rows + two data rows
        assert len(lines) == 4
    print("✓ test_reporter_writes_on_market_change")


def test_reporter_writes_on_opportunity_change():
    """Test reporter writes new row when approved opportunities change."""
    with tempfile.TemporaryDirectory() as tmpdir:
        reporter = LiveReporter(Path(tmpdir))
        
        markets = [create_market("m1"), create_market("m2")]
        opps1 = [create_opportunity("o1", "m1")]
        # Different market = different opportunity hash
        opps2 = [create_opportunity("o1", "m1"), create_opportunity("o2", "m2")]
        
        result1 = reporter.report(
            iteration=1,
            all_markets=markets,
            detected_opportunities=opps1,
            approved_opportunities=opps1,
        )
        assert result1 is True
        
        result2 = reporter.report(
            iteration=2,
            all_markets=markets,
            detected_opportunities=opps2,
            approved_opportunities=opps2,
        )
        assert result2 is True
        
        lines = reporter.summary_csv.read_text().strip().split("\n")
        assert len(lines) == 4
    print("✓ test_reporter_writes_on_opportunity_change")


def test_reporter_state_persists():
    """Test reporter state is persisted and loaded correctly."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        markets = [create_market("m1")]
        opps = [create_opportunity("o1", "m1")]
        
        reporter1 = LiveReporter(tmpdir)
        reporter1.report(
            iteration=1,
            all_markets=markets,
            detected_opportunities=opps,
            approved_opportunities=opps,
        )
        
        reporter2 = LiveReporter(tmpdir)
        assert reporter2.last_state["market_ids_hash"] is not None
        assert reporter2.last_state["approved_opp_ids_hash"] is not None
        
        result = reporter2.report(
            iteration=2,
            all_markets=markets,
            detected_opportunities=opps,
            approved_opportunities=opps,
        )
        assert result is False
    print("✓ test_reporter_state_persists")


def test_reporter_hash_order_independent():
    """Test hashing is order-independent."""
    with tempfile.TemporaryDirectory() as tmpdir:
        reporter = LiveReporter(Path(tmpdir))
        
        m1_m2 = [create_market("m1"), create_market("m2")]
        m2_m1 = [create_market("m2"), create_market("m1")]
        
        hash1 = reporter._compute_hash(reporter._get_market_ids(m1_m2))
        hash2 = reporter._compute_hash(reporter._get_market_ids(m2_m1))
        
        assert hash1 == hash2
    print("✓ test_reporter_hash_order_independent")


def test_reporter_csv_multiple_iterations():
    """Test CSV accumulates rows across multiple iterations."""
    with tempfile.TemporaryDirectory() as tmpdir:
        reporter = LiveReporter(Path(tmpdir))
        
        reporter.report(
            iteration=1,
            all_markets=[create_market("m1"), create_market("m2")],
            detected_opportunities=[create_opportunity("o1", "m1")],
            approved_opportunities=[create_opportunity("o1", "m1")],
        )
        
        reporter.report(
            iteration=2,
            all_markets=[create_market("m1"), create_market("m2"), create_market("m3")],
            detected_opportunities=[
                create_opportunity("o1", "m1"),
                create_opportunity("o2", "m2"),
            ],
            approved_opportunities=[
                create_opportunity("o1", "m1"),
                create_opportunity("o2", "m2"),
            ],
        )
        
        reporter.report(
            iteration=3,
            all_markets=[create_market("m1"), create_market("m2"), create_market("m3")],
            detected_opportunities=[create_opportunity("o1", "m1")],
            approved_opportunities=[create_opportunity("o1", "m1")],
        )
        
        lines = reporter.summary_csv.read_text().strip().split("\n")
        assert len(lines) == 5  # 2 header rows + 3 data rows
    print("✓ test_reporter_csv_multiple_iterations")


if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("RUNNING REPORTER TESTS")
    print("=" * 70 + "\n")
    
    tests = [
        test_reporter_initialization,
        test_reporter_first_report_writes_csv,
        test_reporter_deduplicates_same_markets,
        test_reporter_writes_on_market_change,
        test_reporter_writes_on_opportunity_change,
        test_reporter_state_persists,
        test_reporter_hash_order_independent,
        test_reporter_csv_multiple_iterations,
    ]
    
    failed = 0
    for test in tests:
        try:
            test()
        except AssertionError as e:
            print(f"✗ {test.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"✗ {test.__name__}: {type(e).__name__}: {e}")
            failed += 1
    
    print("\n" + "=" * 70)
    print(f"RESULTS: {len(tests) - failed}/{len(tests)} tests passed")
    print("=" * 70 + "\n")
    
    sys.exit(0 if failed == 0 else 1)
