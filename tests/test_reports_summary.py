from pathlib import Path
import tempfile
import shutil

from src.report_summary import generate_reports_summary


def write_file(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_generate_reports_summary_with_sample_reports():
    tmpdir = Path(tempfile.mkdtemp(prefix="reports_summary_test_"))
    try:
        # Create sample live_summary.csv
        live_csv = (
            "TIMESTAMP,READABLE_TIME,ITERATION,MARKETS,MARKETS_Δ,DETECTED,DETECTED_Δ,APPROVED,APPROVED_Δ,APPROVAL%,STATUS,MARKET_HASH,OPP_HASH\n"
            "2026-01-07T08:59:16.694497,2026-01-07 08:59:16.694,1,2,-1,1,0,1,0,100.0%,✓ NEW,34c00fa986672a62,0f5aa07cf677419d\n"
        )
        write_file(tmpdir / "live_summary.csv", live_csv)

        # Create sample paper_trades.csv with header (per engine._write_report)
        trades_csv = (
            "timestamp,market_id,outcome_id,side,amount,price,fees,slippage,realized_pnl\n"
            "2026-01-07T07:43:07.395949,market_001,yes,BUY,1.0,0.36355,0.00036,0.00072,-0.36464\n"
        )
        write_file(tmpdir / "paper_trades.csv", trades_csv)

        summary = generate_reports_summary(tmpdir)
        # Basic assertions for human-readable content
        assert "Live Summary:" in summary
        assert "Paper Trades:" in summary
        assert "Iteration 1" in summary
        assert "market=market_001" in summary
        assert "BUY 1.0@0.36355" in summary
        assert "approval=100.0%" in summary
    finally:
        shutil.rmtree(tmpdir)


def test_generate_reports_summary_handles_missing_files():
    tmpdir = Path(tempfile.mkdtemp(prefix="reports_summary_test_"))
    try:
        summary = generate_reports_summary(tmpdir)
        assert "No report files found" in summary
    finally:
        shutil.rmtree(tmpdir)
