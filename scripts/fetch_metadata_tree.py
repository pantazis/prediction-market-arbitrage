import sys
import os
import json
import requests
sys.path.append(os.path.abspath("src"))
from predarb.config import load_config
from predarb.kalshi_client import KalshiClient
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("MetadataFetcher")

def fetch_metadata():
    cfg = load_config("config_live_paper.yml")
    
    # 1. Polymarket Tags
    print("\n--- POLYMARKET TAGS ---")
    try:
        url = f"{cfg.polymarket.host}/tags"
        print(f"GET {url}...")
        resp = requests.get(url)
        if resp.status_code == 200:
            tags = resp.json()
            # Expecting list of dicts or strings?
            # Gamma API usually returns [{"id":..., "label":...}] or similar
            if isinstance(tags, list):
                print(f"Found {len(tags)} tags.")
                # Print top 20
                for t in tags[:20]:
                    print(t)
            else:
                print(f"Unexpected format: {type(tags)}")
        else:
            print(f"Error {resp.status_code}: {resp.text}")
    except Exception as e:
        print(f"Polymarket Error: {e}")

    # 2. Kalshi Series
    print("\n--- KALSHI SERIES ---")
    try:
        kc = KalshiClient(
            api_key_id=cfg.kalshi.api_key_id,
            private_key_pem=cfg.kalshi.private_key_pem,
            api_host=cfg.kalshi.api_host,
            env=cfg.kalshi.env
        )
        # Try /trade-api/v2/series
        url = "/trade-api/v2/series"
        print(f"GET {url}...")
        data = kc._make_request("GET", url)
        if data and "series" in data:
            series_list = data["series"]
            print(f"Found {len(series_list)} series.")
            for s in series_list[:20]:
                print(f"{s.get('ticker')}: {s.get('title')}")
        else:
            print("No series data found (or endpoint invalid). Trying extraction from markets...")
            # Fallback: fetch markets and extract unique series_ticker
            m_data = kc._make_request("GET", "/trade-api/v2/markets", params={"limit": 100})
            if m_data and "markets" in m_data:
                unique_series = set()
                for m in m_data["markets"]:
                    s = m.get("series_ticker")
                    if s: unique_series.add(s)
                print(f"Extracted {len(unique_series)} unique series from recent markets: {list(unique_series)}")

    except Exception as e:
        print(f"Kalshi Error: {e}")

if __name__ == "__main__":
    fetch_metadata()
