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
from pathlib import Path
import yaml

from predarb.models import Market

logger = logging.getLogger(__name__)

# Optional semantic similarity imports
try:
    from sentence_transformers import SentenceTransformer, util
    SEMANTIC_AVAILABLE = True
except (ImportError, OSError, Exception):
    SEMANTIC_AVAILABLE = False
    SentenceTransformer = None
    util = None

# Global model cache
_semantic_model: Optional[SentenceTransformer] = None



# Category Mapping: Kalshi Category -> Relevant Polymarket Tags
# Markets will be matched if they map to the same conceptual bucket.
CATEGORY_MAP = {
    "Politics": ["Politics", "US Politics", "Elections", "Government", "White House"],
    "Economics": ["Economics", "Economy", "Fed", "Interest Rates", "Inflation"],
    "Crypto": ["Crypto", "Bitcoin", "Ethereum", "Currencies"],
}

# --------------------------
# 1. Cleaning & Filters
# --------------------------

def _norm_text(s: str) -> str:
    """Normalize text for embedding clarity."""
    if not s:
        return ""
    s = str(s).lower()
    # Keep $ and % as they are semantically important for SBERT
    s = re.sub(r"https?://\S+", " ", s)
    # Allow alphanumeric, spaces, and common currency/pct symbols
    s = re.sub(r"[^a-z0-9\s\.\-\$\%]", " ", s)
    return " ".join(s.split())


def _get_text_blob(market: Market) -> str:
    """Extract rich semantic text from Market object."""
    # Use question + truncated description + metadata
    parts = [market.question or ""]
    
    # Add description if available (truncated to reduce boilerplate noise)
    if hasattr(market, 'description') and market.description:
        desc = str(market.description)
        parts.append(desc[:200])  # First 200 chars usually contain the core rules
    
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
        model_name: str = 'all-mpnet-base-v2',  # Upgraded model
        min_similarity: float = 0.10,
        max_hours_diff: int = 24,
        enabled: bool = True,
        batch_size: int = 50,
        top_k: int = 5,
        encode_batch_size: int = 32,
    ):
        """
        Initialize cross-venue matcher.
        
        Args:
            model_name: Sentence-transformers model name
            min_similarity: Minimum cosine similarity (0.0-1.0)
            max_hours_diff: Maximum hours between expiry dates
            enabled: If False, matcher is disabled (returns empty list)
            batch_size: Number of markets to process per batch (default: 50)
            top_k: Top-k candidates to retrieve per Kalshi market
            encode_batch_size: Batch size for embedding encoding
        """
        self.model_name = model_name
        self.min_similarity = min_similarity
        self.max_hours_diff = max_hours_diff
        self.enabled = enabled
        self.batch_size = batch_size
        self.top_k = top_k
        self.encode_batch_size = encode_batch_size
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
    
    def _get_polymarket_subset(self, k_category: str, poly_markets: List[Market]) -> List[Market]:
        """
        Filter Polymarket candidates by relevance to Kalshi category.
        
        Uses CATEGORY_MAP to match Kalshi category against Polymarket tags.
        If no mapping exists or category is unknown, returns ALL Polymarket markets (safe fallback).
        """
        if not k_category:
            return poly_markets
            
        target_tags = CATEGORY_MAP.get(k_category)
        if not target_tags:
            # Safe fallback: if Kalshi category isn't mapped, search everything
            return poly_markets
            
        subset = []
        target_tags_lower = {t.lower() for t in target_tags}
        for pm in poly_markets:
            # Check if any of the market's tags match our target tags
            p_tags = {str(t).lower() for t in (pm.tags or [])}
            if not p_tags.isdisjoint(target_tags_lower):
                subset.append(pm)
                
        # If filtering removed everything (unlikely but possible), safe fallback? 
        # No, if we have specific tags and found nothing, it means no relevant markets exist.
        return subset

    def precompute_embeddings(self, markets: List[Market]) -> Dict[str, object]:
        """
        Pre-compute embeddings for a list of markets.
        
        Args:
            markets: List of markets to vectorize
            
        Returns:
            Dictionary with 'binary_markets' list and 'embeddings' tensor
        """
        if not self.enabled:
            return {}
            
        model = self._load_model()
        if model is None:
            return {}
            
        # Filter for binary markets
        binary_markets = [m for m in markets if _is_binary_market(m)]
        if not binary_markets:
            return {}
            
        logger.info(f"Pre-computing embeddings for {len(binary_markets)} markets...")
        texts = [_get_text_blob(m) for m in binary_markets]
        
        embeddings = model.encode(
            texts,
            convert_to_tensor=True,
            normalize_embeddings=True,
            show_progress_bar=False,
            batch_size=self.encode_batch_size,
        )
        
        return {
            "markets": binary_markets,
            "embeddings": embeddings
        }

    def find_pairs(
        self,
        kalshi_markets: List[Market],
        poly_markets: List[Market],
        precomputed_poly: Optional[Dict[str, object]] = None
    ) -> List[Tuple[Market, Market, float]]:
        """
        Find semantic matches between Kalshi and Polymarket markets.
        
        Args:
            kalshi_markets: List of Kalshi Market objects
            poly_markets: List of Polymarket Market objects (ignored if precomputed_poly is matched)
            precomputed_poly: Optional dict from precompute_embeddings(poly_markets)
        
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
            
        # Initialize verifier for classification if needed
        # In a real app, this should be passed in via dependency injection, but we'll lazy-init here
        from predarb.llm_verifier import LLMVerifier, LLMVerifierConfig
        
        # We need a config to init verifier. For now, create a default one or load from env?
        # A bit hacky to init here, but efficient for this step.
        # Ideally, CrossVenueMatcher should receive the verifier in __init__.
        # Let's assume we can create one quickly.
        config_path = Path("config_live_paper.yml")
        verifier_config = None
        if config_path.exists():
            import yaml
            with open(config_path) as f:
                cfg = yaml.safe_load(f)
                llm_cfg = cfg.get("llm_verification", {})
                verifier_config = LLMVerifierConfig(**llm_cfg)
        
        if not verifier_config:
            verifier_config = LLMVerifierConfig(enabled=False) # Fallback
            
        verifier = LLMVerifier(verifier_config)

        # Prepare Polymarket data (use cache if available)
        p_subset_all: List[Market] = []
        p_emb_all = None
        
        if precomputed_poly and "markets" in precomputed_poly and "embeddings" in precomputed_poly:
            p_subset_all = precomputed_poly["markets"]  # type: ignore
            p_emb_all = precomputed_poly["embeddings"]
            logger.debug(f"Using pre-computed Polymarket embeddings for {len(p_subset_all)} items")
        else:
            # Fallback to standard flow
            p_subset_all = p_binary
            # We will compute embeddings on demand or all at once?
            # To match original logic, we filter by category then embed.
            # But duplicate embedding is what we want to avoid.
            pass

        # Group Kalshi markets by category to batch process efficiently
        k_by_category: Dict[str, List[Market]] = {}
        total_k = len(k_binary)
        logger.info(f"Categorizing {total_k} Kalshi markets (AI Phase)...")
        
        for idx, m in enumerate(k_binary, 1):
            # Log progress every 10% or every 50 items
            if idx % 50 == 0 or idx == total_k:
                pct = (idx / total_k) * 100
                logger.info(f"Categorizing: {idx}/{total_k} ({pct:.1f}%) complete...")

            cat = str(m.category) if hasattr(m, "category") and m.category else "Uncategorized"
            
            # Smart Categorization: If Uncategorized, ask LLM
            if cat == "Uncategorized" or not cat:
                if verifier.config.enabled:
                    cat = verifier.classify_market(m)
                    # Update the market object so it sticks for this run
                    if hasattr(m, "category"):
                        m.category = cat
                    else:
                        object.__setattr__(m, "category", cat)
            
            if cat not in k_by_category:
                k_by_category[cat] = []
            k_by_category[cat].append(m)
            
        pairs: List[Tuple[Market, Market, float]] = []
        
        try:
            # Process each category
            total_cats = len(k_by_category)
            for cat_idx, (category, k_list) in enumerate(k_by_category.items(), 1):
                # 1. Get relevant Polymarket subset
                p_subset = self._get_polymarket_subset(category, p_binary)
                
                if not p_subset:
                    logger.debug(f"No Polymarket candidates for Kalshi category '{category}'")
                    continue
                    
                logger.info(f"Matching Category '{category}' ({cat_idx}/{total_cats}): {len(k_list)} Kalshi vs {len(p_subset)} Poly")
                
                # 2. Encode Polymarket subset
                if p_emb_all is not None:
                     # Filter embeddings from precomputed tensor
                     # This requires mapping indices, which is complex if we filtered by category.
                     # SIMPLIFICATION: If we use pre-computed, we engage "Global Search" or we still filter?
                     # Better Plan: Even with pre-computed, we can filter using the market objects.
                     # But current CATEGORY_MAP logic filters markets first.
                     
                     # If we have pre-computed ALL Polymarket embeddings, we should rely on their indices.
                     # Let's subset the embeddings based on the category filter.
                     
                     # Get indices of p_subset within p_subset_all
                     # This is slow if O(N^2).
                     # Optimization: For Batch Mode, we assume we want to match against ALL relevant Polymarkets.
                     # Actually, reusing the 'category filter' is good, but requires subsets.
                     
                     # Simple approach for Batch Mode:
                     # If we have precomputed embeddings, skipping the category textual filter might be faster?
                     # No, filtering is 1000x faster than vector search.
                     
                     # Efficient Subsetting:
                     # Create a map of ID -> Index from p_subset_all
                     p_id_to_idx = {m.id: i for i, m in enumerate(p_subset_all)}
                     
                     # Find indices for p_subset (polymarkets matching category)
                     valid_indices = []
                     final_p_subset = []
                     for pm in p_subset:
                         if pm.id in p_id_to_idx:
                             valid_indices.append(p_id_to_idx[pm.id])
                             final_p_subset.append(pm)
                             
                     if not valid_indices:
                         continue
                         
                     # Sub-select embeddings
                     # p_emb is a Tensor
                     import torch
                     p_emb = p_emb_all[valid_indices]
                     p_subset = final_p_subset # Update to ensure alignment
                     
                else:
                    # Fallback: Compute fresh
                    logger.info(f"  Vectorizing {len(p_subset)} Polymarket items...")
                    p_texts = [_get_text_blob(m) for m in p_subset]
                    p_emb = model.encode(
                        p_texts,
                        convert_to_tensor=True,
                        normalize_embeddings=True,
                        show_progress_bar=False,
                        batch_size=self.encode_batch_size,
                    )
                
                # 3. Process Kalshi markets in this category
                logger.info(f"  Vectorizing {len(k_list)} Kalshi items...")
                k_texts = [_get_text_blob(m) for m in k_list]
                k_emb = model.encode(
                    k_texts,
                    convert_to_tensor=True,
                    normalize_embeddings=True,
                    show_progress_bar=False,
                    batch_size=self.encode_batch_size,
                )
                
                # 4. Search
                logger.info("  Computing vector similarities (Semantic Search)...")
                top_k = min(self.top_k, len(p_subset))
                hits = util.semantic_search(k_emb, p_emb, top_k=top_k)
                
                for k_local_idx, hit_list in enumerate(hits):
                    k_market = k_list[k_local_idx]
                    
                    for hit in hit_list:
                        score = hit['score']
                        if score < self.min_similarity:
                            continue
                        
                        p_idx = hit['corpus_id']
                        p_market = p_subset[p_idx]
                        
                        # Date proximity check
                        time_diff = _time_diff_hours(k_market, p_market)
                        if time_diff is None or time_diff > self.max_hours_diff:
                            continue
                        
                        pairs.append((k_market, p_market, float(score)))

            logger.info(f"Batch processing complete. Found {len(pairs)} matches total.")
                
        except Exception as e:
            logger.error(f"Embedding/search failed: {e}")
            return []

        
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
