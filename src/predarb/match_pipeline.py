"""
Multi-stage match pipeline data models for cross-venue market matching.

This module defines the core data structures used by the MatchPipeline:
- PipelineStage: Defines a filtering stage with its filter function and rejection reason generator
- RejectionRecord: Records why a candidate pair was rejected and at which stage
- MatchCandidate: Represents a potential match between Kalshi and Polymarket markets
- MatchPipeline: The main pipeline class that runs candidates through 5 filtering stages

Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 5.1, 5.4, 7.1, 7.2, 7.3, 7.4, 7.5
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Callable, Dict, List, Optional, Tuple

from sentence_transformers import SentenceTransformer, util

from predarb.asset_normalizer import AssetNormalizer
from predarb.category_inferrer import CategoryInferrer
from predarb.extractors import ThresholdExtractor, ExtractedThreshold
from predarb.ticker_parser import TickerParser

if TYPE_CHECKING:
    from predarb.models import Market

logger = logging.getLogger(__name__)


@dataclass
class PipelineStage:
    """
    Defines a single stage in the multi-stage match pipeline.
    
    Each stage has a filter function that determines if a candidate pair
    should pass through, and a rejection reason function that explains
    why a pair was rejected.
    
    Attributes:
        name: Human-readable name of the stage (e.g., "category", "asset", "threshold")
        filter_fn: Function that takes two markets and returns True if they pass the filter
        rejection_reason_fn: Function that generates a rejection reason string for failed pairs
    
    Requirements: 7.1
    """
    name: str
    filter_fn: Callable[["Market", "Market"], bool]
    rejection_reason_fn: Callable[["Market", "Market"], str]


@dataclass
class RejectionRecord:
    """
    Records the rejection of a candidate market pair.
    
    When a pair fails a pipeline stage, a RejectionRecord is created
    to track which markets were involved, which stage rejected them,
    and why.
    
    Attributes:
        kalshi_id: The ID of the Kalshi market in the rejected pair
        polymarket_id: The ID of the Polymarket market in the rejected pair
        stage: The name of the pipeline stage that rejected the pair
        reason: Human-readable explanation of why the pair was rejected
    
    Requirements: 7.2, 7.3
    """
    kalshi_id: str
    polymarket_id: str
    stage: str
    reason: str


@dataclass
class MatchCandidate:
    """
    Represents a potential match between a Kalshi market and a Polymarket market.
    
    A MatchCandidate is created when a pair passes all pipeline stages.
    It contains the matched markets along with metadata about how they
    matched (structural vs semantic) and the confidence level.
    
    Attributes:
        kalshi_market: The Kalshi market in the match
        polymarket_market: The Polymarket market in the match
        structural_matches: Dict indicating which fields matched structurally
                           (e.g., {"asset": True, "threshold": True, "direction": False, "date": True})
        semantic_score: Cosine similarity score (0.0-1.0) between market embeddings
        confidence: Overall confidence score (0.0-1.0) for the match
    
    Requirements: 7.1, 7.6
    """
    kalshi_market: "Market"
    polymarket_market: "Market"
    structural_matches: Dict[str, bool] = field(default_factory=dict)
    semantic_score: float = 0.0
    confidence: float = 0.0


class MatchPipeline:
    """
    Multi-stage filtering pipeline for cross-venue market matching.
    
    Runs candidate market pairs through 5 filtering stages:
    1. Category Filter - check category compatibility
    2. Asset Filter - require matching normalized assets when both available
    3. Threshold Filter - require thresholds within 0.1% when both available
    4. Date Filter - require dates within 2 hours, exclude if missing
    5. Semantic Similarity - require >= 0.60 for structural matches, >= 0.85 for semantic-only
    
    Tracks rejections per stage with reasons for debugging and tuning.
    
    Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 5.1, 5.4, 7.1, 7.4, 7.5
    """
    
    # Semantic similarity thresholds
    STRUCTURAL_MATCH_THRESHOLD = 0.60
    SEMANTIC_ONLY_THRESHOLD = 0.85
    
    # Date tolerance in seconds (2 hours)
    DATE_TOLERANCE_SECONDS = 2 * 60 * 60
    
    # Threshold tolerance (0.1%)
    THRESHOLD_TOLERANCE = 0.001
    
    # Known asset keywords for extraction from text
    ASSET_KEYWORDS = {
        'bitcoin': 'bitcoin',
        'btc': 'bitcoin',
        'ethereum': 'ethereum',
        'eth': 'ethereum',
        'ether': 'ethereum',
        'solana': 'solana',
        'sol': 'solana',
        'dogecoin': 'dogecoin',
        'doge': 'dogecoin',
        'xrp': 'xrp',
        'ripple': 'xrp',
        'cardano': 'cardano',
        'ada': 'cardano',
        's&p': 'sp500',
        's&p 500': 'sp500',
        'sp500': 'sp500',
        'spx': 'sp500',
        'gold': 'gold',
        'xau': 'gold',
        'oil': 'oil',
        'wti': 'oil',
        'crude': 'oil',
    }
    
    # Incompatible category pairs
    INCOMPATIBLE_CATEGORIES = {
        ("CRYPTO", "POLITICS"),
        ("CRYPTO", "SPORTS"),
        ("CRYPTO", "ECONOMICS"),
        ("POLITICS", "SPORTS"),
        ("POLITICS", "ECONOMICS"),
        ("SPORTS", "ECONOMICS"),
    }
    
    def __init__(
        self,
        ticker_parser: TickerParser,
        threshold_extractor: ThresholdExtractor,
        asset_normalizer: AssetNormalizer,
        category_inferrer: CategoryInferrer,
        embedding_model: Optional[SentenceTransformer] = None,
    ):
        """
        Initialize the MatchPipeline with required components.
        
        Args:
            ticker_parser: Parser for Kalshi ticker formats
            threshold_extractor: Extractor for price/value thresholds
            asset_normalizer: Normalizer for asset names
            category_inferrer: Inferrer for market categories
            embedding_model: Optional pre-loaded SentenceTransformer model.
                           If None, loads 'all-MiniLM-L6-v2' on first use.
        """
        self.ticker_parser = ticker_parser
        self.threshold_extractor = threshold_extractor
        self.asset_normalizer = asset_normalizer
        self.category_inferrer = category_inferrer
        self._embedding_model = embedding_model
        
        self.stages: List[PipelineStage] = self._build_stages()
        self.rejections: List[RejectionRecord] = []
        self.stage_counts: Dict[str, int] = {}
        
        # Cache for extracted data
        self._market_data_cache: Dict[str, Dict] = {}
    
    @property
    def embedding_model(self) -> SentenceTransformer:
        """Lazy-load the embedding model on first access."""
        if self._embedding_model is None:
            self._embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
        return self._embedding_model
    
    def _extract_asset_from_text(self, text: str) -> Optional[str]:
        """
        Extract asset name from market question text.
        
        Looks for known asset keywords in the text and returns the
        canonical asset name.
        """
        if not text:
            return None
        
        text_lower = text.lower()
        
        # Check for known asset keywords
        for keyword, asset in self.ASSET_KEYWORDS.items():
            if keyword in text_lower:
                return asset
        
        return None
    
    def _build_stages(self) -> List[PipelineStage]:
        """Build the 5-stage pipeline."""
        return [
            PipelineStage(
                name="category",
                filter_fn=self._category_filter,
                rejection_reason_fn=self._category_rejection_reason,
            ),
            PipelineStage(
                name="asset",
                filter_fn=self._asset_filter,
                rejection_reason_fn=self._asset_rejection_reason,
            ),
            PipelineStage(
                name="threshold",
                filter_fn=self._threshold_filter,
                rejection_reason_fn=self._threshold_rejection_reason,
            ),
            PipelineStage(
                name="date",
                filter_fn=self._date_filter,
                rejection_reason_fn=self._date_rejection_reason,
            ),
            # Note: Semantic similarity is handled separately in process()
            # because it needs to compute scores and determine thresholds
        ]
    
    def _get_market_data(self, market: "Market") -> Dict:
        """
        Extract and cache structured data from a market.
        
        Returns a dict with: category, asset, threshold, direction, expiry
        """
        if market.id in self._market_data_cache:
            return self._market_data_cache[market.id]
        
        data: Dict = {
            "category": None,
            "asset": None,
            "threshold": None,
            "direction": None,
            "expiry": None,
        }
        
        # Infer category
        data["category"] = self.category_inferrer.infer_if_needed(market)
        
        # Try to parse Kalshi ticker first
        ticker = getattr(market, "slug", None) or market.id
        parsed_ticker = self.ticker_parser.parse(ticker)
        
        if parsed_ticker:
            data["asset"] = self.asset_normalizer.normalize(parsed_ticker.asset)
            data["threshold"] = parsed_ticker.threshold
            data["direction"] = parsed_ticker.direction
            data["expiry"] = parsed_ticker.expiry
        else:
            # Fall back to text extraction
            # First try to extract asset from question text
            extracted_asset = self._extract_asset_from_text(market.question)
            if extracted_asset:
                data["asset"] = self.asset_normalizer.normalize(extracted_asset)
            elif market.asset and market.asset.lower() not in ('will', 'the', 'a', 'an', 'if'):
                # Only use market.asset if it's not a common word
                data["asset"] = self.asset_normalizer.normalize(market.asset)
            
            # Extract threshold from question
            extracted = self.threshold_extractor.extract(market.question)
            if extracted:
                data["threshold"] = extracted.value
                data["direction"] = extracted.direction
            elif market.threshold is not None:
                data["threshold"] = market.threshold
                data["direction"] = market.comparator
            
            # Use market expiry
            data["expiry"] = market.expiry or market.end_date
        
        self._market_data_cache[market.id] = data
        return data
    
    def _category_filter(self, kalshi: "Market", poly: "Market") -> bool:
        """Stage 1: Check category compatibility."""
        kalshi_data = self._get_market_data(kalshi)
        poly_data = self._get_market_data(poly)
        
        cat1 = kalshi_data["category"]
        cat2 = poly_data["category"]
        
        # If either is OTHER, allow (can't determine compatibility)
        if cat1 == "OTHER" or cat2 == "OTHER":
            return True
        
        # Check if categories are incompatible
        pair = tuple(sorted([cat1, cat2]))
        return pair not in self.INCOMPATIBLE_CATEGORIES
    
    def _category_rejection_reason(self, kalshi: "Market", poly: "Market") -> str:
        """Generate rejection reason for category filter."""
        kalshi_data = self._get_market_data(kalshi)
        poly_data = self._get_market_data(poly)
        return f"Incompatible categories: {kalshi_data['category']} vs {poly_data['category']}"
    
    def _asset_filter(self, kalshi: "Market", poly: "Market") -> bool:
        """Stage 2: Require matching normalized assets when both available (financial markets only)."""
        kalshi_data = self._get_market_data(kalshi)
        poly_data = self._get_market_data(poly)
        
        # Skip asset matching for non-financial categories (politics, sports, etc.)
        # These don't have tradeable assets in the financial sense
        non_financial_categories = {"POLITICS", "SPORTS", "CULTURE", "SCIENCE", "CLIMATE", "OTHER"}
        if kalshi_data["category"] in non_financial_categories or poly_data["category"] in non_financial_categories:
            return True  # Pass through - rely on semantic matching
        
        asset1 = kalshi_data["asset"]
        asset2 = poly_data["asset"]
        
        # If either is missing, pass (can't compare)
        if asset1 is None or asset2 is None:
            return True
        
        # Both have assets - must match
        return asset1 == asset2
    
    def _asset_rejection_reason(self, kalshi: "Market", poly: "Market") -> str:
        """Generate rejection reason for asset filter."""
        kalshi_data = self._get_market_data(kalshi)
        poly_data = self._get_market_data(poly)
        return f"Asset mismatch: {kalshi_data['asset']} vs {poly_data['asset']}"
    
    def _threshold_filter(self, kalshi: "Market", poly: "Market") -> bool:
        """Stage 3: Require thresholds within 0.1% when both available (financial markets only)."""
        kalshi_data = self._get_market_data(kalshi)
        poly_data = self._get_market_data(poly)
        
        # Skip threshold matching for non-financial categories
        non_financial_categories = {"POLITICS", "SPORTS", "CULTURE", "SCIENCE", "CLIMATE", "OTHER"}
        if kalshi_data["category"] in non_financial_categories or poly_data["category"] in non_financial_categories:
            return True  # Pass through - rely on semantic matching
        
        t1 = kalshi_data["threshold"]
        t2 = poly_data["threshold"]
        
        # If either is missing, pass (can't compare)
        if t1 is None or t2 is None:
            return True
        
        # Both have thresholds - check tolerance
        if t1 == 0 and t2 == 0:
            return True
        if t1 == 0 or t2 == 0:
            return False
        
        relative_diff = abs(t1 - t2) / max(abs(t1), abs(t2))
        return relative_diff <= self.THRESHOLD_TOLERANCE
    
    def _threshold_rejection_reason(self, kalshi: "Market", poly: "Market") -> str:
        """Generate rejection reason for threshold filter."""
        kalshi_data = self._get_market_data(kalshi)
        poly_data = self._get_market_data(poly)
        t1 = kalshi_data["threshold"]
        t2 = poly_data["threshold"]
        if t1 and t2:
            diff_pct = abs(t1 - t2) / max(abs(t1), abs(t2)) * 100
            return f"Threshold mismatch: {t1} vs {t2} (diff: {diff_pct:.2f}%)"
        return f"Threshold mismatch: {t1} vs {t2}"
    
    def _date_filter(self, kalshi: "Market", poly: "Market") -> bool:
        """Stage 4: Require dates within 2 hours, exclude if missing."""
        kalshi_data = self._get_market_data(kalshi)
        poly_data = self._get_market_data(poly)
        
        date1 = kalshi_data["expiry"]
        date2 = poly_data["expiry"]
        
        # If either is missing, reject (per Req 5.4)
        if date1 is None or date2 is None:
            return False
        
        # Normalize to UTC for comparison (Req 5.5)
        date1_utc = self._normalize_to_utc(date1)
        date2_utc = self._normalize_to_utc(date2)
        
        # Check if within 2 hours
        diff_seconds = abs((date1_utc - date2_utc).total_seconds())
        return diff_seconds <= self.DATE_TOLERANCE_SECONDS
    
    def _normalize_to_utc(self, dt: datetime) -> datetime:
        """Normalize a datetime to UTC."""
        if dt.tzinfo is None:
            # Assume UTC if no timezone
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    
    def _date_rejection_reason(self, kalshi: "Market", poly: "Market") -> str:
        """Generate rejection reason for date filter."""
        kalshi_data = self._get_market_data(kalshi)
        poly_data = self._get_market_data(poly)
        
        date1 = kalshi_data["expiry"]
        date2 = poly_data["expiry"]
        
        if date1 is None and date2 is None:
            return "Both markets missing expiry date"
        if date1 is None:
            return "Kalshi market missing expiry date"
        if date2 is None:
            return "Polymarket market missing expiry date"
        
        diff_hours = abs((date1 - date2).total_seconds()) / 3600
        return f"Date mismatch: {date1.isoformat()} vs {date2.isoformat()} (diff: {diff_hours:.1f}h)"
    
    def _has_structural_data(self, kalshi: "Market", poly: "Market") -> bool:
        """Check if both markets have structural data for matching."""
        kalshi_data = self._get_market_data(kalshi)
        poly_data = self._get_market_data(poly)
        
        # Consider structural if at least one of: asset, threshold, or date matches
        has_asset = kalshi_data["asset"] is not None and poly_data["asset"] is not None
        has_threshold = kalshi_data["threshold"] is not None and poly_data["threshold"] is not None
        has_date = kalshi_data["expiry"] is not None and poly_data["expiry"] is not None
        
        return has_asset or has_threshold or has_date
    
    def _compute_semantic_score(self, kalshi: "Market", poly: "Market") -> float:
        """Compute semantic similarity between two markets."""
        text1 = kalshi.question
        text2 = poly.question
        
        embeddings = self.embedding_model.encode([text1, text2], convert_to_tensor=True)
        similarity = util.cos_sim(embeddings[0], embeddings[1]).item()
        return float(similarity)
    
    def _build_structural_matches(self, kalshi: "Market", poly: "Market") -> Dict[str, bool]:
        """Build dict of which fields matched structurally."""
        kalshi_data = self._get_market_data(kalshi)
        poly_data = self._get_market_data(poly)
        
        matches: Dict[str, bool] = {}
        
        # Asset match
        if kalshi_data["asset"] and poly_data["asset"]:
            matches["asset"] = kalshi_data["asset"] == poly_data["asset"]
        else:
            matches["asset"] = False
        
        # Threshold match
        if kalshi_data["threshold"] is not None and poly_data["threshold"] is not None:
            t1, t2 = kalshi_data["threshold"], poly_data["threshold"]
            if t1 == 0 and t2 == 0:
                matches["threshold"] = True
            elif t1 == 0 or t2 == 0:
                matches["threshold"] = False
            else:
                relative_diff = abs(t1 - t2) / max(abs(t1), abs(t2))
                matches["threshold"] = relative_diff <= self.THRESHOLD_TOLERANCE
        else:
            matches["threshold"] = False
        
        # Direction match
        if kalshi_data["direction"] and poly_data["direction"]:
            # Normalize directions for comparison
            dir1 = kalshi_data["direction"]
            dir2 = poly_data["direction"]
            # Map "at_least" to "above", "at_most" to "below"
            dir1_norm = "above" if dir1 in ("above", "at_least", ">", ">=") else "below" if dir1 in ("below", "at_most", "<", "<=") else dir1
            dir2_norm = "above" if dir2 in ("above", "at_least", ">", ">=") else "below" if dir2 in ("below", "at_most", "<", "<=") else dir2
            matches["direction"] = dir1_norm == dir2_norm
        else:
            matches["direction"] = False
        
        # Date match
        if kalshi_data["expiry"] and poly_data["expiry"]:
            date1_utc = self._normalize_to_utc(kalshi_data["expiry"])
            date2_utc = self._normalize_to_utc(poly_data["expiry"])
            diff_seconds = abs((date1_utc - date2_utc).total_seconds())
            matches["date"] = diff_seconds <= self.DATE_TOLERANCE_SECONDS
        else:
            matches["date"] = False
        
        return matches
    
    def process(
        self, 
        kalshi_markets: List["Market"], 
        poly_markets: List["Market"]
    ) -> List[MatchCandidate]:
        """
        Run all candidate pairs through the pipeline.
        
        Args:
            kalshi_markets: List of Kalshi markets to match
            poly_markets: List of Polymarket markets to match
            
        Returns:
            List of MatchCandidate objects that passed all stages
        """
        # Reset state for new run
        self.rejections = []
        self.stage_counts = {stage.name: 0 for stage in self.stages}
        self.stage_counts["semantic"] = 0
        self._market_data_cache = {}
        
        candidates: List[MatchCandidate] = []
        
        # Generate all pairs
        for kalshi in kalshi_markets:
            for poly in poly_markets:
                result = self._process_pair(kalshi, poly)
                if result is not None:
                    candidates.append(result)
        
        logger.info(
            f"Pipeline processed {len(kalshi_markets) * len(poly_markets)} pairs, "
            f"accepted {len(candidates)} matches"
        )
        
        return candidates
    
    def _process_pair(
        self, 
        kalshi: "Market", 
        poly: "Market"
    ) -> Optional[MatchCandidate]:
        """Process a single market pair through all stages."""
        # Run through structural filter stages (1-4)
        for stage in self.stages:
            if not stage.filter_fn(kalshi, poly):
                reason = stage.rejection_reason_fn(kalshi, poly)
                self.rejections.append(RejectionRecord(
                    kalshi_id=kalshi.id,
                    polymarket_id=poly.id,
                    stage=stage.name,
                    reason=reason,
                ))
                self.stage_counts[stage.name] += 1
                return None
        
        # Stage 5: Semantic similarity
        semantic_score = self._compute_semantic_score(kalshi, poly)
        has_structural = self._has_structural_data(kalshi, poly)
        
        # Determine threshold based on structural data availability
        threshold = self.STRUCTURAL_MATCH_THRESHOLD if has_structural else self.SEMANTIC_ONLY_THRESHOLD
        
        if semantic_score < threshold:
            self.rejections.append(RejectionRecord(
                kalshi_id=kalshi.id,
                polymarket_id=poly.id,
                stage="semantic",
                reason=f"Semantic score {semantic_score:.3f} below threshold {threshold:.2f} "
                       f"({'structural' if has_structural else 'semantic-only'} mode)",
            ))
            self.stage_counts["semantic"] += 1
            return None
        
        # Build structural matches dict
        structural_matches = self._build_structural_matches(kalshi, poly)
        
        # Compute confidence score
        confidence = self._compute_confidence(structural_matches, semantic_score)
        
        return MatchCandidate(
            kalshi_market=kalshi,
            polymarket_market=poly,
            structural_matches=structural_matches,
            semantic_score=semantic_score,
            confidence=confidence,
        )
    
    def _compute_confidence(
        self, 
        structural_matches: Dict[str, bool], 
        semantic_score: float
    ) -> float:
        """
        Compute confidence score based on structural vs semantic matching.
        
        Full structural match (all fields) returns >= 0.95
        Semantic-only match returns semantic_score * 0.7
        """
        # Count structural matches
        match_count = sum(1 for v in structural_matches.values() if v)
        total_fields = len(structural_matches)
        
        if total_fields > 0 and match_count == total_fields:
            # Full structural match
            return max(0.95, semantic_score)
        elif match_count > 0:
            # Partial structural match
            structural_ratio = match_count / total_fields
            return 0.7 + (0.25 * structural_ratio) + (0.05 * semantic_score)
        else:
            # Semantic-only match
            return semantic_score * 0.7
    
    def get_rejection_summary(self) -> Dict[str, int]:
        """Get rejection counts per stage."""
        return dict(self.stage_counts)
