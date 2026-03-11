# Product Overview

Prediction Market Arbitrage Bot - automated cross-venue arbitrage detection and paper trading system for prediction markets.

## What It Does

Detects and executes arbitrage opportunities across Polymarket and Kalshi prediction markets using:
- Semantic matching (Sentence-BERT embeddings) to find equivalent markets across venues
- Multiple arbitrage detectors (parity, ladder, composite, exclusive sum, consistency, timelag)
- LLM verification layer to confirm market equivalence
- Paper trading simulation with realistic fee/slippage modeling

## Key Constraints

- **NO SHORT SELLING** on Polymarket - all strategies must be BUY-only or require existing inventory to SELL
- **DUPLICATE detector disabled** - requires short selling which isn't supported
- Cross-venue arbitrage requires both Kalshi (supports shorting) and Polymarket (no shorting)
- Sports markets excluded from Kalshi (not present on Polymarket)

## Operating Modes

1. **Live Paper Trading** - Real-time API data, simulated trades
2. **Stress Testing** - Deterministic fake data injection for validation
3. **Strict A+B Mode** - Cross-venue only (requires both exchanges)

## Data Flow

```
Fetch Markets → Tag/Filter → Semantic Match → LLM Verify → Detect Opportunities → Risk Check → Execute (Paper)
```

## Notifications

Telegram integration for real-time alerts on opportunities, trades, and system status.
