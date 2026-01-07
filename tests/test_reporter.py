"""Tests for live incremental reporting."""

import json
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from predarb.models import Market, Opportunity, Outcome, TradeAction
from predarb.reporter import LiveReporter


@pytest.fixture
def temp_reports_dir():
    """Create a temporary reports directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


def create_market(market_id: str) -> Market:
    """Helper to create a test market aligned with current models."""
    outcomes = [
        Outcome(id="yes", label="Yes", price=0.5),
        Outcome(id="no", label="No", price=0.5),
    ]
    return Market(
        id=market_id,
        question="Test question?",
        outcomes=outcomes,
        liquidity=1000.0,
        volume=500.0,
    )


def create_opportunity(opp_id: str, market_id: str, detector_type: str = "parity") -> Opportunity:
    """Helper to create a test opportunity aligned with current models."""
    actions = [
        TradeAction(
            market_id=market_id,
            outcome_id="yes",
            side="BUY",
            amount=100.0,
            limit_price=0.5,
        )
    ]
    return Opportunity(
        type=detector_type,
        market_ids=[market_id],
        description=f"Test {opp_id}",
        net_edge=0.05,
        actions=actions,
        metadata={"opp_id": opp_id},
    )


def test_reporter_initialization(temp_reports_dir):
    """Test reporter initializes correctly."""
    reporter = LiveReporter(temp_reports_dir)
    assert reporter.reports_dir == temp_reports_dir
    assert reporter.state_file == temp_reports_dir / ".last_report_state.json"
    assert reporter.summary_csv == temp_reports_dir / "live_summary.csv"
    assert reporter.last_state["market_ids_hash"] is None
    assert reporter.last_state["approved_opp_ids_hash"] is None


def test_reporter_first_report_writes_csv(temp_reports_dir):
    """Test first report creates CSV with header and row."""
    reporter = LiveReporter(temp_reports_dir)
    
    markets = [create_market("m1"), create_market("m2")]
    opps_detected = [create_opportunity("o1", "m1"), create_opportunity("o2", "m1")]
    opps_approved = [create_opportunity("o1", "m1")]
    
    # First report should write
    result = reporter.report(
        iteration=1,
        all_markets=markets,
        detected_opportunities=opps_detected,
        approved_opportunities=opps_approved,
    )
    
    assert result is True  # Data changed
    assert reporter.summary_csv.exists()
    
    # Check CSV contents
    lines = reporter.summary_csv.read_text().strip().split("\n")
    # We write 2 header rows + 1 data row
    assert len(lines) == 3
    assert lines[0].startswith("TIMESTAMP,READABLE_TIME,ITERATION,MARKETS")
    # Parse data row and validate key columns
    cols = lines[2].split(",")
    assert int(cols[2]) == 1  # ITERATION
    assert int(cols[3]) == 2  # MARKETS
    assert int(cols[5]) == 2  # DETECTED
    assert int(cols[7]) == 1  # APPROVED


def test_reporter_deduplicates_same_markets(temp_reports_dir):
    """Test reporter skips writing if markets and opportunities haven't changed."""
    reporter = LiveReporter(temp_reports_dir)
    
    markets = [create_market("m1"), create_market("m2")]
    opps_detected = [create_opportunity("o1", "m1")]
    opps_approved = [create_opportunity("o1", "m1")]
    
    # First report
    result1 = reporter.report(
        iteration=1,
        all_markets=markets,
        detected_opportunities=opps_detected,
        approved_opportunities=opps_approved,
    )
    assert result1 is True
    
    # Second report with same data
    result2 = reporter.report(
        iteration=2,
        all_markets=markets,
        detected_opportunities=opps_detected,
        approved_opportunities=opps_approved,
    )
    assert result2 is False  # No change
    
    # CSV should still have only 2 header rows + 1 data row
    lines = reporter.summary_csv.read_text().strip().split("\n")
    assert len(lines) == 3


def test_reporter_writes_on_market_change(temp_reports_dir):
    """Test reporter writes new row when markets change."""
    reporter = LiveReporter(temp_reports_dir)
    
    markets1 = [create_market("m1")]
    markets2 = [create_market("m1"), create_market("m2")]
    opps = [create_opportunity("o1", "m1")]
    
    # First report
    result1 = reporter.report(
        iteration=1,
        all_markets=markets1,
        detected_opportunities=opps,
        approved_opportunities=opps,
    )
    assert result1 is True
    
    # Second report with new market
    result2 = reporter.report(
        iteration=2,
        all_markets=markets2,
        detected_opportunities=opps,
        approved_opportunities=opps,
    )
    assert result2 is True  # Markets changed
    
    # CSV should have 2 header rows + 2 data rows
    lines = reporter.summary_csv.read_text().strip().split("\n")
    assert len(lines) == 4


def test_reporter_writes_on_opportunity_change(temp_reports_dir):
    """Test reporter writes new row when approved opportunities change."""
    reporter = LiveReporter(temp_reports_dir)
    
    markets = [create_market("m1"), create_market("m2")]
    opps1 = [create_opportunity("o1", "m1")]
    opps2 = [create_opportunity("o1", "m1"), create_opportunity("o2", "m2")]
    
    # First report
    result1 = reporter.report(
        iteration=1,
        all_markets=markets,
        detected_opportunities=opps1,
        approved_opportunities=opps1,
    )
    assert result1 is True
    
    # Second report with additional opportunity
    result2 = reporter.report(
        iteration=2,
        all_markets=markets,
        detected_opportunities=opps2,
        approved_opportunities=opps2,
    )
    assert result2 is True  # Opportunities changed
    
    # CSV should have 2 header rows + 2 data rows
    lines = reporter.summary_csv.read_text().strip().split("\n")
    assert len(lines) == 4
    cols = lines[3].split(",")
    assert int(cols[2]) == 2  # ITERATION
    assert int(cols[3]) == 2  # MARKETS (we included m1 and m2)
    assert int(cols[5]) == 2  # DETECTED
    assert int(cols[7]) == 2  # APPROVED


def test_reporter_state_persists(temp_reports_dir):
    """Test reporter state is persisted and loaded correctly."""
    markets = [create_market("m1")]
    opps = [create_opportunity("o1", "m1")]
    
    # First reporter instance
    reporter1 = LiveReporter(temp_reports_dir)
    reporter1.report(
        iteration=1,
        all_markets=markets,
        detected_opportunities=opps,
        approved_opportunities=opps,
    )
    
    # New reporter instance should load persisted state
    reporter2 = LiveReporter(temp_reports_dir)
    assert reporter2.last_state["market_ids_hash"] is not None
    assert reporter2.last_state["approved_opp_ids_hash"] is not None
    
    # Should not write if data is the same
    result = reporter2.report(
        iteration=2,
        all_markets=markets,
        detected_opportunities=opps,
        approved_opportunities=opps,
    )
    assert result is False


def test_reporter_state_file_format(temp_reports_dir):
    """Test state file is valid JSON with expected keys."""
    reporter = LiveReporter(temp_reports_dir)
    markets = [create_market("m1")]
    opps = [create_opportunity("o1", "m1")]
    
    reporter.report(
        iteration=1,
        all_markets=markets,
        detected_opportunities=opps,
        approved_opportunities=opps,
    )
    
    # Load and check state file
    assert reporter.state_file.exists()
    state = json.loads(reporter.state_file.read_text())
    assert "market_ids_hash" in state
    assert "approved_opp_ids_hash" in state
    assert "last_updated" in state
    assert len(state["market_ids_hash"]) == 64  # SHA256 hex digest


def test_reporter_hash_order_independent(temp_reports_dir):
    """Test hashing is order-independent."""
    reporter = LiveReporter(temp_reports_dir)
    
    # Create same markets in different order
    m1_m2 = [create_market("m1"), create_market("m2")]
    m2_m1 = [create_market("m2"), create_market("m1")]
    
    hash1 = reporter._compute_hash(reporter._get_market_ids(m1_m2))
    hash2 = reporter._compute_hash(reporter._get_market_ids(m2_m1))
    
    assert hash1 == hash2, "Hash should be order-independent"


def test_reporter_handles_missing_opportunity_ids(temp_reports_dir):
    """Test reporter handles opportunities without explicit id attribute."""
    reporter = LiveReporter(temp_reports_dir)
    
    markets = [create_market("m1")]
    
    # Create an object without market_ids to exercise fallback path
    class LiteOpp:
        pass
    opps = [LiteOpp()]
    
    # Should not crash
    result = reporter.report(
        iteration=1,
        all_markets=markets,
        detected_opportunities=opps,
        approved_opportunities=opps,
    )
    
    assert result is True
    assert reporter.summary_csv.exists()


def test_reporter_csv_multiple_iterations(temp_reports_dir):
    """Test CSV accumulates rows across multiple iterations."""
    reporter = LiveReporter(temp_reports_dir)
    
    # Iteration 1: 2 markets, 1 opp
    reporter.report(
        iteration=1,
        all_markets=[create_market("m1"), create_market("m2")],
        detected_opportunities=[create_opportunity("o1", "m1")],
        approved_opportunities=[create_opportunity("o1", "m1")],
    )
    
    # Iteration 2: 3 markets, 2 opps (should write)
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
    
    # Iteration 3: same as iteration 2 (should not write)
    reporter.report(
        iteration=3,
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
    
    # Iteration 4: removed one opportunity (should write)
    reporter.report(
        iteration=4,
        all_markets=[create_market("m1"), create_market("m2"), create_market("m3")],
        detected_opportunities=[create_opportunity("o1", "m1")],
        approved_opportunities=[create_opportunity("o1", "m1")],
    )
    
    # CSV should have 2 header rows + 3 data rows (iterations 1, 2, 4)
    lines = reporter.summary_csv.read_text().strip().split("\n")
    assert len(lines) == 5
    c1 = lines[2].split(","); c2 = lines[3].split(","); c3 = lines[4].split(",")
    assert [int(c1[2]), int(c1[3]), int(c1[5]), int(c1[7])] == [1, 2, 1, 1]
    assert [int(c2[2]), int(c2[3]), int(c2[5]), int(c2[7])] == [2, 3, 2, 2]
    assert [int(c3[2]), int(c3[3]), int(c3[5]), int(c3[7])] == [4, 3, 1, 1]
