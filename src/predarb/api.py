from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from pathlib import Path
from typing import List, Dict, Optional
import csv
import json
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Prediction Market Arbitrage API",
    description="API to serve arbitrage watchlist and market data.",
    version="1.0.0"
)

# Paths
DATA_DIR = Path("data")
WATCHLIST_PATH = DATA_DIR / "watchlist_pairs.csv"
SNAPSHOT_PATH = DATA_DIR / "markets_snapshot.json"

@app.get("/health")
async def health_check():
    return {"status": "ok"}

@app.get("/watchlist")
async def get_watchlist():
    """Returns the parsed content of data/watchlist_pairs.csv."""
    if not WATCHLIST_PATH.exists():
        return JSONResponse(content=[], status_code=200)
    
    try:
        watchlist = []
        with WATCHLIST_PATH.open("r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                watchlist.append(row)
        return watchlist
    except Exception as e:
        logger.error(f"Failed to read watchlist: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/watchlist/csv")
async def get_watchlist_csv():
    """Returns the raw data/watchlist_pairs.csv file."""
    if not WATCHLIST_PATH.exists():
        raise HTTPException(status_code=404, detail="Watchlist CSV not found")
    return FileResponse(WATCHLIST_PATH, media_type='text/csv', filename="watchlist_pairs.csv")

@app.get("/markets/snapshot")
async def get_markets_snapshot():
    """Returns the data/markets_snapshot.json file."""
    if not SNAPSHOT_PATH.exists():
        raise HTTPException(status_code=404, detail="Markets snapshot not found")
    
    try:
        with SNAPSHOT_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return data
    except Exception as e:
        logger.error(f"Failed to read snapshot: {e}")
        raise HTTPException(status_code=500, detail=str(e))

from predarb.config import load_config
from predarb.kalshi_client import KalshiClient
from predarb.polymarket_client import PolymarketClient

# Init Clients
try:
    config = load_config("config.yml")
    kalshi_client = KalshiClient() # Uses env vars
    poly_client = PolymarketClient(config.polymarket)
    logger.info("Clients initialized.")
except Exception as e:
    logger.error(f"Failed to init clients: {e}")
    kalshi_client = None
    poly_client = None

@app.get("/check_orderbook")
async def check_orderbook(kalshi_id: str, poly_yes_id: str):
    """
    Fetch live orderbooks for a pair.
    kalshi_id: Ticker (e.g. KHARRIS-24NOV05)
    poly_yes_id: Token ID for YES outcome (Condition ID or Token ID depending on client)
    """
    if not kalshi_client or not poly_client:
        raise HTTPException(status_code=503, detail="Market clients not initialized")
    
    try:
        # Fetch Kalshi
        k_ob = kalshi_client.fetch_orderbook(kalshi_id)
        
        # Fetch Poly
        p_ob = poly_client.fetch_orderbook(poly_yes_id)
        
        # Calculate Spread (Naive)
        # Kalshi OB structure? Check fetch_orderbook return.
        # Polymarket OB structure? Check fetch_orderbook return.
        
        return {
            "kalshi": k_ob,
            "polymarket": p_ob,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Check failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/watchlist/live")
async def watchlist_live(limit: int = 5):
    """
    Return watchlist with LIVE prices for top N items.
    """
    rows = await get_watchlist()
    if not rows:
        return []
    
    results = []
    count = 0
    for row in rows:
        if count >= limit:
            break
        
        k_id = row.get("kalshi_id")
        p_token = row.get("poly_yes_id")
        
        if k_id and p_token:
            try:
                live_data = await check_orderbook(k_id, p_token)
                row["live"] = live_data
            except:
                row["live"] = {"error": "failed"}
        
        results.append(row)
        count += 1
        
    return results

if __name__ == "__main__":
    import uvicorn
    # Allow running directly for testing
    uvicorn.run(app, host="0.0.0.0", port=8000)
