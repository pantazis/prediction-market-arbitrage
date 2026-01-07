"""Tests for unified JSON reporting system."""

import json
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from predarb.models import Market, Opportunity, Outcome, Trade, TradeAction
from predarb.unified_reporter import UnifiedReporter


@pytest.fixture
def temp_reports_dir():
    """Create a temporary reports directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


def create_market(market_id: str) -> Market:
    """Helper to create a test market."""
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


def create_opportunity(opp_id: str, market_id: str) -> Opportunity:
    """Helper to create a test opportunity."""
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
        type="parity",
        market_ids=[market_id],
        description=f"Test {opp_id}",
        net_edge=0.05,
        actions=actions,
        metadata={"opp_id": opp_id},
    )


def create_trade(market_id: str, side: str = "BUY") -> Trade:
    """Helper to create a test trade."""
    return Trade(
        id=f"trade_{market_id}_{side}",
        timestamp=datetime.utcnow(),
        market_id=market_id,
        outcome_id="yes",
        side=side,
        amount=100.0,
        price=0.5,
        fees=0.01,
        slippage=0.0,
        realized_pnl=5.0,
    )


class TestUnifiedReporterInitialization:
    """Tests for UnifiedReporter initialization."""

    def test_creates_reports_directory(self, temp_reports_dir):
        """Test reporter creates reports directory if it doesn't exist."""
        subdir = temp_reports_dir / "new_reports"
        reporter = UnifiedReporter(subdir)
        assert subdir.exists()
        assert reporter.reports_dir == subdir

    def test_creates_unified_report_file(self, temp_reports_dir):
        """Test reporter creates unified_report.json on first use."""
        reporter = UnifiedReporter(temp_reports_dir)
        report_file = temp_reports_dir / "unified_report.json"
        
        # File shouldn't exist until first write
        assert not report_file.exists()
        
        # Report data structure should be initialized
        assert "metadata" in reporter.report_data
        assert "iterations" in reporter.report_data
        assert "opportunity_executions" in reporter.report_data
        assert "trades" in reporter.report_data

    def test_loads_existing_report(self, temp_reports_dir):
        """Test reporter loads existing unified_report.json."""
        report_file = temp_reports_dir / "unified_report.json"
        
        # Create initial report
        initial_data = {
            "metadata": {
                "version": "1.0",
                "created_at": "2026-01-07T10:00:00",
                "last_updated": "2026-01-07T10:00:00",
                "description": "Test report",
                "last_state": {
                    "market_ids_hash": "abc123",
                    "approved_opp_ids_hash": "def456",
                }
            },
            "iterations": [{"iteration": 1, "timestamp": "2026-01-07T10:00:00"}],
            "opportunity_executions": [],
            "trades": []
        }
        report_file.write_text(json.dumps(initial_data, indent=2))
        
        # Load and verify
        reporter = UnifiedReporter(temp_reports_dir)
        assert len(reporter.report_data["iterations"]) == 1
        assert reporter.last_state["market_ids_hash"] == "abc123"


class TestReportIteration:
    """Tests for report_iteration method."""

    def test_first_iteration_writes_data(self, temp_reports_dir):
        """Test first iteration writes to unified report."""
        reporter = UnifiedReporter(temp_reports_dir)
        
        markets = [create_market("m1"), create_market("m2")]
        detected = [create_opportunity("o1", "m1")]
        approved = [create_opportunity("o1", "m1")]
        
        changed = reporter.report_iteration(
            iteration=1,
            all_markets=markets,
            detected_opportunities=detected,
            approved_opportunities=approved,
        )
        
        assert changed is True
        assert reporter.report_file.exists()
        
        # Verify file contents
        with open(reporter.report_file) as f:
            data = json.load(f)
        
        assert len(data["iterations"]) == 1
        iteration = data["iterations"][0]
        assert iteration["iteration"] == 1
        assert iteration["markets"]["count"] == 2
        assert iteration["opportunities_detected"]["count"] == 1
        assert iteration["opportunities_approved"]["count"] == 1

    def test_unchanged_state_skips_write(self, temp_reports_dir):
        """Test iteration with no changes doesn't write duplicate."""
        reporter = UnifiedReporter(temp_reports_dir)
        
        markets = [create_market("m1")]
        detected = [create_opportunity("o1", "m1")]
        approved = [create_opportunity("o1", "m1")]
        
        # First call writes
        changed1 = reporter.report_iteration(1, markets, detected, approved)
        assert changed1 is True
        
        # Second call with same data skips
        changed2 = reporter.report_iteration(2, markets, detected, approved)
        assert changed2 is False
        
        # Verify only one iteration in file
        with open(reporter.report_file) as f:
            data = json.load(f)
        assert len(data["iterations"]) == 1

    def test_changed_markets_triggers_write(self, temp_reports_dir):
        """Test market changes trigger new iteration write."""
        reporter = UnifiedReporter(temp_reports_dir)
        
        markets1 = [create_market("m1")]
        markets2 = [create_market("m1"), create_market("m2")]
        opps = [create_opportunity("o1", "m1")]
        
        reporter.report_iteration(1, markets1, opps, opps)
        changed = reporter.report_iteration(2, markets2, opps, opps)
        
        assert changed is True
        
        with open(reporter.report_file) as f:
            data = json.load(f)
        assert len(data["iterations"]) == 2
        assert data["iterations"][1]["markets"]["count"] == 2

    def test_changed_opportunities_triggers_write(self, temp_reports_dir):
        """Test opportunity changes trigger new iteration write."""
        reporter = UnifiedReporter(temp_reports_dir)
        
        markets = [create_market("m1")]
        opps1 = [create_opportunity("o1", "m1")]
        opps2 = [create_opportunity("o1", "m1"), create_opportunity("o2", "m1")]
        
        reporter.report_iteration(1, markets, opps1, opps1)
        changed = reporter.report_iteration(2, markets, opps2, opps2)
        
        assert changed is True
        
        with open(reporter.report_file) as f:
            data = json.load(f)
        assert len(data["iterations"]) == 2
        assert data["iterations"][1]["opportunities_approved"]["count"] == 2

    def test_calculates_deltas_correctly(self, temp_reports_dir):
        """Test delta calculations between iterations."""
        reporter = UnifiedReporter(temp_reports_dir)
        
        markets1 = [create_market("m1"), create_market("m2")]
        markets2 = [create_market("m1")]  # One fewer
        detected1 = [create_opportunity("o1", "m1"), create_opportunity("o2", "m1")]
        detected2 = [create_opportunity("o1", "m1")]  # One fewer
        
        reporter.report_iteration(1, markets1, detected1, detected1)
        reporter.report_iteration(2, markets2, detected2, detected2)
        
        with open(reporter.report_file) as f:
            data = json.load(f)
        
        iter2 = data["iterations"][1]
        assert iter2["markets"]["delta"] == -1
        assert iter2["opportunities_detected"]["delta"] == -1
        assert iter2["opportunities_approved"]["delta"] == -1


class TestLogOpportunityExecution:
    """Tests for log_opportunity_execution method."""

    def test_logs_execution_with_trace_id(self, temp_reports_dir):
        """Test logging opportunity execution creates trace entry."""
        reporter = UnifiedReporter(temp_reports_dir)
        
        opp = create_opportunity("o1", "m1")
        
        trace_id = reporter.log_opportunity_execution(
            opportunity=opp,
            detector_name="test_detector",
            prices_before={"m1": 0.5},
            intended_actions=[],
            risk_approval={"approved": True},
            executions=[],
            hedge=None,
            status="SUCCESS",
            realized_pnl=5.0,
            latency_ms=100,
        )
        
        assert trace_id is not None
        assert len(trace_id) > 16  # SHA256 hash
        
        with open(reporter.report_file) as f:
            data = json.load(f)
        
        assert len(data["opportunity_executions"]) == 1
        exec_entry = data["opportunity_executions"][0]
        assert exec_entry["trace_id"] == trace_id
        assert exec_entry["status"] == "SUCCESS"
        assert exec_entry["realized_pnl"] == 5.0

    def test_logs_failed_execution(self, temp_reports_dir):
        """Test logging failed opportunity execution."""
        reporter = UnifiedReporter(temp_reports_dir)
        
        opp = create_opportunity("o1", "m1")
        
        trace_id = reporter.log_opportunity_execution(
            opportunity=opp,
            detector_name="test_detector",
            prices_before={"m1": 0.5},
            intended_actions=[],
            risk_approval={"approved": True},
            executions=[],
            hedge=None,
            status="FAILED",
            realized_pnl=0.0,
            latency_ms=50,
            failure_flags=["Insufficient balance"],
        )
        
        with open(reporter.report_file) as f:
            data = json.load(f)
        
        exec_entry = data["opportunity_executions"][0]
        assert exec_entry["status"] == "FAILED"
        assert "Insufficient balance" in exec_entry.get("failure_flags", [])

    def test_execution_includes_opportunity_details(self, temp_reports_dir):
        """Test execution log includes opportunity metadata."""
        reporter = UnifiedReporter(temp_reports_dir)
        
        opp = create_opportunity("o1", "m1")
        trace_id = reporter.log_opportunity_execution(
            opportunity=opp,
            detector_name="test_detector",
            prices_before={"m1": 0.5},
            intended_actions=[],
            risk_approval={"approved": True},
            executions=[],
            hedge=None,
            status="SUCCESS",
            realized_pnl=5.0,
            latency_ms=100,
        )
        
        with open(reporter.report_file) as f:
            data = json.load(f)
        
        exec_entry = data["opportunity_executions"][0]
        assert exec_entry["opportunity"]["type"] == "test"
        assert "m1" in exec_entry["opportunity"]["market_ids"]
        assert exec_entry["opportunity_type"] == "parity"
        assert exec_entry["market_ids"] == ["m1"]
        assert exec_entry["net_edge"] == 0.05


class TestLogTrades:
    """Tests for log_trades method."""

    def test_logs_single_trade(self, temp_reports_dir):
        """Test logging a single trade."""
        reporter = UnifiedReporter(temp_reports_dir)
        
        trade = create_trade("m1", "BUY")
        reporter.log_trades([trade])
        
        with open(reporter.report_file) as f:
            data = json.load(f)
        
        assert len(data["trades"]) == 1
        trade_entry = data["trades"][0]
        assert trade_entry["market_id"] == "m1"
        assert trade_entry["side"] == "BUY"
        assert trade_entry["amount"] == 100.0
        assert trade_entry["realized_pnl"] == 5.0

    def test_logs_multiple_trades(self, temp_reports_dir):
        """Test logging multiple trades at once."""
        reporter = UnifiedReporter(temp_reports_dir)
        
        trades = [
            create_trade("m1", "BUY"),
            create_trade("m1", "SELL"),
            create_trade("m2", "BUY"),
        ]
        reporter.log_trades(trades)
        
        with open(reporter.report_file) as f:
            data = json.load(f)
        
        assert len(data["trades"]) == 3
        sides = [t["side"] for t in data["trades"]]
        assert sides == ["BUY", "SELL", "BUY"]

    def test_appends_trades_to_existing(self, temp_reports_dir):
        """Test trades are appended to existing trade log."""
        reporter = UnifiedReporter(temp_reports_dir)
        
        trade1 = create_trade("m1", "BUY")
        trade2 = create_trade("m2", "SELL")
        
        reporter.log_trades([trade1])
        reporter.log_trades([trade2])
        
        with open(reporter.report_file) as f:
            data = json.load(f)
        
        assert len(data["trades"]) == 2


class TestAtomicWrites:
    """Tests for atomic file write operations."""

    def test_atomic_write_prevents_corruption(self, temp_reports_dir):
        """Test atomic writes protect against partial writes."""
        reporter = UnifiedReporter(temp_reports_dir)
        
        markets = [create_market("m1")]
        opps = [create_opportunity("o1", "m1")]
        
        # Write initial data
        reporter.report_iteration(1, markets, opps, opps)
        
        # Verify file is valid JSON
        with open(reporter.report_file) as f:
            data1 = json.load(f)
        
        # Write more data
        reporter.report_iteration(2, markets + [create_market("m2")], opps, opps)
        
        # Verify file is still valid JSON
        with open(reporter.report_file) as f:
            data2 = json.load(f)
        
        assert len(data2["iterations"]) == 2

    def test_handles_write_errors_gracefully(self, temp_reports_dir):
        """Test reporter handles write errors without corrupting data."""
        reporter = UnifiedReporter(temp_reports_dir)
        
        markets = [create_market("m1")]
        opps = [create_opportunity("o1", "m1")]
        
        # Write initial data
        reporter.report_iteration(1, markets, opps, opps)
        
        # Make directory read-only to force write error
        reporter.report_file.chmod(0o444)
        
        try:
            # This should fail but not crash
            reporter.report_iteration(2, markets, opps, opps)
        except (OSError, PermissionError):
            pass  # Expected
        finally:
            # Restore permissions
            reporter.report_file.chmod(0o644)
        
        # Original data should still be intact
        with open(reporter.report_file) as f:
            data = json.load(f)
        assert len(data["iterations"]) == 1


class TestStateManagement:
    """Tests for internal state tracking."""

    def test_computes_hash_consistently(self, temp_reports_dir):
        """Test hash computation is consistent for same inputs."""
        reporter = UnifiedReporter(temp_reports_dir)
        
        markets = [create_market("m1"), create_market("m2")]
        hash1 = reporter._compute_hash([m.id for m in markets])
        hash2 = reporter._compute_hash([m.id for m in markets])
        
        assert hash1 == hash2

    def test_hash_order_independent(self, temp_reports_dir):
        """Test hash is order-independent (sorted internally)."""
        reporter = UnifiedReporter(temp_reports_dir)
        
        ids1 = ["m1", "m2", "m3"]
        ids2 = ["m3", "m1", "m2"]
        
        hash1 = reporter._compute_hash(ids1)
        hash2 = reporter._compute_hash(ids2)
        
        assert hash1 == hash2

    def test_persists_state_across_instances(self, temp_reports_dir):
        """Test state persists when creating new reporter instances."""
        markets = [create_market("m1")]
        opps = [create_opportunity("o1", "m1")]
        
        # First instance writes data
        reporter1 = UnifiedReporter(temp_reports_dir)
        reporter1.report_iteration(1, markets, opps, opps)
        
        # Second instance loads saved state
        reporter2 = UnifiedReporter(temp_reports_dir)
        assert reporter2.last_state["market_ids_hash"] is not None
        
        # Should detect no change
        changed = reporter2.report_iteration(2, markets, opps, opps)
        assert changed is False
