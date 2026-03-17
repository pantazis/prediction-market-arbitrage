"""Cross-venue arbitrage detection components.

This module provides market normalization for cross-venue arbitrage detection
between Polymarket and Kalshi prediction markets.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from predarb.config import BrokerConfig, CrossVenueDetectorConfig
from predarb.models import Market, NormalizedMarket, Opportunity, TradeAction


class MarketNormalizer:
    """Normalizes Polymarket and Kalshi markets to unified format.

    Converts venue-specific market formats into a unified NormalizedMarket
    structure for cross-venue comparison:

    - Polymarket: Prices already in [0.0-1.0], extract from outcomes array
    - Kalshi: Convert cents (0-100) to probability (0.0-1.0), derive NO prices

    For Kalshi NO prices, bid/ask inversion is applied:
        no_bid = 1.0 - yes_ask
        no_ask = 1.0 - yes_bid
    """

    def normalize(self, market: Market) -> NormalizedMarket:
        """Normalize a market to unified format based on exchange.

        Args:
            market: The market to normalize

        Returns:
            NormalizedMarket with prices in [0.0-1.0] range
        """
        exchange = (market.exchange or "").lower()

        if exchange == "polymarket":
            nm = self.normalize_polymarket(market)
        elif exchange == "kalshi":
            nm = self.normalize_kalshi(market)
        else:
            # Unknown exchange - try to normalize as generic
            nm = self._normalize_generic(market)

        return self._validate_prices(nm)

    def normalize_polymarket(self, market: Market) -> NormalizedMarket:
        """Extract YES/NO prices from Polymarket outcomes array.

        Polymarket prices are already in [0.0-1.0] probability range.
        Extracts prices from best_bid/best_ask dictionaries or outcomes array.

        Args:
            market: Polymarket market to normalize

        Returns:
            NormalizedMarket with extracted YES/NO prices
        """
        yes_bid: Optional[float] = None
        yes_ask: Optional[float] = None
        no_bid: Optional[float] = None
        no_ask: Optional[float] = None

        # Try to extract from best_bid/best_ask dictionaries first
        if market.best_bid:
            yes_bid = market.best_bid.get("Yes") or market.best_bid.get("YES")
            no_bid = market.best_bid.get("No") or market.best_bid.get("NO")

        if market.best_ask:
            yes_ask = market.best_ask.get("Yes") or market.best_ask.get("YES")
            no_ask = market.best_ask.get("No") or market.best_ask.get("NO")

        # Fall back to outcomes array if bid/ask not available
        yes_outcome = market.outcome_by_label("yes") or market.outcome_by_label("Yes")
        no_outcome = market.outcome_by_label("no") or market.outcome_by_label("No")

        if yes_outcome:
            if yes_bid is None:
                yes_bid = yes_outcome.price
            if yes_ask is None:
                yes_ask = yes_outcome.price

        if no_outcome:
            if no_bid is None:
                no_bid = no_outcome.price
            if no_ask is None:
                no_ask = no_outcome.price

        # Use NaN for missing prices (will be caught by validation)
        yes_bid = yes_bid if yes_bid is not None else float("nan")
        yes_ask = yes_ask if yes_ask is not None else float("nan")
        no_bid = no_bid if no_bid is not None else float("nan")
        no_ask = no_ask if no_ask is not None else float("nan")

        return NormalizedMarket(
            market_id=market.id,
            exchange="polymarket",
            question=market.question,
            yes_bid=yes_bid,
            yes_ask=yes_ask,
            no_bid=no_bid,
            no_ask=no_ask,
            liquidity_usd=market.liquidity or 0.0,
            updated_at=market.updated_at,
            original=market,
            is_tradeable=True,
            non_tradeable_reason=None,
        )

    def normalize_kalshi(self, market: Market) -> NormalizedMarket:
        """Convert Kalshi cents to probability, derive NO prices.

        Kalshi prices are in cents (0-100), converted to [0.0-1.0] probability.
        NO prices are derived using bid/ask inversion:
            no_bid = 1.0 - yes_ask
            no_ask = 1.0 - yes_bid

        Args:
            market: Kalshi market to normalize

        Returns:
            NormalizedMarket with converted YES prices and derived NO prices
        """
        yes_bid: Optional[float] = None
        yes_ask: Optional[float] = None

        # Extract YES prices from best_bid/best_ask (in cents)
        if market.best_bid:
            raw_yes_bid = market.best_bid.get("Yes") or market.best_bid.get("YES")
            if raw_yes_bid is not None:
                # Convert cents to probability if value > 1 (indicates cents)
                yes_bid = raw_yes_bid / 100.0 if raw_yes_bid > 1.0 else raw_yes_bid

        if market.best_ask:
            raw_yes_ask = market.best_ask.get("Yes") or market.best_ask.get("YES")
            if raw_yes_ask is not None:
                # Convert cents to probability if value > 1 (indicates cents)
                yes_ask = raw_yes_ask / 100.0 if raw_yes_ask > 1.0 else raw_yes_ask

        # Fall back to outcomes array
        yes_outcome = market.outcome_by_label("yes") or market.outcome_by_label("Yes")
        if yes_outcome:
            # Outcome prices may already be normalized or in cents
            price = yes_outcome.price
            if yes_bid is None:
                yes_bid = price / 100.0 if price > 1.0 else price
            if yes_ask is None:
                yes_ask = price / 100.0 if price > 1.0 else price

        # Use NaN for missing YES prices
        yes_bid = yes_bid if yes_bid is not None else float("nan")
        yes_ask = yes_ask if yes_ask is not None else float("nan")

        # Derive NO prices using bid/ask inversion
        # no_bid = 1.0 - yes_ask (best bid for NO is complement of best ask for YES)
        # no_ask = 1.0 - yes_bid (best ask for NO is complement of best bid for YES)
        if not math.isnan(yes_ask):
            no_bid = 1.0 - yes_ask
        else:
            no_bid = float("nan")

        if not math.isnan(yes_bid):
            no_ask = 1.0 - yes_bid
        else:
            no_ask = float("nan")

        return NormalizedMarket(
            market_id=market.id,
            exchange="kalshi",
            question=market.question,
            yes_bid=yes_bid,
            yes_ask=yes_ask,
            no_bid=no_bid,
            no_ask=no_ask,
            liquidity_usd=market.liquidity or 0.0,
            updated_at=market.updated_at,
            original=market,
            is_tradeable=True,
            non_tradeable_reason=None,
        )

    def _normalize_generic(self, market: Market) -> NormalizedMarket:
        """Normalize a market from an unknown exchange.

        Attempts to extract prices from outcomes array, assuming prices
        are already in [0.0-1.0] range.

        Args:
            market: Market from unknown exchange

        Returns:
            NormalizedMarket with best-effort price extraction
        """
        yes_bid: Optional[float] = None
        yes_ask: Optional[float] = None
        no_bid: Optional[float] = None
        no_ask: Optional[float] = None

        # Try best_bid/best_ask first
        if market.best_bid:
            yes_bid = market.best_bid.get("Yes") or market.best_bid.get("YES")
            no_bid = market.best_bid.get("No") or market.best_bid.get("NO")

        if market.best_ask:
            yes_ask = market.best_ask.get("Yes") or market.best_ask.get("YES")
            no_ask = market.best_ask.get("No") or market.best_ask.get("NO")

        # Fall back to outcomes
        yes_outcome = market.outcome_by_label("yes") or market.outcome_by_label("Yes")
        no_outcome = market.outcome_by_label("no") or market.outcome_by_label("No")

        if yes_outcome:
            if yes_bid is None:
                yes_bid = yes_outcome.price
            if yes_ask is None:
                yes_ask = yes_outcome.price

        if no_outcome:
            if no_bid is None:
                no_bid = no_outcome.price
            if no_ask is None:
                no_ask = no_outcome.price

        # Use NaN for missing prices
        yes_bid = yes_bid if yes_bid is not None else float("nan")
        yes_ask = yes_ask if yes_ask is not None else float("nan")
        no_bid = no_bid if no_bid is not None else float("nan")
        no_ask = no_ask if no_ask is not None else float("nan")

        return NormalizedMarket(
            market_id=market.id,
            exchange=market.exchange or "unknown",
            question=market.question,
            yes_bid=yes_bid,
            yes_ask=yes_ask,
            no_bid=no_bid,
            no_ask=no_ask,
            liquidity_usd=market.liquidity or 0.0,
            updated_at=market.updated_at,
            original=market,
            is_tradeable=True,
            non_tradeable_reason=None,
        )

    def _validate_prices(self, nm: NormalizedMarket) -> NormalizedMarket:
        """Mark market as non-tradeable if prices are invalid.

        Checks for:
        - Missing prices (NaN)
        - Prices outside [0.0, 1.0] range

        Args:
            nm: NormalizedMarket to validate

        Returns:
            NormalizedMarket with is_tradeable and non_tradeable_reason updated
        """
        prices = [nm.yes_bid, nm.yes_ask, nm.no_bid, nm.no_ask]

        # Check for NaN values
        nan_prices = []
        if math.isnan(nm.yes_bid):
            nan_prices.append("yes_bid")
        if math.isnan(nm.yes_ask):
            nan_prices.append("yes_ask")
        if math.isnan(nm.no_bid):
            nan_prices.append("no_bid")
        if math.isnan(nm.no_ask):
            nan_prices.append("no_ask")

        if nan_prices:
            nm.is_tradeable = False
            nm.non_tradeable_reason = f"missing prices: {', '.join(nan_prices)}"
            return nm

        # Check for out-of-range values
        out_of_range = []
        if not (0.0 <= nm.yes_bid <= 1.0):
            out_of_range.append(f"yes_bid={nm.yes_bid}")
        if not (0.0 <= nm.yes_ask <= 1.0):
            out_of_range.append(f"yes_ask={nm.yes_ask}")
        if not (0.0 <= nm.no_bid <= 1.0):
            out_of_range.append(f"no_bid={nm.no_bid}")
        if not (0.0 <= nm.no_ask <= 1.0):
            out_of_range.append(f"no_ask={nm.no_ask}")

        if out_of_range:
            nm.is_tradeable = False
            nm.non_tradeable_reason = f"prices out of range [0.0, 1.0]: {', '.join(out_of_range)}"
            return nm

        return nm


@dataclass
class ExtractedPrices:
    """Extracted price data for arbitrage calculations.

    Contains bid, ask, and mid prices for both YES and NO outcomes.
    Mid prices are calculated as (bid + ask) / 2.
    """

    yes_bid: float
    yes_ask: float
    yes_mid: float
    no_bid: float
    no_ask: float
    no_mid: float


class PriceExtractor:
    """Extracts and validates prices from normalized markets.

    Provides methods to extract complete price data from NormalizedMarket
    objects and calculate mid prices from bid/ask spreads.
    """

    def extract(self, market: NormalizedMarket) -> Optional[ExtractedPrices]:
        """Extract prices from a normalized market.

        Returns None if the market is not tradeable (invalid prices).
        Calculates mid prices as (bid + ask) / 2 for both YES and NO.

        Args:
            market: NormalizedMarket to extract prices from

        Returns:
            ExtractedPrices with all 6 price fields, or None if invalid
        """
        if not market.is_tradeable:
            return None

        yes_mid = self.calculate_mid(market.yes_bid, market.yes_ask)
        no_mid = self.calculate_mid(market.no_bid, market.no_ask)

        return ExtractedPrices(
            yes_bid=market.yes_bid,
            yes_ask=market.yes_ask,
            yes_mid=yes_mid,
            no_bid=market.no_bid,
            no_ask=market.no_ask,
            no_mid=no_mid,
        )

    def calculate_mid(self, bid: float, ask: float) -> float:
        """Calculate mid price from bid/ask.

        Args:
            bid: Best bid price
            ask: Best ask price

        Returns:
            Mid price as (bid + ask) / 2
        """
        return (bid + ask) / 2.0





@dataclass
class StalenessResult:
    """Result of staleness check.

    Contains age information for both markets and flags indicating
    whether quotes are stale or should be discarded.

    Attributes:
        kalshi_age_seconds: Age of Kalshi quote in seconds
        poly_age_seconds: Age of Polymarket quote in seconds
        kalshi_stale: True if Kalshi quote exceeds staleness threshold
        poly_stale: True if Polymarket quote exceeds staleness threshold
        should_discard: True if both markets are stale (opportunity should be discarded)
        flag: "STALE" if one market is stale but not both, None otherwise
    """

    kalshi_age_seconds: float
    poly_age_seconds: float
    kalshi_stale: bool
    poly_stale: bool
    should_discard: bool
    flag: Optional[str] = None


class StaleQuoteFilter:
    """Filters opportunities based on quote staleness.

    Checks the freshness of market quotes and determines whether
    opportunities should be flagged or discarded based on staleness.

    Rules:
    - If updated_at is None, treat as stale (conservative approach)
    - If one market is stale: flag="STALE", should_discard=False
    - If both markets are stale: should_discard=True
    - Default threshold is 300 seconds (5 minutes)
    """

    def __init__(self, threshold_seconds: int = 300):
        """Initialize the stale quote filter.

        Args:
            threshold_seconds: Maximum age in seconds before a quote is
                considered stale. Default is 300 (5 minutes).
        """
        self.threshold_seconds = threshold_seconds

    def check(
        self,
        kalshi: NormalizedMarket,
        poly: NormalizedMarket,
        now: Optional[datetime] = None,
    ) -> StalenessResult:
        """Check staleness of both markets.

        Calculates the age of each market's quote and determines
        staleness flags based on the configured threshold.

        Args:
            kalshi: Normalized Kalshi market
            poly: Normalized Polymarket market
            now: Current time for age calculation. If None, uses datetime.utcnow()

        Returns:
            StalenessResult with ages, staleness flags, and discard recommendation
        """
        if now is None:
            now = datetime.now(timezone.utc)

        kalshi_age = self._calculate_age(kalshi.updated_at, now)
        poly_age = self._calculate_age(poly.updated_at, now)

        kalshi_stale = kalshi_age > self.threshold_seconds
        poly_stale = poly_age > self.threshold_seconds

        # Determine discard and flag status
        should_discard = kalshi_stale and poly_stale
        flag: Optional[str] = None

        # Flag as STALE if one (but not both) is stale
        if (kalshi_stale or poly_stale) and not should_discard:
            flag = "STALE"

        return StalenessResult(
            kalshi_age_seconds=kalshi_age,
            poly_age_seconds=poly_age,
            kalshi_stale=kalshi_stale,
            poly_stale=poly_stale,
            should_discard=should_discard,
            flag=flag,
        )

    def _calculate_age(
        self,
        updated_at: Optional[datetime],
        now: datetime,
    ) -> float:
        """Calculate age in seconds.

        If updated_at is None, returns infinity to treat as stale
        (conservative approach per design requirements).

        Args:
            updated_at: Timestamp of last update, or None if unknown
            now: Current time for age calculation

        Returns:
            Age in seconds, or float('inf') if updated_at is None
        """
        if updated_at is None:
            # Treat missing timestamp as stale (conservative)
            return float("inf")

        # Handle timezone-naive datetimes by assuming UTC
        if updated_at.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)

        delta = now - updated_at
        return delta.total_seconds()


@dataclass
class LiquidityResult:
    """Result of liquidity check.

    Contains liquidity information for both markets and flags indicating
    whether liquidity is low or the opportunity should be discarded.

    Attributes:
        kalshi_liquidity: Liquidity in USD for Kalshi market
        poly_liquidity: Liquidity in USD for Polymarket market
        kalshi_low: True if Kalshi liquidity is below minimum threshold
        poly_low: True if Polymarket liquidity is below minimum threshold
        should_discard: True if both markets are below minimum (opportunity should be discarded)
        max_executable_size: Maximum executable size based on minimum liquidity of both venues
        flag: "LOW_LIQUIDITY" if one market is low but not both, None otherwise
    """

    kalshi_liquidity: float
    poly_liquidity: float
    kalshi_low: bool
    poly_low: bool
    should_discard: bool
    max_executable_size: float
    flag: Optional[str] = None


class LiquidityFilter:
    """Filters opportunities based on liquidity.

    Checks the available liquidity in both markets and determines whether
    opportunities should be flagged or discarded based on minimum thresholds.

    Rules:
    - If one market is below threshold: flag="LOW_LIQUIDITY", should_discard=False
    - If both markets are below threshold: should_discard=True
    - max_executable_size = min(kalshi_liquidity, poly_liquidity)
    - Default minimum is $100
    """

    def __init__(self, min_liquidity_usd: float = 100.0):
        """Initialize the liquidity filter.

        Args:
            min_liquidity_usd: Minimum liquidity in USD required for a market
                to be considered liquid. Default is $100.
        """
        self.min_liquidity_usd = min_liquidity_usd

    def check(
        self,
        kalshi: NormalizedMarket,
        poly: NormalizedMarket,
    ) -> LiquidityResult:
        """Check liquidity of both markets.

        Evaluates the liquidity of each market against the configured
        minimum threshold and determines flags based on the results.

        Args:
            kalshi: Normalized Kalshi market
            poly: Normalized Polymarket market

        Returns:
            LiquidityResult with liquidity values, flags, and max executable size
        """
        kalshi_liquidity = kalshi.liquidity_usd
        poly_liquidity = poly.liquidity_usd

        kalshi_low = kalshi_liquidity < self.min_liquidity_usd
        poly_low = poly_liquidity < self.min_liquidity_usd

        # Determine discard and flag status
        should_discard = kalshi_low and poly_low
        flag: Optional[str] = None

        # Flag as LOW_LIQUIDITY if one (but not both) is low
        if (kalshi_low or poly_low) and not should_discard:
            flag = "LOW_LIQUIDITY"

        max_executable_size = self.calculate_max_size(kalshi_liquidity, poly_liquidity)

        return LiquidityResult(
            kalshi_liquidity=kalshi_liquidity,
            poly_liquidity=poly_liquidity,
            kalshi_low=kalshi_low,
            poly_low=poly_low,
            should_discard=should_discard,
            max_executable_size=max_executable_size,
            flag=flag,
        )

    def calculate_max_size(
        self,
        kalshi_liquidity: float,
        poly_liquidity: float,
    ) -> float:
        """Calculate maximum executable size based on minimum liquidity.

        The maximum executable size is constrained by the venue with
        the least liquidity, as both legs of a cross-venue trade must
        be executable.

        Args:
            kalshi_liquidity: Liquidity in USD for Kalshi market
            poly_liquidity: Liquidity in USD for Polymarket market

        Returns:
            Maximum executable size as min(kalshi_liquidity, poly_liquidity)
        """
        return min(kalshi_liquidity, poly_liquidity)



@dataclass
class FeasibilityResult:
    """Result of feasibility check.

    Contains the feasibility status and optional restructured actions
    when an opportunity can be converted to a BUY-only strategy.

    Attributes:
        is_feasible: True if the opportunity can be executed
        reason: Explanation if not feasible
        restructured_actions: Alternative BUY-only actions if restructured
    """

    is_feasible: bool
    reason: Optional[str] = None
    restructured_actions: Optional[List["TradeAction"]] = None


class FeasibilityChecker:
    """Validates opportunities against venue constraints.

    Key constraint: NO SHORT SELLING on Polymarket.

    This checker ensures that all proposed trade actions are executable
    on their respective venues. Polymarket does not support short selling,
    so any strategy requiring a SELL on Polymarket must either:
    1. Have existing inventory to sell (not implemented yet)
    2. Be restructured as a BUY-only strategy (SELL YES → BUY NO)

    Kalshi supports shorting, so SELL actions on Kalshi are always allowed.

    Strategies:
    - Polymarket YES overpriced: BUY Kalshi YES + BUY Polymarket NO
    - Kalshi YES overpriced: BUY Polymarket YES + SELL Kalshi YES
    """

    def check(
        self,
        opportunity: "Opportunity",
        inventory: Optional[Dict[str, float]] = None,
    ) -> FeasibilityResult:
        """Check if opportunity is feasible given venue constraints.

        Validates that all trade actions can be executed on their
        respective venues. Attempts to restructure Polymarket SELL
        actions as BUY-only when possible.

        Args:
            opportunity: The opportunity to check
            inventory: Optional current inventory for Polymarket sells.
                       Keys are market_id:outcome_id, values are position sizes.

        Returns:
            FeasibilityResult with feasibility status and optional
            restructured actions
        """
        if inventory is None:
            inventory = {}

        # Check if any action requires Polymarket SELL
        if not self._has_polymarket_sell(opportunity.actions):
            # No Polymarket SELL actions - opportunity is feasible as-is
            return FeasibilityResult(is_feasible=True)

        # Check if we have inventory to cover Polymarket SELL actions
        poly_sells = [
            a for a in opportunity.actions
            if a.side == "SELL" and self._is_polymarket_market(a.market_id, opportunity)
        ]

        all_covered = True
        for action in poly_sells:
            inventory_key = f"{action.market_id}:{action.outcome_id}"
            available = inventory.get(inventory_key, 0.0)
            if available < action.amount:
                all_covered = False
                break

        if all_covered:
            # Have inventory to cover all Polymarket SELL actions
            return FeasibilityResult(is_feasible=True)

        # Try to restructure as BUY-only
        restructured = self._restructure_as_buy_only(opportunity)
        if restructured is not None:
            return FeasibilityResult(
                is_feasible=True,
                restructured_actions=restructured,
            )

        # Cannot restructure - opportunity is infeasible
        return FeasibilityResult(
            is_feasible=False,
            reason="Requires SELL on Polymarket without inventory and cannot restructure",
        )

    def _has_polymarket_sell(self, actions: List["TradeAction"]) -> bool:
        """Check if any action is a Polymarket SELL.

        Identifies actions that would require short selling on Polymarket,
        which is not supported by the venue.

        Args:
            actions: List of trade actions to check

        Returns:
            True if any action is a SELL on a Polymarket market
        """
        for action in actions:
            if action.side == "SELL":
                # Check if this is a Polymarket market by market_id pattern
                # Polymarket market IDs are typically UUIDs or contain "poly"
                # For now, we check based on metadata in the opportunity
                # This is a simplified check - in practice, we'd look up the market
                market_id_lower = action.market_id.lower()
                if "poly" in market_id_lower or self._looks_like_polymarket_id(action.market_id):
                    return True
        return False

    def _is_polymarket_market(self, market_id: str, opportunity: "Opportunity") -> bool:
        """Check if a market_id belongs to Polymarket.

        Uses opportunity metadata to determine the exchange for a market.

        Args:
            market_id: The market ID to check
            opportunity: The opportunity containing metadata

        Returns:
            True if the market is on Polymarket
        """
        # Check metadata for exchange info
        metadata = opportunity.metadata or {}

        # Check if market_id matches polymarket_market_id in metadata
        poly_market_id = metadata.get("polymarket_market_id")
        if poly_market_id and market_id == poly_market_id:
            return True

        # Check market_exchanges mapping if available
        market_exchanges = metadata.get("market_exchanges", {})
        if market_id in market_exchanges:
            return market_exchanges[market_id] == "polymarket"

        # Fallback: check market_id pattern
        market_id_lower = market_id.lower()
        if "poly" in market_id_lower:
            return True

        return self._looks_like_polymarket_id(market_id)

    def _looks_like_polymarket_id(self, market_id: str) -> bool:
        """Heuristic check if market_id looks like a Polymarket ID.

        Polymarket uses long hex strings or UUIDs for market IDs,
        while Kalshi uses shorter alphanumeric tickers.

        Args:
            market_id: The market ID to check

        Returns:
            True if the ID pattern suggests Polymarket
        """
        # Polymarket IDs are typically long hex strings (64+ chars)
        # or UUIDs (36 chars with dashes)
        if len(market_id) >= 36:
            # Check if it's a UUID pattern
            if "-" in market_id and len(market_id) == 36:
                return True
            # Check if it's a long hex string
            if len(market_id) >= 64:
                try:
                    int(market_id, 16)
                    return True
                except ValueError:
                    pass
        return False

    def _restructure_as_buy_only(
        self,
        opportunity: "Opportunity",
    ) -> Optional[List["TradeAction"]]:
        """Attempt to restructure opportunity as BUY-only.

        When Polymarket YES is overpriced, the original strategy might be:
          SELL Polymarket YES + BUY Kalshi YES

        This can be restructured to:
          BUY Polymarket NO + BUY Kalshi YES

        The economic exposure is equivalent because:
          SELL YES ≡ BUY NO (in a binary market)

        Args:
            opportunity: The opportunity to restructure

        Returns:
            List of restructured TradeActions if successful, None if cannot restructure
        """
        from predarb.models import TradeAction

        restructured: List[TradeAction] = []

        for action in opportunity.actions:
            if action.side == "SELL" and self._is_polymarket_market(action.market_id, opportunity):
                # Convert SELL YES to BUY NO (or SELL NO to BUY YES)
                outcome_lower = action.outcome_id.lower()
                if outcome_lower in ("yes", "y"):
                    new_outcome = "NO"
                elif outcome_lower in ("no", "n"):
                    new_outcome = "YES"
                else:
                    # Cannot restructure non-binary outcomes
                    return None

                # Calculate the complementary price
                # If selling YES at 0.60, buying NO should be at ~0.40
                new_limit_price = 1.0 - action.limit_price

                restructured.append(TradeAction(
                    market_id=action.market_id,
                    outcome_id=new_outcome,
                    side="BUY",
                    amount=action.amount,
                    limit_price=new_limit_price,
                ))
            else:
                # Keep non-Polymarket actions or BUY actions as-is
                restructured.append(action)

        return restructured

    def _generate_strategy(
        self,
        kalshi: NormalizedMarket,
        poly: NormalizedMarket,
        kalshi_cheaper: bool,
    ) -> List["TradeAction"]:
        """Generate feasible strategy based on price comparison.

        Creates trade actions that respect venue constraints:
        - Polymarket: BUY only (no short selling)
        - Kalshi: BUY or SELL (supports shorting)

        Strategies:
        - If Polymarket YES overpriced (kalshi_cheaper=True):
            BUY Kalshi YES + BUY Polymarket NO
        - If Kalshi YES overpriced (kalshi_cheaper=False):
            BUY Polymarket YES + SELL Kalshi YES

        Args:
            kalshi: Normalized Kalshi market
            poly: Normalized Polymarket market
            kalshi_cheaper: True if Kalshi YES is cheaper than Polymarket YES

        Returns:
            List of TradeActions implementing the feasible strategy
        """
        from predarb.models import TradeAction

        actions: List[TradeAction] = []

        if kalshi_cheaper:
            # Polymarket YES is overpriced
            # Strategy: BUY Kalshi YES + BUY Polymarket NO
            # This is equivalent to: BUY Kalshi YES + SELL Polymarket YES
            # but uses BUY-only on Polymarket

            # BUY Kalshi YES at the ask price
            actions.append(TradeAction(
                market_id=kalshi.market_id,
                outcome_id="YES",
                side="BUY",
                amount=1.0,  # Amount will be adjusted by caller
                limit_price=kalshi.yes_ask,
            ))

            # BUY Polymarket NO at the ask price
            # (equivalent exposure to SELL Polymarket YES)
            actions.append(TradeAction(
                market_id=poly.market_id,
                outcome_id="NO",
                side="BUY",
                amount=1.0,  # Amount will be adjusted by caller
                limit_price=poly.no_ask,
            ))
        else:
            # Kalshi YES is overpriced
            # Strategy: BUY Polymarket YES + SELL Kalshi YES
            # Kalshi supports shorting, so SELL is allowed

            # BUY Polymarket YES at the ask price
            actions.append(TradeAction(
                market_id=poly.market_id,
                outcome_id="YES",
                side="BUY",
                amount=1.0,  # Amount will be adjusted by caller
                limit_price=poly.yes_ask,
            ))

            # SELL Kalshi YES at the bid price
            # (Kalshi supports shorting)
            actions.append(TradeAction(
                market_id=kalshi.market_id,
                outcome_id="YES",
                side="SELL",
                amount=1.0,  # Amount will be adjusted by caller
                limit_price=kalshi.yes_bid,
            ))

        return actions



    def detect_price_discrepancy(
        kalshi: NormalizedMarket,
        poly: NormalizedMarket,
        config: CrossVenueDetectorConfig,
        price_extractor: PriceExtractor,
        feasibility_checker: FeasibilityChecker,
    ) -> Optional[Opportunity]:
        """Detect price discrepancy between venues.

        Identifies arbitrage opportunities when the same event has different
        prices on Kalshi vs Polymarket. Calculates net edge after accounting
        for fees on both venues.

        Fee structure:
        - Kalshi: 7 basis points (0.07%)
        - Polymarket: 10 basis points per side (0.10% * 2 = 0.20%)
        - Slippage: configurable (default 20 basis points)

        Strategies (respecting Polymarket no-short-selling constraint):
        - If Kalshi YES cheaper: BUY Kalshi YES + BUY Polymarket NO
        - If Polymarket YES cheaper: BUY Polymarket YES + SELL Kalshi YES

        Args:
            kalshi: Normalized Kalshi market
            poly: Normalized Polymarket market
            config: Detector configuration with thresholds and fee settings
            price_extractor: For extracting prices from normalized markets
            feasibility_checker: For generating feasible strategies

        Returns:
            Opportunity if price discrepancy detected with positive net edge,
            None otherwise (below threshold, non-tradeable, or negative edge)

        Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5
        """
        # Step 1: Extract prices from both markets
        kalshi_prices = price_extractor.extract(kalshi)
        poly_prices = price_extractor.extract(poly)

        # If either market is non-tradeable, skip
        if kalshi_prices is None or poly_prices is None:
            return None

        # Step 2: Calculate price difference using mid prices
        kalshi_yes_mid = kalshi_prices.yes_mid
        poly_yes_mid = poly_prices.yes_mid
        price_diff = abs(kalshi_yes_mid - poly_yes_mid)

        # Step 3: Apply threshold check (Requirement 2.2)
        if price_diff < config.min_price_diff_threshold:
            return None

        # Step 4: Determine which venue is cheaper
        kalshi_cheaper = kalshi_yes_mid < poly_yes_mid

        # Step 5: Calculate gross edge (the price difference is our gross edge)
        gross_edge = price_diff

        # Step 6: Calculate fees (Requirement 2.3)
        # For simplicity, we use a notional amount of 1.0 (unit trade)
        # Fees are proportional to the trade amount
        amount = 1.0

        # Kalshi fees: 7 basis points
        kalshi_fees = amount * (config.kalshi_fee_bps / 10000.0)

        # Polymarket fees: 10 basis points per side (buy and sell equivalent)
        # When we BUY Polymarket NO (or YES), we pay fees on entry
        # The "per side" means we pay on both entry and exit, so 2x
        poly_fees = amount * (config.polymarket_fee_bps / 10000.0) * 2

        # Slippage estimate
        slippage = amount * (config.slippage_bps / 10000.0)

        # Total fees
        total_fees = kalshi_fees + poly_fees + slippage

        # Step 7: Calculate net edge (Requirement 2.3)
        net_edge = gross_edge - total_fees

        # Step 8: Discard if net_edge <= 0 (Requirement 2.5)
        if net_edge <= 0:
            return None

        # Step 9: Generate TradeActions using FeasibilityChecker (Requirement 2.4)
        actions = feasibility_checker._generate_strategy(kalshi, poly, kalshi_cheaper)

        # Step 10: Build metadata with venue-specific details (Requirement 6.4)
        metadata: Dict[str, object] = {
            "kalshi_price": kalshi_yes_mid,
            "polymarket_price": poly_yes_mid,
            "price_diff": price_diff,
            "gross_edge": gross_edge,
            "fees_kalshi": kalshi_fees,
            "fees_polymarket": poly_fees,
            "slippage": slippage,
            "total_fees": total_fees,
            "kalshi_market_id": kalshi.market_id,
            "polymarket_market_id": poly.market_id,
            "market_exchanges": {
                kalshi.market_id: "kalshi",
                poly.market_id: "polymarket",
            },
            "kalshi_cheaper": kalshi_cheaper,
        }

        # Step 11: Build description
        if kalshi_cheaper:
            description = (
                f"Cross-venue price discrepancy: Kalshi YES ({kalshi_yes_mid:.2%}) "
                f"cheaper than Polymarket YES ({poly_yes_mid:.2%}). "
                f"Strategy: BUY Kalshi YES + BUY Polymarket NO. "
                f"Net edge: {net_edge:.4f} ({net_edge*100:.2f}%)"
            )
        else:
            description = (
                f"Cross-venue price discrepancy: Polymarket YES ({poly_yes_mid:.2%}) "
                f"cheaper than Kalshi YES ({kalshi_yes_mid:.2%}). "
                f"Strategy: BUY Polymarket YES + SELL Kalshi YES. "
                f"Net edge: {net_edge:.4f} ({net_edge*100:.2f}%)"
            )

        # Step 12: Return Opportunity with type="CROSS_VENUE_PRICE" (Requirement 6.1)
        return Opportunity(
            type="CROSS_VENUE_PRICE",
            market_ids=[kalshi.market_id, poly.market_id],
            description=description,
            net_edge=net_edge,
            actions=actions,
            metadata=metadata,
        )


def detect_parity_violation(
    kalshi: NormalizedMarket,
    poly: NormalizedMarket,
    config: CrossVenueDetectorConfig,
    price_extractor: PriceExtractor,
) -> Optional[Opportunity]:
    """Detect cross-venue parity violation.

    A parity violation occurs when buying YES on one venue and NO on another
    costs less than $1.00 (guaranteed profit at settlement).

    Two scenarios to check:
    1. Kalshi YES ask + Polymarket NO ask < 1.0 - fees
    2. Polymarket YES ask + Kalshi NO ask < 1.0 - fees

    Both scenarios are BUY-only, so no short-selling constraint issues.

    Fee structure:
    - Kalshi: 7 basis points (0.07%)
    - Polymarket: 10 basis points per side (0.10% * 2 = 0.20%)
    - Slippage: configurable (default 20 basis points)

    Args:
        kalshi: Normalized Kalshi market
        poly: Normalized Polymarket market
        config: Detector configuration with thresholds and fee settings
        price_extractor: For extracting prices from normalized markets

    Returns:
        Opportunity if parity violation detected with positive guaranteed profit,
        None otherwise (no violation, non-tradeable, or negative profit after fees)

    Validates: Requirements 4.1, 4.2, 4.3, 4.4, 4.5
    """
    # Step 1: Extract prices from both markets
    kalshi_prices = price_extractor.extract(kalshi)
    poly_prices = price_extractor.extract(poly)

    # If either market is non-tradeable, skip
    if kalshi_prices is None or poly_prices is None:
        return None

    # Step 2: Calculate fees for a unit trade
    amount = 1.0

    # Kalshi fees: 7 basis points
    kalshi_fees = amount * (config.kalshi_fee_bps / 10000.0)

    # Polymarket fees: 10 basis points per side (buy and sell equivalent)
    poly_fees = amount * (config.polymarket_fee_bps / 10000.0) * 2

    # Slippage estimate
    slippage = amount * (config.slippage_bps / 10000.0)

    # Total fees for both legs
    total_fees = kalshi_fees + poly_fees + slippage

    # Step 3: Check Scenario 1 - Kalshi YES + Polymarket NO
    # Buy YES on Kalshi at ask, Buy NO on Polymarket at ask
    scenario1_cost = kalshi_prices.yes_ask + poly_prices.no_ask
    scenario1_profit = 1.0 - scenario1_cost - total_fees

    # Step 4: Check Scenario 2 - Polymarket YES + Kalshi NO
    # Buy YES on Polymarket at ask, Buy NO on Kalshi at ask
    scenario2_cost = poly_prices.yes_ask + kalshi_prices.no_ask
    scenario2_profit = 1.0 - scenario2_cost - total_fees

    # Step 5: Determine best scenario (if any has positive profit)
    best_scenario: Optional[int] = None
    best_profit = 0.0
    best_cost = 0.0

    if scenario1_profit > 0 and scenario1_profit >= scenario2_profit:
        best_scenario = 1
        best_profit = scenario1_profit
        best_cost = scenario1_cost
    elif scenario2_profit > 0:
        best_scenario = 2
        best_profit = scenario2_profit
        best_cost = scenario2_cost

    # No profitable parity violation found
    if best_scenario is None:
        return None

    # Step 6: Generate TradeActions for the best scenario (Requirement 4.5)
    actions: List[TradeAction] = []

    if best_scenario == 1:
        # Scenario 1: BUY Kalshi YES + BUY Polymarket NO
        actions.append(TradeAction(
            market_id=kalshi.market_id,
            outcome_id="YES",
            side="BUY",
            amount=amount,
            limit_price=kalshi_prices.yes_ask,
        ))
        actions.append(TradeAction(
            market_id=poly.market_id,
            outcome_id="NO",
            side="BUY",
            amount=amount,
            limit_price=poly_prices.no_ask,
        ))
        strategy_desc = "BUY Kalshi YES + BUY Polymarket NO"
        kalshi_outcome = "YES"
        kalshi_price = kalshi_prices.yes_ask
        poly_outcome = "NO"
        poly_price = poly_prices.no_ask
    else:
        # Scenario 2: BUY Polymarket YES + BUY Kalshi NO
        actions.append(TradeAction(
            market_id=poly.market_id,
            outcome_id="YES",
            side="BUY",
            amount=amount,
            limit_price=poly_prices.yes_ask,
        ))
        actions.append(TradeAction(
            market_id=kalshi.market_id,
            outcome_id="NO",
            side="BUY",
            amount=amount,
            limit_price=kalshi_prices.no_ask,
        ))
        strategy_desc = "BUY Polymarket YES + BUY Kalshi NO"
        kalshi_outcome = "NO"
        kalshi_price = kalshi_prices.no_ask
        poly_outcome = "YES"
        poly_price = poly_prices.yes_ask

    # Step 7: Build metadata with venue-specific details (Requirement 6.4)
    metadata: Dict[str, object] = {
        "kalshi_yes_ask": kalshi_prices.yes_ask,
        "kalshi_no_ask": kalshi_prices.no_ask,
        "poly_yes_ask": poly_prices.yes_ask,
        "poly_no_ask": poly_prices.no_ask,
        "total_cost": best_cost,
        "guaranteed_profit": best_profit,
        "fees_kalshi": kalshi_fees,
        "fees_polymarket": poly_fees,
        "slippage": slippage,
        "fees_total": total_fees,
        "scenario": best_scenario,
        "kalshi_market_id": kalshi.market_id,
        "polymarket_market_id": poly.market_id,
        "market_exchanges": {
            kalshi.market_id: "kalshi",
            poly.market_id: "polymarket",
        },
        "kalshi_outcome": kalshi_outcome,
        "kalshi_price": kalshi_price,
        "poly_outcome": poly_outcome,
        "poly_price": poly_price,
    }

    # Step 8: Build description
    description = (
        f"Cross-venue parity violation: {strategy_desc}. "
        f"Total cost: {best_cost:.4f} ({best_cost*100:.2f}%). "
        f"Guaranteed profit: {best_profit:.4f} ({best_profit*100:.2f}%)"
    )

    # Step 9: Return Opportunity with type="CROSS_VENUE_PARITY" (Requirement 6.1)
    return Opportunity(
        type="CROSS_VENUE_PARITY",
        market_ids=[kalshi.market_id, poly.market_id],
        description=description,
        net_edge=best_profit,
        actions=actions,
        metadata=metadata,
    )






import re
from typing import Tuple


@dataclass
class BucketMapping:
    """Mapping between Polymarket range and Kalshi buckets.

    Represents the relationship between a Polymarket range market
    (e.g., "BTC between $90k-$100k") and the corresponding Kalshi
    bucket contracts that cover the same range.

    Attributes:
        polymarket_market: The Polymarket range market
        kalshi_buckets: List of Kalshi bucket contracts covering the range
        range_start: Lower bound of the range (e.g., 90000 for $90k)
        range_end: Upper bound of the range (e.g., 100000 for $100k)
    """

    polymarket_market: NormalizedMarket
    kalshi_buckets: List[NormalizedMarket]
    range_start: float
    range_end: float


class RangeBucketAnalyzer:
    """Analyzes range market vs bucket contract arbitrage.

    Polymarket range markets (e.g., "BTC between $90k-$100k")
    map to multiple Kalshi bucket contracts. This analyzer:

    1. Identifies when a Polymarket range maps to Kalshi buckets
    2. Compares sum of Kalshi bucket YES prices to Polymarket price
    3. Detects arbitrage when |sum - poly_price| > threshold
    4. Generates multi-leg trade actions respecting short constraints

    Key constraint: NO SHORT SELLING on Polymarket.
    - If Kalshi underpriced: BUY all Kalshi buckets
    - If Kalshi overpriced: BUY Polymarket + SELL Kalshi buckets

    Validates: Requirements 5.1, 5.2, 5.3, 5.4, 5.5
    """

    # Common patterns for range markets
    RANGE_PATTERNS = [
        # "BTC between $90k-$100k" or "BTC $90k-$100k"
        r"(?:between\s+)?\$?([\d,.]+)(k|m)?\s*[-–—to]+\s*\$?([\d,.]+)(k|m)?",
        # "90000 to 100000" or "90,000-100,000"
        r"([\d,]+)\s*[-–—to]+\s*([\d,]+)",
        # "above $90k" or "below $100k" (single bound)
        r"(?:above|over|greater than)\s+\$?([\d,.]+)(k|m)?",
        r"(?:below|under|less than)\s+\$?([\d,.]+)(k|m)?",
    ]

    def __init__(self, config: CrossVenueDetectorConfig):
        """Initialize the range bucket analyzer.

        Args:
            config: Detector configuration with bucket_sum_threshold and fee settings
        """
        self.config = config
        self.price_extractor = PriceExtractor()

    def identify_bucket_mapping(
        self,
        poly_market: NormalizedMarket,
        kalshi_markets: List[NormalizedMarket],
    ) -> Optional[BucketMapping]:
        """Identify if Polymarket range maps to Kalshi buckets.

        Analyzes the Polymarket market question to extract range bounds,
        then finds Kalshi bucket contracts that fall within that range.

        Args:
            poly_market: Polymarket range market to analyze
            kalshi_markets: List of potential Kalshi bucket contracts

        Returns:
            BucketMapping if a valid mapping is found, None otherwise

        Validates: Requirement 5.1
        """
        # Step 1: Extract range from Polymarket market question
        range_bounds = self._extract_range_from_question(poly_market.question)
        if range_bounds is None:
            return None

        range_start, range_end = range_bounds

        # Step 2: Find Kalshi buckets that fall within this range
        matching_buckets: List[NormalizedMarket] = []

        for kalshi_market in kalshi_markets:
            if kalshi_market.exchange != "kalshi":
                continue

            # Check if this Kalshi market is a bucket within the range
            bucket_bounds = self._extract_range_from_question(kalshi_market.question)
            if bucket_bounds is None:
                continue

            bucket_start, bucket_end = bucket_bounds

            # Check if bucket overlaps with the Polymarket range
            if self._ranges_overlap(range_start, range_end, bucket_start, bucket_end):
                matching_buckets.append(kalshi_market)

        # Step 3: Require at least one matching bucket
        if not matching_buckets:
            return None

        # Step 4: Sort buckets by their start value for consistent ordering
        matching_buckets.sort(key=lambda m: self._extract_range_from_question(m.question)[0]
                             if self._extract_range_from_question(m.question) else 0)

        return BucketMapping(
            polymarket_market=poly_market,
            kalshi_buckets=matching_buckets,
            range_start=range_start,
            range_end=range_end,
        )

    def detect_bucket_arbitrage(
        self,
        mapping: BucketMapping,
        price_extractor: Optional[PriceExtractor] = None,
    ) -> Optional[Opportunity]:
        """Detect arbitrage between range and buckets.

        Compares sum of Kalshi bucket YES prices to Polymarket outcome price.
        If |sum - poly_price| > bucket_sum_threshold, detect arbitrage.

        Args:
            mapping: BucketMapping with Polymarket range and Kalshi buckets
            price_extractor: Optional PriceExtractor (uses self.price_extractor if None)

        Returns:
            Opportunity if arbitrage detected with positive net edge,
            None otherwise

        Validates: Requirements 5.2, 5.5
        """
        if price_extractor is None:
            price_extractor = self.price_extractor

        # Step 1: Extract Polymarket price
        poly_prices = price_extractor.extract(mapping.polymarket_market)
        if poly_prices is None:
            return None

        poly_yes_price = poly_prices.yes_mid

        # Step 2: Calculate sum of Kalshi bucket YES prices
        bucket_sum = self._calculate_bucket_sum(mapping.kalshi_buckets, price_extractor)
        if bucket_sum is None:
            return None

        # Step 3: Calculate price difference
        price_diff = abs(bucket_sum - poly_yes_price)

        # Step 4: Apply threshold check (Requirement 5.2)
        if price_diff < self.config.bucket_sum_threshold:
            return None

        # Step 5: Determine direction - is Kalshi underpriced or overpriced?
        kalshi_underpriced = bucket_sum < poly_yes_price

        # Step 6: Calculate gross edge
        gross_edge = price_diff

        # Step 7: Calculate fees across all legs (Requirement 5.5)
        num_kalshi_legs = len(mapping.kalshi_buckets)
        amount = 1.0

        # Kalshi fees: 7 bps per leg
        kalshi_fees = num_kalshi_legs * amount * (self.config.kalshi_fee_bps / 10000.0)

        # Polymarket fees: 10 bps per side (buy and sell equivalent)
        poly_fees = amount * (self.config.polymarket_fee_bps / 10000.0) * 2

        # Slippage: apply to all legs
        slippage = (num_kalshi_legs + 1) * amount * (self.config.slippage_bps / 10000.0)

        total_fees = kalshi_fees + poly_fees + slippage

        # Step 8: Calculate net edge
        net_edge = gross_edge - total_fees

        # Step 9: Discard if net_edge <= 0
        if net_edge <= 0:
            return None

        # Step 10: Generate trade actions (Requirement 5.3, 5.4)
        actions = self._generate_bucket_actions(
            mapping, kalshi_underpriced, price_extractor
        )

        # Step 11: Build metadata
        bucket_ids = [b.market_id for b in mapping.kalshi_buckets]
        metadata: Dict[str, object] = {
            "polymarket_range_price": poly_yes_price,
            "kalshi_bucket_sum": bucket_sum,
            "bucket_count": num_kalshi_legs,
            "bucket_ids": bucket_ids,
            "price_diff": price_diff,
            "gross_edge": gross_edge,
            "fees_kalshi": kalshi_fees,
            "fees_polymarket": poly_fees,
            "slippage": slippage,
            "total_fees": total_fees,
            "kalshi_underpriced": kalshi_underpriced,
            "range_start": mapping.range_start,
            "range_end": mapping.range_end,
            "polymarket_market_id": mapping.polymarket_market.market_id,
            "market_exchanges": {
                mapping.polymarket_market.market_id: "polymarket",
                **{b.market_id: "kalshi" for b in mapping.kalshi_buckets},
            },
        }

        # Step 12: Build description
        if kalshi_underpriced:
            strategy_desc = f"BUY {num_kalshi_legs} Kalshi buckets"
        else:
            strategy_desc = f"BUY Polymarket range + SELL {num_kalshi_legs} Kalshi buckets"

        description = (
            f"Range bucket arbitrage: Polymarket range ({poly_yes_price:.2%}) vs "
            f"Kalshi bucket sum ({bucket_sum:.2%}). "
            f"Strategy: {strategy_desc}. "
            f"Net edge: {net_edge:.4f} ({net_edge*100:.2f}%)"
        )

        # Step 13: Build market_ids list
        market_ids = [mapping.polymarket_market.market_id] + bucket_ids

        # Step 14: Return Opportunity with type="RANGE_BUCKET"
        return Opportunity(
            type="RANGE_BUCKET",
            market_ids=market_ids,
            description=description,
            net_edge=net_edge,
            actions=actions,
            metadata=metadata,
        )

    def _calculate_bucket_sum(
        self,
        buckets: List[NormalizedMarket],
        price_extractor: Optional[PriceExtractor] = None,
    ) -> Optional[float]:
        """Calculate sum of bucket YES prices.

        Sums the YES mid prices of all bucket contracts. Returns None
        if any bucket is non-tradeable (missing prices).

        Args:
            buckets: List of Kalshi bucket contracts
            price_extractor: Optional PriceExtractor (uses self.price_extractor if None)

        Returns:
            Sum of YES mid prices, or None if any bucket is non-tradeable
        """
        if price_extractor is None:
            price_extractor = self.price_extractor

        if not buckets:
            return None

        total = 0.0
        for bucket in buckets:
            prices = price_extractor.extract(bucket)
            if prices is None:
                # Non-tradeable bucket - cannot calculate sum
                return None
            total += prices.yes_mid

        return total

    def _generate_bucket_actions(
        self,
        mapping: BucketMapping,
        kalshi_underpriced: bool,
        price_extractor: Optional[PriceExtractor] = None,
    ) -> List[TradeAction]:
        """Generate trade actions for bucket arbitrage.

        Respects the NO SHORT SELLING constraint on Polymarket:
        - If Kalshi underpriced: BUY all Kalshi buckets (no Polymarket action needed
          for pure arbitrage, but we include SELL Poly YES equivalent as BUY Poly NO)
        - If Kalshi overpriced: BUY Polymarket YES + SELL all Kalshi buckets

        Args:
            mapping: BucketMapping with Polymarket range and Kalshi buckets
            kalshi_underpriced: True if Kalshi bucket sum < Polymarket price
            price_extractor: Optional PriceExtractor (uses self.price_extractor if None)

        Returns:
            List of TradeActions for the arbitrage strategy

        Validates: Requirements 5.3, 5.4
        """
        if price_extractor is None:
            price_extractor = self.price_extractor

        actions: List[TradeAction] = []
        amount = 1.0  # Unit trade, will be adjusted by caller

        if kalshi_underpriced:
            # Requirement 5.3: Kalshi buckets underpriced relative to Polymarket
            # Strategy: BUY all Kalshi buckets + BUY Polymarket NO
            # (BUY Poly NO is equivalent to SELL Poly YES, respecting no-short constraint)

            # BUY all Kalshi buckets
            for bucket in mapping.kalshi_buckets:
                bucket_prices = price_extractor.extract(bucket)
                if bucket_prices is None:
                    continue

                actions.append(TradeAction(
                    market_id=bucket.market_id,
                    outcome_id="YES",
                    side="BUY",
                    amount=amount,
                    limit_price=bucket_prices.yes_ask,
                ))

            # BUY Polymarket NO (equivalent to SELL Polymarket YES)
            poly_prices = price_extractor.extract(mapping.polymarket_market)
            if poly_prices is not None:
                actions.append(TradeAction(
                    market_id=mapping.polymarket_market.market_id,
                    outcome_id="NO",
                    side="BUY",
                    amount=amount,
                    limit_price=poly_prices.no_ask,
                ))

        else:
            # Requirement 5.4: Kalshi buckets overpriced relative to Polymarket
            # Strategy: BUY Polymarket YES + SELL all Kalshi buckets
            # (Kalshi supports shorting, so SELL is allowed)

            # BUY Polymarket YES
            poly_prices = price_extractor.extract(mapping.polymarket_market)
            if poly_prices is not None:
                actions.append(TradeAction(
                    market_id=mapping.polymarket_market.market_id,
                    outcome_id="YES",
                    side="BUY",
                    amount=amount,
                    limit_price=poly_prices.yes_ask,
                ))

            # SELL all Kalshi buckets
            for bucket in mapping.kalshi_buckets:
                bucket_prices = price_extractor.extract(bucket)
                if bucket_prices is None:
                    continue

                actions.append(TradeAction(
                    market_id=bucket.market_id,
                    outcome_id="YES",
                    side="SELL",
                    amount=amount,
                    limit_price=bucket_prices.yes_bid,
                ))

        return actions

    def _extract_range_from_question(
        self,
        question: str,
    ) -> Optional[Tuple[float, float]]:
        """Extract numeric range bounds from a market question.

        Parses market questions to find range specifications like:
        - "BTC between $90k-$100k"
        - "Price 90000 to 100000"
        - "Value $90,000-$100,000"

        Args:
            question: Market question text to parse

        Returns:
            Tuple of (range_start, range_end) if found, None otherwise
        """
        if not question:
            return None

        question_lower = question.lower()

        # Pattern 1: "between $90k-$100k" with optional k/m suffix
        pattern1 = r"(?:between\s+)?\$?([\d,.]+)(k|m)?\s*[-–—to]+\s*\$?([\d,.]+)(k|m)?"
        match = re.search(pattern1, question_lower, re.IGNORECASE)
        if match:
            num1, suffix1, num2, suffix2 = match.groups()
            start = self._parse_number_with_suffix(num1, suffix1)
            end = self._parse_number_with_suffix(num2, suffix2)
            if start is not None and end is not None:
                if start > end:
                    start, end = end, start
                return (start, end)

        # Pattern 2: "between X and Y" with optional k/m suffix
        pattern2_and = r"(?:between\s+)?\$?([\d,.]+)(k|m)?\s+and\s+\$?([\d,.]+)(k|m)?"
        match = re.search(pattern2_and, question_lower, re.IGNORECASE)
        if match:
            num1, suffix1, num2, suffix2 = match.groups()
            start = self._parse_number_with_suffix(num1, suffix1)
            end = self._parse_number_with_suffix(num2, suffix2)
            if start is not None and end is not None:
                if start > end:
                    start, end = end, start
                return (start, end)

        # Pattern 3: "90000 to 100000" (plain numbers)
        pattern3 = r"([\d,]+)\s*[-–—to]+\s*([\d,]+)"
        match = re.search(pattern3, question_lower)
        if match:
            start = self._parse_number(match.group(1))
            end = self._parse_number(match.group(2))
            if start is not None and end is not None:
                if start > end:
                    start, end = end, start
                return (start, end)

        # Pattern 4: "above $90k" (single bound, open upper)
        pattern4 = r"(?:above|over|greater than)\s+\$?([\d,.]+)(k|m)?"
        match = re.search(pattern4, question_lower, re.IGNORECASE)
        if match:
            num, suffix = match.groups()
            value = self._parse_number_with_suffix(num, suffix)
            if value is not None:
                return (value, float("inf"))

        # Pattern 5: "below $100k" (single bound, open lower)
        pattern5 = r"(?:below|under|less than)\s+\$?([\d,.]+)(k|m)?"
        match = re.search(pattern5, question_lower, re.IGNORECASE)
        if match:
            num, suffix = match.groups()
            value = self._parse_number_with_suffix(num, suffix)
            if value is not None:
                return (0.0, value)

        return None

    def _parse_number_with_suffix(
        self,
        text: str,
        suffix: Optional[str],
    ) -> Optional[float]:
        """Parse a number with an optional k/m suffix.

        Args:
            text: Text containing a number (e.g., "90", "90,000")
            suffix: Optional suffix ('k' or 'm')

        Returns:
            Parsed float value, or None if parsing fails
        """
        if not text:
            return None

        # Remove commas and whitespace
        text = text.replace(",", "").replace(" ", "").strip()

        try:
            value = float(text)
        except ValueError:
            return None

        # Apply suffix multiplier
        if suffix:
            suffix_lower = suffix.lower()
            if suffix_lower == "k":
                value *= 1000.0
            elif suffix_lower == "m":
                value *= 1000000.0

        return value

    def _parse_number(self, text: str) -> Optional[float]:
        """Parse a number from text, handling k/m suffixes and commas.

        Args:
            text: Text containing a number (e.g., "90k", "90,000", "90000")

        Returns:
            Parsed float value, or None if parsing fails
        """
        if not text:
            return None

        # Remove commas and whitespace
        text = text.replace(",", "").replace(" ", "").strip()

        # Handle k/m suffixes
        multiplier = 1.0
        if text.endswith("k"):
            multiplier = 1000.0
            text = text[:-1]
        elif text.endswith("m"):
            multiplier = 1000000.0
            text = text[:-1]

        try:
            return float(text) * multiplier
        except ValueError:
            return None

    def _ranges_overlap(
        self,
        range1_start: float,
        range1_end: float,
        range2_start: float,
        range2_end: float,
    ) -> bool:
        """Check if two ranges overlap.

        Args:
            range1_start: Start of first range
            range1_end: End of first range
            range2_start: Start of second range
            range2_end: End of second range

        Returns:
            True if ranges overlap, False otherwise
        """
        # Ranges overlap if one starts before the other ends
        return range1_start <= range2_end and range2_start <= range1_end


class OpportunityClassifier:
    """Classifies and formats arbitrage opportunities.

    Creates standardized Opportunity objects from detection results,
    ensuring consistent output format for downstream consumers
    (risk manager, broker).

    Responsibilities:
    - Map detection types to correct opportunity type strings
    - Include both market IDs in market_ids list
    - Merge staleness and liquidity info into metadata
    - Include flags list (["STALE"], ["LOW_LIQUIDITY"], or [])
    - Ensure all required metadata fields are present

    Validates: Requirements 6.1, 6.2, 6.3, 6.4, 6.5
    """

    OPPORTUNITY_TYPES = {
        "price_discrepancy": "CROSS_VENUE_PRICE",
        "parity_violation": "CROSS_VENUE_PARITY",
        "range_bucket": "RANGE_BUCKET",
    }

    def classify(
        self,
        detection_type: str,
        kalshi: NormalizedMarket,
        poly: NormalizedMarket,
        actions: List[TradeAction],
        net_edge: float,
        metadata: Dict[str, Any],
        staleness: StalenessResult,
        liquidity: LiquidityResult,
    ) -> Opportunity:
        """Create classified Opportunity object.

        Maps the detection type to the correct opportunity type string,
        builds complete metadata including staleness and liquidity info,
        and creates a standardized Opportunity object.

        Args:
            detection_type: Type of detection ("price_discrepancy",
                "parity_violation", or "range_bucket")
            kalshi: Normalized Kalshi market
            poly: Normalized Polymarket market
            actions: List of TradeAction objects for the strategy
            net_edge: Expected profit after all fees and slippage
            metadata: Detection-specific metadata (prices, fees, etc.)
            staleness: Result from StaleQuoteFilter.check()
            liquidity: Result from LiquidityFilter.check()

        Returns:
            Opportunity object with:
            - Correct opportunity type (Requirement 6.1)
            - Both market IDs (Requirement 6.2)
            - Complete TradeActions (Requirement 6.3)
            - Full metadata with venue-specific details (Requirement 6.4)
            - net_edge set to expected profit (Requirement 6.5)

        Raises:
            ValueError: If detection_type is not recognized
        """
        # Step 1: Map detection type to opportunity type (Requirement 6.1)
        opportunity_type = self.OPPORTUNITY_TYPES.get(detection_type)
        if opportunity_type is None:
            raise ValueError(
                f"Unknown detection type: {detection_type}. "
                f"Valid types: {list(self.OPPORTUNITY_TYPES.keys())}"
            )

        # Step 2: Build market_ids list with both IDs (Requirement 6.2)
        market_ids = [kalshi.market_id, poly.market_id]

        # Step 3: Build complete metadata (Requirement 6.4)
        complete_metadata = self._build_metadata(
            kalshi=kalshi,
            poly=poly,
            staleness=staleness,
            liquidity=liquidity,
            extra=metadata,
        )

        # Step 4: Build description based on detection type
        description = self._build_description(
            detection_type=detection_type,
            kalshi=kalshi,
            poly=poly,
            net_edge=net_edge,
            metadata=complete_metadata,
        )

        # Step 5: Create and return Opportunity object
        return Opportunity(
            type=opportunity_type,
            market_ids=market_ids,
            description=description,
            net_edge=net_edge,
            actions=actions,
            metadata=complete_metadata,
        )

    def _build_metadata(
        self,
        kalshi: NormalizedMarket,
        poly: NormalizedMarket,
        staleness: StalenessResult,
        liquidity: LiquidityResult,
        extra: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Build complete metadata dictionary.

        Merges detection-specific metadata with staleness and liquidity
        information, ensuring all required fields are present.

        Required fields (Requirement 6.4, 7.2, 8.2):
        - kalshi_price: Kalshi YES mid price
        - polymarket_price: Polymarket YES mid price
        - price_diff: Absolute price difference
        - fees_kalshi: Kalshi fees
        - fees_polymarket: Polymarket fees
        - kalshi_age_seconds: Age of Kalshi quote
        - poly_age_seconds: Age of Polymarket quote
        - kalshi_liquidity: Kalshi liquidity in USD
        - poly_liquidity: Polymarket liquidity in USD
        - max_executable_size: Maximum executable size
        - flags: List of flags (["STALE"], ["LOW_LIQUIDITY"], or [])

        Args:
            kalshi: Normalized Kalshi market
            poly: Normalized Polymarket market
            staleness: Result from StaleQuoteFilter.check()
            liquidity: Result from LiquidityFilter.check()
            extra: Detection-specific metadata to merge

        Returns:
            Complete metadata dictionary with all required fields
        """
        # Start with the extra metadata
        metadata: Dict[str, Any] = dict(extra)

        # Add market identification
        metadata["kalshi_market_id"] = kalshi.market_id
        metadata["polymarket_market_id"] = poly.market_id
        metadata["market_exchanges"] = {
            kalshi.market_id: "kalshi",
            poly.market_id: "polymarket",
        }

        # Add staleness information (Requirement 7.2)
        metadata["kalshi_age_seconds"] = staleness.kalshi_age_seconds
        metadata["poly_age_seconds"] = staleness.poly_age_seconds
        metadata["kalshi_stale"] = staleness.kalshi_stale
        metadata["poly_stale"] = staleness.poly_stale

        # Add liquidity information (Requirement 8.2)
        metadata["kalshi_liquidity"] = liquidity.kalshi_liquidity
        metadata["poly_liquidity"] = liquidity.poly_liquidity
        metadata["kalshi_low_liquidity"] = liquidity.kalshi_low
        metadata["poly_low_liquidity"] = liquidity.poly_low
        metadata["max_executable_size"] = liquidity.max_executable_size

        # Build flags list
        flags: List[str] = []
        if staleness.flag:
            flags.append(staleness.flag)
        if liquidity.flag:
            flags.append(liquidity.flag)
        metadata["flags"] = flags

        # Ensure required price fields are present with defaults if missing
        if "kalshi_price" not in metadata:
            # Calculate mid price from normalized market
            metadata["kalshi_price"] = (kalshi.yes_bid + kalshi.yes_ask) / 2.0

        if "polymarket_price" not in metadata:
            # Calculate mid price from normalized market
            metadata["polymarket_price"] = (poly.yes_bid + poly.yes_ask) / 2.0

        if "price_diff" not in metadata:
            kalshi_mid = metadata["kalshi_price"]
            poly_mid = metadata["polymarket_price"]
            metadata["price_diff"] = abs(kalshi_mid - poly_mid)

        # Ensure fee fields are present with defaults if missing
        if "fees_kalshi" not in metadata:
            metadata["fees_kalshi"] = 0.0

        if "fees_polymarket" not in metadata:
            metadata["fees_polymarket"] = 0.0

        return metadata

    def _build_description(
        self,
        detection_type: str,
        kalshi: NormalizedMarket,
        poly: NormalizedMarket,
        net_edge: float,
        metadata: Dict[str, Any],
    ) -> str:
        """Build human-readable description for the opportunity.

        Creates a description based on the detection type and relevant
        metadata values.

        Args:
            detection_type: Type of detection
            kalshi: Normalized Kalshi market
            poly: Normalized Polymarket market
            net_edge: Expected profit after fees
            metadata: Complete metadata dictionary

        Returns:
            Human-readable description string
        """
        kalshi_price = metadata.get("kalshi_price", 0.0)
        poly_price = metadata.get("polymarket_price", 0.0)
        flags = metadata.get("flags", [])

        flag_str = f" [{', '.join(flags)}]" if flags else ""

        if detection_type == "price_discrepancy":
            price_diff = metadata.get("price_diff", 0.0)
            if kalshi_price < poly_price:
                strategy = "BUY Kalshi YES + BUY Polymarket NO"
            else:
                strategy = "BUY Polymarket YES + SELL Kalshi YES"

            return (
                f"Cross-venue price discrepancy: Kalshi ({kalshi_price:.2%}) vs "
                f"Polymarket ({poly_price:.2%}), diff={price_diff:.2%}. "
                f"Strategy: {strategy}. Net edge: {net_edge:.4f} ({net_edge*100:.2f}%){flag_str}"
            )

        elif detection_type == "parity_violation":
            total_cost = metadata.get("total_cost", 0.0)
            guaranteed_profit = metadata.get("guaranteed_profit", net_edge)

            return (
                f"Cross-venue parity violation: Total cost {total_cost:.2%} < 100%. "
                f"Guaranteed profit: {guaranteed_profit:.4f} ({guaranteed_profit*100:.2f}%){flag_str}"
            )

        elif detection_type == "range_bucket":
            bucket_sum = metadata.get("kalshi_bucket_sum", 0.0)
            bucket_count = metadata.get("bucket_count", 0)
            poly_range_price = metadata.get("polymarket_range_price", poly_price)

            return (
                f"Range bucket arbitrage: Polymarket range ({poly_range_price:.2%}) vs "
                f"Kalshi bucket sum ({bucket_sum:.2%}, {bucket_count} buckets). "
                f"Net edge: {net_edge:.4f} ({net_edge*100:.2f}%){flag_str}"
            )

        else:
            # Fallback for unknown types
            return (
                f"Cross-venue opportunity ({detection_type}): "
                f"Net edge: {net_edge:.4f} ({net_edge*100:.2f}%){flag_str}"
            )




class CrossVenueDetector:
    """Detects cross-venue arbitrage opportunities.

    Main orchestrator class that consumes matched pairs from CrossVenueMatcher
    and identifies arbitrage opportunities:
    - Price discrepancies between venues
    - Cross-venue parity violations
    - Range bucket arbitrage

    Integrates with the existing detector pattern (same interface as other
    detectors like ParityDetector, LadderDetector, etc.).

    Key constraint: NO SHORT SELLING on Polymarket - all strategies must be
    BUY-only or use Kalshi for shorts.

    Validates: Requirements 2.1, 3.5, 6.1, 6.2, 6.3, 6.4, 6.5
    """

    def __init__(
        self,
        config: CrossVenueDetectorConfig,
        broker_config: "BrokerConfig",
    ):
        """Initialize the cross-venue detector with all components.

        Args:
            config: CrossVenueDetectorConfig with thresholds and fee settings
            broker_config: BrokerConfig for trade execution parameters
        """
        self.config = config
        self.broker_config = broker_config

        # Initialize all component classes
        self.normalizer = MarketNormalizer()
        self.price_extractor = PriceExtractor()
        self.feasibility_checker = FeasibilityChecker()
        self.stale_filter = StaleQuoteFilter(config.staleness_threshold_seconds)
        self.liquidity_filter = LiquidityFilter(config.min_liquidity_usd)
        self.classifier = OpportunityClassifier()
        self.range_analyzer = RangeBucketAnalyzer(config)

    def detect(
        self,
        matched_pairs: List[Tuple[Market, Market, float]],
    ) -> List[Opportunity]:
        """Detect arbitrage opportunities from matched pairs.

        Processes each matched pair through the full detection pipeline:
        1. Normalize both markets
        2. Skip if either is non-tradeable
        3. Check staleness - skip if both stale
        4. Check liquidity - skip if both below minimum
        5. Run price discrepancy detection
        6. Run parity violation detection
        7. Collect all opportunities and return

        Args:
            matched_pairs: List of (kalshi_market, poly_market, similarity_score)
                tuples from CrossVenueMatcher

        Returns:
            List of Opportunity objects for all detected arbitrage opportunities
        """
        if not self.config.enabled:
            return []

        opportunities: List[Opportunity] = []

        for kalshi_market, poly_market, similarity_score in matched_pairs:
            # Step 1: Normalize both markets
            kalshi_normalized = self.normalizer.normalize(kalshi_market)
            poly_normalized = self.normalizer.normalize(poly_market)

            # Step 2: Skip if either is non-tradeable
            if not kalshi_normalized.is_tradeable:
                continue
            if not poly_normalized.is_tradeable:
                continue

            # Step 3: Check staleness
            staleness = self.stale_filter.check(kalshi_normalized, poly_normalized)
            if staleness.should_discard:
                # Both markets are stale - skip this pair
                continue

            # Step 4: Check liquidity
            liquidity = self.liquidity_filter.check(kalshi_normalized, poly_normalized)
            if liquidity.should_discard:
                # Both markets have low liquidity - skip this pair
                continue

            # Step 5: Run price discrepancy detection
            price_opp = self._detect_price_discrepancy(
                kalshi_normalized,
                poly_normalized,
                staleness,
                liquidity,
                similarity_score,
            )
            if price_opp is not None:
                opportunities.append(price_opp)

            # Step 6: Run parity violation detection
            parity_opp = self._detect_parity_violation(
                kalshi_normalized,
                poly_normalized,
                staleness,
                liquidity,
                similarity_score,
            )
            if parity_opp is not None:
                opportunities.append(parity_opp)

        return opportunities

    def _detect_price_discrepancy(
        self,
        kalshi: NormalizedMarket,
        poly: NormalizedMarket,
        staleness: StalenessResult,
        liquidity: LiquidityResult,
        similarity_score: float,
    ) -> Optional[Opportunity]:
        """Detect price discrepancy between venues.

        Identifies arbitrage when the same event has different prices on
        Kalshi vs Polymarket. Calculates net edge after fees.

        Args:
            kalshi: Normalized Kalshi market
            poly: Normalized Polymarket market
            staleness: Result from staleness check
            liquidity: Result from liquidity check
            similarity_score: Semantic similarity score from matcher

        Returns:
            Opportunity if price discrepancy detected with positive net edge,
            None otherwise
        """
        # Extract prices
        kalshi_prices = self.price_extractor.extract(kalshi)
        poly_prices = self.price_extractor.extract(poly)

        if kalshi_prices is None or poly_prices is None:
            return None

        # Calculate price difference using mid prices
        kalshi_yes_mid = kalshi_prices.yes_mid
        poly_yes_mid = poly_prices.yes_mid
        price_diff = abs(kalshi_yes_mid - poly_yes_mid)

        # Apply threshold check
        if price_diff < self.config.min_price_diff_threshold:
            return None

        # Determine which venue is cheaper
        kalshi_cheaper = kalshi_yes_mid < poly_yes_mid

        # Calculate gross edge
        gross_edge = price_diff

        # Calculate fees
        amount = 1.0
        kalshi_fees = amount * (self.config.kalshi_fee_bps / 10000.0)
        poly_fees = amount * (self.config.polymarket_fee_bps / 10000.0) * 2
        slippage = amount * (self.config.slippage_bps / 10000.0)
        total_fees = kalshi_fees + poly_fees + slippage

        # Calculate net edge
        net_edge = gross_edge - total_fees

        # Discard if net_edge <= 0
        if net_edge <= 0:
            return None

        # Generate feasible trade actions
        actions = self.feasibility_checker._generate_strategy(kalshi, poly, kalshi_cheaper)

        # Adjust trade amounts based on liquidity
        max_size = liquidity.max_executable_size
        for action in actions:
            action.amount = min(action.amount, max_size)

        # Build metadata
        metadata: Dict[str, Any] = {
            "kalshi_price": kalshi_yes_mid,
            "polymarket_price": poly_yes_mid,
            "price_diff": price_diff,
            "gross_edge": gross_edge,
            "fees_kalshi": kalshi_fees,
            "fees_polymarket": poly_fees,
            "slippage": slippage,
            "total_fees": total_fees,
            "kalshi_cheaper": kalshi_cheaper,
            "similarity_score": similarity_score,
        }

        # Use classifier to create standardized opportunity
        return self.classifier.classify(
            detection_type="price_discrepancy",
            kalshi=kalshi,
            poly=poly,
            actions=actions,
            net_edge=net_edge,
            metadata=metadata,
            staleness=staleness,
            liquidity=liquidity,
        )

    def _detect_parity_violation(
        self,
        kalshi: NormalizedMarket,
        poly: NormalizedMarket,
        staleness: StalenessResult,
        liquidity: LiquidityResult,
        similarity_score: float,
    ) -> Optional[Opportunity]:
        """Detect cross-venue parity violation.

        A parity violation occurs when buying YES on one venue and NO on
        another costs less than $1.00 (guaranteed profit at settlement).

        Args:
            kalshi: Normalized Kalshi market
            poly: Normalized Polymarket market
            staleness: Result from staleness check
            liquidity: Result from liquidity check
            similarity_score: Semantic similarity score from matcher

        Returns:
            Opportunity if parity violation detected with positive profit,
            None otherwise
        """
        # Extract prices
        kalshi_prices = self.price_extractor.extract(kalshi)
        poly_prices = self.price_extractor.extract(poly)

        if kalshi_prices is None or poly_prices is None:
            return None

        # Calculate fees
        amount = 1.0
        kalshi_fees = amount * (self.config.kalshi_fee_bps / 10000.0)
        poly_fees = amount * (self.config.polymarket_fee_bps / 10000.0) * 2
        slippage = amount * (self.config.slippage_bps / 10000.0)
        total_fees = kalshi_fees + poly_fees + slippage

        # Check Scenario 1: Kalshi YES + Polymarket NO
        scenario1_cost = kalshi_prices.yes_ask + poly_prices.no_ask
        scenario1_profit = 1.0 - scenario1_cost - total_fees

        # Check Scenario 2: Polymarket YES + Kalshi NO
        scenario2_cost = poly_prices.yes_ask + kalshi_prices.no_ask
        scenario2_profit = 1.0 - scenario2_cost - total_fees

        # Determine best scenario
        best_scenario: Optional[int] = None
        best_profit = 0.0
        best_cost = 0.0

        if scenario1_profit > 0 and scenario1_profit >= scenario2_profit:
            best_scenario = 1
            best_profit = scenario1_profit
            best_cost = scenario1_cost
        elif scenario2_profit > 0:
            best_scenario = 2
            best_profit = scenario2_profit
            best_cost = scenario2_cost

        if best_scenario is None:
            return None

        # Generate trade actions
        actions: List[TradeAction] = []
        max_size = liquidity.max_executable_size

        if best_scenario == 1:
            actions.append(TradeAction(
                market_id=kalshi.market_id,
                outcome_id="YES",
                side="BUY",
                amount=min(amount, max_size),
                limit_price=kalshi_prices.yes_ask,
            ))
            actions.append(TradeAction(
                market_id=poly.market_id,
                outcome_id="NO",
                side="BUY",
                amount=min(amount, max_size),
                limit_price=poly_prices.no_ask,
            ))
            kalshi_outcome = "YES"
            kalshi_price = kalshi_prices.yes_ask
            poly_outcome = "NO"
            poly_price = poly_prices.no_ask
        else:
            actions.append(TradeAction(
                market_id=poly.market_id,
                outcome_id="YES",
                side="BUY",
                amount=min(amount, max_size),
                limit_price=poly_prices.yes_ask,
            ))
            actions.append(TradeAction(
                market_id=kalshi.market_id,
                outcome_id="NO",
                side="BUY",
                amount=min(amount, max_size),
                limit_price=kalshi_prices.no_ask,
            ))
            kalshi_outcome = "NO"
            kalshi_price = kalshi_prices.no_ask
            poly_outcome = "YES"
            poly_price = poly_prices.yes_ask

        # Build metadata
        metadata: Dict[str, Any] = {
            "kalshi_yes_ask": kalshi_prices.yes_ask,
            "kalshi_no_ask": kalshi_prices.no_ask,
            "poly_yes_ask": poly_prices.yes_ask,
            "poly_no_ask": poly_prices.no_ask,
            "total_cost": best_cost,
            "guaranteed_profit": best_profit,
            "fees_kalshi": kalshi_fees,
            "fees_polymarket": poly_fees,
            "slippage": slippage,
            "fees_total": total_fees,
            "scenario": best_scenario,
            "kalshi_outcome": kalshi_outcome,
            "kalshi_price": kalshi_price,
            "poly_outcome": poly_outcome,
            "poly_price": poly_price,
            "similarity_score": similarity_score,
        }

        # Use classifier to create standardized opportunity
        return self.classifier.classify(
            detection_type="parity_violation",
            kalshi=kalshi,
            poly=poly,
            actions=actions,
            net_edge=best_profit,
            metadata=metadata,
            staleness=staleness,
            liquidity=liquidity,
        )

    def _calculate_fees(
        self,
        kalshi_amount: float,
        poly_amount: float,
    ) -> Tuple[float, float]:
        """Calculate fees for both venues.

        Args:
            kalshi_amount: Trade amount on Kalshi
            poly_amount: Trade amount on Polymarket

        Returns:
            Tuple of (kalshi_fees, poly_fees)
        """
        kalshi_fees = kalshi_amount * (self.config.kalshi_fee_bps / 10000.0)
        poly_fees = poly_amount * (self.config.polymarket_fee_bps / 10000.0) * 2
        return kalshi_fees, poly_fees
