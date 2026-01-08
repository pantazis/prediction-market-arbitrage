# How to Test the Full Arbitrage Bot (Explained Simply)

## What's an Arbitrage Bot? 🤖

Imagine you see:
- **Store A** selling Bitcoin at $0.45 (45 cents on the dollar)
- **Store B** selling "No Bitcoin" at $0.52 (52 cents on the dollar)

If you buy BOTH, you spend $0.97 but get $1.00 when it resolves = **$0.03 profit!** 💰

That's arbitrage - finding price differences and making risk-free money.

## The Full Cycle (Step-by-Step)

```
1. 📊 FETCH MARKETS → Get all available markets from exchanges
2. 🔍 DETECT OPPORTUNITIES → Find price mismatches 
3. ✅ VALIDATE → Check if trade is safe (enough money, good liquidity)
4. 💸 EXECUTE → Buy both sides at the same time
5. 🔄 REBALANCE → If one side fails, close the other (hedge)
6. 📈 REPORT → Record what happened
```

## Testing Without Real Money 🎮

We use **"injection"** to fake market data (like a video game simulator):

### Method 1: Quick Test (Happy Path)
```bash
python -m predarb stress --scenario happy_path
```

**What it does:**
- Creates 15 fake markets with good arbitrage opportunities
- Runs the bot on them (no real money!)
- Shows you what trades it would make

**Output:**
```
✅ Found 15 opportunities
✅ Executed 12 trades  
✅ Made $450 profit (fake money)
```

### Method 2: Stress Test (Hard Mode)
```bash
python -m predarb stress --scenario high_volume
```

**What it does:**
- Creates 1000 fake markets (lots of noise!)
- Only 10 have real opportunities
- Tests if bot can handle the load

### Method 3: Rebalancing Test (What You Asked About! 🎯)
```bash
python -m predarb stress --scenario partial_fill
```

**What it does:**
- Creates markets where one side is DEEP (lots of money) and one side is SHALLOW (little money)
- Bot buys the DEEP side easily
- Bot tries to buy SHALLOW side → **FAILS** (not enough money)
- Bot must **HEDGE** = close the DEEP side to avoid risk

**Example:**
```
1. Bot buys YES side → ✅ SUCCESS ($100 filled)
2. Bot buys NO side → ❌ FAILED (only had $20 liquidity)
3. Bot REBALANCES → Sells the YES side to avoid being stuck
4. Final result: $0 exposure (safe!)
```

This tests the **"Oh crap, one side failed, close everything!"** logic.

## Testing Cash Management 💵

### Scenario: Fee/Slippage Test
```bash
python -m predarb stress --scenario fee_slippage
```

**What it does:**
- Creates 20 markets with TINY edges (like 1-2% profit)
- Adds realistic fees (0.5% per trade)
- Tests if bot correctly calculates: "Is this worth it after fees?"

**Math:**
```
Edge before fees: 2%
Trading fees: 0.5% × 2 sides = 1%
Real profit: 2% - 1% = 1% → Still worth it!

Edge before fees: 1%
Trading fees: 1%
Real profit: 1% - 1% = 0% → NOT worth it! Skip!
```

### Scenario: Risk Rejections Test
```bash
python -m predarb stress --scenario many_risk_rejections
```

**What it does:**
- 20 markets with LOW LIQUIDITY (not enough money to buy)
- 15 markets with LOW EDGE (profit too small)
- 5 markets with GOOD opportunities

Tests if bot correctly says "NO" to bad trades and "YES" to good ones.

## The Complete Test (Everything Together!)

### Run All Scenarios
```bash
# 1. Happy path (should work perfectly)
python -m predarb stress --scenario happy_path

# 2. Partial fills (tests rebalancing/hedging)
python -m predarb stress --scenario partial_fill

# 3. High volume (tests performance)
python -m predarb stress --scenario high_volume

# 4. Risk rejections (tests cash management)
python -m predarb stress --scenario many_risk_rejections

# 5. Fee/slippage (tests cost calculations)
python -m predarb stress --scenario fee_slippage

# 6. Semantic clustering (tests duplicate detection)
python -m predarb stress --scenario semantic_clustering
```

### Check the Report
After each test:
```bash
python -c "from src.report_summary import generate_reports_summary; print(generate_reports_summary())"
```

**You'll see:**
```
📊 UNIFIED REPORT SUMMARY
========================

Iterations: 1
Total Opportunities Found: 15
Total Executed: 12
Total Trades: 24

💰 P&L SUMMARY:
  Realized P&L: $450.00
  Total Fees: $12.00
  Net Profit: $438.00

✅ SUCCESS: 10 trades
⚠️  PARTIAL: 2 trades (hedged successfully)
```

## Understanding Rebalancing (The Important Part!)

### What's Rebalancing?

**Without Rebalancing:**
```
1. Buy YES for $45
2. Try to buy NO for $52 → FAILS
3. You're stuck holding YES (RISKY! 😱)
```

**With Rebalancing:**
```
1. Buy YES for $45 ✅
2. Try to buy NO for $52 → ❌ FAILS
3. IMMEDIATELY sell YES for ~$45 ✅
4. Net result: $0 exposure (SAFE! 😊)
```

### Test It Yourself

1. **Run the test:**
```bash
python -m predarb stress --scenario partial_fill --no-verify
```

2. **Check the report:**
```bash
cat reports/unified_report.json
```

3. **Look for:**
```json
{
  "opportunity_executions": [
    {
      "status": "partial",
      "hedge": {
        "hedged": true,
        "hedge_executions": [
          {
            "side": "SELL",
            "amount": 100,
            "reason": "Closing position after execution failure"
          }
        ]
      }
    }
  ]
}
```

This shows the bot **rebalanced** by selling what it bought!

## Creating Your Own Test Scenarios

Want to test something specific? Create a custom market file:

### Example: Testing Large Cash Rebalancing

**Create:** `my_test_markets.json`
```json
[
  {
    "id": "big_trade_1",
    "question": "Will I test rebalancing?",
    "outcomes": [
      {
        "id": "yes",
        "label": "Yes",
        "price": 0.40,
        "liquidity": 100000
      },
      {
        "id": "no", 
        "label": "No",
        "price": 0.55,
        "liquidity": 500
      }
    ],
    "end_date": "2026-12-31T00:00:00Z",
    "liquidity": 100500,
    "volume": 50000,
    "resolution_source": "manual"
  }
]
```

**Run it:**
```bash
python -m predarb stress --inject file:my_test_markets.json
```

**What happens:**
- YES side: $100k liquidity → Bot buys easily
- NO side: $500 liquidity → Bot can't buy enough
- Bot hedges by selling YES side
- Tests large cash rebalancing!

## Exit Codes (Did it Work?) ✅❌

After running a test, check the exit code:

```bash
python -m predarb stress --scenario partial_fill
echo $LASTEXITCODE  # Windows PowerShell
```

**Exit Codes:**
- `0` = ✅ Everything worked perfectly!
- `2` = ❌ Report file missing
- `3` = ❌ Report is broken (bad JSON)
- `4` = ❌ No iterations ran
- `5` = ❌ Missing data (inconsistent report)
- `6` = ❌ Rebalancing FAILED (residual exposure left!)

If you get exit code `6`, it means **the bot didn't rebalance properly** and left you with risky positions!

## Quick Commands (Copy-Paste Ready)

### Test Everything
```bash
# Run all tests
pytest tests/test_stress_scenarios.py -v

# Test just rebalancing
pytest tests/test_simulation_harness.py::test_hedge_on_one_leg_failure -v

# Test semantic clustering
python -m predarb stress --scenario semantic_clustering
```

### View Results
```bash
# See what happened
python demo_semantic_clustering.py

# Read the report
python -c "from src.report_summary import generate_reports_summary; print(generate_reports_summary())"

# Check report manually
cat reports/unified_report.json | python -m json.tool
```

## Summary (TL;DR) 📝

1. **Injection** = Fake market data (testing without real money)
2. **Stress scenarios** = Pre-built test cases
3. **Rebalancing** = Closing positions when trades fail
4. **`partial_fill` scenario** = Tests rebalancing with big/small liquidity
5. **Exit codes** = Tell you if it worked (0 = good, 6 = rebalancing failed)

**To test full cycle with rebalancing:**
```bash
python -m predarb stress --scenario partial_fill
```

**To test large cash management:**
```bash
python -m predarb stress --scenario high_volume
python -m predarb stress --scenario many_risk_rejections
```

**All tests:**
```bash
pytest tests/ -v
```

That's it! You're now testing like a pro! 🚀
