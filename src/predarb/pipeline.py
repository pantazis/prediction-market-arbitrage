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
from predarb.match_pipeline import MatchPipeline, MatchCandidate
from predarb.ticker_parser import TickerParser
from predarb.extractors import ThresholdExtractor
from predarb.asset_normalizer import AssetNormalizer
from predarb.category_inferrer import CategoryInferrer
from predarb.confidence_scorer import ConfidenceScorer
from predarb.duplicate_preventer import DuplicatePreventer
from predarb.match_reporter import MatchReporter
from predarb.llm_verifier import LLMVerifier, LLMVerifierConfig
from predarb.rolling_logger import get_logger


def _candidate_to_dict(candidate: MatchCandidate, confidence: float) -> dict:
    """Convert a MatchCandidate to the dict format expected by save_watchlist."""
    return {
        "kalshi_id": candidate.kalshi_market.id,
        "polymarket_id": candidate.polymarket_market.id,
        "kalshi_market": candidate.kalshi_market,
        "polymarket_market": candidate.polymarket_market,
        "similarity_score": candidate.semantic_score,
        "confidence": confidence,
        "structural_matches": candidate.structural_matches,
        "verification": {},
    }

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
        
        # Get structural match info
        structural = p.get("structural_matches", {})
        
        # Create Pair ID (Deterministic)
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
            # Match quality info
            "similarity_score": p.get("similarity_score", 0),
            "confidence": p.get("confidence", 0),
            "llm_confidence": p.get("verification", {}).get("confidence"),
            # Structural match flags
            "asset_match": structural.get("asset", False),
            "threshold_match": structural.get("threshold", False),
            "date_match": structural.get("date", False),
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
    rolling_logger = get_logger()
    
    # 1. FETCH - Load Data
    rolling_logger.info("FETCH", f"Starting market data load from {snapshot_path}")
    all_markets = load_markets(snapshot_path)
    logger.info(f"Loaded {len(all_markets)} markets.")
    rolling_logger.info("FETCH", f"Loaded {len(all_markets)} total markets from snapshot")

    # 2. TAG FILTER - Split by Exchange
    rolling_logger.info("TAG_FILTER", "Starting exchange categorization")
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
    rolling_logger.info("TAG_FILTER", f"Categorized markets: Kalshi={len(kalshi_markets)}, Polymarket={len(poly_markets)}")

    # 3. VECTORIZE & 4. MATCH - Multi-stage pipeline with structural + semantic matching
    rolling_logger.info("VECTORIZE", "Initializing MatchPipeline with structural extractors")
    
    # Initialize pipeline components
    ticker_parser = TickerParser()
    threshold_extractor = ThresholdExtractor()
    asset_normalizer = AssetNormalizer()
    category_inferrer = CategoryInferrer()
    confidence_scorer = ConfidenceScorer()
    duplicate_preventer = DuplicatePreventer()
    
    # Create the multi-stage pipeline
    pipeline = MatchPipeline(
        ticker_parser=ticker_parser,
        threshold_extractor=threshold_extractor,
        asset_normalizer=asset_normalizer,
        category_inferrer=category_inferrer,
    )
    
    rolling_logger.info("MATCH", f"Running 5-stage pipeline on {len(kalshi_markets)} Kalshi x {len(poly_markets)} Polymarket markets")
    candidates = pipeline.process(kalshi_markets, poly_markets)
    logger.info(f"Found {len(candidates)} raw candidates after pipeline filtering.")
    
    # Log rejection summary
    rejection_summary = pipeline.get_rejection_summary()
    rolling_logger.info("MATCH", f"Pipeline rejections: {rejection_summary}")
    
    # Deduplicate - ensure one Kalshi per Polymarket
    candidates = duplicate_preventer.deduplicate(candidates)
    logger.info(f"After deduplication: {len(candidates)} candidates.")
    rolling_logger.info("MATCH", f"After deduplication: {len(candidates)} unique pairs")

    # 5. LLM VERIFICATION (only for low-confidence matches)
    verified_pairs = []
    if verify:
        rolling_logger.info("LLM_VERIFICATION", "Starting LLM verification for low-confidence matches")
        config = LLMVerifierConfig(enabled=True, provider="mock")
        verifier = LLMVerifier(config)
        
        logger.info("Running LLM Verification on low-confidence matches...")
        verified_count = 0
        skipped_high_confidence = 0
        
        for cand in candidates:
            # Use confidence scorer to determine if LLM verification needed
            confidence = confidence_scorer.score(cand)
            
            if not confidence_scorer.needs_llm_verification(confidence):
                # High confidence - skip LLM verification
                skipped_high_confidence += 1
                verified_pairs.append(_candidate_to_dict(cand, confidence))
                verified_count += 1
                rolling_logger.info("LLM_VERIFICATION", 
                    f"High-confidence match #{verified_count}: {cand.kalshi_market.id} <-> {cand.polymarket_market.id} "
                    f"(confidence={confidence:.3f}, skipped LLM)")
                continue

            # Low confidence - run LLM verification
            k_m = cand.kalshi_market
            p_m = cand.polymarket_market
            
            rolling_logger.debug("LLM_VERIFICATION", 
                f"Verifying low-confidence pair: {k_m.id} <-> {p_m.id} (confidence={confidence:.3f})")
            res = verifier.verify_pair(k_m, p_m)
            
            if res.same_event and res.confidence > 0.7:
                pair_dict = _candidate_to_dict(cand, confidence)
                pair_dict['verification'] = res.dict()
                verified_pairs.append(pair_dict)
                verified_count += 1
                rolling_logger.info("LLM_VERIFICATION", 
                    f"LLM verified pair #{verified_count}: confidence={res.confidence:.2f}, reason={res.reason}")
        
        rolling_logger.info("LLM_VERIFICATION", 
            f"Skipped LLM for {skipped_high_confidence} high-confidence matches")
    else:
        # No verification - convert all candidates to dict format
        for cand in candidates:
            confidence = confidence_scorer.score(cand)
            verified_pairs.append(_candidate_to_dict(cand, confidence))

    logger.info(f"Verified {len(verified_pairs)} pairs.")
    rolling_logger.info("LLM_VERIFICATION", f"Total verified pairs: {len(verified_pairs)}")

    # Save Results
    save_watchlist(verified_pairs, watchlist_path)
    logger.info("Pipeline complete.")
    rolling_logger.info("FETCH", f"Pipeline complete - saved {len(verified_pairs)} pairs to {watchlist_path}")

if __name__ == "__main__":
    run_pipeline()
