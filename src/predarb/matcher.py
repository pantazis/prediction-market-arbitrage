"""
Matcher logic for arbitrage bot.
Refactored from `smart_matcher.py` to be part of the package.
Includes Vectorization and Tag Filtering.
"""

import json
import re
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime
from dateutil import parser
from sentence_transformers import SentenceTransformer, util

from predarb.models import Market
from predarb.category_mapper import CategoryMapper

logger = logging.getLogger(__name__)

class SmartMatcher:
    def __init__(self, model_name: str = 'all-MiniLM-L6-v2', map_file: str = "data/category_map.csv", rolling_logger=None):
        self.model_name = model_name
        self.model = None # Lazy load
        self.category_mapper = CategoryMapper(map_file, rolling_logger=rolling_logger)
        self.rolling_logger = rolling_logger

    def _load_model(self):
        if self.model is None:
            logger.info(f"Loading embedding model {self.model_name}...")
            if self.rolling_logger:
                self.rolling_logger.info("VECTORIZE", f"Loading SentenceTransformer model: {self.model_name}")
            self.model = SentenceTransformer(self.model_name)
            if self.rolling_logger:
                self.rolling_logger.info("VECTORIZE", f"Model {self.model_name} loaded successfully")

    def _norm_text(self, s: str) -> str:
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

    def _parse_date(self, date_str: Any) -> Optional[datetime]:
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

    def get_text_blob(self, m: Market, source: str) -> str:
        """Creates a rich semantic string for the embedding model."""
        if source == 'polymarket':
            # Polymarket often puts the real context in the Group Title (if available in Market model)
            # Assuming 'market.extra_info' might hold raw json or we rely on standard fields
            # The Market model in src/predarb/models.py needs to be checked.
            # Using standard fields for now.
            text = f"{m.question} {m.description or ''}"
            return self._norm_text(text)
        else:
            # Kalshi
            text = f"{m.title} {m.description or ''}"
            return self._norm_text(text)

    def find_matches(
        self,
        kalshi_markets: List[Market],
        poly_markets: List[Market],
        min_similarity: float = 0.60,
        max_hours_diff: int = 24
    ) -> List[Dict]:
        
        self._load_model()
        
        # 1. Filter by Validity & Tag Compatibility
        # We'll create buckets to speed up matching? 
        # Actually, for SBERT semantic search, we usually search all vs all. 
        # But we can post-filter or pre-filter. 
        # Let's simple pre-filter: Only keeping valid markets first.
        
        logger.info(f"Matching {len(kalshi_markets)} Kalshi vs {len(poly_markets)} Poly markets")
        
        # Prepare Texts
        k_valid = kalshi_markets # Assumed pre-filtered by caller or we trust input
        p_valid = poly_markets
        
        if not k_valid or not p_valid:
            logger.warning("One of the market lists is empty.")
            return []

        k_texts = [self.get_text_blob(m, 'kalshi') for m in k_valid]
        p_texts = [self.get_text_blob(m, 'polymarket') for m in p_valid]

        # Encode
        logger.info("Encoding markets...")
        if self.rolling_logger:
            self.rolling_logger.info("VECTORIZE", f"Encoding {len(k_texts)} Kalshi market descriptions")
        k_emb = self.model.encode(k_texts, convert_to_tensor=True, show_progress_bar=False)
        if self.rolling_logger:
            self.rolling_logger.info("VECTORIZE", f"Encoding {len(p_texts)} Polymarket market descriptions")
        p_emb = self.model.encode(p_texts, convert_to_tensor=True, show_progress_bar=False)
        if self.rolling_logger:
            self.rolling_logger.info("VECTORIZE", "Embeddings created successfully")

        # Semantic Search
        if self.rolling_logger:
            self.rolling_logger.info("MATCH", f"Running semantic search (top_k=5) for {len(k_valid)} x {len(p_valid)} market pairs")
        hits = util.semantic_search(k_emb, p_emb, top_k=5)

        pairs = []
        rejected_low_similarity = 0
        rejected_category = 0
        rejected_date = 0
        
        for k_idx, hit_list in enumerate(hits):
            k_market = k_valid[k_idx]
            k_date = self._parse_date(k_market.end_date) # Market model uses end_date? Check model.

            for hit in hit_list:
                score = hit['score']
                if score < min_similarity:
                    rejected_low_similarity += 1
                    continue

                p_idx = hit['corpus_id']
                p_market = p_valid[p_idx]
                
                # Check Bucket Compatibility
                if not self.category_mapper.are_compatible(k_market, 'kalshi', p_market, 'polymarket'):
                    rejected_category += 1
                    continue
                
                p_date = self._parse_date(p_market.end_date)

                # Date Check
                time_diff = 0
                if k_date and p_date:
                    time_diff = abs((k_date - p_date).total_seconds() / 3600)
                    if time_diff > max_hours_diff:
                        rejected_date += 1
                        continue
                else:
                    # If dates are missing, skip to be safe
                    rejected_date += 1
                    continue

                pairs.append({
                    "similarity_score": round(float(score), 4),
                    "time_diff_hours": round(time_diff, 2),
                    "kalshi_id": k_market.id,
                    "polymarket_id": p_market.id,
                    "kalshi_market": k_market,
                    "polymarket_market": p_market
                })
                
                # Log the individual match score as requested
                if self.rolling_logger:
                    self.rolling_logger.info("MATCH", f"Found Pair: {k_market.id} <-> {p_market.id} | Score: {score:.4f}")
        
        pairs.sort(key=lambda x: x['similarity_score'], reverse=True)
        
        if self.rolling_logger:
            self.rolling_logger.info("MATCH", f"Matching complete: {len(pairs)} pairs accepted")
            self.rolling_logger.info("MATCH", f"Rejected - low similarity: {rejected_low_similarity}, category mismatch: {rejected_category}, date diff: {rejected_date}")
        
        return pairs
