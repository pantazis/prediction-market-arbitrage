"""
Summary utility for unified JSON report.

Reads reports/unified_report.json and generates human-readable summaries.
Also provides legacy CSV export for backward compatibility.
"""

from pathlib import Path
from typing import Union, Dict, Any
import json
import csv


def read_unified_report(reports_dir: Union[str, Path] = None) -> Dict[str, Any]:
    """Read the unified JSON report.
    
    Args:
        reports_dir: Directory containing reports. Defaults to ./reports
        
    Returns:
        Parsed JSON report structure
    """
    if reports_dir is None:
        reports_dir = Path(__file__).parent.parent / "reports"
    else:
        reports_dir = Path(reports_dir)
    
    report_path = reports_dir / "unified_report.json"
    
    if not report_path.exists():
        return {
            "metadata": {},
            "iterations": [],
            "opportunity_executions": [],
            "trades": []
        }
    
    try:
        with open(report_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"Error reading unified report: {e}")
        return {
            "metadata": {},
            "iterations": [],
            "opportunity_executions": [],
            "trades": []
        }


def generate_reports_summary(reports_dir: Union[str, Path] = "reports") -> str:
    """Read unified report and return a human-readable summary.
    
    Args:
        reports_dir: Directory containing reports
        
    Returns:
        Human-readable summary string
    """
def generate_reports_summary(reports_dir: Union[str, Path] = "reports") -> str:
    """Read unified report and return a human-readable summary.
    
    Args:
        reports_dir: Directory containing reports
        
    Returns:
        Human-readable summary string
    """
    report = read_unified_report(reports_dir)
    
    metadata = report.get("metadata", {})
    iterations = report.get("iterations", [])
    executions = report.get("opportunity_executions", [])
    trades = report.get("trades", [])
    
    parts = []
    
    # Metadata
    parts.append("=" * 80)
    parts.append("UNIFIED ARBITRAGE BOT REPORT SUMMARY")
    parts.append("=" * 80)
    parts.append("")
    parts.append(f"Version: {metadata.get('version', 'N/A')}")
    parts.append(f"Created: {metadata.get('created_at', 'N/A')}")
    parts.append(f"Last Updated: {metadata.get('last_updated', 'N/A')}")
    parts.append("")
    
    # Iterations
    parts.append(f"ITERATIONS: {len(iterations)} total")
    parts.append("-" * 80)
    
    for iter_rec in iterations[-10:]:  # Show last 10
        markets = iter_rec.get('markets', {})
        detected = iter_rec.get('opportunities_detected', {})
        approved = iter_rec.get('opportunities_approved', {})
        
        parts.append(
            f"- Iteration {iter_rec.get('iteration', '?')}: "
            f"markets={markets.get('count', 0)}(delta{markets.get('delta', 0):+d}) "
            f"detected={detected.get('count', 0)}(delta{detected.get('delta', 0):+d}) "
            f"approved={approved.get('count', 0)}(delta{approved.get('delta', 0):+d}) "
            f"approval={iter_rec.get('approval_rate_pct', 'N/A')}%"
        )
    
    parts.append("")
    
    # Executions
    parts.append(f"OPPORTUNITY EXECUTIONS: {len(executions)} total")
    parts.append("-" * 80)
    
    if executions:
        status_counts = {}
        total_pnl = 0.0
        for exec_rec in executions:
            status = exec_rec.get('status', 'unknown')
            status_counts[status] = status_counts.get(status, 0) + 1
            total_pnl += exec_rec.get('realized_pnl', 0.0)
        
        for status, count in sorted(status_counts.items()):
            parts.append(f"  {status}: {count}")
        
        parts.append(f"Total PnL: ${total_pnl:,.2f}")
        
        parts.append("")
        parts.append("Recent Executions:")
        for exec_rec in executions[-5:]:  # Show last 5
            opp = exec_rec.get('opportunity', {})
            parts.append(
                f"- {exec_rec.get('timestamp', 'N/A')}: "
                f"{opp.get('type', 'N/A')} "
                f"status={exec_rec.get('status', 'N/A')} "
                f"pnl=${exec_rec.get('realized_pnl', 0):,.2f}"
            )
    
    parts.append("")
    
    # Trades
    parts.append(f"TRADES: {len(trades)} total")
    parts.append("-" * 80)
    
    if trades:
        buy_count = sum(1 for t in trades if t.get('side', '').upper() == 'BUY')
        sell_count = sum(1 for t in trades if t.get('side', '').upper() == 'SELL')
        total_volume = sum(t.get('amount', 0) * t.get('price', 0) for t in trades)
        total_fees = sum(t.get('fees', 0) for t in trades)
        trade_pnl = sum(t.get('realized_pnl', 0) for t in trades)
        
        parts.append(f"BUY: {buy_count}, SELL: {sell_count}")
        parts.append(f"Total Volume: ${total_volume:,.2f}")
        parts.append(f"Total Fees: ${total_fees:,.2f}")
        parts.append(f"Trade PnL: ${trade_pnl:,.2f}")
        
        parts.append("")
        parts.append("Recent Trades:")
        for trade in trades[-10:]:  # Show last 10
            parts.append(
                f"- {trade.get('timestamp', 'N/A')}: "
                f"{trade.get('side', 'N/A')} "
                f"{trade.get('amount', 0):.2f} @ ${trade.get('price', 0):.4f} "
                f"pnl=${trade.get('realized_pnl', 0):+,.2f}"
            )
    
    parts.append("")
    parts.append("=" * 80)
    
    return "\n".join(parts)


def export_legacy_csv(reports_dir: Union[str, Path] = "reports", output_dir: Union[str, Path] = None):
    """Export unified report to legacy CSV format for backward compatibility.
    
    Creates:
        - live_summary.csv (iterations)
        - opportunity_logs.jsonl (executions)
        - paper_trades.csv (trades)
    
    Args:
        reports_dir: Directory containing unified report
        output_dir: Directory to write legacy files. Defaults to reports_dir
    """
    if output_dir is None:
        output_dir = reports_dir
    
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    report = read_unified_report(reports_dir)
    
    # Export iterations to live_summary.csv
    iterations = report.get("iterations", [])
    if iterations:
        with open(output_dir / "live_summary.csv", "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "TIMESTAMP", "ITERATION", "MARKETS", "MARKETS_Δ",
                "DETECTED", "DETECTED_Δ", "APPROVED", "APPROVED_Δ",
                "APPROVAL%", "MARKET_HASH", "OPP_HASH"
            ])
            
            for iter_rec in iterations:
                writer.writerow([
                    iter_rec.get('timestamp', ''),
                    iter_rec.get('iteration', ''),
                    iter_rec.get('markets', {}).get('count', 0),
                    f"{iter_rec.get('markets', {}).get('delta', 0):+d}",
                    iter_rec.get('opportunities_detected', {}).get('count', 0),
                    f"{iter_rec.get('opportunities_detected', {}).get('delta', 0):+d}",
                    iter_rec.get('opportunities_approved', {}).get('count', 0),
                    f"{iter_rec.get('opportunities_approved', {}).get('delta', 0):+d}",
                    f"{iter_rec.get('approval_rate_pct', 0.0):.1f}%" if iter_rec.get('approval_rate_pct') else "N/A",
                    iter_rec.get('hashes', {}).get('markets', ''),
                    iter_rec.get('hashes', {}).get('approved_opps', '')
                ])
        print(f"Exported {len(iterations)} iterations to live_summary.csv")
    
    # Export executions to opportunity_logs.jsonl
    executions = report.get("opportunity_executions", [])
    if executions:
        with open(output_dir / "opportunity_logs.jsonl", "w", encoding="utf-8") as f:
            for exec_rec in executions:
                f.write(json.dumps(exec_rec) + "\n")
        print(f"Exported {len(executions)} executions to opportunity_logs.jsonl")
    
    # Export trades to paper_trades.csv
    trades = report.get("trades", [])
    if trades:
        with open(output_dir / "paper_trades.csv", "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "timestamp", "market_id", "outcome_id", "side",
                "amount", "price", "fees", "slippage", "realized_pnl"
            ])
            
            for trade in trades:
                writer.writerow([
                    trade.get('timestamp', ''),
                    trade.get('market_id', ''),
                    trade.get('outcome_id', ''),
                    trade.get('side', ''),
                    trade.get('amount', 0),
                    trade.get('price', 0),
                    trade.get('fees', 0),
                    trade.get('slippage', 0),
                    trade.get('realized_pnl', 0)
                ])
        print(f"Exported {len(trades)} trades to paper_trades.csv")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "export":
        print("Exporting unified report to legacy CSV format...")
        export_legacy_csv()
    else:
        print(generate_reports_summary())
