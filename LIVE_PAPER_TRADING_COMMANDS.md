# Live Paper Trading - Command Reference

## Quick Commands

### Basic Usage

```bash
# Default: 8 hours, 500 USDC starting capital
python run_live_paper.py

# Short test run (6 minutes)
python run_live_paper.py --duration 0.1

# 30 minute run
python run_live_paper.py --duration 0.5

# Full day run (24 hours)
python run_live_paper.py --duration 24

# Custom starting capital (1000 USDC)
python run_live_paper.py --capital 1000

# Combined: 4 hours with 250 USDC
python run_live_paper.py --duration 4 --capital 250
```

### Debug Mode

```bash
# Run with debug logging
python run_live_paper.py --log-level DEBUG

# Run with minimal logging
python run_live_paper.py --log-level WARNING
```

### Custom Config

```bash
# Use custom config file
python run_live_paper.py --config my_config.yml
```

## Pre-Flight Checks

```bash
# 1. Check API connectivity
python check_connection.py

# 2. Verify config is valid
python -c "from predarb.config import load_config; load_config('config_live_paper.yml'); print('✓ Config valid')"

# 3. Ensure reports directory exists
mkdir -p reports

# 4. Check Python dependencies
pip install -r requirements.txt --dry-run
```

## During Run

```bash
# Monitor in real-time (separate terminal)
watch -n 5 tail -20 reports/live_paper_trades.csv

# Monitor console output
python run_live_paper.py 2>&1 | tee live_run_$(date +%Y%m%d_%H%M%S).log

# Stop gracefully
# Press Ctrl+C in the running terminal
```

## Post-Run Analysis

```bash
# View final report
cat reports/live_paper_trades.csv

# View unified JSON report
python -m json.tool reports/unified_report.json | less

# Count total trades
wc -l reports/live_paper_trades.csv

# Calculate net PnL from trades
# (Requires parsing CSV - use Python or spreadsheet)

# Check for errors
grep -i error reports/live_paper_trades.csv
```

## Verification & Invariants

```bash
# Run broker invariant tests
pytest tests/test_broker_invariants.py -v

# Run risk invariant tests
pytest tests/test_risk_invariants.py -v

# Run all tests
pytest tests/ -v

# Check that no short selling occurred
grep "SELL" reports/live_paper_trades.csv
# Should only appear if positions were previously opened
```

## Configuration Flags

### Critical Settings in `config_live_paper.yml`

```yaml
# Starting balance (overridden by --capital)
broker.initial_cash: 500.0

# Stop loss threshold (15% = stop at $425 if started with $500)
risk.kill_switch_drawdown: 0.15

# Max per trade (10% = max $50 per trade with $500 capital)
risk.max_allocation_per_market: 0.10

# Scan frequency (5 seconds between iterations)
engine.refresh_seconds: 5.0

# Duration (calculated from --duration parameter)
engine.iterations: [auto-calculated]

# Minimum edge required (1% net profit after fees)
risk.min_net_edge_threshold: 0.01

# Minimum market liquidity ($500 USDC)
risk.min_liquidity_usd: 500.0
```

## Troubleshooting

### Problem: No opportunities detected

```bash
# Solution 1: Lower thresholds
# Edit config_live_paper.yml:
#   risk.min_net_edge_threshold: 0.005  # Lower from 0.01
#   risk.min_liquidity_usd: 250.0       # Lower from 500

# Solution 2: Check market conditions
python -c "
from predarb.config import load_config
from predarb.polymarket_client import PolymarketClient
config = load_config('config_live_paper.yml')
client = PolymarketClient(config.polymarket)
markets = client.fetch_markets()
print(f'Fetched {len(markets)} markets')
print(f'Sample market: {markets[0].question if markets else \"None\"}')
"
```

### Problem: API connection failures

```bash
# Check network connectivity
curl -I https://gamma-api.polymarket.com

# Verify no firewall blocking
telnet gamma-api.polymarket.com 443

# Test with longer timeout
# Edit config_live_paper.yml and add timeout settings
```

### Problem: Script crashes

```bash
# Run with full traceback
python run_live_paper.py --log-level DEBUG 2>&1 | tee crash.log

# Check Python version (requires 3.10+)
python --version

# Reinstall dependencies
pip install -r requirements.txt --force-reinstall
```

## Expected Output Format

### Console Output (Live)

```
================================================================================
LIVE PAPER-TRADING ARBITRAGE BOT
================================================================================
Configuration:     /opt/prediction-market-arbitrage/config_live_paper.yml
Starting Capital:  $500.00 USDC
Duration:          8 hours
Iterations:        5760
Refresh Rate:      5s
Stop Loss:         15.0% drawdown
Max Per Trade:     $50.00
Fee:               20 bps
Slippage:          30 bps
================================================================================

Enabled Detectors: Parity, Ladder, ExclusiveSum, Consistency
Report Output:     reports/live_paper_trades.csv

================================================================================
STARTING TRADING SESSION
================================================================================

======================================================================
Iteration 1/5760
======================================================================
Cash Available:    $500.00
Unrealized PnL:    $0.00
Total Equity:      $500.00
Realized PnL:      $0.00
Active Positions:  0
Total Trades:      0
Max Drawdown:      0.00%
======================================================================
```

### End Report (Summary)

```
================================================================================
END-OF-RUN REPORT
================================================================================

📊 SESSION SUMMARY
────────────────────────────────────────────────────────────────────────────────
Start Time:        2026-01-09 10:00:00
End Time:          2026-01-09 18:00:00
Duration:          8:00:00 (8.00 hours)
Iterations:        5760 planned

💰 WALLET PERFORMANCE
────────────────────────────────────────────────────────────────────────────────
Initial Capital:   $500.00 USDC
Final Cash:        $485.23 USDC
Unrealized PnL:    $8.45 USDC
Final Equity:      $493.68 USDC
Total PnL:         -$6.32 USDC (-1.26%)
Max Drawdown:      2.95%

📈 TRADING ACTIVITY
────────────────────────────────────────────────────────────────────────────────
Total Trades:      8
  BUY Orders:      6
  SELL Orders:     2
Total Fees:        $2.15 USDC
Total Slippage:    $3.21 USDC
Win Rate:          62.5% (5W / 3L)
Biggest Win:       $4.23 USDC
Biggest Loss:      -$2.87 USDC
```

## File Locations

| File | Description |
|------|-------------|
| `run_live_paper.py` | Main runner script |
| `config_live_paper.yml` | Live paper trading configuration |
| `reports/live_paper_trades.csv` | Trade log (timestamped entries) |
| `reports/unified_report.json` | Complete session report |
| `reports/live_summary.csv` | Iteration summaries |
| `LIVE_PAPER_TRADING_GUIDE.md` | Comprehensive guide |

## Performance Metrics

### What to Track

1. **PnL Metrics**
   - Total PnL (realized + unrealized)
   - Win rate
   - Average win vs average loss
   - Max drawdown

2. **Efficiency Metrics**
   - Opportunities detected per hour
   - Approval rate (approved / detected)
   - Fill rate (if tracking partial fills)
   - Capital utilization

3. **Cost Metrics**
   - Total fees paid
   - Total slippage cost
   - Cost per trade
   - Cost as % of PnL

4. **Risk Metrics**
   - Max concurrent positions
   - Average position size
   - Largest loss
   - Drawdown events

## Integration with Existing Tools

```bash
# Run stress test first (validation)
python run_all_scenarios.py

# Then run live paper trading
python run_live_paper.py --duration 1

# Compare results with simulation
python sim_run.py --days 0.041  # Same as 1 hour

# Run continuous mixed mode (real + injected)
python run_continuous_mixed.py --scenario happy_path --days 0.33  # 8 hours
```

## Safety Checklist

Before running with real capital (future):

- [ ] Paper trading shows consistent profitability
- [ ] Drawdown stays within acceptable limits
- [ ] No unexpected crashes or errors
- [ ] Opportunity approval rate is reasonable (>1%)
- [ ] Fee and slippage models are accurate
- [ ] Kill switches work as expected
- [ ] Position limits are enforced
- [ ] Short selling prevention is working
- [ ] Rebalancing logic is sound
- [ ] Reports are accurate and complete

---

**Ready to Start?**

```bash
python run_live_paper.py
```
