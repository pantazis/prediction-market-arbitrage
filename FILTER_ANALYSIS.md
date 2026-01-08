# Filter Effectiveness Report

## Current Situation

**🔴 PROBLEM: Your filters are TOO STRICT!**

### Key Findings:
- **95.7% rejection rate** - Only 4.3% of detected opportunities are approved
- Out of 328 opportunities detected, only 14 were approved
- Your filters are catching injected stress scenarios (7 executed from injected markets)
- But they're also rejecting 96% of everything else

## Why This Happens

Your current filter settings are VERY conservative:

```yaml
risk:
  min_liquidity_usd: 500      # Requires $500 liquidity
  min_net_edge_threshold: 0.005  # Requires 0.5% edge

filter:
  min_volume_24h: 1000        # Requires $1k daily volume
  min_liquidity: 10000        # Requires $10k depth
  min_days_to_expiry: 3       # Requires 3+ days to expiry
```

The **high_volume** stress scenario injects markets with:
- 10 arbitrage markets: liquidity $20k, volume $15k ✓
- 990 normal markets: liquidity $10k, volume $5k ✓

Most real Polymarket markets have LOWER liquidity/volume than your thresholds!

## Solutions

### Option 1: RELAX Filters (Recommended for Testing)

Edit `config.yml`:

```yaml
risk:
  min_liquidity_usd: 250           # Was 500 → 250
  min_net_edge_threshold: 0.002    # Was 0.005 → 0.002

filter:
  min_volume_24h: 500              # Was 1000 → 500
  min_liquidity: 5000              # Was 10000 → 5000
  min_days_to_expiry: 1            # Was 3 → 1
```

**Expected result:** 15-25% approval rate (catching more opportunities)

### Option 2: Test with Different Scenarios

Try scenarios designed for your current filters:

```bash
# Stop current bot
kill $(cat bot.pid)

# Test with happy_path (designed for success)
python -m predarb stress --scenario happy_path --no-verify

# Or run mixed with happy_path instead
python run_continuous_mixed.py --scenario happy_path --days 0.1
```

### Option 3: TIGHTEN Filters (If you want ultra-conservative)

Keep current strict settings but understand you'll miss most opportunities.

## How to Test & Iterate

1. **Stop the current bot:**
   ```bash
   kill $(cat bot.pid)
   ```

2. **Edit config.yml** with new filter values

3. **Run a quick test:**
   ```bash
   python -m predarb stress --scenario happy_path --no-verify
   ```

4. **Check approval rate:**
   ```bash
   python analyze_filter_effectiveness.py
   ```

5. **Iterate** until you find the right balance:
   - **Too strict** (<5% approval): Relax filters
   - **Too loose** (>50% approval): Tighten filters  
   - **Just right** (10-30% approval): Good balance

## What Each Filter Does

| Filter | Purpose | Current | Recommended |
|--------|---------|---------|-------------|
| `min_liquidity_usd` | Minimum $ in market for risk manager | 500 | 250 (test) / 500 (prod) |
| `min_net_edge_threshold` | Minimum profit % required | 0.5% | 0.2% (test) / 0.5% (prod) |
| `min_volume_24h` | Minimum daily trading volume | $1000 | $500 (test) / $1000 (prod) |
| `min_liquidity` | Minimum depth in market | $10k | $5k (test) / $10k (prod) |
| `min_days_to_expiry` | Days before market closes | 3 | 1 (test) / 3 (prod) |

## Current Bot Status

Your continuous bot is running with:
- 95.7% rejection rate
- 7 injected opportunities executed (all successful)
- 32 real market opportunities executed (22 success, 9 partial, 1 cancelled)
- Filters ARE working but TOO STRICT for most markets

## Recommendation

**For 2-day stress testing: RELAX filters to 250/0.002/500/5000/1**

This will:
- Catch more edge cases
- Test broader range of market conditions
- Still maintain reasonable quality bar
- Better validate bot behavior under varied opportunities

After 2 days, analyze results and decide production filter levels.
