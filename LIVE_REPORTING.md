# Live Incremental Reporting

## Overview

The **Live Incremental Reporter** is a production-grade component that generates append-only CSV reports during live arbitrage bot execution. It automatically deduplicates data to prevent duplicate reporting while ensuring restart-safety and minimal I/O overhead.

## Key Features

✅ **Append-only reporting** - Never overwrites existing rows  
✅ **Smart deduplication** - Only writes when data actually changes  
✅ **Restart-safe** - Persists state to disk for recovery after crashes  
✅ **Deterministic** - Order-independent hashing prevents false positives  
✅ **Non-blocking** - Minimal I/O, designed for continuous loops  
✅ **Production-ready** - No placeholders, comprehensive error handling

## Architecture

### Core Components

| Component | Location | Role |
|-----------|----------|------|
| **LiveReporter** | `src/predarb/reporter.py` | Main deduplication engine |
| **Engine integration** | `src/predarb/engine.py` | Calls reporter in run loop |
| **State file** | `reports/.last_report_state.json` | Persistent hash storage |
| **CSV report** | `reports/live_summary.csv` | Append-only data log |

### Hashing Strategy

The reporter uses **SHA256 hashing** on sorted, order-independent data:

```python
# Market hash: sorted market IDs
markets = ["m1", "m2", "m3"]
hash = sha256("|".join(sorted(markets)))

# Opportunity hash: sorted opportunity identifiers
opps = ["type1:m1|m2", "type2:m3"]
hash = sha256("|".join(sorted(opps)))
```

This ensures:
- Markets `[m1, m2]` hash identically to `[m2, m1]`
- Adding/removing markets changes the hash
- Adding/removing opportunities changes the hash
- Floating-point noise is avoided (no price diffs)

## Integration with Engine

The reporter is integrated into the `Engine` class:

```python
class Engine:
    def __init__(self, config, client, notifier=None):
        # ... existing code ...
        self.reporter = LiveReporter()
        self._last_detected = []
        self._last_approved = []
        self._last_markets = []
    
    def run_once(self) -> List[Opportunity]:
        # ... detect opportunities ...
        
        # Store for reporting
        self._last_markets = all_markets
        self._last_detected = all_detected_opportunities
        self._last_approved = executed
        return executed
    
    def run(self):
        for i in range(self.config.engine.iterations):
            self.run_once()
            
            # Generate report (only writes if data changed)
            self.reporter.report(
                iteration=i + 1,
                all_markets=self._last_markets,
                detected_opportunities=self._last_detected,
                approved_opportunities=self._last_approved,
            )
            time.sleep(self.config.engine.refresh_seconds)
```

## Report Format

### CSV Schema

File: `reports/live_summary.csv`

| Column | Type | Description |
|--------|------|-------------|
| `timestamp` | ISO8601 | UTC timestamp of report generation |
| `iteration` | int | Iteration number (1-indexed) |
| `markets_found` | int | Total markets fetched from API |
| `opps_found` | int | Opportunities detected by all detectors |
| `opps_after_filter` | int | Opportunities approved by risk manager |

### Example CSV

```csv
timestamp,iteration,markets_found,opps_found,opps_after_filter
2026-01-07T08:09:19.541940,1,2,1,1
2026-01-07T08:09:19.551098,3,3,1,1
2026-01-07T08:09:19.554387,4,3,2,2
2026-01-07T08:09:19.558772,5,3,1,1
```

Note: Only iterations with data changes are recorded (iteration 2 is missing because data was identical).

### State File

File: `reports/.last_report_state.json`

```json
{
  "market_ids_hash": "34c00fa986672a62e926d7c8b40c8a2c6c93fded97e1e39e2a4f23ae7394b4c8",
  "approved_opp_ids_hash": "0f5aa07cf677419de48c50ad46e3a0cd0f97d66ad8c35a45a46f11d2a35c3f2f",
  "last_updated": "2026-01-07T08:09:19.560390"
}
```

This file enables restart-safety: if the bot crashes and restarts, it resumes from the correct state without reprinting old data.

## Usage

### Basic Usage

```python
from predarb.reporter import LiveReporter

reporter = LiveReporter()

# Report iteration results
wrote = reporter.report(
    iteration=1,
    all_markets=markets,
    detected_opportunities=all_opps,
    approved_opportunities=executed_opps,
)

# Returns True if new row was written, False if state unchanged
if wrote:
    print("New report row appended")
else:
    print("No changes, skipped report")
```

### Custom Reports Directory

```python
from pathlib import Path

reporter = LiveReporter(reports_dir=Path("/custom/reports/path"))
```

### Running the Demo

```bash
python demo_reporter.py
```

Output shows:
- ✓ Rows appended when data changes
- ✗ Rows skipped when data is identical
- State file persistence
- CSV accumulation

## Behavior Examples

| Scenario | Iteration | Markets | Opps | Approved | Write? | Why |
|----------|-----------|---------|------|----------|--------|-----|
| First run | 1 | 10 | 5 | 3 | ✓ | Initial state |
| No change | 2 | 10 | 5 | 3 | ✗ | Same hashes |
| New market | 3 | 11 | 5 | 3 | ✓ | Market hash changed |
| New opp | 4 | 11 | 6 | 4 | ✓ | Opportunity hash changed |
| Opp removed | 5 | 11 | 5 | 3 | ✓ | Opportunity hash changed |
| Bot restart | 6 | 11 | 5 | 3 | ✗ | State loaded from disk |

## Implementation Details

### Deduplication Logic

```python
def report(self, iteration, all_markets, detected_opportunities, approved_opportunities):
    # Compute hashes of current state
    current_market_hash = self._compute_hash(self._get_market_ids(all_markets))
    current_approved_hash = self._compute_hash(self._get_opportunity_ids(approved_opportunities))
    
    # Check if state changed
    if (current_market_hash == self.last_state["market_ids_hash"] and
        current_approved_hash == self.last_state["approved_opp_ids_hash"]):
        return False  # No change, skip
    
    # Write row and update state
    self._append_csv_row(...)
    self._save_state(current_market_hash, current_approved_hash)
    return True
```

### Error Handling

The reporter is resilient to I/O failures:

```python
def _append_csv_row(self, ...):
    try:
        with open(self.summary_csv, "a", encoding="utf-8") as f:
            # Write CSV
    except OSError as e:
        logger.error(f"Failed to append CSV row: {e}")
        # Continue without blocking engine

def _save_state(self, ...):
    try:
        with open(self.state_file, "w") as f:
            json.dump(state, f)
    except OSError as e:
        logger.error(f"Failed to save state: {e}")
        # Continue without blocking engine
```

## Performance Characteristics

- **Hashing**: O(m + o) where m = markets, o = opportunities
- **CSV write**: Single append (no full file rewrite)
- **State persistence**: Single JSON write (small, ~256 bytes)
- **Memory**: Minimal overhead (no state accumulation)
- **CPU**: Negligible (SHA256 on small lists)

For typical runs (100 markets, 20 opportunities):
- Hash computation: <1ms
- CSV append: <5ms
- State write: <2ms
- **Total overhead**: <10ms per iteration

## Testing

Comprehensive test suite in `tests/test_reporter.py`:

```bash
pytest tests/test_reporter.py -v
```

Tests cover:
- First report creation
- Deduplication (same data)
- Detection of market changes
- Detection of opportunity changes
- State persistence across instances
- Hash order-independence
- Opportunities without explicit IDs
- Multi-iteration CSV accumulation

## Deployment Checklist

- [x] Reporter initialized in Engine.__init__()
- [x] Detected/approved opportunities tracked in run_once()
- [x] Reporter called in run() loop after run_once()
- [x] State file created automatically (no manual setup needed)
- [x] CSV header created automatically on first write
- [x] Error handling for I/O failures
- [x] Logging at INFO level for state changes
- [x] Logging at DEBUG level for skipped iterations

## Optional Extensions (For Future)

These are easy to add but not required:

1. **Telegram integration**
   ```python
   if wrote and self.notifier:
       self.notifier.notify_report_update(markets_found, opps_after_filter)
   ```

2. **Prometheus metrics**
   ```python
   if wrote:
       metrics.markets_gauge.set(len(all_markets))
       metrics.opps_gauge.set(len(approved_opportunities))
   ```

3. **JSONL streaming** (for dashboards)
   ```python
   if wrote:
       with open("reports/live_summary.jsonl", "a") as f:
           json.dump(row, f)
           f.write("\n")
   ```

4. **Status endpoint**
   ```python
   @app.get("/api/status")
   def get_status():
       return reporter.last_state
   ```

## Troubleshooting

### CSV not being written
- Check that `reports/` directory exists and is writable
- Check logs for "Failed to append CSV row" errors
- Verify reporter is called with non-empty market/opportunity lists

### State file corruption
- Delete `reports/.last_report_state.json`
- Reporter will recreate it on next write
- Existing CSV is preserved (append-only)

### Duplicate reports after restart
- Check that state file is readable after restart
- Verify filesystem is persisting files correctly
- Look at state file timestamps to confirm persistence

## References

- **Master Prompt**: See root README for the original specification
- **Source Code**: `src/predarb/reporter.py`
- **Integration**: `src/predarb/engine.py` (run_once, run methods)
- **Tests**: `tests/test_reporter.py`
- **Demo**: `demo_reporter.py`
