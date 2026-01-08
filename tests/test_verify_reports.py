"""Tests for report verification tool."""
import json
import pytest
from pathlib import Path
from datetime import datetime, timedelta
from src.predarb.verify_reports import (
    ReportVerifier,
    verify_reports,
    EXIT_OK,
    EXIT_MISSING,
    EXIT_INVALID_SCHEMA,
    EXIT_NO_ITERATIONS,
    EXIT_MISSING_DATA,
    EXIT_INVARIANT_FAILED,
)


@pytest.fixture
def valid_report_data():
    """Create valid report data structure."""
    return {
        "metadata": {
            "version": "1.0",
            "created_at": datetime.utcnow().isoformat() + "Z",
            "last_updated": datetime.utcnow().isoformat() + "Z",
            "description": "Test report",
        },
        "iterations": [
            {
                "iteration": 1,
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "markets": {"count": 10, "delta": 10},
                "opportunities_detected": {"count": 5, "delta": 5},
                "opportunities_approved": {"count": 3, "delta": 3},
                "approval_rate_pct": 60.0,
            }
        ],
        "opportunity_executions": [
            {
                "trace_id": "test_trace_1",
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "status": "success",
                "executions": [
                    {
                        "trade_id": "trade_1",
                        "market_id": "market_1",
                        "outcome_id": "yes",
                        "side": "BUY",
                        "amount": 100.0,
                        "price": 0.45,
                    }
                ],
                "hedge": {"performed": False, "hedge_executions": []},
                "failure_flags": [],
            }
        ],
        "trades": [
            {
                "trade_id": "trade_1",
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "market_id": "market_1",
                "outcome_id": "yes",
                "side": "BUY",
                "amount": 100.0,
                "price": 0.45,
                "fees": 1.0,
                "slippage": 0.5,
                "realized_pnl": 5.0,
            }
        ],
    }


def test_verify_missing_file(tmp_path):
    """Test that missing file returns EXIT_MISSING."""
    report_path = tmp_path / "nonexistent.json"
    verifier = ReportVerifier(str(report_path))
    
    exit_code = verifier.verify()
    
    assert exit_code == EXIT_MISSING
    assert len(verifier.errors) > 0
    assert "not found" in verifier.errors[0].lower()


def test_verify_invalid_json(tmp_path):
    """Test that invalid JSON returns EXIT_INVALID_SCHEMA."""
    report_path = tmp_path / "invalid.json"
    report_path.write_text("{not valid json}")
    
    verifier = ReportVerifier(str(report_path))
    exit_code = verifier.verify()
    
    assert exit_code == EXIT_INVALID_SCHEMA
    assert any("Invalid JSON" in e for e in verifier.errors)


def test_verify_missing_required_keys(tmp_path, valid_report_data):
    """Test that missing required keys returns EXIT_INVALID_SCHEMA."""
    report_path = tmp_path / "missing_keys.json"
    
    # Remove required key
    del valid_report_data["metadata"]
    
    with open(report_path, 'w') as f:
        json.dump(valid_report_data, f)
    
    verifier = ReportVerifier(str(report_path))
    exit_code = verifier.verify()
    
    assert exit_code == EXIT_INVALID_SCHEMA
    assert any("metadata" in e.lower() for e in verifier.errors)


def test_verify_no_iterations(tmp_path, valid_report_data):
    """Test that empty iterations returns EXIT_NO_ITERATIONS."""
    report_path = tmp_path / "no_iterations.json"
    
    valid_report_data["iterations"] = []
    
    with open(report_path, 'w') as f:
        json.dump(valid_report_data, f)
    
    verifier = ReportVerifier(str(report_path))
    exit_code = verifier.verify()
    
    assert exit_code == EXIT_NO_ITERATIONS
    assert any("no iterations" in e.lower() for e in verifier.errors)


def test_verify_missing_executions(tmp_path, valid_report_data):
    """Test that missing executions with approved opps returns EXIT_MISSING_DATA."""
    report_path = tmp_path / "missing_exec.json"
    
    # Have approved opportunities but no executions
    valid_report_data["iterations"][0]["opportunities_approved"]["count"] = 5
    valid_report_data["opportunity_executions"] = []
    
    with open(report_path, 'w') as f:
        json.dump(valid_report_data, f)
    
    verifier = ReportVerifier(str(report_path))
    exit_code = verifier.verify()
    
    assert exit_code == EXIT_MISSING_DATA
    assert any("approved opportunities but 0 executions" in e for e in verifier.errors)


def test_verify_invariant_failed_no_hedge(tmp_path, valid_report_data):
    """Test that partial status without hedge returns EXIT_INVARIANT_FAILED."""
    report_path = tmp_path / "no_hedge.json"
    
    # Partial status but no hedge performed
    valid_report_data["opportunity_executions"][0]["status"] = "partial"
    valid_report_data["opportunity_executions"][0]["hedge"]["performed"] = False
    
    with open(report_path, 'w') as f:
        json.dump(valid_report_data, f)
    
    verifier = ReportVerifier(str(report_path))
    exit_code = verifier.verify()
    
    assert exit_code == EXIT_INVARIANT_FAILED
    assert any("hedge not performed" in e for e in verifier.errors)


def test_verify_invariant_residual_no_flatten(tmp_path, valid_report_data):
    """Test that residual_exposure flag without hedge executions fails."""
    report_path = tmp_path / "residual_no_flatten.json"
    
    # Residual exposure flag but no hedge executions
    valid_report_data["opportunity_executions"][0]["failure_flags"] = ["residual_exposure"]
    valid_report_data["opportunity_executions"][0]["hedge"]["hedge_executions"] = []
    
    with open(report_path, 'w') as f:
        json.dump(valid_report_data, f)
    
    verifier = ReportVerifier(str(report_path))
    exit_code = verifier.verify()
    
    assert exit_code == EXIT_INVARIANT_FAILED
    assert any("residual_exposure" in e and "no hedge executions" in e for e in verifier.errors)


def test_verify_success_case(tmp_path, valid_report_data):
    """Test that valid report returns EXIT_OK."""
    report_path = tmp_path / "valid.json"
    
    with open(report_path, 'w') as f:
        json.dump(valid_report_data, f)
    
    verifier = ReportVerifier(str(report_path))
    exit_code = verifier.verify()
    
    assert exit_code == EXIT_OK
    assert len(verifier.errors) == 0


def test_verify_success_with_warnings(tmp_path, valid_report_data):
    """Test that valid report can have warnings but still pass."""
    report_path = tmp_path / "valid_warnings.json"
    
    # Make report old (more than 1 hour)
    old_time = (datetime.utcnow() - timedelta(hours=2)).isoformat() + "Z"
    valid_report_data["metadata"]["last_updated"] = old_time
    
    with open(report_path, 'w') as f:
        json.dump(valid_report_data, f)
    
    verifier = ReportVerifier(str(report_path))
    exit_code = verifier.verify()
    
    assert exit_code == EXIT_OK
    assert len(verifier.warnings) > 0
    assert any("stale" in w.lower() for w in verifier.warnings)


def test_verify_cancelled_with_hedge(tmp_path, valid_report_data):
    """Test that cancelled status with hedge performed passes."""
    report_path = tmp_path / "cancelled_hedged.json"
    
    valid_report_data["opportunity_executions"][0]["status"] = "cancelled"
    valid_report_data["opportunity_executions"][0]["hedge"]["performed"] = True
    valid_report_data["opportunity_executions"][0]["hedge"]["hedge_executions"] = [
        {"side": "SELL", "amount": 100, "price": 0.45}
    ]
    
    with open(report_path, 'w') as f:
        json.dump(valid_report_data, f)
    
    verifier = ReportVerifier(str(report_path))
    exit_code = verifier.verify()
    
    assert exit_code == EXIT_OK


def test_verify_success_with_residual_flag_warning(tmp_path, valid_report_data):
    """Test that success with residual_exposure flag generates warning but passes."""
    report_path = tmp_path / "success_residual.json"
    
    valid_report_data["opportunity_executions"][0]["status"] = "success"
    valid_report_data["opportunity_executions"][0]["failure_flags"] = ["residual_exposure"]
    valid_report_data["opportunity_executions"][0]["hedge"]["hedge_executions"] = [
        {"side": "SELL", "amount": 10, "price": 0.50}
    ]
    
    with open(report_path, 'w') as f:
        json.dump(valid_report_data, f)
    
    verifier = ReportVerifier(str(report_path))
    exit_code = verifier.verify()
    
    assert exit_code == EXIT_OK
    assert any("residual_exposure" in w and "low liquidity" in w for w in verifier.warnings)


def test_verify_reports_function(tmp_path, valid_report_data):
    """Test the verify_reports convenience function."""
    report_path = tmp_path / "report.json"
    
    with open(report_path, 'w') as f:
        json.dump(valid_report_data, f)
    
    exit_code = verify_reports(str(report_path), verbose=False)
    
    assert exit_code == EXIT_OK


def test_verify_reports_prints_summary(tmp_path, valid_report_data, capsys):
    """Test that verbose mode prints summary."""
    report_path = tmp_path / "report.json"
    
    with open(report_path, 'w') as f:
        json.dump(valid_report_data, f)
    
    exit_code = verify_reports(str(report_path), verbose=True)
    
    captured = capsys.readouterr()
    assert "REPORT VERIFICATION SUMMARY" in captured.out
    assert "Iterations: 1" in captured.out
    assert "✅ All checks passed" in captured.out


def test_print_summary_with_multiple_iterations(tmp_path, valid_report_data):
    """Test summary with multiple iterations."""
    report_path = tmp_path / "multi_iter.json"
    
    # Add more iterations
    valid_report_data["iterations"].append({
        "iteration": 2,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "markets": {"count": 15, "delta": 5},
        "opportunities_detected": {"count": 8, "delta": 3},
        "opportunities_approved": {"count": 4, "delta": 1},
        "approval_rate_pct": 50.0,
    })
    
    with open(report_path, 'w') as f:
        json.dump(valid_report_data, f)
    
    verifier = ReportVerifier(str(report_path))
    exit_code = verifier.verify()
    
    assert exit_code == EXIT_OK
    
    # Check summary calculation
    verifier.print_summary()


def test_verify_execution_structure_warnings(tmp_path, valid_report_data):
    """Test that execution with missing fields generates warnings."""
    report_path = tmp_path / "missing_fields.json"
    
    # Remove some fields from execution
    del valid_report_data["opportunity_executions"][0]["timestamp"]
    
    with open(report_path, 'w') as f:
        json.dump(valid_report_data, f)
    
    verifier = ReportVerifier(str(report_path))
    exit_code = verifier.verify()
    
    # Should still pass but with warnings
    assert exit_code == EXIT_OK
    assert any("missing fields" in w.lower() for w in verifier.warnings)
