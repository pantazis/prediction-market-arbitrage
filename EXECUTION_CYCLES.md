# Application Execution Cycles (Comprehensive Overview)

This document summarizes all execution cycles supported by the repository, from the modern `src/predarb` engine to the Telegram-controlled bot and simulation harness. It reflects the current Find-First architecture and live incremental reporting, and notes legacy/optional variations where relevant.

---

## 1) Predarb Engine Run Loop (Find-First)
Files: src/predarb/__main__.py, src/predarb/cli.py, src/predarb/engine.py, src/predarb/reporter.py, src/predarb/exec_logger.py

High-level steps:
1. CLI parses args (`run|once|selftest`) and loads config (config.yml + env).
2. Instantiate `PolymarketClient` with credentials.
3. Instantiate `Engine(config, client, notifier?)`.
4. Loop (`run()`):
   - Fetch 100% of active markets: `client.get_active_markets()`.
   - Detect opportunities on ALL markets (Find-First):
     - Detectors sequence: Parity, Ladder, Duplicate, ExclusiveSum, TimeLag, Consistency.
     - Pattern: `detector.detect(markets) → List[Opportunity]`.
   - Risk-gating for each opportunity (edge, liquidity, allocation, positions).
   - Execute approved opportunities via `PaperBroker`:
     - Build intended `TradeAction`s, simulate fills with fees/slippage/liquidity.
     - Track positions, P&L, equity curve.
   - Live incremental reporting (append-only CSV + dedup): `LiveReporter.report(...)` writes `reports/live_summary.csv`.
   - DRY-RUN execution trace logging (append-only JSONL): `ExecLogger` writes `reports/opportunity_logs.jsonl`.
   - Optional Telegram notifications: `notifier.send_message(...)`.
   - Sleep `refresh_seconds` and repeat.

Key properties:
- Find-First: no pre-filtering in the main loop; risk manager is the gate-keeper.
- Deterministic hashing for reporting dedup; restart-safe state persisted.
- Append-only outputs: CSV rows and JSONL traces never overwrite.

Optional variations:
- LLM Group Verification: run `matchers` + `llm_verifier` to validate semantic groups before risk/execute.
- Legacy pre-filter (deprecated): `filter_markets → rank_markets` (documented but removed from main loop).

---

## 2) Single Iteration (`run_once`) Cycle
Files: src/predarb/engine.py

Steps (no sleep/repeat):
1. Fetch markets.
2. Detect opportunities across all markets.
3. Risk-gate and execute approved.
4. Report CSV and emit JSONL traces.
5. Optionally notify via Telegram.

Use for quick tests, CI checks, or controlled runs.

---

## 3) Self-Test Cycle (Offline Fixture)
Files: src/predarb/__main__.py, tests/fixtures/markets.json

Steps:
1. `predarb selftest --fixtures tests/fixtures/markets.json`.
2. Load config, inject fixture markets (no HTTP).
3. Run detectors, risk, and reporter once.
4. Produce deterministic outputs suitable for CI.

---

## 4) Simulation Harness Cycle
Files: sim_run.py, src/predarb/testing/*, src/predarb/notifiers/telegram.py

Steps:
1. Start via `python -m sim_run --days N --trade-size X [...options]`.
2. Use `FakePolymarketClient` and `synthetic_data` to evolve markets deterministically (no network).
3. Run `Engine` end-to-end with real or mock Telegram notifier.
4. Execute paper trades; record positions and P&L.
5. Send notifications (real/mocked) for trades, status, daily summaries.

---

## 5) Telegram-Controlled Bot Cycles (Bidirectional)
Files: arbitrage_bot/main.py, arbitrage_bot/core/*, arbitrage_bot/telegram/*

Outbound (App → User):
1. Engine detects/executed → Notifier formats event (trade_entered/exited, error, daily, status, mode_changed, risk_warning).
2. Send to Telegram API asynchronously; respect rate limits and retries.

Inbound (User → App):
1. Listener polls Telegram updates.
2. Parse `/command` + args; validate chat_id and permissions; enforce rate limit.
3. Route to handler; handler queues `ControlAction|RiskAction` to `ControlQueue` (non-blocking).
4. Immediate response to user; deferred execution in `bot_loop`.
5. `bot_loop` processes queued actions (start/pause/stop/mode/freeze/unfreeze/forceclose/etc.).

Operating modes:
- SCAN_ONLY: detect + report, no executions.
- PAPER: full cycle with `PaperBroker`.
- LIVE: requires confirmation; broker would place real orders (optional implementation).

---

## 6) DRY-RUN Execution Trace Cycle (ExecLogger)
Files: src/predarb/exec_logger.py, reports/opportunity_logs.jsonl

Per approved opportunity (DRY-RUN):
1. Build stable `trace_id` (sha256 over opportunity_id + detector + markets + intended_actions).
2. Record snapshot: prices_before, intended_actions, risk_approval, executions, hedge/cancel, status, realized_pnl, latency_ms.
3. Safe append via temp-file + atomic rename; order-invariant ID for identical inputs.

---

## 7) Paper Trade Logging Cycle
Files: reports/paper_trades.csv, src/predarb/broker.py

Steps:
1. For each executed `TradeAction`, simulate fills.
2. Append trade rows with cost, fees, realized P&L when closing.
3. Maintain positions and equity curve in broker state.

---

## 8) Live Incremental Reporting Cycle
Files: src/predarb/reporter.py, reports/live_summary.csv, reports/.last_report_state.json

Steps:
1. Compute deterministic hashes of market IDs and opportunity IDs.
2. If state changed from last row, append one CSV line with deltas and approval%.
3. Persist state for restart-safe resumption; skip identical states.

CSV columns include: timestamp, readable time, iteration, MARKETS/Δ, DETECTED/Δ, APPROVED/Δ, APPROVAL%, STATUS, MARKET_HASH, OPP_HASH.

---

## 9) Risk Kill-Switch and Limits Cycle
Files: src/predarb/risk.py, arbitrage_bot/core/bot_loop.py

Steps:
1. Evaluate min edge, liquidity, allocation, position limits.
2. On drawdown breach, trigger kill switch: halt new trades, notify user.
3. Commands `/freeze` and `/unfreeze` modify execution gates.

---

## 10) Optional Live Trading Cycle (If Enabled)
Files: src/predarb/broker.py (to be extended), src/predarb/polymarket_client.py

Steps:
1. Replace `PaperBroker` with real broker using `py-clob-client`.
2. Submit `POST /orders` for intended actions; monitor fills.
3. Hedge or cancel on failure; update positions; send notifications.
4. Continue reporting (CSV + JSONL traces) for audit.

Note: The repository currently ships with paper trading; live requires additional integration and confirmations.

---

## 11) Legacy Client Cycle (Reference)
Files: src/*.py, bot.py

Steps:
1. Load legacy config and engine.
2. Filter+rank markets (legacy path).
3. Detect → Risk → Paper execute → Telegram notify.

Modern `src/predarb/*` supersedes legacy modules.

---

## 12) Error Handling & Retries Cycle
Files: src/predarb/notifiers/telegram.py, arbitrage_bot/telegram/*

- Notifier: handle HTTP errors, rate limits (429) with queue + exponential backoff.
- Handlers: return immediate responses; all side-effects deferred to bot_loop.
- SafeMessageFormatter: escape markdown; format numbers; limit message length.

---

## Module References (Quick Links)
- Engine: src/predarb/engine.py
- Client: src/predarb/polymarket_client.py
- Broker: src/predarb/broker.py
- Risk: src/predarb/risk.py
- Detectors: src/predarb/detectors/*
- Reporter: src/predarb/reporter.py
- ExecLogger: src/predarb/exec_logger.py
- Matchers/LLM Verifier: src/predarb/matchers.py, src/predarb/llm_verifier.py
- Telegram bot: arbitrage_bot/main.py, arbitrage_bot/core/*, arbitrage_bot/telegram/*
- Simulation: sim_run.py, src/predarb/testing/*

---

## Quick Start Commands
- Predarb run loop:
  - `python -m predarb run`
- Single iteration:
  - `python -m predarb once`
- Selftest with fixtures:
  - `python -m predarb selftest --fixtures tests/fixtures/markets.json`
- Simulation harness:
  - `python -m sim_run --days 2 --trade-size 200 --no-telegram`
- Telegram tests:
  - `pytest tests/test_telegram_interface.py tests/test_telegram_notifier.py -v`

