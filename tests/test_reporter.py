"""Tests for live incremental reporting."""

import json
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from predarb.models import Market, Opportunity, Outcome
from predarb.reporter import LiveReporter


@pytest.fixture
def temp_reports_dir():
    """Create a temporary reports directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


def create_market(market_id: str) -> Market:
    """Helper to create a test market."""
    outcomes = [
        Outcome(id="yes", name="Yes", price=0.5),
        Outcome(id="no", name="No", price=0.5),
    ]
    return Market(
        id=market_id,
        question="Test question?",
        outcomes=outcomes,
        liquidity_usd=1000.0,
        volume_24h=500.0,
    )


def create_opportunity(opp_id: str, market_id: str, detector_type: str = "parity") -> Opportunity:
    """Helper to create a test opportunity."""
    opp = Opportunity(
        market_id=market_id,
        edge=0.05,
        expected_profit_usd=50.0,
    )
    # Manually set attributes for testing
    opp.id = opp_id
    opp.detector_type = detector_type
    return opp


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
    assert len(lines) == 2  # Header + 1 data row
    assert lines[0] == "timestamp,iteration,markets_found,opps_found,opps_after_filter"
    assert "1,2,2,1" in lines[1]  # iteration, markets, opps_detected, opps_approved


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
    
    # CSV should still have only 2 lines (header + 1 data)
    lines = reporter.summary_csv.read_text().strip().split("\n")
    assert len(lines) == 2


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
    
    # CSV should have 3 lines (header + 2 data rows)
    lines = reporter.summary_csv.read_text().strip().split("\n")
    assert len(lines) == 3


def test_reporter_writes_on_opportunity_change(temp_reports_dir):
    """Test reporter writes new row when approved opportunities change."""
    reporter = LiveReporter(temp_reports_dir)
    
    markets = [create_market("m1")]
    opps1 = [create_opportunity("o1", "m1")]
    opps2 = [create_opportunity("o1", "m1"), create_opportunity("o2", "m1")]
    
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
    
    # CSV should have 3 lines (header + 2 data rows)
    lines = reporter.summary_csv.read_text().strip().split("\n")
    assert len(lines) == 3
    assert "2,2,1" in lines[2]  # iteration 2, 1 market, 1 opp detected (original), 2 approved


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
    
    # Create opportunity without id attribute
    opp = Opportunity(
        market_id="m1",
        edge=0.05,
        expected_profit_usd=50.0,
    )
    opps = [opp]
    
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
    
    # CSV should have header + 3 data rows (iterations 1, 2, 4)
    lines = reporter.summary_csv.read_text().strip().split("\n")
    assert len(lines) == 4
    assert "1,2,2,1,1" in lines[1]
    assert "2,3,2,2,2" in lines[2]
    assert "4,3,1,1,1" in lines[3]
