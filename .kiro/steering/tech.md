# Tech Stack & Build System

## Language & Runtime

- Python 3.12+
- Virtual environment at `.venv/`

## Core Dependencies

- **pydantic** - Data validation and configuration models
- **sentence-transformers** - Semantic matching (all-MiniLM-L6-v2 model)
- **numpy** - Vector operations for embeddings
- **requests** - HTTP client for market APIs
- **cryptography** - RSA signing for Kalshi authentication
- **pyyaml** - Configuration file parsing
- **python-dotenv** - Environment variable loading

## Optional Dependencies

- **openai/google-generativeai** - LLM verification providers
- **pytest** - Testing framework

## Configuration

- `config.yml` - Main configuration (risk, broker, detectors, telegram)
- `config_live_paper.yml` - Live paper trading config
- `config_strict_ab.yml` - Strict cross-venue mode
- `.env` - API credentials (never committed)

## Common Commands

### Running the Bot

```bash
# Single iteration
python -m predarb once --config config.yml

# Continuous run (N iterations)
python -m predarb run --config config_live_paper.yml --iterations 32

# Background execution
nohup .venv/bin/python -m predarb run --config config_live_paper.yml --iterations 480 > bot.log 2>&1 & echo $! > bot.pid

# Stop bot
kill $(cat bot.pid)
```

### Testing

```bash
# Run all tests
pytest tests/

# Specific test categories
pytest tests/test_unified_reporter.py -v
pytest tests/test_*_invariants.py -v

# Stress test with scenarios
python -m predarb stress --scenario happy_path
python -m predarb stress --scenario high_volume --iterations 10

# Dual-venue stress test
python -m predarb dual-stress --cross-venue

# Strict A+B validation
python -m predarb validate-ab
```

### Verification & Utilities

```bash
# Verify report integrity
python -m predarb.verify_reports

# Self-test (no API calls)
python -m predarb selftest

# Download market data
python scripts/download_markets.py --kalshi --poly --max-markets 100
```

## Environment Variables

```bash
# Polymarket (read-only, no auth needed for public API)
POLYMARKET_API_KEY=
POLYMARKET_SECRET=
POLYMARKET_PASSPHRASE=

# Kalshi (required for Kalshi markets)
KALSHI_API_KEY_ID=
KALSHI_PRIVATE_KEY_PEM=
KALSHI_API_HOST=https://api.elections.kalshi.com

# Telegram notifications
TELEGRAM_ENABLED=true
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=

# LLM verification (optional)
OPENAI_API_KEY=
```

## PYTHONPATH

When running from project root, set:
```bash
PYTHONPATH=/opt/prediction-market-arbitrage/src
```
