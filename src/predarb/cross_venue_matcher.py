"""
Cross-venue semantic matcher for finding arbitrage candidates.

Integrates MatchPipeline for multi-stage filtering with structural + semantic matching.
Automatically pairs Kalshi and Polymarket markets using:
1. Category filtering
2. Asset normalization
3. Threshold matching
4. Date filtering
5. Semantic similarity
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Dict, List, Tuple, Optional
from pathlib import Path

from predarb.models import Market
from predarb.match_pipeline import MatchPipeline, MatchCandidate
from predarb.ticker_parser import TickerParser
from predarb.extractors import ThresholdExtractor
from predarb.asset_normalizer import AssetNormalizer
from predarb.category_inferrer import CategoryInferrer
from predarb.confidence_scorer import ConfidenceScorer
from predarb.duplicate_preventer import DuplicatePreventer

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
    Multi-stage matcher for finding cross-venue arbitrage pairs.
    
    Uses MatchPipeline with 5-stage filtering:
    1. Category filter - check category compatibility
    2. Asset filter - require matching normalized assets
    3. Threshold filter - require thresholds within 0.1%
    4. Date filter - require dates within 2 hours
    5. Semantic similarity - SBERT embeddings
    """
    
    def __init__(
        self,
        model_name: str = 'all-MiniLM-L6-v2',  # Faster model for pipeline
        min_similarity: float = 0.60,
        max_hours_diff: int = 2,  # Stricter default
        enabled: bool = True,
        batch_size: int = 50,
        top_k: int = 5,
        encode_batch_size: int = 32,
    ):
        """
        Initialize cross-venue matcher with MatchPipeline.
        
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
        
        # Initialize new pipeline components
        self.ticker_parser = TickerParser()
        self.threshold_extractor = ThresholdExtractor()
        self.asset_normalizer = AssetNormalizer()
        self.category_inferrer = CategoryInferrer()
        self.confidence_scorer = ConfidenceScorer()
        self.duplicate_preventer = DuplicatePreventer()
        
        # Pipeline will be created lazily with the model
        self._pipeline: Optional[MatchPipeline] = None
        
        # Load Category Map (Bridge Table) - kept for backward compatibility
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
        """Lazy load the sentence transformer model and create pipeline."""
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
        
        # Create pipeline with the loaded model
        if self._pipeline is None:
            self._pipeline = MatchPipeline(
                ticker_parser=self.ticker_parser,
                threshold_extractor=self.threshold_extractor,
                asset_normalizer=self.asset_normalizer,
                category_inferrer=self.category_inferrer,
                embedding_model=_semantic_model,
            )
        
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
        
        Uses the new MatchPipeline with 5-stage filtering:
        1. Category filter
        2. Asset filter (BTC must match BTC)
        3. Threshold filter ($95k must match $95k)
        4. Date filter (expiry within 2 hours)
        5. Semantic similarity
        
        Args:
            kalshi_markets: List of Kalshi Market objects
            poly_markets: List of Polymarket Market objects
            precomputed_poly: Optional dict (ignored, kept for backward compatibility)
        
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
        
        # Load model and create pipeline
        model = self._load_model()
        if model is None or self._pipeline is None:
            return []
        
        # PRE-FILTER: Group markets by extracted asset OR category to reduce search space
        # This is a major optimization - only compare BTC markets with BTC markets, etc.
        k_by_group: Dict[str, List[Market]] = {}
        p_by_group: Dict[str, List[Market]] = {}
        
        for m in k_binary:
            group = self._get_market_group(m)
            if group:
                if group not in k_by_group:
                    k_by_group[group] = []
                k_by_group[group].append(m)
        
        for m in p_binary:
            group = self._get_market_group(m)
            if group:
                if group not in p_by_group:
                    p_by_group[group] = []
                p_by_group[group].append(m)
        
        logger.info(f"Market groups - Kalshi: {list(k_by_group.keys())}, Poly: {list(p_by_group.keys())}")
        
        # Find common groups
        common_groups = set(k_by_group.keys()) & set(p_by_group.keys())
        if not common_groups:
            logger.info("No common groups found between venues")
            return []
        
        logger.info(f"Common groups to match: {common_groups}")
        
        # Run pipeline only on markets with matching groups
        all_candidates: List[MatchCandidate] = []
        
        for group in common_groups:
            k_subset = k_by_group[group]
            p_subset = p_by_group[group]
            
            logger.info(f"Matching group '{group}': {len(k_subset)} Kalshi × {len(p_subset)} Poly")
            
            # Run the multi-stage pipeline on this subset
            candidates = self._pipeline.process(k_subset, p_subset)
            all_candidates.extend(candidates)
            
            # Log rejection summary for this group
            rejection_summary = self._pipeline.get_rejection_summary()
            logger.info(f"  Rejections for {group}: {rejection_summary}")
        
        logger.info(f"Total candidates from all assets: {len(all_candidates)}")
        
        # Deduplicate - ensure one Kalshi per Polymarket
        all_candidates = self.duplicate_preventer.deduplicate(all_candidates)
        logger.info(f"After deduplication: {len(all_candidates)} unique pairs")
        
        # Convert MatchCandidate to tuple format for backward compatibility
        pairs: List[Tuple[Market, Market, float]] = []
        for cand in all_candidates:
            # Use confidence score (combines structural + semantic)
            confidence = self.confidence_scorer.score(cand)
            pairs.append((cand.kalshi_market, cand.polymarket_market, confidence))
        
        # Sort by score desc
        pairs.sort(key=lambda x: x[2], reverse=True)
        
        # Log the matches found
        for k, p, score in pairs:
            logger.info(f"Match: {k.id} <-> {p.id} (confidence={score:.3f})")
        
        return pairs
    
    def _extract_asset(self, market: Market) -> Optional[str]:
        """Extract normalized asset from market for pre-filtering."""
        # Try ticker parsing first (Kalshi)
        ticker = getattr(market, "slug", None) or market.id
        parsed = self.ticker_parser.parse(ticker)
        if parsed and parsed.asset:
            return self.asset_normalizer.normalize(parsed.asset)
        
        # Try text extraction
        text = market.question.lower() if market.question else ""
        
        # Check for known assets
        asset_keywords = {
            'bitcoin': 'bitcoin', 'btc': 'bitcoin',
            'ethereum': 'ethereum', 'eth': 'ethereum', 'ether': 'ethereum',
            'solana': 'solana', 'sol': 'solana',
            'dogecoin': 'dogecoin', 'doge': 'dogecoin',
            'xrp': 'xrp', 'ripple': 'xrp',
            's&p': 'sp500', 's&p 500': 'sp500', 'sp500': 'sp500', 'spx': 'sp500',
        }
        
        for keyword, asset in asset_keywords.items():
            if keyword in text:
                return asset
        
        return None
    
    def _get_market_group(self, market: Market) -> Optional[str]:
        """
        Get the grouping key for a market (asset or category).
        
        For financial markets (crypto, stocks): returns asset name (bitcoin, ethereum, sp500)
        For other markets (politics, sports): returns category name
        """
        # First try to extract asset (for crypto/financial markets)
        asset = self._extract_asset(market)
        if asset:
            return f"asset:{asset}"
        
        # Fall back to category inference (for politics, sports, etc.)
        category = self.category_inferrer.infer_if_needed(market)
        if category and category != "OTHER":
            return f"category:{category}"
        
        # Also check the bucket assignment from category_map.csv
        bucket = self._assign_bucket(market)
        if bucket:
            return f"bucket:{bucket}"
        
        return None
    
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
