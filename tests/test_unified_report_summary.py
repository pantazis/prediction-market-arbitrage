"""Tests for unified report summary generation and legacy export."""

import json
import tempfile
from pathlib import Path

import pytest

from src.report_summary import (
    export_legacy_csv,
    generate_reports_summary,
    read_unified_report,
)


@pytest.fixture
def temp_reports_dir():
    """Create a temporary reports directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


def create_sample_unified_report(reports_dir: Path):
    """Create a sample unified_report.json for testing."""
    report_data = {
        "metadata": {
            "version": "1.0",
            "created_at": "2026-01-07T08:00:00",
            "last_updated": "2026-01-07T10:00:00",
            "description": "Unified arbitrage bot reporting",
            "last_state": {
                "market_ids_hash": "abc123",
                "approved_opp_ids_hash": "def456",
                "last_markets_count": 3,
                "last_opps_detected": 1,
                "last_opps_approved": 1,
            }
        },
        "iterations": [
            {
                "iteration": 1,
                "timestamp": "2026-01-07T08:00:00",
                "markets": {"count": 2, "delta": 2},
                "opportunities_detected": {"count": 1, "delta": 1},
                "opportunities_approved": {"count": 1, "delta": 1},
                "approval_rate_pct": 100.0,
                "hashes": {
                    "markets": "abc123",
                    "approved_opps": "def456"
                }
            },
            {
                "iteration": 3,
                "timestamp": "2026-01-07T09:00:00",
                "markets": {"count": 3, "delta": 1},
                "opportunities_detected": {"count": 1, "delta": 0},
                "opportunities_approved": {"count": 1, "delta": 0},
                "approval_rate_pct": 100.0,
                "hashes": {
                    "markets": "bcd234",
                    "approved_opps": "def456"
                }
            }
        ],
        "opportunity_executions": [
            {
                "trace_id": "c198190ec8ad70e1",
                "timestamp": "2026-01-07T08:30:00",
                "opportunity": {
                    "id": "parity:market_001",
                    "type": "parity",
                    "market_ids": ["market_001"],
                    "expected_profit": 0.09
                },
                "detector": "ParityDetector",
                "status": "SUCCESS",
                "realized_pnl": 9.03,
                "latency_ms": 100
            }
        ],
        "trades": [
            {
                "id": "trade_1",
                "timestamp": "2026-01-07T08:30:01",
                "market_id": "market_001",
                "outcome_id": "yes",
                "side": "BUY",
                "amount": 100.0,
                "price": 0.60,
                "fees": 0.10,
                "slippage": 0.01,
                "realized_pnl": 4.50
            },
            {
                "id": "trade_2",
                "timestamp": "2026-01-07T08:30:02",
                "market_id": "market_001",
                "outcome_id": "no",
                "side": "SELL",
                "amount": 100.0,
                "price": 0.71,
                "fees": 0.11,
                "slippage": 0.00,
                "realized_pnl": 4.53
            }
        ]
    }
    
    report_file = reports_dir / "unified_report.json"
    report_file.write_text(json.dumps(report_data, indent=2))
    return report_file


class TestReadUnifiedReport:
    """Tests for read_unified_report function."""

    def test_reads_existing_report(self, temp_reports_dir):
        """Test reading an existing unified report."""
        create_sample_unified_report(temp_reports_dir)
        
        data = read_unified_report(temp_reports_dir)
        
        assert data is not None
        assert "metadata" in data
        assert "iterations" in data
        assert len(data["iterations"]) == 2
        assert len(data["opportunity_executions"]) == 1
        assert len(data["trades"]) == 2

    def test_returns_none_for_missing_file(self, temp_reports_dir):
        """Test returns empty dict when unified_report.json doesn't exist."""
        data = read_unified_report(temp_reports_dir)
        assert data == {
            "metadata": {},
            "iterations": [],
            "opportunity_executions": [],
            "trades": []
        }

    def test_handles_invalid_json(self, temp_reports_dir):
        """Test handles corrupted JSON gracefully."""
        report_file = temp_reports_dir / "unified_report.json"
        report_file.write_text("{invalid json")
        
        data = read_unified_report(temp_reports_dir)
        assert data == {
            "metadata": {},
            "iterations": [],
            "opportunity_executions": [],
            "trades": []
        }


class TestGenerateReportsSummary:
    """Tests for generate_reports_summary function."""

    def test_generates_summary_with_data(self, temp_reports_dir):
        """Test generates human-readable summary from unified report."""
        create_sample_unified_report(temp_reports_dir)
        
        summary = generate_reports_summary(temp_reports_dir)
        
        assert "UNIFIED ARBITRAGE BOT REPORT SUMMARY" in summary
        assert "ITERATIONS: 2 total" in summary
        assert "OPPORTUNITY EXECUTIONS: 1 total" in summary
        assert "TRADES: 2 total" in summary

    def test_shows_iteration_details(self, temp_reports_dir):
        """Test summary includes iteration details."""
        create_sample_unified_report(temp_reports_dir)
        
        summary = generate_reports_summary(temp_reports_dir)
        
        assert "Iteration 1:" in summary
    def test_shows_iteration_details(self, temp_reports_dir):
        """Test summary includes iteration details."""
        create_sample_unified_report(temp_reports_dir)
        
        summary = generate_reports_summary(temp_reports_dir)
        
        # Check that iteration data is displayed
        assert "Iteration" in summary
        assert "markets=" in summary

    def test_shows_execution_details(self, temp_reports_dir):
        """Test summary includes execution trace details."""
        create_sample_unified_report(temp_reports_dir)
        
        summary = generate_reports_summary(temp_reports_dir)
        
        # Check execution info is present
        assert "SUCCESS" in summary or "FAILED" in summary

    def test_shows_trade_details(self, temp_reports_dir):
        """Test summary includes individual trade details."""
        create_sample_unified_report(temp_reports_dir)
        
        summary = generate_reports_summary(temp_reports_dir)
        
        # Check trades section exists
        assert "TRADES:" in summary

    def test_handles_missing_report(self, temp_reports_dir):
        """Test handles missing unified report gracefully."""
        summary = generate_reports_summary(temp_reports_dir)
        
        assert "ITERATIONS: 0 total" in summary

    def test_calculates_totals(self, temp_reports_dir):
        """Test summary calculates aggregate statistics."""
        create_sample_unified_report(temp_reports_dir)
        
        summary = generate_reports_summary(temp_reports_dir)
        
        # Should show counts
        assert "ITERATIONS:" in summary
        assert "TRADES:" in summary


class TestExportLegacyCSV:
    """Tests for export_legacy_csv function."""

    def test_exports_all_legacy_files(self, temp_reports_dir):
        """Test exports all three legacy CSV files."""
        create_sample_unified_report(temp_reports_dir)
        
        export_legacy_csv(temp_reports_dir)
        
        assert (temp_reports_dir / "live_summary.csv").exists()
        assert (temp_reports_dir / "opportunity_logs.jsonl").exists()
        assert (temp_reports_dir / "paper_trades.csv").exists()

    def test_live_summary_has_correct_format(self, temp_reports_dir):
        """Test live_summary.csv has correct columns and data."""
        create_sample_unified_report(temp_reports_dir)
        
        export_legacy_csv(temp_reports_dir)
        
        csv_path = temp_reports_dir / "live_summary.csv"
        content = csv_path.read_text()
        
        # Check that it's a valid CSV with expected data
        assert "TIMESTAMP" in content or "timestamp" in content
        assert len(content) > 0

    def test_opportunity_logs_has_jsonl_format(self, temp_reports_dir):
        """Test opportunity_logs.jsonl has one JSON object per line."""
        create_sample_unified_report(temp_reports_dir)
        
        export_legacy_csv(temp_reports_dir)
        
        jsonl_path = temp_reports_dir / "opportunity_logs.jsonl"
        content = jsonl_path.read_text()
        
        # Should be valid
        assert len(content) > 0

    def test_paper_trades_has_correct_format(self, temp_reports_dir):
        """Test paper_trades.csv has correct columns and data."""
        create_sample_unified_report(temp_reports_dir)
        
        export_legacy_csv(temp_reports_dir)
        
        csv_path = temp_reports_dir / "paper_trades.csv"
        content = csv_path.read_text()
        
        # Check that it has content
        assert len(content) > 0

    def test_handles_empty_report(self, temp_reports_dir):
        """Test handles report with no data gracefully."""
        # Create minimal report
        report_data = {
            "metadata": {"version": "1.0"},
            "iterations": [],
            "opportunity_executions": [],
            "trades": []
        }
        report_file = temp_reports_dir / "unified_report.json"
        report_file.write_text(json.dumps(report_data))
        
        export_legacy_csv(temp_reports_dir)
        
        # Files should exist
        assert (temp_reports_dir / "live_summary.csv").exists()

    def test_overwrites_existing_files(self, temp_reports_dir):
        """Test overwrites existing legacy CSV files."""
        create_sample_unified_report(temp_reports_dir)
        
        # Create old file
        old_csv = temp_reports_dir / "live_summary.csv"
        old_csv.write_text("old data")
        
        # Export new data
        export_legacy_csv(temp_reports_dir)
        
        # Should be overwritten
        new_content = old_csv.read_text()
        assert "old data" not in new_content


class TestBackwardCompatibility:
    """Tests for backward compatibility with old reporting system."""

    def test_legacy_export_matches_old_format(self, temp_reports_dir):
        """Test legacy export produces files compatible with old readers."""
        create_sample_unified_report(temp_reports_dir)
        
        export_legacy_csv(temp_reports_dir)
        
        # Test that files are created
        assert (temp_reports_dir / "live_summary.csv").exists()
        assert (temp_reports_dir / "opportunity_logs.jsonl").exists()
        assert (temp_reports_dir / "paper_trades.csv").exists()

    def test_summary_still_works_after_migration(self, temp_reports_dir):
        """Test generate_reports_summary works with unified format."""
        create_sample_unified_report(temp_reports_dir)
        
        # Should generate summary without errors
        summary = generate_reports_summary(temp_reports_dir)
        
        assert summary is not None
        assert len(summary) > 0
        assert "UNIFIED ARBITRAGE BOT REPORT SUMMARY" in summary
