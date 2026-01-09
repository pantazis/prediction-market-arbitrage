# 🚀 DUAL-VENUE STRESS TESTING - COMMAND CHEAT SHEET

## Quick Commands

### 🎯 Run Everything (Recommended)
```bash
python run_all_scenarios.py
```
**What it does:** Runs comprehensive test suite with all validations  
**Exit code:** 0 = pass, 1 = fail  
**Time:** ~5 seconds

---

### 🧪 Run CLI Stress Test
```bash
# Built-in comprehensive scenario
python -m predarb dual-stress --cross-venue --seed 42

# Custom injection for each venue
python -m predarb dual-stress --inject-a scenario:happy_path --inject-b scenario:high_volume

# Mix fixtures and scenarios
python -m predarb dual-stress --inject-a file:poly.json --inject-b file:kalshi.json

# Disable one venue
python -m predarb dual-stress --inject-a scenario:parity_arb --inject-b none
```
**What it does:** Runs engine with injected data from both venues  
**Output:** reports/unified_report.json, reports/paper_trades.csv

---

### ✅ Run Unit Tests
```bash
# All dual-injection tests (19 tests)
pytest tests/test_dual_injection.py -v

# All cross-venue scenario tests (19 tests)
pytest tests/test_cross_venue_scenarios.py -v

# Run both (38 tests)
pytest tests/test_dual_injection.py tests/test_cross_venue_scenarios.py -v
```
**What it does:** Validates injection layer and scenario generator  
**Time:** <1 second

---

### 📊 Check Results
```bash
# View unified report
cat reports/unified_report.json | jq

# View paper trades
cat reports/paper_trades.csv

# View live summary
cat reports/live_summary.csv
```

---

## Injection Specs

### Scenario Names
- `happy_path` - 15 markets, good opportunities
- `high_volume` - 1000 markets, few opportunities
- `many_risk_rejections` - Many detected, most rejected
- `partial_fill` - Asymmetric liquidity
- `latency_freshness` - Time-lag scenarios
- `fee_slippage` - Marginal opportunities
- `semantic_clustering` - Duplicate detection test

### File Format
```json
[
  {
    "id": "market_1",
    "question": "Will event occur?",
    "outcomes": [
      {"id": "yes", "label": "YES", "price": 0.6, "liquidity": 5000},
      {"id": "no", "label": "NO", "price": 0.4, "liquidity": 5000}
    ],
    "end_date": "2026-12-31T23:59:59Z",
    "liquidity": 10000,
    "volume": 15000,
    "tags": ["test"]
  }
]
```

### Inline JSON
```bash
python -m predarb dual-stress --inject-a 'inline:[{"id":"test","question":"Test?","outcomes":[...],...}]' --inject-b none
```

---

## Environment Setup

```bash
# Required
export PYTHONPATH=/opt/prediction-market-arbitrage/src

# Use virtual environment
.venv/bin/python <command>

# Or activate venv
source .venv/bin/activate
python <command>
```

---

## Validation Checks

The comprehensive test runner validates:

✅ **Determinism** - Same seed produces identical results  
✅ **Market counts** - Poly + Kalshi = Total  
✅ **Exchange tags** - All markets tagged with venue  
✅ **Opportunity detection** - Expected types found  
✅ **Approval rate** - Reasonable (not 0% or 100%)  
✅ **Report generation** - Unified report exists  

---

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | All tests passed |
| 1 | At least one test failed |

---

## Expected Results (seed=42)

| Metric | Value |
|--------|-------|
| Total markets | 37 |
| Polymarket markets | 20 |
| Kalshi markets | 17 |
| Opportunities detected | ~5 |
| Opportunities approved | ~2 |
| Approval rate | ~40% |

---

## Troubleshooting

### "No module named predarb"
```bash
export PYTHONPATH=/opt/prediction-market-arbitrage/src
```

### "No opportunities detected"
- Check detector config in `config.yml`
- Verify `enable_parity`, `enable_ladder`, etc. are true
- Lower `min_gross_edge` and `min_liquidity_usd` for testing

### "All opportunities rejected"
- This is expected for negative test cases
- Check risk filter settings in `config.yml`
- Review rejection reasons in logs

---

## Files Created

| Path | Purpose |
|------|---------|
| `src/predarb/dual_injection.py` | Dual-venue injection mechanism |
| `src/predarb/cross_venue_scenarios.py` | Scenario generator |
| `run_all_scenarios.py` | Comprehensive test runner |
| `tests/test_dual_injection.py` | Unit tests (19) |
| `tests/test_cross_venue_scenarios.py` | Unit tests (19) |
| `DUAL_VENUE_STRESS_TESTING.md` | User guide |
| `IMPLEMENTATION_DUAL_VENUE_STRESS_TESTING.md` | Implementation summary |
| `quickstart_dual_venue.sh` | Interactive quickstart |
| `COMMANDS.md` | This cheat sheet |

---

## Integration Examples

### In Python Code
```python
from predarb.dual_injection import DualInjectionClient, InjectionFactory
from predarb.engine import Engine
from predarb.config import load_config

# Create providers
venue_a = InjectionFactory.from_spec("scenario:happy_path", seed=42, exchange="polymarket")
venue_b = InjectionFactory.from_spec("scenario:high_volume", seed=42, exchange="kalshi")

# Create dual client
dual_client = DualInjectionClient(venue_a, venue_b)

# Run engine
config = load_config("config.yml")
engine = Engine(config, clients=[dual_client])
opportunities = engine.run_once()
```

### In CI/CD
```bash
#!/bin/bash
set -e
export PYTHONPATH=/opt/prediction-market-arbitrage/src
.venv/bin/python run_all_scenarios.py
echo "✅ Stress tests passed"
```

---

## Documentation

📚 **Read first:** `DUAL_VENUE_STRESS_TESTING.md`  
🔧 **Implementation:** `IMPLEMENTATION_DUAL_VENUE_STRESS_TESTING.md`  
📋 **Operations:** `CODEBASE_OPERATIONS.json` → `dual_venue_stress_testing`  
💡 **Examples:** Unit tests in `tests/`

---

**Last updated:** 2026-01-09  
**Version:** 1.0  
**Status:** Production Ready ✅
