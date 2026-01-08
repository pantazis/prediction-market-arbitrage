# Short Selling Enabled in Paper Broker

## Changes Made

Modified `src/predarb/broker.py` to enable short selling (selling without holding a position).

### What Changed

1. **SELL orders no longer require existing position**
   - Removed constraint: `qty = min(qty, held)`
   - Positions can now go negative (short positions)
   - Example: position = -1.0 means you're short 1 unit

2. **Cost basis tracking for short positions**
   - Tracks average price of short positions
   - Handles weighted averages when adding to shorts

3. **Updated `close_position()` method**
   - Automatically determines correct closing side:
     - Long position (qty > 0) → SELL to close
     - Short position (qty < 0) → BUY to close

4. **Updated `flatten_all()` method**
   - Correctly handles both long and short positions

## Why This Was Needed

**Problem**: All arbitrage opportunities were failing with "partial" status

- Detectors created strategies like: SELL @ $0.934, BUY @ $0.0495
- Broker rejected SELL because position = 0 (can't sell what you don't own)
- Only BUY executed → partial fill → hedged immediately → small loss

**Root Cause**: The opportunities were designed for short selling but broker didn't support it.

## How It Works Now

### Example Arbitrage

**Opportunity**: DUPLICATE detector finds same outcome priced differently
- Market A: Outcome "Yes" @ $0.934 (expensive)
- Market B: Outcome "Yes" @ $0.0495 (cheap)

**Strategy**:
1. SELL Market A @ $0.934 (short the expensive one)
2. BUY Market B @ $0.0495 (buy the cheap one)
3. Net profit: $0.934 - $0.0495 = $0.8845 (88.45% edge!)

**Before**: SELL rejected → BUY executed → hedged → lost fees
**After**: Both legs execute → profit captured → positions flatten

## Testing Results

```
Initial: $10,000.00 cash, 0 position
After SELL 1.0 @ $0.95: $10,000.95 cash, -1.0 position (short)
After BUY  1.0 @ $0.90: $10,000.04 cash,  0.0 position (closed)
Net P&L: +$0.04 (profit after fees/slippage)
```

## Next Steps

1. **Restart the bot** to use the new short-selling capability
2. **Monitor performance** - opportunities should now execute fully
3. **Watch for "success" status** instead of "partial" in unified_report.json

## Important Notes

- ✅ This is **paper trading only** - no real money at risk
- ✅ Short positions are normal in arbitrage trading
- ✅ Hedge system still works - closes positions if something fails
- ⚠️ When going live, ensure exchange/API supports short selling

