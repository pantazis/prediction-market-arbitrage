# 🎯 LIVE PAPER TRADING - QUICK START CARD

## ⚡ ONE-LINE COMMANDS

```bash
# Run with defaults (8 hours, 500 USDC)
python3 run_live_paper.py

# Quick test (6 minutes)
python3 run_live_paper.py --duration 0.1

# Full setup + run
./run_live_paper_setup.sh

# Validate before running
python3 validate_live_paper_setup.py
```

---

## 📋 PRE-FLIGHT CHECKLIST

```bash
# 1. Check Python (need 3.10+)
python3 --version

# 2. Install dependencies
pip3 install -r requirements.txt

# 3. Validate setup
python3 validate_live_paper_setup.py

# 4. Test API
python3 -c "from predarb.polymarket_client import PolymarketClient; from predarb.config import load_config; c=PolymarketClient(load_config('config_live_paper.yml').polymarket); print(f'{len(c.fetch_markets())} markets')"
```

---

## 🎛️ COMMON OPTIONS

| Command | Duration | Capital | Purpose |
|---------|----------|---------|---------|
| `python3 run_live_paper.py` | 8 hours | $500 | Default run |
| `--duration 0.1` | 6 min | $500 | Quick test |
| `--duration 4 --capital 1000` | 4 hours | $1000 | Custom |
| `--log-level DEBUG` | 8 hours | $500 | Debug mode |

---

## 📊 LIVE OUTPUT

```
======================================================================
Iteration 10/5760
======================================================================
Cash Available:    $485.23       ← Current cash
Unrealized PnL:    $8.45         ← Open positions P&L
Total Equity:      $493.68       ← Cash + Unrealized
Realized PnL:      -$14.77       ← Closed positions P&L
Active Positions:  2             ← Number of open positions
Total Trades:      8             ← Trades executed
Max Drawdown:      2.95%         ← Worst loss from peak
======================================================================
```

---

## 📁 OUTPUT FILES

| File | Contents |
|------|----------|
| `reports/live_paper_trades.csv` | All trades with timestamps |
| `reports/unified_report.json` | Complete session metrics |
| `reports/live_summary.csv` | Iteration-by-iteration data |

---

## ✅ SUCCESS INDICATORS

- ✓ Opportunities detected per hour: 10-100
- ✓ Approval rate: 1-10%
- ✓ Actual trades: 1-20 per 8 hours
- ✓ Max drawdown: <15%
- ✓ No negative balances
- ✓ No short selling errors

---

## 🛑 STOP CONDITIONS

| Condition | Threshold | Action |
|-----------|-----------|--------|
| Time | 8 hours (default) | Graceful stop + report |
| Drawdown | 15% loss | Emergency stop |
| Manual | Ctrl+C | Graceful stop + report |

---

## 🔧 QUICK FIXES

### No opportunities detected
```yaml
# Edit config_live_paper.yml:
risk:
  min_net_edge_threshold: 0.005  # Lower from 0.01
  min_liquidity_usd: 250.0       # Lower from 500
```

### API errors
```bash
# Check connectivity
curl -I https://gamma-api.polymarket.com

# Run with debug
python3 run_live_paper.py --log-level DEBUG
```

### Missing dependencies
```bash
pip3 install -r requirements.txt --force-reinstall
```

---

## 📖 DOCUMENTATION

| File | Purpose |
|------|---------|
| `README_LIVE_PAPER_TRADING.md` | Executive summary |
| `LIVE_PAPER_TRADING_GUIDE.md` | Complete guide |
| `LIVE_PAPER_TRADING_COMMANDS.md` | All commands |
| `LIVE_PAPER_TRADING_SUMMARY.md` | Delivery summary |

---

## 🎯 CONFIGURATION HIGHLIGHTS

```yaml
# config_live_paper.yml key settings:

broker:
  initial_cash: 500.0           # Starting balance
  fee_bps: 20.0                 # 0.2% fees
  slippage_bps: 30.0            # 0.3% slippage

risk:
  max_allocation_per_market: 0.10    # 10% max per trade
  kill_switch_drawdown: 0.15         # 15% stop loss
  min_liquidity_usd: 500.0           # Min market liquidity

engine:
  refresh_seconds: 5.0               # Scan every 5s
  iterations: 5760                   # 8 hours (auto-calc)

detectors:
  enable_parity: true                # YES+NO != 1.0
  enable_ladder: true                # Price monotonicity
  enable_exclusive_sum: true         # Exclusive outcomes
  enable_duplicate: false            # Requires short selling
```

---

## 🚀 QUICKEST START

```bash
# 1. One command setup + run
./run_live_paper_setup.sh

# 2. Or manual
pip3 install -r requirements.txt && python3 run_live_paper.py

# 3. View results
cat reports/live_paper_trades.csv
python3 -m json.tool reports/unified_report.json | less
```

---

## 🎓 REMEMBER

- ✅ Paper trading only (no real money)
- ✅ Real-time data only (no historical)
- ✅ 500 USDC starting balance
- ✅ 8-hour default duration
- ✅ 15% stop loss
- ✅ Full PnL tracking
- ✅ Comprehensive reporting

---

## 📞 HELP

```bash
# Show all options
python3 run_live_paper.py --help

# Run validation
python3 validate_live_paper_setup.py

# Run tests
pytest tests/test_broker_invariants.py -v
```

---

**READY TO START? RUN THIS NOW:**

```bash
python3 run_live_paper.py --duration 0.1
```

*This runs a 6-minute test session to verify everything works.*
