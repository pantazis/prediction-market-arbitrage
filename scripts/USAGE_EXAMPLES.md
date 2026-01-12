# Market Data Downloader - Quick Start Guide

## Overview

The `scripts/download_markets.py` script downloads market data from Kalshi and Polymarket APIs and saves it to timestamped JSON/JSONL files.

## Installation

Ensure dependencies are installed:

```bash
pip install python-dotenv requests
```

## Basic Usage

### 1. Download Both Kalshi and Polymarket Markets

```bash
python scripts/download_markets.py --kalshi --poly
```

### 2. Download with Orderbooks

Fetch orderbooks for the top 50 markets (by volume) from each exchange:

```bash
python scripts/download_markets.py \
  --kalshi \
  --poly \
  --kalshi-orderbooks 50 \
  --poly-orderbooks 50
```

### 3. Use Custom Environment File

If your `.env` file is in a different location:

```bash
ENV_FILE=/path/to/app/.env python scripts/download_markets.py --kalshi --poly
```

### 4. Kalshi Only with Filters

Download only open markets from a specific series:

```bash
python scripts/download_markets.py \
  --kalshi \
  --kalshi-status open \
  --kalshi-series KXPRES \
  --kalshi-orderbooks 20
```

### 5. Custom Output Directory

```bash
python scripts/download_markets.py \
  --kalshi \
  --poly \
  --out my_data_dumps
```

## Environment Variables

The script loads environment variables from `.env` (configurable via `ENV_FILE`).

**Supported variables (all optional):**

```bash
# Kalshi
KALSHI_API_KEY_ID=your_key_id_here
KALSHI_PRIVATE_KEY_PATH=/path/to/key.pem
KALSHI_PRIVATE_KEY_PEM=-----BEGIN RSA PRIVATE KEY-----...

# Polymarket
POLYMARKET_API_KEY=your_api_key_here
POLYMARKET_SECRET=your_secret_here
POLYMARKET_PASSPHRASE=your_passphrase_here
POLYMARKET_FUNDER=0x1234567890abcdef...

# HTTP
HTTP_TIMEOUT=30
```

## Output Structure

Each run creates a timestamped folder with all downloaded data:

```
market_dumps/
└── 20260112_143025_UTC/
    ├── manifest.json                          # Metadata about the download
    ├── kalshi_markets.json                    # All Kalshi markets (pretty-printed)
    ├── kalshi_markets.jsonl                   # Same data, one object per line
    ├── kalshi_orderbooks_top.json            # Top N orderbooks (if requested)
    ├── kalshi_orderbooks_top.jsonl
    ├── polymarket_gamma_markets.json          # All Polymarket markets
    ├── polymarket_gamma_markets.jsonl
    ├── polymarket_clob_orderbooks_top.json   # Top N orderbooks (if requested)
    └── polymarket_clob_orderbooks_top.jsonl
```

## Example: Full Download

Complete download with all options:

```bash
ENV_FILE=.env python scripts/download_markets.py \
  --kalshi \
  --poly \
  --kalshi-status open \
  --kalshi-orderbooks 50 \
  --poly-orderbooks 50 \
  --out market_dumps
```

**Expected output:**

```
✓ Loaded environment from: .env

📁 Output directory: market_dumps/20260112_143025_UTC

📊 Downloading Kalshi data...
  Fetching Kalshi markets page 1...
  Fetching Kalshi markets page 2...
  ✓ Retrieved 427 Kalshi markets
  ✓ Saved: market_dumps/20260112_143025_UTC/kalshi_markets.json
  ✓ Saved: market_dumps/20260112_143025_UTC/kalshi_markets.jsonl

📖 Fetching top 50 Kalshi orderbooks...
  [1/50] Fetching orderbook for KXPRESNOV...
  [2/50] Fetching orderbook for KXPRESPOP...
  ...
  ✓ Saved: market_dumps/20260112_143025_UTC/kalshi_orderbooks_top.json
  ✓ Saved: market_dumps/20260112_143025_UTC/kalshi_orderbooks_top.jsonl

📊 Downloading Polymarket data...
  Fetching Polymarket markets page 1...
  Fetching Polymarket markets page 2...
  ✓ Retrieved 1,234 Polymarket markets
  ✓ Saved: market_dumps/20260112_143025_UTC/polymarket_gamma_markets.json
  ✓ Saved: market_dumps/20260112_143025_UTC/polymarket_gamma_markets.jsonl

📖 Fetching top 50 Polymarket orderbooks...
  [1/50] Fetching orderbook for token 12345678...
  [2/50] Fetching orderbook for token 87654321...
  ...
  ✓ Saved: market_dumps/20260112_143025_UTC/polymarket_clob_orderbooks_top.json
  ✓ Saved: market_dumps/20260112_143025_UTC/polymarket_clob_orderbooks_top.jsonl

  ✓ Saved: market_dumps/20260112_143025_UTC/manifest.json

✅ Download complete! Data saved to: market_dumps/20260112_143025_UTC
```

## Features

- ✅ **Automatic pagination** - Handles cursor/offset pagination for both APIs
- ✅ **Retry logic** - 3 attempts with exponential backoff (1s, 2s, 4s)
- ✅ **Dual formats** - Both JSON (pretty) and JSONL (streaming-friendly)
- ✅ **Top-N orderbooks** - Fetch orderbooks for highest volume markets
- ✅ **Environment loading** - Configurable .env file path
- ✅ **No secrets in output** - Never prints API keys or secrets
- ✅ **Clean progress logging** - Real-time feedback without clutter
- ✅ **Manifest metadata** - Each run includes download details

## API Endpoints

### Kalshi
- **Markets:** `GET https://api.elections.kalshi.com/trade-api/v2/markets`
- **Orderbook:** `GET https://api.elections.kalshi.com/trade-api/v2/markets/{ticker}/orderbook`

### Polymarket
- **Markets:** `GET https://gamma-api.polymarket.com/markets`
- **Orderbook:** `GET https://clob.polymarket.com/book?token_id=...`

## Troubleshooting

### Error: "Must specify at least one data source"

You must include at least one of `--kalshi` or `--poly` flags.

### Warning: ".env not found"

The script will continue using system environment variables. Set `ENV_FILE` to the correct path:

```bash
ENV_FILE=/path/to/.env python scripts/download_markets.py --kalshi --poly
```

### HTTP Timeouts

Increase the timeout in your `.env`:

```bash
HTTP_TIMEOUT=60
```

### Retry Failures

The script automatically retries failed requests 3 times with exponential backoff. If you see repeated failures, check:
- Network connectivity
- API credentials (if using private endpoints)
- API rate limits

## Notes

- The script uses **public endpoints** by default (no authentication required)
- Orderbook fetching may require API credentials for some endpoints
- All timestamps are in UTC
- File sizes can be large for full market dumps (50-100MB+)
- JSONL format is ideal for streaming/processing line-by-line
