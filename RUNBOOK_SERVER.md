# Server Runbook — Stop Old Bot, Verify, Deploy New Bot

This runbook shows how to safely stop any previously running arbitrage bot, verify the system, and start the new bot. It covers common setups: systemd service, tmux/screen session, Docker (if you use it), and a simple virtualenv process.

## Overview
- Stop/cleanup any old processes to avoid duplicate trading loops
- Run deterministic self-tests (no network) to confirm code health
- Optionally run a live connection check (network)
- Start the new bot and monitor logs/outputs

## Prerequisites
- Python 3.10+ on the server
- Project files deployed to a directory (e.g., /opt/arbitrage or C:\arbitrage)
- Virtualenv created and dependencies installed:

```bash
python -m venv .venv
. .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -U pip
pip install -r requirements.txt
```

## Environment Variables (.env)
Create a .env file beside config.yml with the required credentials. Example:

```
# Polymarket CLOB (required for live connection)
POLYMARKET_API_KEY=... 
POLYMARKET_SECRET=...
POLYMARKET_PASSPHRASE=...
POLYMARKET_PRIVATE_KEY=...        # optional depending on flow
POLYMARKET_FUNDER=...             # optional

# Telegram (optional outbound/inbound)
TELEGRAM_ENABLED=true             # or false
TELEGRAM_BOT_TOKEN=123456789:ABC...
TELEGRAM_CHAT_ID=987654321
```

Notes:
- predarb CLI reads config.yml and merges with .env.
- If Telegram is disabled, set TELEGRAM_ENABLED=false (or omit token/chat id).

## Step 1 — Stop Previous Bot

Pick the method that matches how the bot runs on your server.

### A) systemd service (Linux)
```bash
sudo systemctl stop arbitrage-bot.service
sudo systemctl disable arbitrage-bot.service    # optional
sudo systemctl status arbitrage-bot.service
```
Confirm stopped: status shows inactive (dead).

### B) tmux session
```bash
tmux ls
tmux kill-session -t arbitrage   # or the actual session name
tmux ls                          # ensure removed
```

### C) screen session
```bash
screen -ls
screen -S arbitrage -X quit      # or the actual session name
screen -ls
```

### D) Docker container
```bash
docker ps
docker stop arbitrage-bot        # or container ID/name
docker ps                        # confirm stopped
```

### E) Bare process (fallback)
```bash
ps aux | grep -E "python (-m predarb|bot.py)" | grep -v grep
# If any remain, stop them safely:
pkill -f "python -m predarb"
pkill -f "python bot.py"
```

## Step 2 — Sanity Checks (No-Network)
Run deterministic checks that do not require external APIs.

```bash
. .venv/bin/activate                 # Windows: .venv\Scripts\activate
python -m predarb selftest           # uses tests/fixtures/markets.json
pytest -q tests/test_reporter.py     # optional quick subset
```

Expected: selftest prints detected opportunities; pytest subset passes. These do not perform network calls.

## Step 3 — Optional Live Connection Check (Network)
Only if you want to validate Polymarket CLOB connectivity before starting the loop.

```bash
python bot.py test_connection --config config.yml
```

Expected: prints “Connection successful. Found N markets.” If this fails, verify your .env credentials and host reachability.

## Step 4 — Start the New Bot

Choose one deployment style.

### A) Simple virtualenv process (foreground)
```bash
. .venv/bin/activate                  # Windows: .venv\Scripts\activate
python -m predarb run --config config.yml
```

Smoke test alternative (limited iterations):
```bash
python -m predarb run --config config.yml --iterations 5
```

### B) tmux (background)
```bash
tmux new -s arbitrage -d \
  ". .venv/bin/activate && python -m predarb run --config config.yml"
tmux ls
tmux attach -t arbitrage   # view logs; Ctrl+B then D to detach
```

### C) systemd service (recommended for Linux)
Create /etc/systemd/system/arbitrage-bot.service:

```
[Unit]
Description=Prediction Market Arbitrage Bot
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/arbitrage
EnvironmentFile=/opt/arbitrage/.env
ExecStart=/opt/arbitrage/.venv/bin/python -m predarb run --config /opt/arbitrage/config.yml
Restart=on-failure
RestartSec=5
User=arbitrage
Group=arbitrage

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable arbitrage-bot.service
sudo systemctl start arbitrage-bot.service
sudo systemctl status arbitrage-bot.service
```

### D) Docker (if you maintain your own image)
No Dockerfile is included in this repo. If you have an image, run similarly to:
```bash
docker run -d --name arbitrage-bot \
  --env-file .env \
  -v $(pwd)/config.yml:/app/config.yml \
  -v $(pwd)/reports:/app/reports \
  your-registry/arbitrage-bot:latest \
  python -m predarb run --config /app/config.yml
```

## Step 5 — Monitoring and Outputs
- Logs: stdout (tmux/systemd journal)
  - systemd: `journalctl -u arbitrage-bot -f`
- Reports: 
  - trades CSV: reports/paper_trades.csv
  - live summary CSV: reports/live_summary.csv
- Health: look for the loop logs (Scanning markets…, Detected N opportunities, Sleeping Xs…)

## Rollback
- If issues occur, stop the new process (systemctl stop / tmux kill-session / docker stop)
- Revert code to previous known-good commit and restart
- Keep .env unchanged unless the issue is credentials-related

## Troubleshooting
- Missing credentials: ensure .env contains POLYMARKET_* keys; restart process
- Telegram not sending: set TELEGRAM_ENABLED=true and supply bot token/chat id
- Permission denied: ensure the service user has write access to reports/ and the project dir
- Can’t import predarb: verify the virtualenv is active and requirements are installed

---

Owner: Operations/Trading
Last updated: 2026-01-07
