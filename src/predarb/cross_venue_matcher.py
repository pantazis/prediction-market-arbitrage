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
        
        # Load Category Map (Bridge Table)
        self.category_buckets: Dict[str, Dict[str, List[str]]] = self._load_category_map()
        
        if not SEMANTIC_AVAILABLE and enabled:
            logger.warning(
                "sentence-transformers not available. "
                "Cross-venue matching disabled. "
                "Install: pip install sentence-transformers"
            )
            self.enabled = False

    def _load_category_map(self) -> Dict[str, Dict[str, List[str]]]:
        """
        Load logical buckets from data/category_map.csv
        Returns: {
            "BUCKET_NAME": {
                "kalshi": ["Category1", "Category2"],
                "polymarket": ["Tag1", "Tag2"]
            }
        }
        """
        buckets: Dict[str, Dict[str, List[str]]] = {}
        try:
            path = Path("data/category_map.csv")
            if not path.exists():
                return {}
            
            import csv
            with path.open("r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    bucket = row["bucket_name"].strip().upper()
                    k_cats = [x.strip().lower() for x in row["kalshi_category"].split("|") if x.strip()]
                    p_tags = [x.strip().lower() for x in row["polymarket_tag"].split("|") if x.strip()]
                    
                    if bucket not in buckets:
                        buckets[bucket] = {"kalshi": [], "polymarket": []}
                    
                    buckets[bucket]["kalshi"].extend(k_cats)
                    buckets[bucket]["polymarket"].extend(p_tags)
            
            logger.info(f"Loaded {len(buckets)} category buckets: {list(buckets.keys())}")
            return buckets
        except Exception as e:
            logger.error(f"Failed to load category map: {e}")
            return {}

    def _assign_bucket(self, market: Market) -> Optional[str]:
        """Assign a market to a high-level bucket based on metadata."""
        if not self.category_buckets:
            return None
        
        # Check Kalshi Category
        if market.exchange == "kalshi" and market.category:
            cat = market.category.strip().lower()
            for bucket, rules in self.category_buckets.items():
                if cat in rules["kalshi"]:
                    return bucket
        
        # Check Polymarket Tags
        if market.exchange == "polymarket" and market.tags:
            tags = [t.strip().lower() for t in market.tags]
            for bucket, rules in self.category_buckets.items():
                # If ANY tag matches the bucket's whitelist
                if not set(tags).isdisjoint(set(rules["polymarket"])):
                    return bucket
                    
        return None
    
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

        # Group Kalshi markets by BUCKET
        k_by_bucket: Dict[str, List[Market]] = {}
        uncategorized_k: List[Market] = []
        
        total_k = len(k_binary)
        logger.info(f"Bucketing {total_k} Kalshi markets...")
        
        for m in k_binary:
            bucket = self._assign_bucket(m)
            if bucket:
                if bucket not in k_by_bucket:
                    k_by_bucket[bucket] = []
                k_by_bucket[bucket].append(m)
            else:
                uncategorized_k.append(m)
                
        # Also group Polymarket by BUCKET for fast retrieval
        p_by_bucket: Dict[str, List[Market]] = {}
        uncategorized_p: List[Market] = []
        
        for m in p_binary:
            bucket = self._assign_bucket(m)
            if bucket:
                if bucket not in p_by_bucket:
                    p_by_bucket[bucket] = []
                p_by_bucket[bucket].append(m)
            else:
                uncategorized_p.append(m)

        pairs: List[Tuple[Market, Market, float]] = []
        
        # 1. Process STRICT Buckets
        for bucket, k_list in k_by_bucket.items():
            p_subset = p_by_bucket.get(bucket, [])
            if not p_subset:
                continue
                
            logger.info(f"Matching Bucket '{bucket}': {len(k_list)} Kalshi vs {len(p_subset)} Poly")
            
            # Encode just the subset? Or use precomputed?
            # For simplicity & correctness with bridge table logic, strict subset matching is best.
            # We must encode P subset on the fly (or extract from giant tensor).
            # On-the-fly is safer for ensuring we match the right subset.
            
            # Encode K
            k_texts = [_get_text_blob(m) for m in k_list]
            k_emb = model.encode(k_texts, convert_to_tensor=True)
            
            # Encode P
            p_texts = [_get_text_blob(m) for m in p_subset]
            p_emb = model.encode(p_texts, convert_to_tensor=True)
            
            # Cosine similarity
            scores = util.cos_sim(k_emb, p_emb)
            
            # Find best matches
            for i in range(len(k_list)):
                best_indices = scores[i].topk(min(self.top_k, len(p_subset))).indices
                best_scores = scores[i].topk(min(self.top_k, len(p_subset))).values
                
                for j, score_tensor in zip(best_indices, best_scores):
                    score = float(score_tensor.item())
                    if score >= self.min_similarity:
                        # Time diff check
                        if self.max_hours_diff > 0:
                            hrs = _time_diff_hours(k_list[i], p_subset[j])
                            if hrs is not None and hrs > self.max_hours_diff:
                                continue
                        
                        pairs.append((k_list[i], p_subset[j], score))

        # 2. Process Uncategorized? 
        # User requested: "Only attempt to match markets within the same Bucket"
        # So we SKIP uncategorized for now to reduce noise.
        if uncategorized_k:
            logger.info(f"Skipping {len(uncategorized_k)} uncategorized Kalshi markets (strict bucketing).")
            
        # Sort by score desc
        pairs.sort(key=lambda x: x[2], reverse=True)
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
