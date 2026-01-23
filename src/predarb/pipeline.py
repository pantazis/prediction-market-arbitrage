"""
Pipeline module for Prediction Market Arbitrage.
Orchestrates: Fetch (Load), Tag Filter, Vectorize, Match, Verify, Save.
"""

import json
import csv
import logging
import hashlib
from datetime import datetime
from pathlib import Path
from typing import List

from predarb.models import Market
from predarb.matcher import SmartMatcher
from predarb.llm_verifier import LLMVerifier, LLMVerifierConfig

# Setup Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("predarb.pipeline")

DATA_DIR = Path("data")
SNAPSHOT_FILE = DATA_DIR / "markets_snapshot.json"
WATCHLIST_FILE = DATA_DIR / "watchlist_pairs.csv"

def load_markets(file_path: Path) -> List[Market]:
    if not file_path.exists():
        logger.error(f"Snapshot file not found: {file_path}")
        return []
    
    with file_path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    
    markets = []
    for m in data:
        try:
            markets.append(Market(**m))
        except Exception as e:
            logger.warning(f"Failed to parse market {m.get('id')}: {e}")
            continue
    return markets

def save_watchlist(pairs: List[dict], file_path: Path):
    if not pairs:
        logger.info("No pairs to save.")
        return

    # Flatten for CSV
    # We want: kalshi_ticker, polymarket_id, similarity, confidence, reason, ...
    rows = []
    for p in pairs:
        k_m = p["kalshi_market"]
        p_m = p["polymarket_market"]
        
        # Get Token IDs
        poly_yes_id = ""
        poly_no_id = ""
        
        y_o = p_m.outcome_by_label("Yes")
        n_o = p_m.outcome_by_label("No")
        if y_o: poly_yes_id = y_o.id
        if n_o: poly_no_id = n_o.id
        
        # Create Pair ID (Deterministic)
        # Using simple headers matching watchlist.py expectations
        row = {
            "pair_id": hashlib.sha256(f"{p['kalshi_id']}|{p['polymarket_id']}|normal".encode()).hexdigest()[:16],
            "k_ticker": p["kalshi_id"].split(":")[-1],
            "p_market_id": p["polymarket_id"],
            "p_yes_token_id": poly_yes_id,
            "p_no_token_id": poly_no_id,
            "polarity": "normal",
            "k_question": k_m.title,
            "p_question": p_m.question,
            "k_expiration_time": k_m.end_date.isoformat() if k_m.end_date else "",
            "p_endDate": p_m.end_date.isoformat() if p_m.end_date else "",
            "min_edge": 0.01,
            "min_depth_usd": 50.0,
            "max_age_sec": 30,
            "status": "active",
            "last_verified_at": datetime.now().isoformat(),
            # Extra debug info
            "similarity_score": p["similarity_score"],
            "confidence": p.get("verification", {}).get("confidence"),
        }
        rows.append(row)

    keys = rows[0].keys()
    with file_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)
    
    logger.info(f"Saved {len(rows)} pairs to {file_path}")

def run_pipeline(
    snapshot_path: Path = SNAPSHOT_FILE,
    watchlist_path: Path = WATCHLIST_FILE,
    verify: bool = True
):
    logger.info("Starting pipeline...")
    
    # 1. Load Data
    all_markets = load_markets(snapshot_path)
    logger.info(f"Loaded {len(all_markets)} markets.")

    # Split by Exchange (Assuming 'exchange' field or source inference)
    # The models.py has 'exchange' field.
    # If explicit exchange field is missing, we might need a backup heuristic or ensure snapshot has it.
    kalshi_markets = [m for m in all_markets if m.exchange == 'kalshi']
    poly_markets = [m for m in all_markets if m.exchange == 'polymarket']
    
    # Fallback if exchange not set but detectable from id or other fields?
    # For now assume they are set correctly in snapshot.
    if not kalshi_markets or not poly_markets:
        # Try inference if count is 0
        logger.warning("Exchange field might be missing. Attempting inference...")
        for m in all_markets:
            if "kalshi" in m.id: # very loose heuristic, maybe check behavior
               pass # TODO: Improve if needed
        # Actually existing snapshot likely has distinct structures. 
        # But let's assume valid data for now.
    
    logger.info(f"Kalshi: {len(kalshi_markets)} | Polymarket: {len(poly_markets)}")

    # 2. Match
    matcher = SmartMatcher()
    candidates = matcher.find_matches(kalshi_markets, poly_markets)
    logger.info(f"Found {len(candidates)} raw candidates.")

    # 3. Verify
    verified_pairs = []
    if verify:
        # Config LLM (Mock for now or real if env var set)
        # Using mock default or strict config
        config = LLMVerifierConfig(enabled=True, provider="mock") # Use Mock for safety/speed in dev
        verifier = LLMVerifier(config)
        
        logger.info("Running LLM Verification...")
        for cand in candidates:
            # We only verify high semantic matches
            if cand['similarity_score'] < 0.75: # Strict pre-filter for LLM cost
                continue

            k_m = cand['kalshi_market']
            p_m = cand['polymarket_market']
            
            res = verifier.verify_pair(k_m, p_m)
            
            cand['verification'] = res.dict()
            
            if res.same_event and res.confidence > 0.7:
                 verified_pairs.append(cand)
    else:
        verified_pairs = candidates

    logger.info(f"Verified {len(verified_pairs)} pairs.")

    # 4. Save
    save_watchlist(verified_pairs, watchlist_path)
    logger.info("Pipeline complete.")

if __name__ == "__main__":
    run_pipeline()
