"""SIMULATION HARNESS SETUP AND USAGE GUIDE

This document explains how to use the simulation harness to run the arbitrage bot
against synthetic market data with real Telegram notifications.

## Quick Start

### 1. Environment Setup

Set environment variables for Telegram notifications:

```bash
export TELEGRAM_BOT_TOKEN="your_bot_token_here"
export TELEGRAM_CHAT_ID="your_chat_id_here"
```

Or create a `.env` file in the project root:

```
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_CHAT_ID=your_chat_id_here
```

### 2. Run Simulation with Real Telegram Notifications

```bash
python -m sim_run --days 2 --trade-size 200 --seed 42
```

This will:
- Generate 2 days of deterministic synthetic market data (2,880 minutes)
- Run your existing bot against the fake markets
- Send real Telegram messages:
  - Startup message
  - Per-executed trade messages
  - Daily summary (PnL, open positions)
- Write trades to `reports/paper_trades.csv`

### 3. Run Tests (No Telegram Required)

```bash
pytest tests/test_simulation_harness.py
```

Unit tests use TelegramNotifierMock, which stores messages in memory.
No Telegram credentials needed.

## Architecture

### Components

1. **FakePolymarketClient** (`src/predarb/testing/fake_client.py`)
   - In-memory market data (no HTTP)
   - Deterministic 2-day evolution with controllable seed
   - Generates 20-50 markets with various opportunity types

2. **Synthetic Data Generator** (`src/predarb/testing/synthetic_data.py`)
   - `generate_synthetic_markets()`: Creates initial market snapshot
   - `evolve_markets_minute_by_minute()`: Evolves prices over time
   - Includes:
     - Parity violations (outcome sum != 1)
     - Ladder markets (sequential outcome buckets)
     - Duplicate/clone markets with price divergence
     - Multi-outcome exclusive sum violations
     - Time-lag divergence
     - Rejection cases (illiquid, wide spread, no resolution source)

3. **Notifier Interface** (`src/predarb/notifiers/`)
   - Abstract `Notifier` base class: `send(text: str) -> None`
   - `TelegramNotifierReal`: Sends to real Telegram using bot token + chat_id
   - `TelegramNotifierMock`: Stores messages in memory for testing
   - Both implement compatibility methods: `notify_startup()`, `notify_opportunity()`, etc.

4. **Engine Injection** (`src/predarb/engine.py`)
   - Engine now accepts optional `notifier` parameter
   - `Engine(config, client, notifier=None)`
   - If notifier is None, loads from config (backward compatible)
   - If notifier is provided, uses injected instance (for testing/simulation)

5. **Simulation Entry Point** (`sim_run.py`)
   - CLI: `python -m sim_run --days 2 --trade-size 200 --seed 42`
   - Instantiates FakePolymarketClient + TelegramNotifierReal
   - Runs Engine for specified number of days
   - Sends real Telegram messages during execution

## Usage Examples

### Example 1: Basic 2-Day Simulation

```bash
python -m sim_run --days 2
```

- Generates 30 markets (default)
- Runs 2 days of minute-by-minute data
- Sends Telegram messages (if credentials set)
- Writes trades to reports/paper_trades.csv

### Example 2: Larger Simulation with Custom Seed

```bash
python -m sim_run --days 5 --markets 50 --seed 123
```

- Generates 50 markets
- Runs 5 days
- Uses seed=123 for reproducibility
- Same data produced every time with same seed

### Example 3: No Telegram (Testing Locally)

```bash
python -m sim_run --days 2 --no-telegram
```

- Runs simulation without Telegram notifications
- Useful for development without Telegram credentials

### Example 4: Run Unit Tests

```bash
# All simulation harness tests
pytest tests/test_simulation_harness.py

# Specific test class
pytest tests/test_simulation_harness.py::TestFakePolymarketClient

# Verbose output
pytest tests/test_simulation_harness.py -v
```

## Data Flow: Simulation Harness

```
sim_run.py (entry point)
  ↓
  ├─ Load config.yml
  ├─ Create FakePolymarketClient(num_markets, days, seed)
  ├─ Create TelegramNotifierReal(bot_token, chat_id)
  ├─ Create Engine(config, fake_client, notifier)
  ↓
Engine.run() [loop for N iterations]
  ↓
  ├─ client.fetch_markets()  ← Returns synthetic data (evolves each minute)
  ├─ filter_markets()         ← Existing filtering logic
  ├─ rank_markets()           ← Existing ranking logic
  ├─ Run detector pipeline    ← 6 detectors (existing)
  ├─ broker.execute()         ← Paper trading (existing)
  ├─ notifier.send()          ← TelegramNotifierReal sends real messages
  └─ Write trades.csv
  ↓
Exit
```

## Environment Variables

### Required for Real Telegram

- `TELEGRAM_BOT_TOKEN`: Your Telegram bot token
- `TELEGRAM_CHAT_ID`: Chat ID to send messages to

### Optional

- `TELEGRAM_ENABLED`: Set to "true" to enable (default: false)

### All Polymarket Credentials (for live bot)

- `POLYMARKET_API_KEY`: CLOB API key
- `POLYMARKET_SECRET`: CLOB API secret
- `POLYMARKET_PASSPHRASE`: CLOB API passphrase
- `POLYMARKET_PRIVATE_KEY`: Ethereum private key
- `POLYMARKET_FUNDER`: Funder wallet address

## Test Coverage

### Notifier Tests

- `TestNotifierInterface`: Abstract base class enforcement
- `TestTelegramNotifierMock`: Message storage, compatibility methods
- `TestTelegramNotifierReal`: Credential handling, error cases

### Synthetic Data Tests

- `TestSyntheticDataGeneration`: Market generation, determinism, diversity
- Verifies parity, ladder, duplicate, multioutcome, timelag, rejection cases

### Fake Client Tests

- `TestFakePolymarketClient`: Initialization, market evolution, reset
- Verifies prices change minute-by-minute
- Verifies deterministic behavior with same seed

### Integration Tests

- `TestSimulationIntegration`: Full harness execution
- Verifies Engine works with FakePolymarketClient + mock notifier
- Verifies reports are written
- Verifies notifier receives messages

## Debugging

### Check Generated Markets

```python
from predarb.testing import generate_synthetic_markets

markets = generate_synthetic_markets(num_markets=10, seed=42)
for m in markets:
    print(f"{m.id}: {m.question}")
    print(f"  Outcomes: {[o.label for o in m.outcomes]}")
    print(f"  Prices: {[o.price for o in m.outcomes]}")
    print(f"  Tags: {m.tags}")
```

### Check Synthetic Evolution

```python
from predarb.testing import FakePolymarketClient

client = FakePolymarketClient(num_markets=5, seed=42)
for minute in range(3):
    markets = client.fetch_markets()
    print(f"Minute {minute}: {len(markets)} markets")
    for m in markets[:1]:
        print(f"  {m.id}: {[o.price for o in m.outcomes]}")
```

### Check Mock Notifier Messages

```python
from predarb.notifiers.telegram import TelegramNotifierMock

notifier = TelegramNotifierMock()
notifier.notify_startup("Test")
notifier.notify_trade_summary(3)

for msg in notifier.get_messages():
    print(msg)
    print("---")
```

## Production Notes

- **Simulation only**: FakePolymarketClient generates synthetic data, not connected to real Polymarket
- **Paper trading only**: PaperBroker simulates execution without real capital
- **Deterministic**: Same seed produces identical market evolution every time
- **No API limits**: FakePolymarketClient makes no HTTP calls
- **Testing ready**: TelegramNotifierMock enables unit tests without Telegram

## Common Issues

### Issue: "TELEGRAM_BOT_TOKEN is required but not provided"

**Solution**: Set environment variables or use `--no-telegram` flag

```bash
export TELEGRAM_BOT_TOKEN="your_token"
export TELEGRAM_CHAT_ID="your_chat_id"
python -m sim_run --days 2
```

Or:

```bash
python -m sim_run --days 2 --no-telegram
```

### Issue: "Config file not found: config.yml"

**Solution**: Run from project root where config.yml exists

```bash
cd /path/to/arbitrage
python -m sim_run --days 2
```

### Issue: Tests fail with import errors

**Solution**: Ensure dependencies are installed

```bash
pip install -r requirements.txt
```

## Future Enhancements

1. **Multiple Fake Clients**: Create different synthetic scenarios
2. **Equity Curve Plotting**: Generate PNG/PDF charts of simulations
3. **Replay/Playback**: Save and replay market evolution
4. **Parametric Scenarios**: Generate markets matching specific criteria
5. **Parallel Simulations**: Run multiple seeds in parallel for statistical analysis
"""
