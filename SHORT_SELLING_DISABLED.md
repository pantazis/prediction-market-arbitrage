# SHORT SELLING DISABLED - IMPLEMENTATION SUMMARY

**Date:** 2026-01-08  
**Status:** ✅ COMPLETE  
**Version:** Risk Manager v2.0 (Short-Selling Prevention)

---

## EXECUTIVE SUMMARY

All strategies requiring short selling are now **COMPLETELY DISABLED** in **ALL MODES** (live, paper, simulation, backtest).

**KEY CHANGE:** DUPLICATE arbitrage is **HARD-DISABLED** at multiple layers with fail-fast assertions.

---

## VENUE CONSTRAINTS (NON-NEGOTIABLE)

- ❌ **No short selling** - Trading venue (Polymarket) does NOT support short selling
- ❌ **No negative inventory** - SELL orders require existing position (inventory > 0)
- ✅ **SELL only for exit** - SELL is ONLY allowed to reduce already-owned positions
- ❌ **No cross-market shorts** - Cannot short Market A to hedge Market B

---

## IMPLEMENTATION: 10 HARD FILTERS

### ✅ FILTER 1: GLOBAL DISABLE - DUPLICATE DETECTOR
- **Location:** `src/predarb/risk.py` lines ~40-50
- **Rule:** Reject ALL opportunities with `type == "DUPLICATE"`
- **Message:** `"DUPLICATE arbitrage requires short selling — disabled on this venue."`
- **Applies to:** Live, paper, simulation, backtest

### ✅ FILTER 2: NO SELL-FIRST LOGIC
- **Location:** `src/predarb/risk.py` lines ~52-75
- **Rule:** `IF action.side == SELL AND inventory <= 0 → REJECT`
- **Additional:** SELL amount cannot exceed inventory
- **Message:** `"SELL required but inventory=0. Short selling not supported on this venue."`

### ✅ FILTER 3: NO SAME-OUTCOME BUY+SELL
- **Location:** `src/predarb/risk.py` lines ~77-95
- **Rule:** Reject opportunities with BOTH BUY and SELL for same (market_id, outcome_id)
- **Rationale:** Prevents unnecessary round-trips and potential short attempts

### ✅ FILTER 4: BUY-ONLY STRATEGY ENFORCEMENT
- **Implicit:** Enforced by Filter 2
- **Rule:** All entry actions must be BUY
- **Exception:** SELL allowed ONLY for position reduction (inventory > 0)

### ✅ FILTER 5: MINIMUM EDGE (BUY-ONLY)
- **Location:** `src/predarb/risk.py` lines ~97-115
- **Parameters:**
  - `min_net_edge_threshold: 0.001` (0.1% after fees/slippage)
  - `min_gross_edge: 0.05` (5% before fees/slippage)

### ✅ FILTER 6: MICRO-PRICE FILTER
- **Location:** `src/predarb/risk.py` lines ~117-127
- **Parameter:** `min_buy_price: 0.02` ($0.02)
- **Rationale:** Reject dust liquidity / fake edge

### ✅ FILTER 7: BUY-SIDE LIQUIDITY CHECK
- **Location:** `src/predarb/risk.py` lines ~129-155
- **Parameter:** `min_liquidity_multiple_strict: 3.0`
- **Rule:** Orderbook BUY depth >= 3× trade_size
- **Behavior:** No partial fills allowed

### ✅ FILTER 8: PARTIAL FILL KILL-SWITCH
- **Parameter:** `kill_switch_on_partial: true`
- **Behavior:**
  - Cancel remaining orders on partial fill
  - Mark trade as CANCELLED
  - DO NOT chase fills
  - DO NOT hedge (already implemented in engine.py)

### ✅ FILTER 9: TIME-TO-EXPIRY FILTER
- **Location:** `src/predarb/risk.py` lines ~157-171
- **Parameter:** `min_expiry_hours: 24.0` (24 hours)
- **Rule:** Reject markets expiring within threshold

### ✅ FILTER 10: RISK LIMITS
- **Location:** `src/predarb/risk.py` lines ~173-220
- **Parameters:**
  - `max_open_positions: 20`
  - `max_allocation_per_market: 0.05` (5% of equity)
  - `min_liquidity_usd: 100.0`

---

## EXECUTION-TIME ASSERTION (FAIL-FAST)

**Location:** `src/predarb/broker.py` execute() method

**Checks:**
1. No SELL action unless inventory > 0
2. SELL amount does not exceed inventory

**Behavior on violation:**
```python
raise RuntimeError(
    "FATAL INVARIANT VIOLATION: SELL action reached execution without position! "
    "Market: {market_id}, Outcome: {outcome_id}, Inventory: {inventory}, "
    "Requested: {amount}. Short selling is FORBIDDEN on this venue."
)
```

**Purpose:** Final defense layer - abort iteration if RiskManager filters fail

---

## FILES MODIFIED

### 1. `src/predarb/risk.py`
- **Complete rewrite** of RiskManager.approve() method
- Added 10 hard filters with explicit rejection logging
- +180 lines of comprehensive filter logic

### 2. `src/predarb/broker.py`
- Added mandatory invariant check at start of execute() method
- Fail-fast on SELL without position
- +20 lines

### 3. `src/predarb/config.py`
- Added 6 new RiskConfig parameters
- Documented short-selling prevention filters
- +15 lines

### 4. `config.yml`
- Added risk section with new filter parameters
- Reinforced DUPLICATE disable with detailed comment
- Updated detectors section documentation

### 5. `codebase_schema.json`
- Added comprehensive architecture change entry
- Documented all filters, parameters, and rationale
- Marked previous short-selling implementation as DEPRECATED

---

## CONFIGURATION PARAMETERS

### Risk Section (config.yml)
```yaml
risk:
  # Existing parameters
  max_allocation_per_market: 0.05
  max_open_positions: 20
  min_liquidity_usd: 100.0
  min_net_edge_threshold: 0.001
  kill_switch_drawdown: 0.2
  
  # NEW: Short selling prevention filters
  min_gross_edge: 0.05              # 5% minimum gross edge
  min_buy_price: 0.02               # $0.02 minimum BUY price
  min_liquidity_multiple_strict: 3.0  # 3x trade size depth required
  min_expiry_hours: 24.0            # 24h minimum to expiry
  max_entry_spread_pct: 0.10        # 10% maximum spread
  kill_switch_on_partial: true      # Cancel on partial fill
```

### Detectors Section (config.yml)
```yaml
detectors:
  # DUPLICATE DETECTOR: PERMANENTLY DISABLED
  enable_duplicate: false       # HARD-DISABLED (requires short selling)
  enable_ladder: true            # Works within same market
  enable_parity: true            # Works within same market
  enable_exclusive_sum: true     # Works within same market
  enable_timelag: true           # Price movement detection
  enable_consistency: true       # Logical consistency checks
```

---

## ENFORCEMENT LAYERS (DEFENSE IN DEPTH)

### Layer 1: Configuration
- DUPLICATE detector disabled in config.yml (`enable_duplicate: false`)
- Prevents detector from even running

### Layer 2: RiskManager
- 10 hard filters in approve() method
- Explicit rejection with detailed logging
- Catches any DUPLICATE or SELL-first opportunities

### Layer 3: Broker Execution
- Mandatory invariant assertion at execution time
- Raises RuntimeError on violation
- Final fail-safe if filters are bypassed

**GUARANTEE:** DUPLICATE opportunities can NEVER reach execution in any mode

---

## ALLOWED vs FORBIDDEN STRATEGIES

### ✅ ALLOWED (BUY-ONLY)
- **PARITY:** BUY Yes + BUY No when sum < 1.0
- **EXCLUSIVE_SUM:** BUY underpriced outcomes when sum < 1.0
- **LADDER:** BUY lower threshold (may SELL higher if position exists)
- **TIMELAG:** BUY underpriced outcomes detected by staleness
- **CONSISTENCY:** BUY logically underpriced outcomes

### ❌ FORBIDDEN (REQUIRES SHORT SELLING)
- **DUPLICATE:** SELL Market A, BUY Market B (cross-market arbitrage)
- **SELL-FIRST:** Any strategy requiring SELL before establishing position
- **HEDGING:** Cross-market hedging requiring shorts
- **SAME-OUTCOME:** BUY + SELL for same (market_id, outcome_id)

---

## TESTING & VERIFICATION

### Manual Verification
```bash
# 1. Start bot
cd /opt/prediction-market-arbitrage
PYTHONPATH=/opt/prediction-market-arbitrage/src .venv/bin/python -m predarb run --iterations 10 > bot.log 2>&1

# 2. Check for rejection messages
grep "DUPLICATE arbitrage requires short selling" bot.log
grep "SELL required.*inventory=0" bot.log
grep "REJECTED" bot.log | head -20

# 3. Verify no DUPLICATE opportunities
python3 << 'EOF'
import json
with open("reports/unified_report.json", "r") as f:
    data = json.load(f)
opps = data.get("opportunity_executions", [])
duplicates = [o for o in opps if o.get("opportunity_type") == "DUPLICATE"]
print(f"DUPLICATE opportunities: {len(duplicates)} (should be 0)")
EOF

# 4. Verify no SELL without prior BUY
tail -100 bot.log | grep -E "(BUY|SELL)" | head -20
```

### Expected Output
```
INFO predarb.risk - REJECTED DUPLICATE opportunity: DUPLICATE arbitrage requires short selling — disabled on this venue.
DUPLICATE opportunities: 0 (should be 0)
INFO predarb.risk - APPROVED PARITY opportunity: Yes(0.45) + No(0.50) = 0.950 < 1.0
```

---

## MIGRATION NOTES

### Breaking Changes
- ❌ PaperBroker short selling capability removed (execution-time assertion)
- ❌ DUPLICATE detector effectively unusable (hard rejection)
- ❌ Previous simulations with shorts will fail with RuntimeError

### Backward Compatibility
- **NONE** - Intentionally breaking to enforce venue constraints
- **DO NOT ROLLBACK** - Venue does not support short selling

### Rollback Procedure (NOT RECOMMENDED)
```bash
# Revert changes (DO NOT DO THIS unless absolutely necessary)
git checkout HEAD~1 -- src/predarb/risk.py
git checkout HEAD~1 -- src/predarb/broker.py
git checkout HEAD~1 -- src/predarb/config.py
git checkout HEAD~1 -- config.yml
```

---

## PERFORMANCE EXPECTATIONS

### Before Changes
- DUPLICATE opportunities detected (should be disabled in config)
- SELL-first opportunities potentially allowed in paper mode
- Possible partial fills with hedging

### After Changes
- ✅ ZERO DUPLICATE opportunities (rejected at RiskManager)
- ✅ ZERO SELL-first opportunities (rejected at RiskManager)
- ✅ Only BUY-only or SELL-to-exit strategies approved
- ✅ RuntimeError on any filter bypass (fail-fast)
- ✅ Expected positive P&L from valid arbitrage only

---

## CODE SNIPPETS

### RiskManager - DUPLICATE Rejection
```python
# FILTER 1: GLOBAL DISABLE DUPLICATE
if opp.type.upper() == "DUPLICATE":
    logger.info(
        f"REJECTED {opp.type} opportunity: "
        "DUPLICATE arbitrage requires short selling — disabled on this venue."
    )
    return False
```

### RiskManager - SELL Without Inventory
```python
# FILTER 2: NO SELL-FIRST
for action in opp.actions:
    position_key = f"{action.market_id}:{action.outcome_id}"
    inventory = self.broker_state.positions.get(position_key, 0.0)
    
    if action.side.upper() == "SELL":
        if inventory <= 0:
            logger.info(
                f"REJECTED {opp.type} opportunity: "
                f"SELL required for {action.market_id}:{action.outcome_id} but inventory={inventory}. "
                "Short selling not supported on this venue."
            )
            return False
```

### Broker - Execution-Time Assertion
```python
def execute(self, market_lookup: Dict[str, Market], opportunity: Opportunity) -> List[Trade]:
    # MANDATORY INVARIANT: NO SELL WITHOUT POSITION
    for action in opportunity.actions:
        if action.side.upper() == "SELL":
            position_key = f"{action.market_id}:{action.outcome_id}"
            inventory = self.positions.get(position_key, 0.0)
            if inventory <= 0:
                raise RuntimeError(
                    f"FATAL INVARIANT VIOLATION: SELL action reached execution without position! "
                    f"Market: {action.market_id}, Outcome: {action.outcome_id}, "
                    f"Inventory: {inventory}, Requested: {action.amount}. "
                    f"Short selling is FORBIDDEN on this venue."
                )
```

---

## REFERENCES

- **Architecture Change:** `codebase_schema.json` - `2026_01_08_hard_disable_short_selling`
- **Risk Filters:** `src/predarb/risk.py` - RiskManager.approve()
- **Execution Assertion:** `src/predarb/broker.py` - PaperBroker.execute()
- **Configuration:** `config.yml` - risk and detectors sections
- **Schema Definition:** `src/predarb/config.py` - RiskConfig class

---

## SUPPORT

For questions or issues:
1. Check `bot.log` for rejection messages
2. Verify `config.yml` settings match this document
3. Review `codebase_schema.json` for architecture details
4. Run manual verification tests above

**DO NOT attempt to re-enable short selling** - venue does not support it.

---

**End of Implementation Summary**
