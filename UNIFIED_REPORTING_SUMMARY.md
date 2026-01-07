# Unified Reporting System - Summary

## What Changed

All reporting has been consolidated from **3 separate files** into **1 unified JSON file**:

### Before
```
reports/
├── live_summary.csv           (Loop iterations)
├── opportunity_logs.jsonl     (Execution traces)
├── paper_trades.csv           (Individual trades)
└── .last_report_state.json    (State tracking)
```

### After
```
reports/
└── unified_report.json        (Everything in one file)
```

## Files Modified

- **Created**: `src/predarb/unified_reporter.py` - New unified reporting system
- **Modified**: `src/predarb/engine.py` - Uses `UnifiedReporter` instead of `LiveReporter` + `ExecLogger`
- **Modified**: `src/report_summary.py` - Reads unified JSON, provides legacy CSV export
- **Documentation**: `UNIFIED_REPORTING_MIGRATION.md` - Full migration guide
- **Demo**: `demo_unified_reporting.py` - Interactive demonstration

## Key Benefits

1. **Single Source of Truth** - All data in one structured file
2. **Atomic Updates** - Safer concurrent access via temp file + rename
3. **Easy Querying** - Direct JSON access, no CSV parsing
4. **Change Detection** - Built-in deduplication via state hashing
5. **Backward Compatible** - Export to old format when needed

## Quick Start

### View Reports
```bash
python src/report_summary.py
```

### Export to Legacy CSV Format
```bash
python src/report_summary.py export
```

### Run Demo
```bash
$env:PYTHONPATH="$PWD/src"
python demo_unified_reporting.py
```

## Example Usage

### Python API
```python
from src.report_summary import read_unified_report

# Load report
report = read_unified_report()

# Access data
iterations = report["iterations"]
executions = report["opportunity_executions"]
trades = report["trades"]

# Calculate metrics
total_pnl = sum(t["realized_pnl"] for t in trades)
successful = [e for e in executions if e["status"] == "success"]
```

### Report Structure
```json
{
  "metadata": {
    "version": "1.0",
    "created_at": "2026-01-07T...",
    "last_updated": "2026-01-07T...",
    "last_state": { "...": "..." }
  },
  "iterations": [
    {
      "iteration": 1,
      "timestamp": "2026-01-07T...",
      "markets": {"count": 150, "delta": 5},
      "opportunities_detected": {"count": 3, "delta": 1},
      "opportunities_approved": {"count": 2, "delta": 1},
      "approval_rate_pct": 66.7
    }
  ],
  "opportunity_executions": [
    {
      "trace_id": "abc123...",
      "timestamp": "2026-01-07T...",
      "opportunity": {...},
      "executions": [...],
      "status": "success",
      "realized_pnl": 10.50
    }
  ],
  "trades": [
    {
      "trade_id": "uuid",
      "timestamp": "2026-01-07T...",
      "market_id": "...",
      "side": "BUY",
      "amount": 100.0,
      "price": 0.65,
      "realized_pnl": -66.97
    }
  ]
}
```

## Migration

### For New Deployments
- Just run the bot - it creates `unified_report.json` automatically
- Old CSV files are no longer generated

### For Existing Deployments
- Old files remain accessible (static)
- New data goes to `unified_report.json`
- Use `python src/report_summary.py export` to generate legacy format when needed

### No Code Changes Required
- The engine automatically uses the new reporter
- All functionality works transparently
- Report viewing/analysis updated to read JSON

## Demo Output

```
UNIFIED ARBITRAGE BOT REPORT SUMMARY
================================================================================

Version: 1.0
Created: 2026-01-07T12:11:23.860616
Last Updated: 2026-01-07T12:11:23.878801

ITERATIONS: 2 total
- Iteration 1: markets=2(delta+2) detected=1(delta+1) approved=1(delta+1) approval=100.0%
- Iteration 3: markets=3(delta+1) detected=1(delta+0) approved=1(delta+0) approval=100.0%

OPPORTUNITY EXECUTIONS: 1 total
  success: 1
Total PnL: $9.03

TRADES: 2 total
BUY: 1, SELL: 1
Total Volume: $131.00
Total Fees: $1.31
Trade PnL: $9.03
```

## See Also

- [UNIFIED_REPORTING_MIGRATION.md](UNIFIED_REPORTING_MIGRATION.md) - Detailed migration guide
- [codebase_schema.json](codebase_schema.json) - Technical documentation
- [demo_unified_reporting.py](demo_unified_reporting.py) - Working example
