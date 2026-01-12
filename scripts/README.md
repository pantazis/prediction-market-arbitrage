# Scripts Directory

Standalone utility scripts for the prediction-market-arbitrage project.

## Available Scripts

### download_markets.py

Downloads market data from Kalshi and Polymarket APIs and saves to timestamped JSON/JSONL files.

**Requirements:**
- python-dotenv
- requests

**Usage:**

```bash
# Quick start - download both markets
python scripts/download_markets.py --kalshi --poly

# Full example with orderbooks
ENV_FILE=.env python scripts/download_markets.py \
  --kalshi \
  --poly \
  --kalshi-orderbooks 50 \
  --poly-orderbooks 50 \
  --out market_dumps

# Kalshi only with filters
python scripts/download_markets.py \
  --kalshi \
  --kalshi-status open \
  --kalshi-series KXPRES \
  --kalshi-orderbooks 20

# Custom output directory
python scripts/download_markets.py --kalshi --poly --out my_custom_folder
```

**CLI Arguments:**

| Argument | Default | Description |
|----------|---------|-------------|
| `--out DIR` | `market_dumps` | Output directory base path |
| `--kalshi` | - | Download Kalshi markets (flag) |
| `--poly` | - | Download Polymarket markets (flag) |
| `--kalshi-status STATUS` | `open` | Kalshi market status filter |
| `--kalshi-series TICKER` | - | Kalshi series ticker filter (optional) |
| `--kalshi-orderbooks N` | `0` | Fetch orderbooks for top N Kalshi markets by volume |
| `--poly-orderbooks N` | `0` | Fetch orderbooks for top N Polymarket markets by volume |

**Environment Variables:**

The script loads environment variables from `.env` by default. Override with `ENV_FILE`:

```bash
ENV_FILE=/path/to/custom/.env python scripts/download_markets.py --kalshi --poly
```

Expected variables (all optional, used if present):
- `KALSHI_API_KEY_ID` - Kalshi API key
- `KALSHI_PRIVATE_KEY_PATH` - Path to Kalshi PEM file
- `KALSHI_PRIVATE_KEY_PEM` - Kalshi PEM content
- `POLYMARKET_API_KEY` - Polymarket API key
- `POLYMARKET_SECRET` - Polymarket API secret
- `POLYMARKET_PASSPHRASE` - Polymarket API passphrase
- `POLYMARKET_FUNDER` - Polymarket wallet address
- `HTTP_TIMEOUT` - HTTP request timeout in seconds (default: 30)

**Output Structure:**

```
market_dumps/
└── 20260112_143025_UTC/
    ├── manifest.json                          # Metadata about the download
    ├── kalshi_markets.json                    # Kalshi markets (pretty)
    ├── kalshi_markets.jsonl                   # Kalshi markets (one per line)
    ├── kalshi_orderbooks_top.json            # Top N Kalshi orderbooks
    ├── kalshi_orderbooks_top.jsonl
    ├── polymarket_gamma_markets.json          # Polymarket markets (pretty)
    ├── polymarket_gamma_markets.jsonl         # Polymarket markets (one per line)
    ├── polymarket_clob_orderbooks_top.json   # Top N Polymarket orderbooks
    └── polymarket_clob_orderbooks_top.jsonl
```

**Features:**

- ✅ Automatic pagination for both APIs
- ✅ Exponential backoff retry logic (3 attempts)
- ✅ Timestamped output folders
- ✅ Both JSON and JSONL output formats
- ✅ Top-N orderbook fetching by volume
- ✅ Environment variable loading from .env
- ✅ No hardcoded secrets
- ✅ Clean error handling and progress output

**API Endpoints Used:**

*Kalshi:*
- `GET https://api.elections.kalshi.com/trade-api/v2/markets` (list markets)
- `GET https://api.elections.kalshi.com/trade-api/v2/markets/{ticker}/orderbook` (orderbook)

*Polymarket:*
- `GET https://gamma-api.polymarket.com/markets` (list markets)
- `GET https://clob.polymarket.com/book?token_id=...` (orderbook)
