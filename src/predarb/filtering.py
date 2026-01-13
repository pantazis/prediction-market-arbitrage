"""
Market filtering module for prediction market arbitrage scanning.

Provides minimal eligibility checks only. Legacy volume/spread/liquidity filters
have been removed and will be replaced by new logic later.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional, List, Tuple, Dict

from predarb.models import Market


class RejectionReason(Enum):
    """Enumeration of market rejection reasons."""
    INSUFFICIENT_OUTCOMES = "Insufficient outcomes for trading"
    RESOLUTION_EMPTY = "Resolution source not specified"
    RESOLUTION_SUBJECTIVE = "Resolution may be subjective"


@dataclass
class FilterSettings:
    """
    Configuration for minimal market eligibility checks.

    Attributes:
        require_resolution_source: If True, require explicit resolution_source
    """

    require_resolution_source: bool = False


class MarketFilter:
    """
    Minimal market filtering and compatibility ranking.
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
        Filter markets by minimal eligibility checks.
        """
        self._rejection_reasons = {}
        eligible = []

        for market in markets:
            if not self._passes_hard_filters(market):
                continue
            eligible.append(market)

        return sorted(eligible, key=lambda m: m.id)

    def rank_markets(
        self,
        markets: List[Market],
    ) -> List[Tuple[Market, float]]:
        """
        Compatibility ranking: returns deterministic zero scores.
        """
        scored = [(market, 0.0) for market in markets]
        scored.sort(key=lambda x: x[0].id)
        return scored

    def explain_rejection(self, market: Market) -> List[str]:
        """
        Get human-readable rejection reasons for a market.
        """
        if market.id in self._rejection_reasons:
            return self._rejection_reasons[market.id]
        return []

    # ========== Minimal Eligibility Filters ==========

    def _passes_hard_filters(self, market: Market) -> bool:
        reasons = []

        if not self._has_sufficient_outcomes(market):
            reasons.append(RejectionReason.INSUFFICIENT_OUTCOMES.value)

        issue = self._resolution_issue(market)
        if issue:
            reasons.append(issue.value)

        if reasons:
            self._rejection_reasons[market.id] = reasons
            return False

        return True

    def _has_sufficient_outcomes(self, market: Market) -> bool:
        if not market.outcomes or len(market.outcomes) < 2:
            return False
        return True

    def _resolution_issue(self, market: Market) -> RejectionReason | None:
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

    def _passes_risk_filters(
        self,
        market: Market,
        target_order_size_usd: float,
    ) -> bool:
        return True

    def _get_rejection_reasons(self, market: Market) -> List[str]:
        reasons = []

        if not self._has_sufficient_outcomes(market):
            reasons.append(RejectionReason.INSUFFICIENT_OUTCOMES.value)

        issue = self._resolution_issue(market)
        if issue:
            reasons.append(issue.value)

        return reasons


def filter_markets(
    markets: List[Market],
    settings: Optional[FilterSettings] = None,
    account_equity_usd: Optional[float] = None,
    target_order_size_usd: Optional[float] = None,
) -> List[Market]:
    filter_engine = MarketFilter(settings)
    return filter_engine.filter_markets(markets, account_equity_usd, target_order_size_usd)


def rank_markets(
    markets: List[Market],
    settings: Optional[FilterSettings] = None,
) -> List[Tuple[Market, float]]:
    filter_engine = MarketFilter(settings)
    return filter_engine.rank_markets(markets)


def explain_rejection(
    market: Market,
    settings: Optional[FilterSettings] = None,
) -> List[str]:
    filter_engine = MarketFilter(settings)
    return filter_engine._get_rejection_reasons(market)
