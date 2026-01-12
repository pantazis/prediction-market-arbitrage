#!/usr/bin/env python3
"""
Standalone market data downloader for Kalshi and Polymarket APIs.
Downloads market data and orderbooks, saving to timestamped JSON/JSONL files.

Requirements:
- python-dotenv
- requests

Usage:
    ENV_FILE=.env python scripts/download_markets.py --kalshi --poly --kalshi-orderbooks 50 --poly-orderbooks 50
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

import requests
from dotenv import load_dotenv


# ============================================================================
# Configuration & Environment Loading
# ============================================================================

def load_environment():
    """Load environment variables from .env file."""
    env_file = os.getenv("ENV_FILE", ".env")
    if os.path.exists(env_file):
        load_dotenv(dotenv_path=env_file)
        print(f"✓ Loaded environment from: {env_file}")
    else:
        print(f"⚠ Warning: {env_file} not found, using system environment only")


def get_env_config() -> Dict[str, Any]:
    """Read configuration from environment variables (never print values)."""
    return {
        # Kalshi
        "kalshi_api_key_id": os.getenv("KALSHI_API_KEY_ID", ""),
        "kalshi_private_key_path": os.getenv("KALSHI_PRIVATE_KEY_PATH", ""),
        "kalshi_private_key_pem": os.getenv("KALSHI_PRIVATE_KEY_PEM", ""),
        
        # Polymarket
        "polymarket_api_key": os.getenv("POLYMARKET_API_KEY", ""),
        "polymarket_api_secret": os.getenv("POLYMARKET_SECRET", ""),
        "polymarket_api_passphrase": os.getenv("POLYMARKET_PASSPHRASE", ""),
        "polymarket_wallet_address": os.getenv("POLYMARKET_FUNDER", ""),
        
        # HTTP
        "http_timeout": int(os.getenv("HTTP_TIMEOUT", "30")),
    }


# ============================================================================
# HTTP Client with Retry Logic
# ============================================================================

class HTTPClient:
    """Robust HTTP client with exponential backoff retry logic."""
    
    def __init__(self, timeout: int = 30, max_retries: int = 3):
        self.timeout = timeout
        self.max_retries = max_retries
        self.session = requests.Session()
    
    def get(self, url: str, headers: Optional[Dict[str, str]] = None, 
            params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Execute GET request with retry logic."""
        for attempt in range(self.max_retries):
            try:
                response = self.session.get(
                    url,
                    headers=headers or {},
                    params=params,
                    timeout=self.timeout
                )
                response.raise_for_status()
                return response.json()
            except requests.exceptions.RequestException as e:
                if attempt == self.max_retries - 1:
                    raise
                wait_time = 2 ** attempt  # Exponential backoff: 1s, 2s, 4s
                print(f"  ⚠ Retry {attempt + 1}/{self.max_retries} after {wait_time}s: {e}")
                time.sleep(wait_time)
        
        raise RuntimeError("Max retries exceeded")
    
    def close(self):
        """Close the HTTP session."""
        self.session.close()


# ============================================================================
# Kalshi API Client
# ============================================================================

class KalshiClient:
    """Client for Kalshi API (public endpoints)."""
    
    BASE_URL = "https://api.elections.kalshi.com/trade-api/v2"
    
    def __init__(self, http_client: HTTPClient):
        self.http = http_client
    
    def list_markets(self, status: str = "open", series_ticker: Optional[str] = None, 
                     max_markets: int = 0, category: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        List all markets with pagination support.
        
        Args:
            status: Market status filter (e.g., "open", "closed")
            series_ticker: Optional series ticker filter
            max_markets: Maximum markets to fetch (0 = unlimited)
            category: Optional category filter
        
        Returns:
            List of market dictionaries
        """
        markets = []
        cursor = None
        page = 1
        
        while True:
            print(f"  Fetching Kalshi markets page {page}...")
            params = {"status": status, "limit": 200, "mve_filter": "exclude"}
            if series_ticker:
                params["series_ticker"] = series_ticker
            if category:
                params["category"] = category
            if cursor:
                params["cursor"] = cursor
            
            data = self.http.get(f"{self.BASE_URL}/markets", params=params)
            
            batch = data.get("markets", [])
            markets.extend(batch)
            
            # Check if we've hit the limit
            if max_markets > 0 and len(markets) >= max_markets:
                markets = markets[:max_markets]
                print(f"  ⚠ Stopped at limit: {max_markets} markets")
                break
            
            cursor = data.get("cursor")
            if not cursor or not batch:
                break
            
            page += 1
        
        print(f"  ✓ Retrieved {len(markets)} Kalshi markets")
        return markets
    
    def get_orderbook(self, ticker: str) -> Dict[str, Any]:
        """
        Fetch orderbook for a specific market ticker.
        
        Args:
            ticker: Market ticker symbol
        
        Returns:
            Orderbook data dictionary
        """
        url = f"{self.BASE_URL}/markets/{ticker}/orderbook"
        return self.http.get(url)


# ============================================================================
# Polymarket API Client
# ============================================================================

class PolymarketClient:
    """Client for Polymarket APIs (Gamma and CLOB)."""
    
    GAMMA_BASE_URL = "https://gamma-api.polymarket.com"
    CLOB_BASE_URL = "https://clob.polymarket.com"
    
    def __init__(self, http_client: HTTPClient, api_key: str = "", 
                 api_secret: str = "", api_passphrase: str = ""):
        self.http = http_client
        self.api_key = api_key
        self.api_secret = api_secret
        self.api_passphrase = api_passphrase
    
    def _get_clob_headers(self) -> Dict[str, str]:
        """Build CLOB headers if credentials are available."""
        headers = {}
        if self.api_key:
            headers["POLY-API-KEY"] = self.api_key
        if self.api_secret:
            headers["POLY-SECRET"] = self.api_secret
        if self.api_passphrase:
            headers["POLY-PASSPHRASE"] = self.api_passphrase
        return headers
    
    def list_markets(self, limit: int = 100, max_markets: int = 0, active_only: bool = True,
                     category: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        List markets from Gamma API with pagination.
        
        Args:
            limit: Maximum results per page
            max_markets: Maximum markets to fetch (0 = unlimited)
            active_only: Only return active (non-closed) markets
            category: Optional category filter
        
        Returns:
            List of market dictionaries
        """
        markets = []
        offset = 0
        page = 1
        
        while True:
            print(f"  Fetching Polymarket markets page {page}...")
            params = {"limit": limit, "offset": offset}
            if active_only:
                params["closed"] = "false"
            if category:
                params["category"] = category
            url = f"{self.GAMMA_BASE_URL}/markets"
            
            data = self.http.get(url, params=params)
            
            # Handle both list and dict responses
            if isinstance(data, list):
                batch = data
            else:
                batch = data.get("markets", data.get("data", []))
            
            if not batch:
                break
            
            markets.extend(batch)
            
            # Check if we've hit the limit
            if max_markets > 0 and len(markets) >= max_markets:
                markets = markets[:max_markets]
                print(f"  ⚠ Stopped at limit: {max_markets} markets")
                break
            
            # Stop if we got fewer results than requested
            if len(batch) < limit:
                break
            
            offset += limit
            page += 1
        
        print(f"  ✓ Retrieved {len(markets)} Polymarket markets")
        return markets
    
    def get_orderbook(self, token_id: str) -> Dict[str, Any]:
        """
        Fetch orderbook for a specific token ID from CLOB API.
        
        Args:
            token_id: Token ID for the market outcome
        
        Returns:
            Orderbook data dictionary
        """
        params = {"token_id": token_id}
        headers = self._get_clob_headers()
        url = f"{self.CLOB_BASE_URL}/book"
        return self.http.get(url, headers=headers, params=params)


# ============================================================================
# Data Processing & Output
# ============================================================================

def create_output_directory(base_dir: str) -> Path:
    """Create timestamped output directory."""
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_UTC")
    output_dir = Path(base_dir) / timestamp
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def save_data(output_dir: Path, filename_base: str, data: List[Dict[str, Any]]):
    """Save data in both JSON and JSONL formats."""
    # Save as pretty-printed JSON
    json_path = output_dir / f"{filename_base}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"  ✓ Saved: {json_path}")
    
    # Save as JSONL (one object per line)
    jsonl_path = output_dir / f"{filename_base}.jsonl"
    with open(jsonl_path, "w", encoding="utf-8") as f:
        for item in data:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    print(f"  ✓ Saved: {jsonl_path}")


def save_manifest(output_dir: Path, manifest: Dict[str, Any]):
    """Save execution manifest."""
    manifest_path = output_dir / "manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    print(f"  ✓ Saved: {manifest_path}")


def get_top_markets_by_volume(markets: List[Dict[str, Any]], n: int, 
                               volume_key: str = "volume") -> List[Dict[str, Any]]:
    """Get top N markets sorted by volume (descending)."""
    sorted_markets = sorted(
        markets,
        key=lambda m: float(m.get(volume_key, 0) or 0),
        reverse=True
    )
    return sorted_markets[:n]


# ============================================================================
# Main Download Logic
# ============================================================================

def download_kalshi_data(client: KalshiClient, args, manifest: Dict[str, Any], 
                         output_dir: Path):
    """Download Kalshi markets and orderbooks."""
    print("\n📊 Downloading Kalshi data...")
    
    # Fetch markets
    markets = client.list_markets(status=args.kalshi_status, series_ticker=args.kalshi_series, 
                                  max_markets=args.max_markets, category=args.kalshi_category)
    
    save_data(output_dir, "kalshi_markets", markets)
    manifest["kalshi"] = {
        "markets_count": len(markets),
        "status_filter": args.kalshi_status,
        "series_filter": args.kalshi_series,
        "category_filter": args.kalshi_category,
    }
    
    # Fetch orderbooks for top N markets by volume
    if args.kalshi_orderbooks and args.kalshi_orderbooks > 0:
        print(f"\n📖 Fetching top {args.kalshi_orderbooks} Kalshi orderbooks...")
        top_markets = get_top_markets_by_volume(markets, args.kalshi_orderbooks, "volume")
        orderbooks = []
        
        for i, market in enumerate(top_markets, 1):
            ticker = market.get("ticker", "")
            if not ticker:
                continue
            
            print(f"  [{i}/{len(top_markets)}] Fetching orderbook for {ticker}...")
            try:
                orderbook = client.get_orderbook(ticker)
                orderbook["_ticker"] = ticker
                orderbook["_market_title"] = market.get("title", "")
                orderbooks.append(orderbook)
            except Exception as e:
                print(f"    ⚠ Failed to fetch orderbook for {ticker}: {e}")
        
        save_data(output_dir, "kalshi_orderbooks_top", orderbooks)
        manifest["kalshi"]["orderbooks_count"] = len(orderbooks)


def download_polymarket_data(client: PolymarketClient, args, manifest: Dict[str, Any], 
                              output_dir: Path):
    """Download Polymarket markets and orderbooks."""
    print("\n📊 Downloading Polymarket data...")
    
    # Fetch markets
    markets = client.list_markets(max_markets=args.max_markets, category=args.poly_category)
    save_data(output_dir, "polymarket_markets", markets)
    manifest["polymarket"] = {
        "markets_count": len(markets),
        "category_filter": args.poly_category,
    }
    
    # Fetch orderbooks for top N markets by volume
    if args.poly_orderbooks and args.poly_orderbooks > 0:
        print(f"\n📖 Fetching top {args.poly_orderbooks} Polymarket orderbooks...")
        
        # Extract markets with valid clobTokenIds
        markets_with_tokens = []
        for market in markets:
            tokens = market.get("clobTokenIds", [])
            if tokens:
                markets_with_tokens.append(market)
        
        top_markets = get_top_markets_by_volume(markets_with_tokens, args.poly_orderbooks, "volume")
        orderbooks = []
        
        for i, market in enumerate(top_markets, 1):
            tokens = market.get("clobTokenIds", [])
            question = market.get("question", "Unknown")
            
            for token_id in tokens[:2]:  # Fetch up to 2 outcomes per market
                print(f"  [{i}/{len(top_markets)}] Fetching orderbook for token {token_id[:8]}...")
                try:
                    orderbook = client.get_orderbook(token_id)
                    orderbook["_token_id"] = token_id
                    orderbook["_market_question"] = question
                    orderbooks.append(orderbook)
                except Exception as e:
                    print(f"    ⚠ Failed to fetch orderbook for {token_id}: {e}")
        
        save_data(output_dir, "polymarket_orderbooks_top", orderbooks)
        manifest["polymarket"]["orderbooks_count"] = len(orderbooks)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Download market data from Kalshi and Polymarket APIs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Download both Kalshi and Polymarket markets
  python scripts/download_markets.py --kalshi --poly

  # Download with orderbooks for top 50 markets
  ENV_FILE=.env python scripts/download_markets.py --kalshi --poly --kalshi-orderbooks 50 --poly-orderbooks 50

  # Kalshi only with series filter
  python scripts/download_markets.py --kalshi --kalshi-series KXPRES --kalshi-orderbooks 20

  # Custom output directory
  python scripts/download_markets.py --kalshi --poly --out my_data_dumps
        """
    )
    
    # Output options
    parser.add_argument("--out", default="market_dumps", 
                       help="Output directory base (default: market_dumps)")
    
    # Kalshi options
    parser.add_argument("--kalshi", action="store_true", 
                       help="Download Kalshi markets")
    parser.add_argument("--kalshi-status", default="open", 
                       help="Kalshi market status filter (default: open)")
    parser.add_argument("--kalshi-series", default=None, 
                       help="Kalshi series ticker filter (optional)")
    parser.add_argument("--kalshi-orderbooks", type=int, default=0, 
                       help="Fetch orderbooks for top N Kalshi markets by volume")
    parser.add_argument("--kalshi-category", default=None,
                       help="Kalshi category filter (e.g., politics, sports, economics)")
    
    # Polymarket options
    parser.add_argument("--poly", action="store_true", 
                       help="Download Polymarket markets")
    parser.add_argument("--poly-orderbooks", type=int, default=0, 
                       help="Fetch orderbooks for top N Polymarket markets by volume")
    parser.add_argument("--poly-category", default=None,
                       help="Polymarket category filter (e.g., politics, sports, crypto, economics)")
    
    # Global limits
    parser.add_argument("--max-markets", type=int, default=0,
                       help="Maximum number of markets to fetch per exchange (0 = unlimited)")
    
    args = parser.parse_args()
    
    # Validate that at least one source is specified
    if not args.kalshi and not args.poly:
        print("❌ Error: Must specify at least one data source (--kalshi or --poly)")
        parser.print_help()
        sys.exit(1)
    
    # Load environment
    load_environment()
    env_config = get_env_config()
    
    # Create output directory
    output_dir = create_output_directory(args.out)
    print(f"\n📁 Output directory: {output_dir}")
    
    # Initialize HTTP client
    http_client = HTTPClient(timeout=env_config["http_timeout"])
    
    # Initialize manifest
    manifest = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "output_directory": str(output_dir),
        "options": {
            "kalshi_enabled": args.kalshi,
            "polymarket_enabled": args.poly,
        }
    }
    
    try:
        # Download Kalshi data
        if args.kalshi:
            kalshi_client = KalshiClient(http_client)
            download_kalshi_data(kalshi_client, args, manifest, output_dir)
        
        # Download Polymarket data
        if args.poly:
            poly_client = PolymarketClient(
                http_client,
                api_key=env_config["polymarket_api_key"],
                api_secret=env_config["polymarket_api_secret"],
                api_passphrase=env_config["polymarket_api_passphrase"]
            )
            download_polymarket_data(poly_client, args, manifest, output_dir)
        
        # Save manifest
        save_manifest(output_dir, manifest)
        
        print(f"\n✅ Download complete! Data saved to: {output_dir}")
        
    except Exception as e:
        print(f"\n❌ Error during download: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    finally:
        http_client.close()


if __name__ == "__main__":
    main()
