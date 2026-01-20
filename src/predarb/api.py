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

if __name__ == "__main__":
    import uvicorn
    # Allow running directly for testing
    uvicorn.run(app, host="0.0.0.0", port=8000)
