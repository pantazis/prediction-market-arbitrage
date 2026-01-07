# Unified Reporting Migration Guide

## Overview

The arbitrage bot reporting system has been consolidated from 3 separate files into a single unified JSON file for improved management and querying.

## Changes

### Before (Old System)
```
reports/
├── live_summary.csv           # Loop iteration summaries
├── opportunity_logs.jsonl     # Per-opportunity execution traces
├── paper_trades.csv           # Individual trade records
└── .last_report_state.json    # State tracking
```

### After (New System)
```
reports/
└── unified_report.json        # All reporting data in one file
```

## Benefits

1. **Single Source of Truth**: All reporting data in one structured file
2. **Atomic Updates**: Safer concurrent access with atomic writes
3. **Easier Querying**: No CSV parsing - direct JSON access
4. **Better Structure**: Nested data with full context
5. **Versioning**: Built-in metadata and version tracking

## Unified Report Structure

```json
{
  "metadata": {
    "version": "1.0",
    "created_at": "2026-01-07T...",
    "last_updated": "2026-01-07T...",
    "last_state": {
      "market_ids_hash": "...",
      "approved_opp_ids_hash": "...",
      "last_markets_count": 0,
      "last_opps_detected": 0,
      "last_opps_approved": 0
    }
  },
  "iterations": [
    {
      "iteration": 1,
      "timestamp": "2026-01-07T...",
      "markets": {"count": 150, "delta": 5},
      "opportunities_detected": {"count": 3, "delta": 1},
      "opportunities_approved": {"count": 2, "delta": 1},
      "approval_rate_pct": 66.7,
      "hashes": {...}
    }
  ],
  "opportunity_executions": [
    {
      "trace_id": "abc123...",
      "timestamp": "2026-01-07T...",
      "opportunity": {...},
      "prices_before": {...},
      "intended_actions": [...],
      "risk_approval": {...},
      "executions": [...],
      "hedge": {...},
      "status": "success",
      "realized_pnl": 10.50,
      "latency_ms": 45,
      "failure_flags": []
    }
  ],
  "trades": [
    {
      "trade_id": "uuid",
      "timestamp": "2026-01-07T...",
      "market_id": "...",
      "outcome_id": "...",
      "side": "BUY",
      "amount": 100.0,
      "price": 0.65,
      "fees": 0.65,
      "slippage": 0.32,
      "realized_pnl": -66.97
    }
  ]
}
```

## Usage

### Reading Reports

```python
from src.report_summary import read_unified_report, generate_reports_summary

# Load report
report = read_unified_report("reports")

# Get iterations
iterations = report["iterations"]
print(f"Total iterations: {len(iterations)}")

# Get executions
executions = report["opportunity_executions"]
successful = [e for e in executions if e["status"] == "success"]

# Get trades
trades = report["trades"]
total_pnl = sum(t["realized_pnl"] for t in trades)

# Print human-readable summary
print(generate_reports_summary())
```

### Backward Compatibility

If you need the old CSV/JSONL format:

```python
from src.report_summary import export_legacy_csv

# Export to legacy format
export_legacy_csv("reports")
# Creates: live_summary.csv, opportunity_logs.jsonl, paper_trades.csv
```

Or via command line:
```bash
python src/report_summary.py export
```

## Migration Steps

### Option 1: Fresh Start (Recommended for Development)
1. Delete old report files
2. Run the bot - it will create `unified_report.json`
3. All new data goes to unified format

### Option 2: Keep Old Data + New Format
1. Keep old report files for reference
2. Run the bot - it creates `unified_report.json` alongside old files
3. Old files remain static, new data goes to unified format

### Option 3: Export When Needed
1. Use unified format for live operations
2. Export to legacy format when needed for tools expecting CSV:
   ```bash
   python src/report_summary.py export
   ```

## Querying Examples

### Get Latest Iteration Stats
```python
report = read_unified_report()
latest = report["iterations"][-1]
print(f"Markets: {latest['markets']['count']}")
print(f"Approved: {latest['opportunities_approved']['count']}")
```

### Calculate Total PnL
```python
report = read_unified_report()

# From executions
exec_pnl = sum(e["realized_pnl"] for e in report["opportunity_executions"])

# From trades
trade_pnl = sum(t["realized_pnl"] for t in report["trades"])

print(f"Execution PnL: ${exec_pnl:,.2f}")
print(f"Trade PnL: ${trade_pnl:,.2f}")
```

### Filter by Status
```python
report = read_unified_report()

# Get failed executions
failed = [
    e for e in report["opportunity_executions"] 
    if e["status"] in ["partial", "cancelled"]
]

print(f"Failed/Partial executions: {len(failed)}")
for exec in failed:
    print(f"  {exec['trace_id'][:16]}: {exec['status']} - {exec['failure_flags']}")
```

### Analyze Trade Costs
```python
report = read_unified_report()
trades = report["trades"]

total_fees = sum(t["fees"] for t in trades)
total_slippage = sum(t["slippage"] for t in trades)
total_volume = sum(t["amount"] * t["price"] for t in trades)

print(f"Total Volume: ${total_volume:,.2f}")
print(f"Total Fees: ${total_fees:,.2f} ({total_fees/total_volume*100:.2f}%)")
print(f"Total Slippage: ${total_slippage:,.2f} ({total_slippage/total_volume*100:.2f}%)")
```

## Notes

- The unified reporter uses atomic writes (temp file + rename) for safety
- All timestamps are UTC in ISO8601 format
- Trade IDs are UUIDs for global uniqueness
- Trace IDs are SHA256 hashes for deterministic identification
- State hashes enable change detection for deduplication
- The file is append-only internally but saved atomically

## Troubleshooting

### "unified_report.json not found"
- Normal on first run - the file is created automatically
- Check that `reports/` directory exists and is writable

### Large File Size
- The JSON file grows with each iteration/trade
- Consider archiving old data periodically
- Or implement rotation (future enhancement)

### Need CSV for Excel
```bash
python src/report_summary.py export
```
Opens the generated CSV files in Excel as before.

## Code Changes

Files modified:
- `src/predarb/unified_reporter.py` - New unified reporter
- `src/predarb/engine.py` - Uses `UnifiedReporter` instead of `LiveReporter` + `ExecLogger`
- `src/report_summary.py` - Reads JSON, provides legacy export

Deprecated files (still available but not used):
- `src/predarb/reporter.py` - Old CSV reporter
- `src/predarb/exec_logger.py` - Old JSONL logger
