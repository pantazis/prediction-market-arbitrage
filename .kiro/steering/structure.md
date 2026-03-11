# Project Structure

## Root Layout

```
/
├── src/predarb/          # Main application package
├── arbitrage_bot/        # Telegram bot control interface
├── tests/                # Test suite
├── scripts/              # Utility scripts
├── data/                 # Runtime data (watchlists, caches)
├── reports/              # Generated reports (CSV, JSON)
├── schemas/              # JSON schemas for validation
├── log/                  # Application logs
├── config.yml            # Main configuration
└── bot.py                # Legacy entry point
```

## Core Package: `src/predarb/`

```
src/predarb/
├── __main__.py           # CLI entry point
├── cli.py                # Command definitions (run, once, stress, validate-ab)
├── config.py             # Pydantic config models (AppConfig, RiskConfig, etc.)
├── models.py             # Domain models (Market, Outcome, Opportunity, Trade)
├── engine.py             # Main orchestration loop
├── pipeline.py           # Market processing pipeline
│
├── # Market Clients
├── market_client_base.py # Abstract MarketClient interface
├── polymarket_client.py  # Polymarket API client
├── kalshi_client.py      # Kalshi API client (RSA auth)
│
├── # Matching & Verification
├── matcher.py            # SmartMatcher (semantic matching)
├── cross_venue_matcher.py # Cross-venue pair finding
├── llm_verifier.py       # LLM-based market verification
│
├── # Arbitrage Detection
├── detectors/
│   ├── parity.py         # YES + NO != 1.0
│   ├── ladder.py         # Threshold monotonicity violations
│   ├── duplicates.py     # Cross-venue price differences (DISABLED)
│   ├── exclusivesum.py   # Mutually exclusive sum > 1.0
│   ├── consistency.py    # Logical contradictions
│   ├── timelag.py        # Stale quote detection
│   └── composite.py      # Hierarchical event mispricing
│
├── # Execution & Risk
├── broker.py             # PaperBroker (simulated execution)
├── risk.py               # RiskManager (approval filters)
├── strict_ab_validator.py # Cross-venue validation
│
├── # Reporting
├── unified_reporter.py   # JSON report generation
├── reporter.py           # Legacy CSV reporter
│
├── # Testing Support
├── testing/
│   ├── fake_client.py    # Mock market client
│   └── synthetic_data.py # Test data generation
├── dual_injection.py     # Dual-venue test injection
├── cross_venue_scenarios.py # Stress test scenarios
└── strict_ab_scenarios.py # A+B validation scenarios
```

## Telegram Bot: `arbitrage_bot/`

```
arbitrage_bot/
├── main.py               # Bot entry point
├── core/
│   ├── bot_loop.py       # Async message processing
│   ├── control_queue.py  # Command queue
│   └── state.py          # Bot state management
└── telegram/
    ├── handlers.py       # Command handlers (/status, /stop, etc.)
    ├── notifier.py       # Outbound notifications
    ├── router.py         # Message routing
    └── security.py       # Authorization
```

## Tests: `tests/`

```
tests/
├── conftest.py           # Shared fixtures (markets, configs)
├── fixtures/             # Test data files
├── test_*_invariants.py  # Property-based invariant tests
├── test_engine.py        # Engine integration tests
├── test_broker.py        # Broker execution tests
├── test_detectors.py     # Detector unit tests
├── test_unified_reporter.py # Reporting tests
└── test_dual_injection.py # Dual-venue injection tests
```

## Key Files

| File | Purpose |
|------|---------|
| `config.yml` | Main runtime configuration |
| `CODEBASE_OPERATIONS.json` | Operational reference (commands, scenarios) |
| `reports/unified_report.json` | Primary output (iterations, trades, PnL) |
| `data/watchlist_pairs.csv` | Verified market pairs for monitoring |
| `data/llm_verify_cache.json` | LLM verification cache |

## Data Flow Through Modules

1. `cli.py` → parses args, loads config
2. `engine.py` → orchestrates iteration loop
3. `*_client.py` → fetches markets from APIs
4. `cross_venue_matcher.py` → finds semantic pairs
5. `llm_verifier.py` → confirms market equivalence
6. `detectors/*.py` → identifies opportunities
7. `risk.py` → filters/approves opportunities
8. `broker.py` → executes paper trades
9. `unified_reporter.py` → logs results
