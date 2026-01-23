import sys
import os
sys.path.append(os.path.abspath("src"))
import json
from predarb.kalshi_client import KalshiClient
from predarb.polymarket_client import PolymarketClient
from predarb.config import load_config
import logging

# Setup basic logging
logging.basicConfig(level=logging.INFO)

def inspect():
    # Load config to get credentials/host
    cfg = load_config("config_live_paper.yml")
    
    # 1. Inspect Kalshi
    print("\n--- KALSHI RAW DATA ---")
    try:
        import requests
        kc = KalshiClient(
            api_key_id=cfg.kalshi.api_key_id,
            private_key_pem=cfg.kalshi.private_key_pem,
            api_host=cfg.kalshi.api_host,
            env=cfg.kalshi.env
        )
        # Use internal helper to handle auth and params
        # This returns the JSON dict directly
        data = kc._make_request("GET", "/trade-api/v2/markets", params={"limit": 10})
        
        if data:
            markets = data.get("markets", [])
            if markets:
                m = markets[0]
                print(f"Keys in first Kalshi item: {list(m.keys())}")
                print(f"Ticker: {m.get('ticker')}")
                print(f"Event Ticker: {m.get('event_ticker')}")
                print(f"Series Ticker: {m.get('series_ticker')}")
                print(f"Titles: {m.get('title')} / {m.get('subtitle')}")
                print(f"Category: {m.get('category')}")
                print(json.dumps(m, indent=2))
        else:
            print("Kalshi: No data returned")

    except Exception as e:
        print(f"Kalshi Error: {e}")

    # 2. Inspect Polymarket
    print("\n--- POLYMARKET RAW DATA ---")
    try:
        import requests
        # Config uses 'host' for Gamma API
        url = f"{cfg.polymarket.host}/markets?limit=5"
        print(f"Fetching {url}...")
        resp = requests.get(url)
        if resp.status_code == 200:
            data = resp.json()
            raw_list = data if isinstance(data, list) else data.get("data", [])
            if raw_list:
                item = raw_list[0]
                print(f"Keys in first Polymarket item: {list(item.keys())}")
                print(f"Slug: {item.get('slug')}")
                print(f"Tags: {item.get('tags')}")
                print(f"Category: {item.get('category')}")
                print(f"Parent: {item.get('parent')}")
                print(json.dumps(item, indent=2))
    except Exception as e:
        print(f"Polymarket Error: {e}")

if __name__ == "__main__":
    inspect()
