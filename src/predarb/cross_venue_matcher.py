"""
Cross-venue semantic matcher for finding arbitrage candidates.

Integrates smart_matcher.py logic into the engine lifecycle.
Automatically pairs Kalshi and Polymarket markets using semantic similarity.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Dict, List, Tuple, Optional

from predarb.models import Market

logger = logging.getLogger(__name__)

# Optional semantic similarity imports
try:
    from sentence_transformers import SentenceTransformer, util
    import numpy as np
    SEMANTIC_AVAILABLE = True
except (ImportError, OSError, Exception):
    SEMANTIC_AVAILABLE = False
    SentenceTransformer = None
    util = None
    np = None

# Global model cache
_semantic_model: Optional[SentenceTransformer] = None


def _norm_text(s: str) -> str:
    """Normalize text for embedding clarity."""
    if not s:
        return ""
    s = str(s).lower()
    s = re.sub(r"https?://\S+", " ", s)
    s = s.replace("%", " percent ").replace("$", " usd ")
    s = re.sub(r"[^a-z0-9\s\.\-]", " ", s)
    return " ".join(s.split())


def _get_text_blob(market: Market) -> str:
    """Extract rich semantic text from Market object."""
    # Use question + description + metadata
    parts = [market.question or ""]
    
    # Add description if available
    if hasattr(market, 'description') and market.description:
        parts.append(str(market.description))
    
    # Add group/category context
    if hasattr(market, 'category') and market.category:
        parts.append(str(market.category))
    
    # Normalize and combine
    return _norm_text(" ".join(parts))


def _is_binary_market(market: Market) -> bool:
    """Check if market is binary (Yes/No)."""
    if not market.outcomes or len(market.outcomes) != 2:
        return False
    
    # Check if outcomes are Yes/No variations
    labels = [str(o.label).lower() if hasattr(o, 'label') else str(o).lower() 
              for o in market.outcomes]
    return sorted(labels) == ['no', 'yes']


def _time_diff_hours(m1: Market, m2: Market) -> Optional[float]:
    """Calculate time difference in hours between market expiries."""
    if not m1.end_date or not m2.end_date:
        return None
    
    try:
        dt1 = m1.end_date
        dt2 = m2.end_date
        
        # Handle timezone-aware/naive datetimes
        if dt1.tzinfo and not dt2.tzinfo:
            dt2 = dt2.replace(tzinfo=dt1.tzinfo)
        elif dt2.tzinfo and not dt1.tzinfo:
            dt1 = dt1.replace(tzinfo=dt2.tzinfo)
        
        diff_seconds = abs((dt1 - dt2).total_seconds())
        return diff_seconds / 3600.0
    except Exception as e:
        logger.warning(f"Failed to compute time diff: {e}")
        return None


class CrossVenueMatcher:
    """
    Semantic matcher for finding cross-venue arbitrage pairs.
    
    Uses Sentence-BERT embeddings to match markets across Kalshi and Polymarket.
    """
    
    def __init__(
        self,
        model_name: str = 'all-MiniLM-L6-v2',
        min_similarity: float = 0.60,
        max_hours_diff: int = 24,
        enabled: bool = True
    ):
        """
        Initialize cross-venue matcher.
        
        Args:
            model_name: Sentence-transformers model name
            min_similarity: Minimum cosine similarity (0.0-1.0)
            max_hours_diff: Maximum hours between expiry dates
            enabled: If False, matcher is disabled (returns empty list)
        """
        self.model_name = model_name
        self.min_similarity = min_similarity
        self.max_hours_diff = max_hours_diff
        self.enabled = enabled
        self._model: Optional[SentenceTransformer] = None
        
        if not SEMANTIC_AVAILABLE and enabled:
            logger.warning(
                "sentence-transformers not available. "
                "Cross-venue matching disabled. "
                "Install: pip install sentence-transformers"
            )
            self.enabled = False
    
    def _load_model(self):
        """Lazy load the sentence transformer model."""
        global _semantic_model
        
        if not SEMANTIC_AVAILABLE:
            return None
        
        if _semantic_model is None:
            logger.info(f"Loading semantic model: {self.model_name}")
            try:
                _semantic_model = SentenceTransformer(self.model_name)
                logger.info("Model loaded successfully")
            except Exception as e:
                logger.error(f"Failed to load model: {e}")
                self.enabled = False
                return None
        
        return _semantic_model
    
    def find_pairs(
        self,
        kalshi_markets: List[Market],
        poly_markets: List[Market]
    ) -> List[Tuple[Market, Market, float]]:
        """
        Find semantic matches between Kalshi and Polymarket markets.
        
        Args:
            kalshi_markets: List of Kalshi Market objects
            poly_markets: List of Polymarket Market objects
        
        Returns:
            List of (kalshi_market, poly_market, similarity_score) tuples
            sorted by similarity descending
        """
        if not self.enabled:
            logger.debug("Cross-venue matcher disabled")
            return []
        
        # Filter for binary markets only
        k_binary = [m for m in kalshi_markets if _is_binary_market(m)]
        p_binary = [m for m in poly_markets if _is_binary_market(m)]
        
        if not k_binary or not p_binary:
            logger.info(
                f"Insufficient binary markets: "
                f"Kalshi={len(k_binary)}, Poly={len(p_binary)}"
            )
            return []
        
        logger.info(
            f"Cross-venue matching: {len(k_binary)} Kalshi × {len(p_binary)} Poly"
        )
        
        # Load model
        model = self._load_model()
        if model is None:
            return []
        
        # Extract text representations
        k_texts = [_get_text_blob(m) for m in k_binary]
        p_texts = [_get_text_blob(m) for m in p_binary]
        
        # Encode to embeddings
        try:
            logger.debug("Encoding Kalshi markets...")
            k_emb = model.encode(k_texts, convert_to_tensor=True, show_progress_bar=False)
            
            logger.debug("Encoding Polymarket markets...")
            p_emb = model.encode(p_texts, convert_to_tensor=True, show_progress_bar=False)
            
            logger.debug("Computing similarity matrix...")
            hits = util.semantic_search(k_emb, p_emb, top_k=5)
        except Exception as e:
            logger.error(f"Embedding/search failed: {e}")
            return []
        
        # Filter by similarity and date proximity
        pairs: List[Tuple[Market, Market, float]] = []
        
        for k_idx, hit_list in enumerate(hits):
            k_market = k_binary[k_idx]
            
            for hit in hit_list:
                score = hit['score']
                if score < self.min_similarity:
                    continue
                
                p_idx = hit['corpus_id']
                p_market = p_binary[p_idx]
                
                # Date proximity check
                time_diff = _time_diff_hours(k_market, p_market)
                if time_diff is None or time_diff > self.max_hours_diff:
                    continue
                
                pairs.append((k_market, p_market, float(score)))
        
        # Sort by similarity descending
        pairs.sort(key=lambda x: x[2], reverse=True)
        
        logger.info(f"Found {len(pairs)} cross-venue pairs (min_sim={self.min_similarity})")
        
        return pairs
    
    def get_paired_markets(
        self,
        kalshi_markets: List[Market],
        poly_markets: List[Market]
    ) -> List[Market]:
        """
        Get all markets involved in cross-venue pairs.
        
        This is a convenience method that returns a flat list of markets
        that have at least one cross-venue match.
        
        Args:
            kalshi_markets: List of Kalshi markets
            poly_markets: List of Polymarket markets
        
        Returns:
            Deduplicated list of all markets in pairs
        """
        pairs = self.find_pairs(kalshi_markets, poly_markets)
        
        seen_ids = set()
        paired_markets = []
        
        for k_market, p_market, score in pairs:
            if k_market.id not in seen_ids:
                paired_markets.append(k_market)
                seen_ids.add(k_market.id)
            if p_market.id not in seen_ids:
                paired_markets.append(p_market)
                seen_ids.add(p_market.id)
        
        return paired_markets
