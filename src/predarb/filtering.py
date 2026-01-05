"""
Market filtering and prioritization module for prediction market arbitrage scanning.

Works with predarb.models.Market (Pydantic model from Polymarket API).

Provides 3-layer filtering:
1. Hard eligibility filters (market must be tradable)
2. Risk-based filters (depends on trader account and position size)
3. Liquidity-based prioritization scoring (0..100)
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional, List, Tuple, Dict
import math
from enum import Enum

# Import your existing models
from predarb.models import Market, Outcome


class RejectionReason(Enum):
    """Enumeration of market rejection reasons."""
    INSUFFICIENT_OUTCOMES = "Insufficient outcomes for trading"
    SPREAD_TOO_WIDE = "Spread exceeds maximum threshold"
    VOLUME_TOO_LOW = "24h volume below minimum"
    LIQUIDITY_TOO_LOW = "Liquidity below minimum"
    EXPIRY_TOO_SOON = "Market expires too soon"
    RESOLUTION_EMPTY = "Resolution source not specified"
    RESOLUTION_SUBJECTIVE = "Resolution may be subjective"
    INSUFFICIENT_LIQUIDITY_FOR_SIZE = "Liquidity insufficient for target order size"


@dataclass
class FilterSettings:
    """
    Configuration for market filtering and prioritization.
    
    Attributes:
        max_spread_pct: Maximum acceptable bid-ask spread as % (default 3%)
        min_volume_24h: Minimum 24h trading volume (default $10k)
        min_liquidity: Minimum available liquidity (default $25k)
        min_days_to_expiry: Minimum days until market expiration (default 7)
        min_liquidity_multiple: Min liquidity as multiple of order size (default 20x)
        require_resolution_source: If True, require explicit resolution_source
        allow_missing_end_time: If True, allow markets without end_date but penalize score
        
    Scoring weights (must sum to 1.0):
        spread_score_weight: Weight for spread tightness (default 0.40)
        volume_score_weight: Weight for volume (default 0.20)
        liquidity_score_weight: Weight for liquidity (default 0.30)
        frequency_score_weight: Weight for outcome count (default 0.10)
    """
    max_spread_pct: float = 0.03
    min_volume_24h: float = 10_000.0
    min_liquidity: float = 25_000.0
    min_days_to_expiry: int = 7
    min_liquidity_multiple: float = 20.0
    require_resolution_source: bool = True
    allow_missing_end_time: bool = True
    
    # Scoring weights
    spread_score_weight: float = 0.40
    volume_score_weight: float = 0.20
    liquidity_score_weight: float = 0.30
    frequency_score_weight: float = 0.10
    
    def __post_init__(self):
        """Validate scoring weights sum to ~1.0."""
        total_weight = (
            self.spread_score_weight
            + self.volume_score_weight
            + self.liquidity_score_weight
            + self.frequency_score_weight
        )
        if not (0.99 <= total_weight <= 1.01):
            raise ValueError(f"Scoring weights sum to {total_weight}, not ~1.0")


class MarketFilter:
    """
    Core market filtering and prioritization engine.
    
    Provides methods to:
    - Filter markets by eligibility (3 layers)
    - Rank remaining markets by liquidity quality
    - Explain rejection reasons for debugging
    """
    
    def __init__(self, settings: Optional[FilterSettings] = None):
        """
        Initialize filter with settings.
        
        Args:
            settings: FilterSettings instance; uses defaults if None
        """
        self.settings = settings or FilterSettings()
        self._rejection_reasons: Dict[str, List[str]] = {}
    
    def filter_markets(
        self,
        markets: List[Market],
        account_equity_usd: Optional[float] = None,
        target_order_size_usd: Optional[float] = None,
    ) -> List[Market]:
        """
        Filter markets by hard eligibility and risk-based constraints.
        
        LAYER 1: Hard eligibility (all markets)
        - Must have tradable bid/ask prices
        - Spread must not exceed max_spread_pct
        - Volume, liquidity, and expiry must meet thresholds
        - Resolution rules must be non-empty and concrete
        
        LAYER 2: Risk-based (if account/position size provided)
        - Liquidity must support target_order_size_usd * min_liquidity_multiple
        
        Args:
            markets: List of Market objects
            account_equity_usd: Account size (for risk-based filtering)
            target_order_size_usd: Desired position size per market
        
        Returns:
            List of eligible markets sorted by market_id (stable order)
        """
        self._rejection_reasons = {}
        eligible = []
        
        for market in markets:
            # Layer 1: Hard eligibility checks
            if not self._passes_hard_filters(market):
                continue
            
            # Layer 2: Risk-based checks (if account info provided)
            if account_equity_usd is not None and target_order_size_usd is not None:
                if not self._passes_risk_filters(market, target_order_size_usd):
                    continue
            
            eligible.append(market)
        
        # Return in deterministic order
        return sorted(eligible, key=lambda m: m.id)
    
    def rank_markets(
        self,
        markets: List[Market],
    ) -> List[Tuple[Market, float]]:
        """
        Rank markets by liquidity quality score (0..100).
        
        Score is a weighted combination of:
        - Spread tightness (40%)
        - Trade volume (20%, log-scaled)
        - Available liquidity (30%, log-scaled)
        - Trade frequency (10%)
        
        Args:
            markets: List of eligible Market objects
        
        Returns:
            List of (Market, score) tuples, sorted by score descending
        """
        scored = []
        for market in markets:
            score = self._compute_score(market)
            scored.append((market, score))
        
        # Sort by score descending, then by id for deterministic order
        scored.sort(key=lambda x: (-x[1], x[0].id))
        return scored
    
    def explain_rejection(self, market: Market) -> List[str]:
        """
        Get human-readable rejection reasons for a market.
        
        Args:
            market: Market object
        
        Returns:
            List of rejection reason strings
        """
        if market.id in self._rejection_reasons:
            return self._rejection_reasons[market.id]
        return []
    
    # ========== LAYER 1: Hard Eligibility Filters ==========
    
    def _passes_hard_filters(self, market: Market) -> bool:
        """Check all hard eligibility criteria."""
        reasons = []
        
        # Check: Must have sufficient outcomes
        if not self._has_sufficient_outcomes(market):
            reasons.append(RejectionReason.INSUFFICIENT_OUTCOMES.value)
        
        # Check: Spread constraint
        if not self._passes_spread_filter(market):
            reasons.append(RejectionReason.SPREAD_TOO_WIDE.value)
        
        # Check: Volume constraint
        if not self._passes_volume_filter(market):
            reasons.append(RejectionReason.VOLUME_TOO_LOW.value)
        
        # Check: Liquidity constraint
        if not self._passes_liquidity_filter(market):
            reasons.append(RejectionReason.LIQUIDITY_TOO_LOW.value)
        
        # Check: Expiry constraint
        if not self._passes_expiry_filter(market):
            reasons.append(RejectionReason.EXPIRY_TOO_SOON.value)
        
        # Check: Resolution source
        issue = self._resolution_issue(market)
        if issue:
            reasons.append(issue.value)
        
        if reasons:
            self._rejection_reasons[market.id] = reasons
            return False
        
        return True
    
    def _has_sufficient_outcomes(self, market: Market) -> bool:
        """Check if market has enough outcomes with prices."""
        if not market.outcomes or len(market.outcomes) < 2:
            return False
        prices = self._price_map(market)
        priced_outcomes = sum(1 for _, price in prices.items() if price > 0)
        return priced_outcomes >= 2
    
    def _passes_spread_filter(self, market: Market) -> bool:
        """
        Check if max spread across outcomes is acceptable.
        
        For binary YES/NO markets: prices should sum to ~1.
        For all markets: spread = max_price - min_price should be <= max_spread_pct*2.
        """
        if not market.outcomes or len(market.outcomes) < 2:
            return False

        # Fast path when outcomes already have prices
        priced_outcomes = [getattr(o, "price", None) for o in market.outcomes if getattr(o, "price", None) is not None]
        if len(priced_outcomes) == len(market.outcomes):
            min_price = min(priced_outcomes)
            max_price = max(priced_outcomes)
            spread = max_price - min_price
            if spread <= self.settings.max_spread_pct * 2:
                return True

        # Prefer explicit bid/ask if provided
        best_bid = getattr(market, "best_bid", {}) or {}
        best_ask = getattr(market, "best_ask", {}) or {}
        if best_bid and best_ask:
            labels = [o.label if isinstance(o, Outcome) else str(o) for o in market.outcomes]
            # All outcomes must have bid/ask
            for label in labels:
                bid = best_bid.get(label)
                ask = best_ask.get(label)
                if bid is None or ask is None:
                    return False
                if ask < bid:
                    return False
                spread_abs = ask - bid
                if spread_abs > self.settings.max_spread_pct:
                    return False
            return True

        prices = [price for price in self._price_map(market).values() if price > 0]
        if len(prices) < 2:
            return False

        min_price = min(prices)
        max_price = max(prices)
        spread = max_price - min_price
        return spread <= self.settings.max_spread_pct * 2
    
    def _passes_volume_filter(self, market: Market) -> bool:
        """Check if 24h volume meets minimum."""
        volume = market.volume or 0.0
        return volume >= self.settings.min_volume_24h
    
    def _passes_liquidity_filter(self, market: Market) -> bool:
        """Check if liquidity meets minimum."""
        liquidity = market.liquidity or 0.0
        return liquidity >= self.settings.min_liquidity
    
    def _passes_expiry_filter(self, market: Market) -> bool:
        """Check if market expiration is far enough in future."""
        if market.end_date is None:
            return self.settings.allow_missing_end_time
        
        # Handle timezone-aware datetimes
        now = datetime.utcnow()
        end_time = market.end_date
        
        # Strip timezone for comparison if needed
        if end_time.tzinfo is not None and now.tzinfo is None:
            end_time = end_time.replace(tzinfo=None)
        elif end_time.tzinfo is None and now.tzinfo is not None:
            now = now.replace(tzinfo=None)
        
        days_to_expiry = (end_time - now).days
        return days_to_expiry >= self.settings.min_days_to_expiry
    
    def _resolution_issue(self, market: Market) -> RejectionReason | None:
        """Return resolution-related rejection reason, if any."""
        if not self.settings.require_resolution_source:
            return None
        rules_raw = market.description
        rules_text = rules_raw or ""
        source_text = (market.resolution_source or "")
        lower_rules = rules_text.lower()
        if any(keyword in lower_rules for keyword in ("subjective", "opinion", "consensus", "believe")):
            return RejectionReason.RESOLUTION_SUBJECTIVE
        if rules_raw is not None and rules_text.strip() == "":
            return RejectionReason.RESOLUTION_EMPTY
        if source_text.strip():
            return None
        if rules_text.strip() and "resolve" in lower_rules:
            return None
        return RejectionReason.RESOLUTION_EMPTY

    def _passes_resolution_filter(self, market: Market) -> bool:
        """Check if market has explicit resolution source (if required by settings)."""
        return self._resolution_issue(market) is None
    
    def _get_rejection_reasons(self, market: Market) -> List[str]:
        """Get specific rejection reason(s)."""
        reasons = []
        
        if not self._has_sufficient_outcomes(market):
            reasons.append(RejectionReason.INSUFFICIENT_OUTCOMES.value)
        
        if not self._passes_spread_filter(market):
            reasons.append(RejectionReason.SPREAD_TOO_WIDE.value)
        
        if not self._passes_volume_filter(market):
            reasons.append(RejectionReason.VOLUME_TOO_LOW.value)
        
        if not self._passes_liquidity_filter(market):
            reasons.append(RejectionReason.LIQUIDITY_TOO_LOW.value)
        
        if not self._passes_expiry_filter(market):
            reasons.append(RejectionReason.EXPIRY_TOO_SOON.value)
        
        issue = self._resolution_issue(market)
        if issue:
            reasons.append(issue.value)
        
        return reasons
    
    # ========== LAYER 2: Risk-Based Filters ==========
    
    def _passes_risk_filters(
        self,
        market: Market,
        target_order_size_usd: float,
    ) -> bool:
        """
        Check if market has sufficient liquidity for position size.
        
        Requires: liquidity >= min_liquidity_multiple * target_order_size_usd
        """
        min_required = self.settings.min_liquidity_multiple * target_order_size_usd
        liquidity = market.liquidity or 0.0
        return liquidity >= min_required
    
    # ========== LAYER 3: Scoring & Ranking ==========
    
    def _compute_score(self, market: Market) -> float:
        """
        Compute liquidity quality score (0..100).
        
        Weighted combination of:
        - Spread tightness (40%)
        - Trade volume (20%, log-scaled)
        - Available liquidity (30%, log-scaled)
        - Outcome count (10%)
        
        Returns:
            Float in range [0, 100]
        """
        spread_score = self._score_spread(market)
        volume_score = self._score_volume(market)
        liquidity_score = self._score_liquidity(market)
        frequency_score = self._score_frequency(market)
        outcome_score = self._score_outcome_count(market)
        frequency_component = (frequency_score + outcome_score) / 2
        
        # Weighted average
        total = (
            spread_score * self.settings.spread_score_weight
            + volume_score * self.settings.volume_score_weight
            + liquidity_score * self.settings.liquidity_score_weight
            + frequency_component * self.settings.frequency_score_weight
        )
        
        # Apply expiry penalty if end_date is present but close
        if market.end_date is not None:
            now = datetime.utcnow()
            end_time = market.end_date
            # Strip timezone for comparison if needed
            if end_time.tzinfo is not None and now.tzinfo is None:
                end_time = end_time.replace(tzinfo=None)
            elif end_time.tzinfo is None and now.tzinfo is not None:
                now = now.replace(tzinfo=None)
            
            days_to_expiry = max(0.0, (end_time - now).days)
            if days_to_expiry < 30:
                # Scale down linearly as expiry approaches (down to 0 at expiry)
                factor = max(0.0, days_to_expiry / 30.0)
                total = total * factor
        else:
            # Penalize missing expiry if allowed
            if self.settings.allow_missing_end_time:
                total = total * 0.95

        return float(max(0, min(100, total)))
    
    def _score_spread(self, market: Market) -> float:
        """
        Score based on spread across outcomes.
        
        Tighter spread = higher score. Linear scale from 0% to max_spread_pct.
        """
        best_bid = getattr(market, "best_bid", {}) or {}
        best_ask = getattr(market, "best_ask", {}) or {}
        if best_bid and best_ask:
            labels = [o.label if isinstance(o, Outcome) else str(o) for o in market.outcomes]
            max_spread_abs = 0.0
            for lbl in labels:
                bid = best_bid.get(lbl)
                ask = best_ask.get(lbl)
                if bid is None or ask is None or ask <= 0:
                    continue
                spread_abs = ask - bid
                max_spread_abs = max(max_spread_abs, spread_abs)
            if max_spread_abs == 0:
                return 100.0
            return max(0.0, 100 * (1 - max_spread_abs / max(self.settings.max_spread_pct, 1e-6)))

        prices = [p for p in self._price_map(market).values() if p >= 0]
        if len(prices) < 2:
            return 0.0

        min_price = min(prices)
        max_price = max(prices)
        avg_price = sum(prices) / len(prices)

        if avg_price == 0:
            return 0.0
        
        spread = max_price - min_price
        spread_pct = spread / avg_price
        
        # Scale: 0% spread -> 100, max_spread_pct -> 0
        if spread_pct <= 0.01:
            return 100.0
        
        score = max(0, 100 * (1 - spread_pct / max(self.settings.max_spread_pct, 0.01)))
        return score
    
    def _score_volume(self, market: Market) -> float:
        """
        Score based on 24h trading volume (log-scaled).
        
        min_volume_24h -> 0 points
        min_volume_24h * 10 -> ~50 points
        min_volume_24h * 100 -> ~80 points
        """
        volume = market.volume or 0.0
        if volume <= 0:
            return 0.0
        
        if volume < self.settings.min_volume_24h:
            return 0.0
        
        # Log scale: ln(volume / min_volume) normalized
        ratio = volume / self.settings.min_volume_24h
        log_ratio = math.log(ratio + 1)  # +1 to avoid log(0)
        
        # Normalize: ln(10) ≈ 2.3, ln(100) ≈ 4.6
        # Map [0, 4.6] to [0, 100]
        score = min(100, log_ratio * 21.7)  # 100 / 4.6 ≈ 21.7
        return score
    
    def _score_liquidity(self, market: Market) -> float:
        """
        Score based on available liquidity (log-scaled).
        
        min_liquidity -> 0 points
        min_liquidity * 10 -> ~50 points
        min_liquidity * 100 -> ~80 points
        """
        liquidity = market.liquidity or 0.0
        if liquidity <= 0:
            return 0.0
        
        if liquidity < self.settings.min_liquidity:
            return 0.0
        
        ratio = liquidity / self.settings.min_liquidity
        log_ratio = math.log(ratio + 1)
        
        score = min(100, log_ratio * 21.7)
        return score
    
    def _score_outcome_count(self, market: Market) -> float:
        """
        Score based on number of outcomes.
        
        Binary markets (2 outcomes) -> ~70 points
        Multi-outcome markets (3+) -> higher points (more complex)
        """
        if not market.outcomes:
            return 0.0
        
        outcome_count = len(market.outcomes)
        if outcome_count < 2:
            return 0.0
        
        # 2 outcomes -> 70 points, 3+ outcomes -> 90+ points
        score = min(100, 50 + outcome_count * 10)
        return score

    def _score_frequency(self, market: Market) -> float:
        """
        Score based on recent trading frequency (trades_1h).
        """
        trades = getattr(market, "trades_1h", None)
        if trades is None or trades <= 0:
            return 0.0
        # Log-style scaling to keep in 0..100
        return float(min(100, math.log(trades + 1) * 25))

    def _price_map(self, market: Market) -> Dict[str, float]:
        """
        Derive a mapping of outcome label -> representative price.
        Uses bid/ask midpoint when available, otherwise Outcome.price.
        """
        prices: Dict[str, float] = {}
        labels = []
        for o in market.outcomes:
            if isinstance(o, Outcome):
                labels.append(o.label)
                prices[o.label] = o.price
            elif isinstance(o, dict):
                lbl = str(o.get("label") or o.get("id") or o)
                labels.append(lbl)
                prices[lbl] = float(o.get("price", 0) or 0)
            else:
                lbl = str(getattr(o, "label", o))
                labels.append(lbl)
                price_val = getattr(o, "price", 0)
                prices[lbl] = float(price_val or 0.0)

        best_bid = getattr(market, "best_bid", {}) or {}
        best_ask = getattr(market, "best_ask", {}) or {}
        if best_bid and best_ask:
            for lbl in labels:
                bid = best_bid.get(lbl)
                ask = best_ask.get(lbl)
                if bid is None or ask is None:
                    continue
                prices[lbl] = (bid + ask) / 2
        return prices


def filter_markets(
    markets: List[Market],
    settings: Optional[FilterSettings] = None,
    account_equity_usd: Optional[float] = None,
    target_order_size_usd: Optional[float] = None,
) -> List[Market]:
    """
    Convenience function to filter markets.
    
    Args:
        markets: List of Market objects
        settings: Optional FilterSettings; uses defaults if None
        account_equity_usd: Account size for risk-based filtering
        target_order_size_usd: Position size for risk-based filtering
    
    Returns:
        List of eligible markets
    """
    filter_engine = MarketFilter(settings)
    return filter_engine.filter_markets(markets, account_equity_usd, target_order_size_usd)


def rank_markets(
    markets: List[Market],
    settings: Optional[FilterSettings] = None,
) -> List[Tuple[Market, float]]:
    """
    Convenience function to rank markets by score.
    
    Args:
        markets: List of Market objects
        settings: Optional FilterSettings; uses defaults if None
    
    Returns:
        List of (Market, score) tuples sorted by score descending
    """
    filter_engine = MarketFilter(settings)
    return filter_engine.rank_markets(markets)


def explain_rejection(
    market: Market,
    settings: Optional[FilterSettings] = None,
) -> List[str]:
    """
    Convenience function to get rejection reasons for a market.
    
    Args:
        market: Market object (from predarb.models)
        settings: Optional FilterSettings; uses defaults if None
    
    Returns:
        List of rejection reason strings
    """
    filter_engine = MarketFilter(settings)
    return filter_engine._get_rejection_reasons(market)
