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
from predarb.normalize import tokenize
from predarb.tagging import ensure_market_tags, normalized_tag_set

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

try:
    import faiss
    FAISS_AVAILABLE = True
except (ImportError, OSError, Exception):
    FAISS_AVAILABLE = False
    faiss = None

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

    for attr in (
        "slug",
        "group_item_title",
        "group_title",
        "series_title",
        "series_slug",
        "ticker",
        "event_ticker",
        "subtitle",
    ):
        if hasattr(market, attr):
            value = getattr(market, attr)
            if value:
                parts.append(str(value))

    if market.tags:
        parts.append(" ".join(str(t) for t in market.tags))
    
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


def _normalize_vectors(vectors):
    if np is None:
        return vectors
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return vectors / norms
    
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
        enabled: bool = True,
        batch_size: int = 50,
        tagger_enabled: bool = True,
        require_tag_overlap: bool = False,
        min_shared_tags: int = 1,
        cluster_by_tags: bool = False,
        cluster_tag_prefixes: Optional[List[str]] = None,
        keyword_index_enabled: bool = False,
        min_keyword_overlap: int = 1,
        max_keyword_candidates: int = 200,
        use_faiss: bool = False,
        faiss_top_k: int = 5,
    ):
        """
        Initialize cross-venue matcher.
        
        Args:
            model_name: Sentence-transformers model name
            min_similarity: Minimum cosine similarity (0.0-1.0)
            max_hours_diff: Maximum hours between expiry dates
            enabled: If False, matcher is disabled (returns empty list)
            batch_size: Number of markets to process per batch (default: 50)
        """
        self.model_name = model_name
        self.min_similarity = min_similarity
        self.max_hours_diff = max_hours_diff
        self.enabled = enabled
        self.batch_size = batch_size
        self.tagger_enabled = tagger_enabled
        self.require_tag_overlap = require_tag_overlap
        self.min_shared_tags = min_shared_tags
        self.cluster_by_tags = cluster_by_tags
        self.cluster_tag_prefixes = cluster_tag_prefixes or ["topic", "time"]
        self.keyword_index_enabled = keyword_index_enabled
        self.min_keyword_overlap = min_keyword_overlap
        self.max_keyword_candidates = max_keyword_candidates
        self.use_faiss = use_faiss
        self.faiss_top_k = faiss_top_k
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
    
    def _bucket_key(self, market: Market) -> str:
        tags = normalized_tag_set(market.tags or [])
        parts: List[str] = []
        for prefix in self.cluster_tag_prefixes:
            label = f"{prefix}:none"
            for tag in tags:
                if tag.startswith(f"{prefix}:"):
                    label = tag
                    break
            parts.append(label)
        return "|".join(parts)

    def _ensure_tags(self, markets: List[Market]) -> None:
        if not self.tagger_enabled:
            return
        for market in markets:
            ensure_market_tags(market)

    def _has_tag_overlap(self, a: Market, b: Market) -> bool:
        if not self.require_tag_overlap:
            return True
        tags_a = normalized_tag_set(a.tags or [])
        tags_b = normalized_tag_set(b.tags or [])
        generic = {"type:binary", "type:multi"}
        tags_a = {t for t in tags_a if t not in generic}
        tags_b = {t for t in tags_b if t not in generic}
        entity_a = {t for t in tags_a if t.startswith("entity:") or t.startswith("name:")}
        entity_b = {t for t in tags_b if t.startswith("entity:") or t.startswith("name:")}
        if entity_a or entity_b:
            return bool(entity_a.intersection(entity_b))
        if not tags_a or not tags_b:
            return False
        return len(tags_a.intersection(tags_b)) >= self.min_shared_tags

    def _keyword_tokens(self, market: Market) -> List[str]:
        parts = [market.question or ""]
        if market.description:
            parts.append(str(market.description))
        if hasattr(market, "category") and market.category:
            parts.append(str(market.category))
        for attr in (
            "slug",
            "group_item_title",
            "group_title",
            "series_title",
            "series_slug",
            "ticker",
            "event_ticker",
            "subtitle",
        ):
            if hasattr(market, attr):
                value = getattr(market, attr)
                if value:
                    parts.append(str(value))
        if market.tags:
            parts.append(" ".join(str(t) for t in market.tags))
        text = " ".join(parts)
        tokens = tokenize(text)
        return list(dict.fromkeys(tokens))

    def _build_keyword_index(
        self, markets: List[Market]
    ) -> Tuple[Dict[str, List[int]], List[List[str]]]:
        index: Dict[str, List[int]] = {}
        all_tokens: List[List[str]] = []
        for idx, market in enumerate(markets):
            tokens = self._keyword_tokens(market)
            all_tokens.append(tokens)
            for token in tokens:
                index.setdefault(token, []).append(idx)
        return index, all_tokens

    def _candidate_ids(
        self,
        tokens: List[str],
        index: Dict[str, List[int]],
    ) -> List[int]:
        if not tokens:
            return []
        counts: Dict[int, int] = {}
        for token in tokens:
            for idx in index.get(token, []):
                counts[idx] = counts.get(idx, 0) + 1
        if not counts:
            return []
        min_overlap = max(1, self.min_keyword_overlap)
        candidates = [idx for idx, c in counts.items() if c >= min_overlap]
        if not candidates:
            return []
        if self.max_keyword_candidates and len(candidates) > self.max_keyword_candidates:
            candidates.sort(key=lambda i: counts[i], reverse=True)
            candidates = candidates[: self.max_keyword_candidates]
        return candidates

    def _find_pairs_between(
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
        
        # Process in batches to avoid memory issues
        pairs: List[Tuple[Market, Market, float]] = []
        
        try:
            use_faiss = bool(self.use_faiss and FAISS_AVAILABLE and not self.keyword_index_enabled)
            if self.use_faiss and not FAISS_AVAILABLE:
                logger.warning("FAISS not available; falling back to default search.")

            # Encode Polymarket markets once (corpus)
            logger.info(f"Encoding {len(p_binary)} Polymarket markets...")
            if use_faiss:
                p_emb = model.encode(p_texts, convert_to_numpy=True, show_progress_bar=False, batch_size=32)
                p_emb = _normalize_vectors(p_emb.astype("float32"))
                index = faiss.IndexFlatIP(p_emb.shape[1])
                index.add(p_emb)
            else:
                p_emb = model.encode(p_texts, convert_to_tensor=True, show_progress_bar=False, batch_size=32)

            keyword_index: Dict[str, List[int]] = {}
            if self.keyword_index_enabled:
                keyword_index, _ = self._build_keyword_index(p_binary)
            
            # Process Kalshi markets in batches
            total_batches = (len(k_binary) + self.batch_size - 1) // self.batch_size
            logger.info(f"Processing {len(k_binary)} Kalshi markets in {total_batches} batches of {self.batch_size}...")
            
            for batch_idx in range(0, len(k_binary), self.batch_size):
                batch_end = min(batch_idx + self.batch_size, len(k_binary))
                batch_markets = k_binary[batch_idx:batch_end]
                batch_texts = k_texts[batch_idx:batch_end]
                
                logger.info(f"Batch {batch_idx // self.batch_size + 1}/{total_batches}: Processing markets {batch_idx+1}-{batch_end}...")
                
                # Encode batch
                if use_faiss:
                    k_batch_emb = model.encode(batch_texts, convert_to_numpy=True, show_progress_bar=False, batch_size=32)
                    k_batch_emb = _normalize_vectors(k_batch_emb.astype("float32"))
                else:
                    k_batch_emb = model.encode(batch_texts, convert_to_tensor=True, show_progress_bar=False, batch_size=32)
                
                if use_faiss:
                    top_k = max(1, self.faiss_top_k)
                    scores, ids = index.search(k_batch_emb, top_k)
                    for k_local_idx, k_market in enumerate(batch_markets):
                        for score, p_idx in zip(scores[k_local_idx], ids[k_local_idx]):
                            if p_idx < 0 or score < self.min_similarity:
                                continue
                            p_market = p_binary[int(p_idx)]
                            time_diff = _time_diff_hours(k_market, p_market)
                            if time_diff is None or time_diff > self.max_hours_diff:
                                continue
                            if not self._has_tag_overlap(k_market, p_market):
                                continue
                            pairs.append((k_market, p_market, float(score)))
                elif self.keyword_index_enabled:
                    for k_local_idx, k_market in enumerate(batch_markets):
                        k_tokens = self._keyword_tokens(k_market)
                        candidate_ids = self._candidate_ids(k_tokens, keyword_index)
                        if not candidate_ids:
                            continue
                        sims = util.cos_sim(k_batch_emb[k_local_idx], p_emb[candidate_ids])[0]
                        top_k = min(5, sims.shape[0])
                        scores, indices = sims.topk(top_k)
                        for score, local_idx in zip(scores.tolist(), indices.tolist()):
                            if score < self.min_similarity:
                                continue
                            p_idx = candidate_ids[local_idx]
                            p_market = p_binary[p_idx]
                            time_diff = _time_diff_hours(k_market, p_market)
                            if time_diff is None or time_diff > self.max_hours_diff:
                                continue
                            if not self._has_tag_overlap(k_market, p_market):
                                continue
                            pairs.append((k_market, p_market, float(score)))
                else:
                    # Search for matches
                    hits = util.semantic_search(k_batch_emb, p_emb, top_k=5)
                    
                    # Filter by similarity and date proximity
                    for k_local_idx, hit_list in enumerate(hits):
                        k_market = batch_markets[k_local_idx]
                        
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
                            
                            if not self._has_tag_overlap(k_market, p_market):
                                continue
                            
                            pairs.append((k_market, p_market, float(score)))
                
                logger.info(f"Batch {batch_idx // self.batch_size + 1}/{total_batches}: Found {len(pairs)} matches so far")
                
        except Exception as e:
            logger.error(f"Embedding/search failed: {e}")
            return []
        
        # Sort by similarity descending
        pairs.sort(key=lambda x: x[2], reverse=True)
        
        logger.info(f"Found {len(pairs)} cross-venue pairs (min_sim={self.min_similarity})")
        
        return pairs

    def find_pairs(
        self,
        kalshi_markets: List[Market],
        poly_markets: List[Market]
    ) -> List[Tuple[Market, Market, float]]:
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

        self._ensure_tags(k_binary)
        self._ensure_tags(p_binary)

        if not self.cluster_by_tags:
            return self._find_pairs_between(k_binary, p_binary)

        k_buckets: Dict[str, List[Market]] = {}
        p_buckets: Dict[str, List[Market]] = {}
        for market in k_binary:
            k_buckets.setdefault(self._bucket_key(market), []).append(market)
        for market in p_binary:
            p_buckets.setdefault(self._bucket_key(market), []).append(market)

        pairs: List[Tuple[Market, Market, float]] = []
        shared_keys = set(k_buckets.keys()).intersection(p_buckets.keys())
        logger.info(
            f"Cross-venue tag clusters: {len(shared_keys)} shared buckets"
        )
        for key in shared_keys:
            pairs.extend(self._find_pairs_between(k_buckets[key], p_buckets[key]))

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
