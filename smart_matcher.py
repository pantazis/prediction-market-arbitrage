"""
smart_matcher.py

Purpose
-------
A production-grade candidate generator for Arbitrage Bots.
1. Filters Polymarket/Kalshi dumps for binary markets.
2. Uses Vector Embeddings (SBERT) for semantic matching.
3. Enforces strict Date/Time proximity checks (Safety Layer).

Inputs
------
- polymarket_markets.json
- kalshi_markets.json

Outputs
-------
- smart_pairs.json (High-confidence candidates)
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple
from datetime import datetime, timedelta

# New dependencies
import numpy as np
from dateutil import parser
from sentence_transformers import SentenceTransformer, util

# --------------------------
# 1. Cleaning & Filters
# --------------------------

def _parse_date(date_str: str) -> datetime | None:
    """Robust date parsing for mixed formats."""
    if not date_str:
        return None
    try:
        # Returns naive or aware; we standardize to UTC aware below if needed
        dt = parser.parse(str(date_str))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.now().astimezone().tzinfo)
        return dt
    except Exception:
        return None

def _norm_text(s: str) -> str:
    """Normalize text for embedding clarity."""
    if not s:
        return ""
    s = str(s).lower()
    # Remove URL junk
    s = re.sub(r"https?://\S+", " ", s)
    # Standardize common financial terms
    s = s.replace("%", " percent ").replace("$", " usd ")
    s = re.sub(r"[^a-z0-9\s\.\-]", " ", s)
    return " ".join(s.split())

def polymarket_is_valid(m: Dict[str, Any]) -> bool:
    """
    Keep active binary markets. 
    CRITICAL CHANGE: We now ALLOW 'group' markets (e.g. Elections)
    as long as they have valid Yes/No outcomes.
    """
    if m.get("active") is False or m.get("closed") is True:
        return False

    # Ensure binary Yes/No
    outcomes = m.get("outcomes")
    if isinstance(outcomes, str):
        try:
            outcomes = json.loads(outcomes)
        except:
            outcomes = []
    
    if not outcomes or [str(o).lower() for o in outcomes] != ["yes", "no"]:
        return False

    if not m.get("endDate") or not m.get("clobTokenIds"):
        return False

    return True

def kalshi_is_valid(m: Dict[str, Any]) -> bool:
    """Filter for active binary markets, excluding complex derivatives."""
    if str(m.get("status", "")).lower() != "active":
        return False
    if str(m.get("market_type", "")).lower() != "binary":
        return False

    # Exclude complex parlays/combos which are hard to arb
    title = (m.get("title") or "").lower()
    if any(x in title for x in [" combo", " parlay", "same game", "tri-fecta"]):
        return False
    
    return True

# --------------------------
# 2. Canonical Representation
# --------------------------

def get_text_blob(m: Dict, source: str) -> str:
    """Creates a rich semantic string for the embedding model."""
    if source == 'poly':
        # Polymarket often puts the real context in the Group Title
        # e.g. Group: "US Election", Question: "Trump?"
        group = m.get("groupItemTitle", "")
        question = m.get("question", "")
        desc = m.get("description", "")
        return _norm_text(f"{group} {question} {desc}")
    else:
        # Kalshi
        title = m.get("title", "")
        subtitle = m.get("subtitle", "")
        rules = m.get("rules_primary", "")
        return _norm_text(f"{title} {subtitle} {rules}")

# --------------------------
# 3. Matching Engine
# --------------------------

def find_smart_pairs(
    kalshi_list: List[Dict], 
    poly_list: List[Dict], 
    model_name: str = 'all-MiniLM-L6-v2',
    min_similarity: float = 0.60, # Higher threshold for embeddings
    max_hours_diff: int = 24      # Safety: Dates must be close
) -> List[Dict]:
    
    print(f"Loading model {model_name}...")
    model = SentenceTransformer(model_name)

    # Filter & Prep
    k_clean = [m for m in kalshi_list if kalshi_is_valid(m)]
    p_clean = [m for m in poly_list if polymarket_is_valid(m)]
    
    print(f"filtered: {len(k_clean)} Kalshi, {len(p_clean)} Poly")

    # Encode - This might take 10-20s depending on CPU/GPU
    print("Encoding Kalshi markets...")
    k_texts = [get_text_blob(m, 'kalshi') for m in k_clean]
    k_emb = model.encode(k_texts, convert_to_tensor=True, show_progress_bar=True)

    print("Encoding Polymarket markets...")
    p_texts = [get_text_blob(m, 'poly') for m in p_clean]
    p_emb = model.encode(p_texts, convert_to_tensor=True, show_progress_bar=True)

    print("Computing similarity matrix...")
    # cosine_similarity search
    # results is a list of len(k_clean), each containing top_k hits
    hits = util.semantic_search(k_emb, p_emb, top_k=5)

    pairs = []

    print("Filtering candidates by Date & Similarity...")
    for k_idx, hit_list in enumerate(hits):
        k_market = k_clean[k_idx]
        k_date = _parse_date(k_market.get("expiration_time"))

        for hit in hit_list:
            score = hit['score']
            if score < min_similarity:
                continue

            p_idx = hit['corpus_id']
            p_market = p_clean[p_idx]
            p_date = _parse_date(p_market.get("endDate"))

            # --- HARD SAFETY CHECK: DATE ---
            # If dates differ by > X hours, it is likely NOT the same market
            # or creates massive basis risk.
            if k_date and p_date:
                diff = abs((k_date - p_date).total_seconds() / 3600)
                if diff > max_hours_diff:
                    continue # Skip this pair
            else:
                # If dates are missing, skip to be safe
                continue 

            pairs.append({
                "similarity_score": round(float(score), 4),
                "time_diff_hours": round(diff, 2),
                "kalshi": {
                    "ticker": k_market.get("ticker"),
                    "title": k_market.get("title"),
                    "expiry": str(k_date),
                    "yes_price": k_market.get("yes_bid"), # Example fields
                    "no_price": k_market.get("no_bid")
                },
                "polymarket": {
                    "id": p_market.get("id"),
                    "question": p_market.get("question"),
                    "expiry": str(p_date),
                    "tokens": p_market.get("clobTokenIds")
                }
            })

    # Sort best matches first
    pairs.sort(key=lambda x: x['similarity_score'], reverse=True)
    return pairs

# --------------------------
# Main
# --------------------------

def main():
    # 1. Load Data
    try:
        k_data = json.loads(Path("kalshi_markets.json").read_text(encoding='utf-8'))
        p_data = json.loads(Path("polymarket_markets.json").read_text(encoding='utf-8'))
    except FileNotFoundError:
        print("Error: Input JSON files not found.")
        return

    # 2. Run Matcher
    pairs = find_smart_pairs(k_data, p_data)

    # 3. Save
    out_file = "smart_pairs.json"
    Path(out_file).write_text(json.dumps(pairs, indent=2))
    
    print(f"\n✅ Found {len(pairs)} safe candidates.")
    print(f"Saved to {out_file}")
    
    if pairs:
        print("\nTop Match Example:")
        top = pairs[0]
        print(f"Score: {top['similarity_score']} | Time Diff: {top['time_diff_hours']}h")
        print(f"K: {top['kalshi']['title']}")
        print(f"P: {top['polymarket']['question']}")

if __name__ == "__main__":
    main()
