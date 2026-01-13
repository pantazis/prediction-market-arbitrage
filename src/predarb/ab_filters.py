"""
Reusable, null-safe A+B (Kalshi A + Polymarket B) single-question arbitrage filters.

Implements execution-safety + realism filters with explicit PASS/FAIL reporting.
Missing or invalid inputs always yield FAIL with a reason.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Union
import math

Number = Union[int, float]


@dataclass
class Quote:
    venue: str
    market_id: str
    outcome: str  # "YES" | "NO"
    bid: Optional[float] = None
    ask: Optional[float] = None
    bid_size_usd: Optional[float] = None
    ask_size_usd: Optional[float] = None
    depth_usd: Optional[float] = None
    ts: Optional[float] = None


@dataclass
class FilterConfig:
    # execution safety
    min_leg_usd: float = 100.0
    min_depth_usd: float = 100.0
    max_staleness_sec: float = 600.0
    min_price: float = 0.03
    max_price: float = 0.97

    # costs
    fee_bps_a: float = 7.0
    fee_bps_b: float = 7.0
    slippage_bps: float = 10.0

    # edge threshold
    min_edge: float = 0.01

    # depth handling
    allow_unknown_depth: bool = False


@dataclass
class FilterResultItem:
    code: str
    passed: bool
    value: Any = None
    threshold: Any = None
    detail: str = ""


@dataclass
class FilterReport:
    passed: bool
    fail_filter: Optional[str] = None
    fail_reason: Optional[str] = None

    items: List[FilterResultItem] = field(default_factory=list)
    pass_order: List[str] = field(default_factory=list)

    missing_fields: List[str] = field(default_factory=list)
    invalid_fields: List[str] = field(default_factory=list)

    edge_gross: Optional[float] = None
    edge_net: Optional[float] = None
    executable_size_usd: Optional[float] = None

    spread_a: Optional[float] = None
    spread_b: Optional[float] = None
    fees: Optional[float] = None
    slippage: Optional[float] = None

    staleness_a: Optional[float] = None
    staleness_b: Optional[float] = None

    depth_a: Optional[float] = None
    depth_b: Optional[float] = None

    def add(self, item: FilterResultItem) -> None:
        self.items.append(item)

    def fail(self, code: str, reason: str, item: Optional[FilterResultItem] = None) -> "FilterReport":
        self.passed = False
        self.fail_filter = code
        self.fail_reason = reason
        if item is not None:
            self.items.append(item)
        return self


def _is_finite_number(x: Any) -> bool:
    try:
        return isinstance(x, (int, float)) and math.isfinite(float(x))
    except Exception:
        return False


def _safe_float(x: Any) -> Optional[float]:
    if x is None:
        return None
    try:
        v = float(x)
        if math.isfinite(v):
            return v
        return None
    except Exception:
        return None


def _safe_nonneg(x: Any, default: float = 0.0) -> float:
    v = _safe_float(x)
    if v is None or v < 0:
        return default
    return v


def _venue_fee_bps(cfg: FilterConfig, venue: str) -> float:
    if venue.lower() in ("kalshi", "a"):
        return cfg.fee_bps_a
    return cfg.fee_bps_b


def _cost_per_1usd(cfg: FilterConfig, venue: str) -> float:
    bps = _venue_fee_bps(cfg, venue) + cfg.slippage_bps
    return bps / 10_000.0


def safe_get_first(d: Dict[str, Any], keys: List[str]) -> Any:
    for k in keys:
        if k in d and d[k] not in (None, ""):
            return d[k]
    return None


def extract_best_bid_ask_from_orderbook(
    raw: Any,
    *,
    bid_keys: Optional[List[str]] = None,
    ask_keys: Optional[List[str]] = None,
    bids_path: str = "bids",
    asks_path: str = "asks",
    price_key: str = "price",
    size_key: str = "size",
) -> Tuple[Optional[float], Optional[float], float, float, bool, str]:
    bid_keys = bid_keys or ["bid", "bestBid", "best_bid"]
    ask_keys = ask_keys or ["ask", "bestAsk", "best_ask"]

    schema_indicates_book = False
    detail_parts: List[str] = []

    if not isinstance(raw, dict):
        return None, None, 0.0, 0.0, False, "raw not dict"

    bid_raw = safe_get_first(raw, bid_keys)
    ask_raw = safe_get_first(raw, ask_keys)
    if any(k in raw for k in bid_keys + ask_keys):
        schema_indicates_book = True
        detail_parts.append("flat_keys_present")

    bid = _safe_float(bid_raw)
    ask = _safe_float(ask_raw)

    bid_size = 0.0
    ask_size = 0.0

    bids = raw.get(bids_path)
    asks = raw.get(asks_path)
    if bids is not None or asks is not None:
        schema_indicates_book = True
        detail_parts.append("bids/asks_present")

    if bid is None and isinstance(bids, list) and bids and isinstance(bids[0], dict):
        bid = _safe_float(bids[0].get(price_key))
        bid_size = _safe_nonneg(bids[0].get(size_key), 0.0)

    if ask is None and isinstance(asks, list) and asks and isinstance(asks[0], dict):
        ask = _safe_float(asks[0].get(price_key))
        ask_size = _safe_nonneg(asks[0].get(size_key), 0.0)

    if bid is not None:
        bid_size = max(bid_size, _safe_nonneg(raw.get("bid_size") or raw.get("bidSize") or raw.get("bestBidSize"), 0.0))
    if ask is not None:
        ask_size = max(ask_size, _safe_nonneg(raw.get("ask_size") or raw.get("askSize") or raw.get("bestAskSize"), 0.0))

    debug_detail = ",".join(detail_parts) if detail_parts else "no_schema_hints"
    return bid, ask, bid_size, ask_size, schema_indicates_book, debug_detail


def evaluate_ab_filters(
    *,
    now_ts: float,
    kalshi_leg: Quote,
    polymarket_leg: Quote,
    trade_price_a: Optional[float],
    trade_price_b: Optional[float],
    edge_gross: Optional[float],
    config: FilterConfig,
    schema_hint_a: Optional[Dict[str, Any]] = None,
    schema_hint_b: Optional[Dict[str, Any]] = None,
) -> FilterReport:
    rep = FilterReport(passed=True)

    rep.pass_order.append("F_SCHEMA_MISMATCH")

    def _schema_mismatch(venue: str, q: Quote, raw_hint: Optional[Dict[str, Any]]) -> Optional[str]:
        if raw_hint is None:
            return None
        bid, ask, _, _, indicates, detail = extract_best_bid_ask_from_orderbook(raw_hint)
        if indicates and (q.bid is None or q.ask is None):
            return f"{venue}: orderbook hinted ({detail}) but parsed bid/ask is None (bid={q.bid}, ask={q.ask})"
        return None

    mismatch_a = _schema_mismatch(kalshi_leg.venue, kalshi_leg, schema_hint_a)
    mismatch_b = _schema_mismatch(polymarket_leg.venue, polymarket_leg, schema_hint_b)

    if mismatch_a or mismatch_b:
        reason = mismatch_a or mismatch_b
        return rep.fail(
            "F_SCHEMA_MISMATCH",
            reason,
            FilterResultItem(
                code="F_SCHEMA_MISMATCH",
                passed=False,
                value={"A": mismatch_a, "B": mismatch_b},
                threshold=None,
                detail=reason,
            ),
        )
    rep.add(FilterResultItem(code="F_SCHEMA_MISMATCH", passed=True, value=None, threshold=None, detail="schema ok"))

    rep.pass_order.append("F_DATA_INTEGRITY")

    missing: List[str] = []
    invalid: List[str] = []

    def _check_integrity(q: Quote, label: str) -> Optional[str]:
        if q.bid is None:
            missing.append(f"{label}.bid")
        if q.ask is None:
            missing.append(f"{label}.ask")
        if q.ts is None:
            missing.append(f"{label}.ts")

        if q.bid is None or q.ask is None:
            return f"{label}: missing bid/ask (bid={q.bid}, ask={q.ask})"
        if not _is_finite_number(q.bid) or not _is_finite_number(q.ask):
            invalid.append(f"{label}.bid/ask non-finite")
            return f"{label}: non-finite bid/ask"
        if q.bid <= 0 or q.ask <= 0:
            invalid.append(f"{label}.bid/ask<=0")
            return f"{label}: bid/ask must be >0 (bid={q.bid}, ask={q.ask})"
        if q.bid >= q.ask:
            invalid.append(f"{label}.bid>=ask")
            return f"{label}: invalid book bid>=ask (bid={q.bid}, ask={q.ask})"
        if q.ts is None or not _is_finite_number(q.ts):
            invalid.append(f"{label}.ts invalid")
            return f"{label}: missing/invalid timestamp (ts={q.ts})"
        return None

    err_a = _check_integrity(kalshi_leg, "A")
    if err_a:
        rep.missing_fields = missing
        rep.invalid_fields = invalid
        return rep.fail(
            "F_DATA_INTEGRITY",
            err_a,
            FilterResultItem(code="F_DATA_INTEGRITY", passed=False, value=None, threshold=None, detail=err_a),
        )
    err_b = _check_integrity(polymarket_leg, "B")
    if err_b:
        rep.missing_fields = missing
        rep.invalid_fields = invalid
        return rep.fail(
            "F_DATA_INTEGRITY",
            err_b,
            FilterResultItem(code="F_DATA_INTEGRITY", passed=False, value=None, threshold=None, detail=err_b),
        )

    rep.missing_fields = missing
    rep.invalid_fields = invalid
    rep.add(FilterResultItem(code="F_DATA_INTEGRITY", passed=True, value=None, threshold=None, detail="data ok"))

    rep.spread_a = kalshi_leg.ask - kalshi_leg.bid
    rep.spread_b = polymarket_leg.ask - polymarket_leg.bid

    rep.pass_order.append("F_STALENESS")
    rep.staleness_a = now_ts - float(kalshi_leg.ts)
    rep.staleness_b = now_ts - float(polymarket_leg.ts)

    if rep.staleness_a > config.max_staleness_sec:
        return rep.fail(
            "F_STALENESS",
            f"A stale: age={rep.staleness_a:.1f}s>{config.max_staleness_sec}s",
            FilterResultItem(
                code="F_STALENESS",
                passed=False,
                value=rep.staleness_a,
                threshold=config.max_staleness_sec,
                detail="A stale",
            ),
        )
    if rep.staleness_b > config.max_staleness_sec:
        return rep.fail(
            "F_STALENESS",
            f"B stale: age={rep.staleness_b:.1f}s>{config.max_staleness_sec}s",
            FilterResultItem(
                code="F_STALENESS",
                passed=False,
                value=rep.staleness_b,
                threshold=config.max_staleness_sec,
                detail="B stale",
            ),
        )
    rep.add(
        FilterResultItem(
            code="F_STALENESS",
            passed=True,
            value={"A": rep.staleness_a, "B": rep.staleness_b},
            threshold=config.max_staleness_sec,
            detail="fresh",
        )
    )

    rep.pass_order.append("F_SIZE")

    a_size = _safe_nonneg(kalshi_leg.bid_size_usd if trade_price_a == kalshi_leg.bid else kalshi_leg.ask_size_usd, 0.0)
    b_size = _safe_nonneg(polymarket_leg.bid_size_usd if trade_price_b == polymarket_leg.bid else polymarket_leg.ask_size_usd, 0.0)

    rep.executable_size_usd = min(a_size, b_size) if (a_size is not None and b_size is not None) else 0.0

    if rep.executable_size_usd < config.min_leg_usd:
        return rep.fail(
            "F_SIZE",
            f"exec=${rep.executable_size_usd:.2f}<${config.min_leg_usd:.2f} (A_size={a_size:.2f}, B_size={b_size:.2f})",
            FilterResultItem(
                code="F_SIZE",
                passed=False,
                value=rep.executable_size_usd,
                threshold=config.min_leg_usd,
                detail="insufficient top-of-book size",
            ),
        )
    rep.add(FilterResultItem(code="F_SIZE", passed=True, value=rep.executable_size_usd, threshold=config.min_leg_usd, detail="ok"))

    rep.pass_order.append("F_PRICE_BAND")

    if trade_price_a is None or trade_price_b is None:
        return rep.fail(
            "F_DATA_INTEGRITY",
            "trade price missing",
            FilterResultItem(
                code="F_DATA_INTEGRITY",
                passed=False,
                value={"A_price": trade_price_a, "B_price": trade_price_b},
                threshold=None,
                detail="trade prices required",
            ),
        )

    if not (config.min_price <= float(trade_price_a) <= config.max_price):
        return rep.fail(
            "F_PRICE_BAND",
            f"A price {trade_price_a:.4f} outside [{config.min_price},{config.max_price}]",
            FilterResultItem(
                code="F_PRICE_BAND",
                passed=False,
                value=trade_price_a,
                threshold=[config.min_price, config.max_price],
                detail="A price band",
            ),
        )
    if not (config.min_price <= float(trade_price_b) <= config.max_price):
        return rep.fail(
            "F_PRICE_BAND",
            f"B price {trade_price_b:.4f} outside [{config.min_price},{config.max_price}]",
            FilterResultItem(
                code="F_PRICE_BAND",
                passed=False,
                value=trade_price_b,
                threshold=[config.min_price, config.max_price],
                detail="B price band",
            ),
        )
    rep.add(
        FilterResultItem(
            code="F_PRICE_BAND",
            passed=True,
            value={"A": trade_price_a, "B": trade_price_b},
            threshold=[config.min_price, config.max_price],
            detail="ok",
        )
    )

    rep.pass_order.append("F_DEPTH_AT_PRICE")

    rep.depth_a = _safe_float(kalshi_leg.depth_usd)
    rep.depth_b = _safe_float(polymarket_leg.depth_usd)

    if rep.depth_a is None or rep.depth_b is None:
        if config.allow_unknown_depth:
            rep.add(
                FilterResultItem(
                    code="F_DEPTH_AT_PRICE",
                    passed=True,
                    value={"A": rep.depth_a, "B": rep.depth_b},
                    threshold=config.min_depth_usd,
                    detail="unknown depth allowed",
                )
            )
        else:
            return rep.fail(
                "F_DEPTH_AT_PRICE",
                f"depth unknown (A={rep.depth_a}, B={rep.depth_b})",
                FilterResultItem(
                    code="F_DEPTH_AT_PRICE",
                    passed=False,
                    value={"A": rep.depth_a, "B": rep.depth_b},
                    threshold=config.min_depth_usd,
                    detail="depth missing",
                ),
            )
    else:
        if min(rep.depth_a, rep.depth_b) < config.min_depth_usd:
            return rep.fail(
                "F_DEPTH_AT_PRICE",
                f"depth too low min(A,B)={min(rep.depth_a, rep.depth_b):.2f}<${config.min_depth_usd:.2f}",
                FilterResultItem(
                    code="F_DEPTH_AT_PRICE",
                    passed=False,
                    value={"A": rep.depth_a, "B": rep.depth_b},
                    threshold=config.min_depth_usd,
                    detail="depth insufficient",
                ),
            )
        rep.add(
            FilterResultItem(
                code="F_DEPTH_AT_PRICE",
                passed=True,
                value={"A": rep.depth_a, "B": rep.depth_b},
                threshold=config.min_depth_usd,
                detail="ok",
            )
        )

    rep.pass_order.append("F_EDGE_REALISM")

    rep.edge_gross = _safe_float(edge_gross)
    if rep.edge_gross is None:
        return rep.fail(
            "F_DATA_INTEGRITY",
            "edge_gross missing/invalid",
            FilterResultItem(code="F_DATA_INTEGRITY", passed=False, value=edge_gross, threshold=None, detail="edge required"),
        )

    rep.fees = _cost_per_1usd(config, kalshi_leg.venue) + _cost_per_1usd(config, polymarket_leg.venue)
    rep.slippage = 0.0

    realism_threshold = (rep.spread_a / 2.0) + (rep.spread_b / 2.0) + rep.fees

    if rep.edge_gross < realism_threshold:
        return rep.fail(
            "F_EDGE_REALISM",
            f"edge_gross {rep.edge_gross:.4f} < threshold {realism_threshold:.4f} (half-spreads+fees)",
            FilterResultItem(
                code="F_EDGE_REALISM",
                passed=False,
                value=rep.edge_gross,
                threshold=realism_threshold,
                detail="not enough to beat spreads+costs",
            ),
        )

    rep.edge_net = rep.edge_gross - rep.fees
    if rep.edge_net < config.min_edge:
        return rep.fail(
            "F_EDGE_REALISM",
            f"edge_net {rep.edge_net:.4f} < min_edge {config.min_edge:.4f}",
            FilterResultItem(
                code="F_EDGE_REALISM",
                passed=False,
                value=rep.edge_net,
                threshold=config.min_edge,
                detail="min edge",
            ),
        )

    rep.add(
        FilterResultItem(
            code="F_EDGE_REALISM",
            passed=True,
            value={"gross": rep.edge_gross, "net": rep.edge_net},
            threshold={"realism": realism_threshold, "min_edge": config.min_edge},
            detail="ok",
        )
    )
    rep.passed = True
    return rep


def quote_from_market(
    market: Any,
    outcome_label: str,
    depth_fraction: float,
) -> Quote:
    """
    Build a Quote from a Market with best_bid/ask and outcome liquidity.
    Missing fields remain None to trigger FAIL in filters.
    """
    label = outcome_label.strip().lower()
    bid = None
    ask = None
    if hasattr(market, "best_bid") and isinstance(market.best_bid, dict):
        bid = market.best_bid.get(label)
    if hasattr(market, "best_ask") and isinstance(market.best_ask, dict):
        ask = market.best_ask.get(label)

    liquidity = 0.0
    for outcome in getattr(market, "outcomes", []) or []:
        if str(getattr(outcome, "label", "")).strip().lower() == label:
            liquidity = float(getattr(outcome, "liquidity", 0.0) or 0.0)
            break

    bid_size = liquidity * depth_fraction if liquidity > 0 else None
    ask_size = liquidity * depth_fraction if liquidity > 0 else None
    depth_usd = liquidity * depth_fraction if liquidity > 0 else None

    ts = None
    updated_at = getattr(market, "updated_at", None)
    if updated_at and hasattr(updated_at, "timestamp"):
        ts = float(updated_at.timestamp())

    return Quote(
        venue=str(getattr(market, "exchange", "") or ""),
        market_id=str(getattr(market, "id", "")),
        outcome=label.upper(),
        bid=_safe_float(bid),
        ask=_safe_float(ask),
        bid_size_usd=_safe_float(bid_size),
        ask_size_usd=_safe_float(ask_size),
        depth_usd=_safe_float(depth_usd),
        ts=ts,
    )
