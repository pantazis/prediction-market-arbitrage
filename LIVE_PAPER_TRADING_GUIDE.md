# Live Paper-Trading Arbitrage Bot - Quick Start Guide

## Overview

This guide helps you run the arbitrage bot TODAY using ONLY real-time market data with paper trading (no real orders).

**Key Features:**
- ✅ Real-time API data from Polymarket (and optionally Kalshi)
- ✅ Paper wallet starting at 500 USDC
- ✅ No historical data or fake injections
- ✅ Full PnL tracking (realized + unrealized)
- ✅ Position tracking per venue
- ✅ Automatic stop conditions
- ✅ Comprehensive reporting

## Quick Start

### 1. Run with Default Settings (8 hours, 500 USDC)

```bash
python run_live_paper.py
```

### 2. Run with Custom Duration

```bash
# 30 minutes
python run_live_paper.py --duration 0.5

# 2 hours
python run_live_paper.py --duration 2

# 12 hours
python run_live_paper.py --duration 12
```

### 3. Run with Custom Starting Capital

```bash
# Start with 1000 USDC
python run_live_paper.py --capital 1000

# Start with 100 USDC for 1 hour
python run_live_paper.py --capital 100 --duration 1
```

## Configuration

The bot uses `config_live_paper.yml` which is pre-configured for live paper trading:

```yaml
# Key Settings:
broker:
  initial_cash: 500.0           # Starting balance (overridden by --capital)
  fee_bps: 20.0                 # 0.2% fee
  slippage_bps: 30.0            # 0.3% slippage

risk:
  max_allocation_per_market: 0.10   # Max 10% per trade
  kill_switch_drawdown: 0.15        # Stop at 15% loss
  min_liquidity_usd: 500.0          # Minimum market liquidity

engine:
  refresh_seconds: 5.0          # Scan every 5 seconds
```

## Paper Wallet Tracking

The bot maintains a complete paper wallet with:

| Metric | Description |
|--------|-------------|
| `available_usdc` | Cash available for new trades |
| `reserved_usdc` | Cash reserved for pending orders |
| `realized_pnl_usdc` | Closed position PnL |
| `unrealized_pnl_usdc` | Open position PnL |
| `fees_paid_usdc` | Total fees paid |
| `slippage_cost_usdc` | Total slippage cost |
| `positions` | Inventory per market/outcome |

## Data Rules (STRICT)

✅ **Allowed:**
- Real-time API calls to Polymarket/Kalshi
- Current prices and order books
- Live market data

❌ **Forbidden:**
- Historical data replay
- Injected/fake markets
- Backfill data
- Any `scenario:*` or `file:*` injection

## Execution Model (Paper Trading)

The bot simulates real trading:

1. **Order Placement:**
   - Uses best bid/ask at decision time
   - Applies configurable fees (default 0.2%)
   - Applies slippage model (default 0.3%)
   - Checks order book depth for size validation

2. **Fill Simulation:**
   - Supports partial fills based on depth
   - Reserves funds before placement
   - Updates wallet after fills

3. **Risk Management:**
   - If one leg fills and other doesn't: attempts hedge
   - On failure: cancels unfilled orders
   - Records all costs/losses

## Bot Loop

Each iteration (default 5 seconds):

```
1. Check balances (paper wallet)
2. Fetch real-time prices
3. Fetch real-time order books (top N levels)
4. Calculate spreads/edges
5. Validate:
   - Fees + slippage
   - Order book depth
   - Freshness/latency
   - Risk limits
6. Select arbitrage opportunities
7. Calculate position size
8. Construct both legs
9. Paper-place orders
10. Monitor fills (simulated)
11. Handle partial fills
12. Hedge or cancel on failure
13. Update wallet
14. Record realized PnL
15. Rebalance inventory
16. Log everything
17. Sleep until next iteration
```

## Stop Conditions

The bot stops when:

1. **Duration Limit**: Default 8 hours (configurable via `--duration`)
2. **Drawdown Limit**: Default 15% loss (configurable in config)
3. **Manual Stop**: Ctrl+C

After hitting stop loss, the bot continues logging market edges but stops trading.

## Output and Reporting

### Live Console Output

```
================================================================================
Iteration 10/5760
================================================================================
Cash Available:    $485.23
Unrealized PnL:    $8.45
Total Equity:      $493.68
Realized PnL:      -$14.77
Active Positions:  2
Total Trades:      8
Max Drawdown:      2.95%
================================================================================
  → Detected: 3 opportunities, Approved: 1, Rejected: 2
```

### End-of-Run Report

Automatically generated at session end:

```
💰 WALLET PERFORMANCE
──────────────────────────────────────────
Initial Capital:   $500.00 USDC
Final Cash:        $485.23 USDC
Unrealized PnL:    $8.45 USDC
Final Equity:      $493.68 USDC
Total PnL:         -$6.32 USDC (-1.26%)
Max Drawdown:      2.95%

📈 TRADING ACTIVITY
──────────────────────────────────────────
Total Trades:      8
  BUY Orders:      6
  SELL Orders:     2
Total Fees:        $2.15 USDC
Total Slippage:    $3.21 USDC
Win Rate:          62.5% (5W / 3L)
Biggest Win:       $4.23 USDC
Biggest Loss:      -$2.87 USDC

🎯 OPPORTUNITY DETECTION
──────────────────────────────────────────
Total Detected:    247
Total Approved:    8
Total Rejected:    239
Approval Rate:     3.2%
```

### Generated Files

| File | Description |
|------|-------------|
| `reports/live_paper_trades.csv` | Complete trade log with timestamps |
| `reports/unified_report.json` | Full session report with all metrics |
| `reports/live_summary.csv` | Iteration-by-iteration summary |

## Verification Commands

After the run completes, verify results:

```bash
# View trade log
cat reports/live_paper_trades.csv

# View unified report (formatted)
python -m json.tool reports/unified_report.json | less

# Check wallet timeline
grep "Iteration" reports/live_summary.csv

# Validate invariants
# - All balances should be non-negative
# - reserved_usdc should be 0 at end
# - Sum of realized_pnl should match wallet change
```

## Invariant Checks

The bot enforces these invariants:

1. **No Negative Balances**: Cash never goes below 0
2. **No Short Selling**: SELL orders only allowed if position exists
3. **Reserved Funds**: Funds reserved before orders, released after
4. **Balanced Ledger**: Sum of all PnL = final_equity - initial_equity
5. **Position Tracking**: All positions tracked and reconciled

Run validation:

```bash
pytest tests/test_broker_invariants.py
pytest tests/test_risk_invariants.py
```

## Enabled Strategies

By default, these arbitrage detectors are enabled:

| Detector | Status | Strategy Type |
|----------|--------|---------------|
| **Parity** | ✅ Enabled | YES+NO ≠ 1.0 within single market |
| **Ladder** | ✅ Enabled | Price monotonicity violations |
| **ExclusiveSum** | ✅ Enabled | Mutually exclusive outcomes sum > 1.0 |
| **Consistency** | ✅ Enabled | Logical contradictions |
| **Duplicate** | ❌ Disabled | Cross-venue (requires short selling) |
| **TimeLag** | ❌ Disabled | Requires historical data |

## Troubleshooting

### API Connection Issues

If markets fail to load:

```bash
# Test connection
python check_connection.py

# Check credentials
echo $POLYMARKET_API_KEY
echo $KALSHI_API_KEY_ID
```

### No Opportunities Found

If the bot runs but finds no opportunities:

1. **Lower thresholds** in `config_live_paper.yml`:
   ```yaml
   risk:
     min_net_edge_threshold: 0.005  # Try 0.5% instead of 1%
     min_liquidity_usd: 250.0       # Lower from 500
   ```

2. **Enable more detectors**:
   ```yaml
   detectors:
     enable_timelag: true  # If you have price history
   ```

3. **Check market conditions**: Low volatility = fewer opportunities

### Errors During Execution

Check logs:

```bash
# Run with debug logging
python run_live_paper.py --log-level DEBUG

# View logs
tail -f reports/live_paper_trades.csv
```

## Advanced Usage

### Multi-Venue (Polymarket + Kalshi)

To enable Kalshi:

1. Set environment variables:
   ```bash
   export KALSHI_API_KEY_ID="your_key_id"
   export KALSHI_PRIVATE_KEY_PEM="$(cat path/to/private_key.pem)"
   ```

2. Enable in config:
   ```yaml
   kalshi:
     enabled: true
     env: prod
   ```

3. Run normally:
   ```bash
   python run_live_paper.py
   ```

### Custom Refresh Rate

For faster/slower scanning:

```yaml
engine:
  refresh_seconds: 2.0  # Scan every 2 seconds (faster)
  # OR
  refresh_seconds: 10.0  # Scan every 10 seconds (slower)
```

### Telegram Notifications

To receive alerts:

```bash
export TELEGRAM_ENABLED=true
export TELEGRAM_BOT_TOKEN="your_bot_token"
export TELEGRAM_CHAT_ID="your_chat_id"
```

Then edit config:

```yaml
telegram:
  enabled: true
```

## Safety Features

1. **Kill Switch**: Automatic stop at 15% drawdown
2. **Position Limits**: Max 5 concurrent positions
3. **Size Limits**: Max 10% capital per trade
4. **Liquidity Checks**: Requires 5x depth for order size
5. **Time Filters**: Rejects markets expiring soon
6. **Spread Limits**: Rejects markets with >8% spread

## Expected Performance

**Realistic Expectations:**

- **Opportunities Detected**: 10-100 per hour (depends on market volatility)
- **Approval Rate**: 1-10% (most rejected by risk filters)
- **Expected Trades**: 1-10 per 8-hour session
- **Expected PnL**: -5% to +5% (depends on market conditions)
- **Fees + Slippage**: ~0.5% per round trip

**This is NOT a get-rich-quick system.** The bot demonstrates arbitrage detection but real profits require:
- Lower fees (market maker rates)
- Better execution (co-location)
- Higher capital (economies of scale)

## Next Steps

1. **Run a short test**:
   ```bash
   python run_live_paper.py --duration 0.1  # 6 minutes
   ```

2. **Review results**:
   ```bash
   cat reports/live_paper_trades.csv
   ```

3. **Adjust config** based on results

4. **Run full 8-hour session**:
   ```bash
   python run_live_paper.py
   ```

5. **Analyze performance** and iterate

## Support

For issues or questions:

1. Check `COMMANDS.md` for all available commands
2. Read `CODEBASE_OPERATIONS.json` for architecture
3. Run tests: `pytest tests/`
4. Review logs in `reports/`

---

**Remember**: This is paper trading only. No real money is at risk. Use this to learn, test strategies, and understand market dynamics before considering real capital deployment.
