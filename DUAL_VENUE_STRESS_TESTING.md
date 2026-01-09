# Dual-Venue Stress Testing Framework

Comprehensive end-to-end testing system for arbitrage detection across **TWO** market venues (Polymarket + Kalshi) using deterministic fake data injection, with NO network calls.

---

## 🎯 Overview

This framework allows you to:
- ✅ Inject fake market data into **BOTH** Polymarket and Kalshi simultaneously
- ✅ Test **ALL** arbitrage types end-to-end: duplicate, parity, ladder, exclusive-sum, time-lag, consistency
- ✅ Run deterministically with seeded RNG for reproducible results
- ✅ Validate expected opportunities found and rejected
- ✅ Integrate with existing reports pipeline (`unified_report.json`)
- ✅ Execute in a single CLI command

---

## 🏗️ Architecture

### Components

```
src/predarb/
├── dual_injection.py          # Dual-venue injection mechanism
├── cross_venue_scenarios.py   # Comprehensive scenario generator
└── cli.py                     # CLI with dual-stress command

tests/
├── test_dual_injection.py     # Unit tests for injection
└── test_cross_venue_scenarios.py  # Tests for scenarios

run_all_scenarios.py           # Master test runner with validation
```

### Key Classes

**`DualInjectionClient`** - Wraps two market providers and merges their results
- Takes venue A provider (Polymarket) and venue B provider (Kalshi)
- Automatically tags markets with exchange identifier
- Implements `MarketClient` interface for Engine compatibility

**`InjectionFactory`** - Creates providers from injection specs
- `scenario:<name>` - Built-in stress scenarios
- `file:<path>` - Load from JSON fixture
- `inline:<json>` - Parse inline JSON
- `none` - Disable venue

**`CrossVenueArbitrageScenarios`** - Generates comprehensive test markets
- Plants every arbitrage type across both venues
- Includes negative cases (should be rejected)
- Includes edge cases (partial fills, low liquidity, etc.)

---

## 🚀 Quick Start

### 1. Run All Scenarios (Recommended)

```bash
python run_all_scenarios.py
```

This runs the comprehensive test suite with:
- ✅ Determinism validation
- ✅ Market count validation
- ✅ Exchange tag validation
- ✅ Opportunity detection validation
- ✅ Approval rate validation
- ✅ Report generation validation

**Exit codes:**
- `0` = All tests passed
- `1` = At least one test failed

### 2. Run via CLI

```bash
# Use built-in cross-venue scenario
python -m predarb dual-stress --cross-venue --seed 42

# Custom injection for each venue
python -m predarb dual-stress \
  --inject-a scenario:happy_path \
  --inject-b scenario:high_volume \
  --seed 42

# Mix file fixtures and scenarios
python -m predarb dual-stress \
  --inject-a file:tests/fixtures/poly_markets.json \
  --inject-b scenario:parity_arb \
  --seed 42

# Disable one venue
python -m predarb dual-stress \
  --inject-a scenario:happy_path \
  --inject-b none \
  --seed 42
```

### 3. Run One Iteration vs Multiple

```bash
# Single iteration (default for dual-stress)
python -m predarb dual-stress --cross-venue

# Multiple iterations
python -m predarb dual-stress --cross-venue --iterations 10
```

---

## 📊 Scenario Coverage

The comprehensive cross-venue scenario (`--cross-venue`) includes:

### A. Cross-Venue Duplicate Arbitrage
- ✅ **Profitable duplicate**: Clear price difference (Poly=0.45, Kalshi=0.60)
- ✅ **Near-zero edge**: Tiny difference (1%), should be filtered out
- ✅ **Fee killer**: Edge disappears after fees
- ✅ **Reverse direction**: Kalshi cheaper than Poly

### B. Parity Violations (YES+NO ≠ 1.0)
- ✅ **Clear profitable**: YES+NO = 0.90
- ✅ **Borderline**: YES+NO = 0.98, marginal after fees
- ✅ **Rejected**: YES+NO = 0.985, not enough edge
- ✅ **Multi-outcome**: 3 outcomes sum < 1.0

### C. Ladder Monotonicity Violations
- ✅ **Strict violation**: Price increases for worse outcome
- ✅ **Tiny violation**: Below threshold (0.5%)
- ✅ **Equal-threshold**: Prices exactly equal

### D. Exclusive-Sum Constraint Violations
- ✅ **Profitable**: Mutually exclusive outcomes sum > 1.0
- ✅ **Insufficient depth**: Low liquidity (should reject)

### E. Time-Lag / Stale Quote Arbitrage
- ✅ **Acceptable lag**: 5 minutes stale, price divergence
- ✅ **Max-staleness rejection**: 60 minutes old (should reject)

### F. Consistency Violations
- ✅ **True positive**: Logical contradiction (can't win without reaching finals)
- ✅ **False positive guard**: Ambiguous mapping (should reject)

### G. Operational Edge Cases
- ✅ **Partial fills**: Asymmetric liquidity
- ✅ **Insufficient depth**: Both legs too thin
- ✅ **Fee mismatches**: Marginal opportunities
- ✅ **Tick size rounding**: Weird price increments
- ✅ **Mismatched dates**: Same event, different expiries

---

## 🧪 Testing

### Run Unit Tests

```bash
# All dual-injection tests
pytest tests/test_dual_injection.py -v

# All cross-venue scenario tests
pytest tests/test_cross_venue_scenarios.py -v

# Run both
pytest tests/test_dual_injection.py tests/test_cross_venue_scenarios.py -v
```

### Test Coverage

**`test_dual_injection.py`** (24 tests):
- DualInjectionClient merging logic
- Exchange tagging behavior
- InjectionFactory spec parsing
- FileInjectionProvider fixtures
- InlineInjectionProvider JSON parsing
- Error handling for invalid specs

**`test_cross_venue_scenarios.py`** (23 tests):
- Determinism validation
- Market generation for each arbitrage type
- Duplicate detection viability
- Price consistency
- Unique IDs and valid dates
- Tag presence

---

## 📝 Creating Custom Fixtures

### JSON Fixture Format

```json
[
  {
    "id": "custom:market_1",
    "question": "Will event occur?",
    "outcomes": [
      {"id": "yes", "label": "YES", "price": 0.6, "liquidity": 5000},
      {"id": "no", "label": "NO", "price": 0.4, "liquidity": 5000}
    ],
    "end_date": "2026-12-31T23:59:59Z",
    "liquidity": 10000,
    "volume": 15000,
    "tags": ["test"],
    "exchange": "polymarket"
  }
]
```

### Using Custom Fixtures

```bash
# Single venue
python -m predarb dual-stress \
  --inject-a file:my_poly_markets.json \
  --inject-b file:my_kalshi_markets.json

# Mix with scenario
python -m predarb dual-stress \
  --inject-a file:custom.json \
  --inject-b scenario:happy_path
```

---

## 🔍 Validation & Assertions

The `run_all_scenarios.py` script validates:

### Market Validation
- ✅ Market counts add up correctly
- ✅ All markets have exchange tags
- ✅ All outcome IDs are unique
- ✅ All dates are valid
- ✅ All prices are in [0, 1] range

### Opportunity Validation
- ✅ Expected opportunity types are detected
- ✅ Minimum detection counts are met
- ✅ Some opportunities are approved (not all filtered)
- ✅ Approval rate is reasonable

### Determinism Validation
- ✅ Same seed produces identical market counts
- ✅ Same seed produces identical market IDs
- ✅ Same seed produces identical prices

### Report Validation
- ✅ Unified report exists
- ✅ Report contains expected structure
- ✅ Report path is correct

---

## 📈 Reading Results

### Console Output

```
================================================================================
COMPREHENSIVE ARBITRAGE STRESS TEST
================================================================================

Seed: 42
Testing ALL arbitrage types across BOTH venues

✓ Generated 15 Polymarket markets
✓ Generated 14 Kalshi markets
✓ Total: 29 markets

✓ Fetched 29 markets
✓ Detected 12 opportunities
✓ Approved 8 opportunities

DUPLICATE:
  Description: Cross-venue price differences
  Detected: 4 (expected >= 3)
  Approved: 3
  ✓ PASS: Detection count meets expectations

PARITY:
  Description: YES+NO != 1.0 within single venue
  Detected: 3 (expected >= 2)
  Approved: 2
  ✓ PASS: Detection count meets expectations

...

================================================================================
VALIDATION SUMMARY
================================================================================

✓ Passed: 15
✗ Failed: 0
⚠ Warnings: 2

Pass rate: 88.2%

✅ ALL VALIDATIONS PASSED
```

### Reports Generated

- **`reports/unified_report.json`** - Full arbitrage session report
- **`reports/live_summary.csv`** - Iteration-by-iteration summary
- **`reports/paper_trades.csv`** - Simulated trade executions

---

## 🛠️ Integration with Existing Code

### Engine Integration

The dual injection system is **fully compatible** with the existing Engine:

```python
from predarb.config import load_config
from predarb.engine import Engine
from predarb.dual_injection import DualInjectionClient, InjectionFactory

# Create providers
venue_a = InjectionFactory.from_spec("scenario:happy_path", seed=42, exchange="polymarket")
venue_b = InjectionFactory.from_spec("scenario:high_volume", seed=42, exchange="kalshi")

# Create dual client
dual_client = DualInjectionClient(venue_a, venue_b)

# Use with existing Engine
config = load_config("config.yml")
engine = Engine(config, clients=[dual_client])

# Run as normal
opportunities = engine.run_once()
```

### Detector Compatibility

**All existing detectors work unchanged:**
- `ParityDetector` - Finds YES+NO != 1.0
- `DuplicateDetector` - Finds same event on different exchanges
- `LadderDetector` - Finds monotonicity violations
- `ExclusiveSumDetector` - Finds mutually exclusive constraint violations
- `TimeLagDetector` - Finds stale quote opportunities
- `ConsistencyDetector` - Finds cross-market logic violations

Detectors are **exchange-agnostic** - they operate on the merged market list.

### Risk Manager Integration

The risk manager validates opportunities **after detection**, applying:
- Minimum liquidity filters
- Minimum edge thresholds
- Position limits
- BUY-only enforcement (no short selling)

All filters work identically regardless of exchange source.

---

## 🔧 Configuration

### Required Environment Variables

None! The injection system is **network-free** and requires no credentials.

### Optional Config Tweaks

In `config.yml`:

```yaml
risk:
  min_liquidity_usd: 1000.0    # Adjust for test scenarios
  min_net_edge_threshold: 0.02 # 2% minimum edge

broker:
  fee_bps: 50                  # 0.5% fee
  slippage_bps: 20             # 0.2% slippage

detectors:
  enable_parity: true
  enable_duplicate: true       # Must be true for cross-venue arb
  enable_ladder: true
  enable_exclusive_sum: true
  enable_timelag: true
  enable_consistency: true
```

---

## 🚦 Exit Codes

- **0** = All tests passed successfully
- **1** = One or more tests failed
- **2-6** = Reserved for specific failure modes

---

## 🐛 Troubleshooting

### "No opportunities detected"

**Possible causes:**
1. Risk filters too strict (check `min_liquidity_usd`, `min_net_edge_threshold`)
2. Detectors disabled (check `config.yml` detector flags)
3. Scenario seed produces no viable opportunities (try different seed)

**Solutions:**
```bash
# Check what's in the markets
python -c "
from src.predarb.cross_venue_scenarios import get_cross_venue_scenario
poly, kalshi = get_cross_venue_scenario(42)
print(f'Poly: {len(poly)}, Kalshi: {len(kalshi)}')
"

# Run with verbose output
python run_all_scenarios.py --seed 42
```

### "Market counts don't add up"

**Cause:** DualInjectionClient may have None providers

**Solution:** Check that injection specs are valid:
```bash
python -m predarb dual-stress --inject-a scenario:happy_path --inject-b scenario:high_volume
```

### "All opportunities rejected by risk filters"

**Expected behavior** for negative test cases! Some scenarios plant opportunities that **should** be rejected (low liquidity, tiny edge, etc.).

Check the warnings section in the validation summary to see which types were filtered out.

---

## 📚 Related Documentation

- **`KALSHI_INTEGRATION.md`** - Multi-exchange architecture details
- **`SIMULATION_HARNESS.md`** - Simulation framework overview
- **`TESTING_GUIDE_SIMPLE.md`** - General testing guide
- **`INVARIANT_TESTS.md`** - Unit test patterns

---

## 💡 Advanced Usage

### Custom Scenario Generator

Create your own scenario by extending `StressScenario`:

```python
from src.predarb.stress_scenarios import StressScenario
from src.predarb.models import Market, Outcome

class MyCustomScenario(StressScenario):
    def get_active_markets(self):
        # Generate custom markets
        return [...]

# Register scenario
from src.predarb.stress_scenarios import SCENARIOS
SCENARIOS['my_custom'] = MyCustomScenario

# Use it
python -m predarb dual-stress --inject-a scenario:my_custom --inject-b scenario:happy_path
```

### Programmatic Usage

```python
from run_all_scenarios import run_comprehensive_stress_test

exit_code = run_comprehensive_stress_test(seed=42, verbose=True)
```

### Continuous Integration

```bash
#!/bin/bash
# ci_test.sh

set -e

echo "Running unit tests..."
pytest tests/test_dual_injection.py tests/test_cross_venue_scenarios.py -v

echo "Running comprehensive stress test..."
python run_all_scenarios.py --seed 42

echo "All tests passed!"
```

---

## ✅ Checklist for Adding New Arbitrage Types

When adding a new arbitrage detector:

1. ✅ Add scenario generator in `cross_venue_scenarios.py`
2. ✅ Add expected counts in `run_all_scenarios.py` → `ScenarioValidator.EXPECTED_OPPORTUNITIES`
3. ✅ Add unit tests in `tests/test_cross_venue_scenarios.py`
4. ✅ Update this README with the new scenario details
5. ✅ Run `python run_all_scenarios.py` to validate

---

## 🎓 Learning Examples

### Example 1: Finding Duplicate Arbitrage

```bash
# Generate scenario and check for duplicates
python -m predarb dual-stress --cross-venue --seed 42 --iterations 1

# Check reports/unified_report.json for DUPLICATE opportunities
jq '.sessions[0].opportunities[] | select(.type == "DUPLICATE")' reports/unified_report.json
```

### Example 2: Testing Risk Filters

```bash
# Generate many low-quality opportunities
python -m predarb dual-stress --inject-a scenario:many_risk_rejections --inject-b scenario:many_risk_rejections

# Check approval rate (should be low)
python run_all_scenarios.py
```

### Example 3: Time-Lag Detection

```bash
# Use time-lag scenario
python -m predarb dual-stress --inject-a scenario:latency_freshness --inject-b scenario:latency_freshness

# Check for TIMELAG opportunities
grep "TIMELAG" reports/live_summary.csv
```

---

## 🔗 Command Reference

| Command | Description |
|---------|-------------|
| `python run_all_scenarios.py` | Run full test suite with validation |
| `python run_all_scenarios.py --seed N` | Use specific seed |
| `python run_all_scenarios.py --quiet` | Reduce output verbosity |
| `python -m predarb dual-stress --cross-venue` | Run built-in cross-venue scenario |
| `python -m predarb dual-stress --inject-a SPEC --inject-b SPEC` | Custom injection |
| `pytest tests/test_dual_injection.py -v` | Unit tests for injection |
| `pytest tests/test_cross_venue_scenarios.py -v` | Unit tests for scenarios |

---

## 🏆 Success Criteria

A successful stress test run should show:
- ✅ All market validations pass
- ✅ All expected opportunity types detected
- ✅ Reasonable approval rate (not 0%, not 100%)
- ✅ Reports generated successfully
- ✅ Exit code 0

---

**Questions? Issues?**
Check the test output carefully - validation messages explain exactly what passed/failed and why.
