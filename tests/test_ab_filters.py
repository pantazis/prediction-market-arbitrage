import time
from datetime import datetime

from predarb.ab_filters import (
    Quote,
    FilterConfig,
    evaluate_ab_filters,
    quote_from_market,
)
from predarb.config import PolymarketConfig
from predarb.polymarket_client import PolymarketClient


def test_ab_filters_pass() -> None:
    now = time.time()
    kalshi = Quote(
        venue="kalshi",
        market_id="k1",
        outcome="YES",
        bid=0.50,
        ask=0.51,
        bid_size_usd=200.0,
        ask_size_usd=200.0,
        depth_usd=200.0,
        ts=now,
    )
    polymarket = Quote(
        venue="polymarket",
        market_id="p1",
        outcome="YES",
        bid=0.49,
        ask=0.50,
        bid_size_usd=200.0,
        ask_size_usd=200.0,
        depth_usd=200.0,
        ts=now,
    )
    cfg = FilterConfig()
    report = evaluate_ab_filters(
        now_ts=now,
        kalshi_leg=kalshi,
        polymarket_leg=polymarket,
        trade_price_a=kalshi.bid,
        trade_price_b=polymarket.ask,
        edge_gross=0.02,
        config=cfg,
    )
    assert report.passed is True
    assert report.fail_filter is None


def test_ab_filters_fail_missing_bid() -> None:
    now = time.time()
    kalshi = Quote(
        venue="kalshi",
        market_id="k1",
        outcome="YES",
        bid=None,
        ask=0.51,
        bid_size_usd=200.0,
        ask_size_usd=200.0,
        depth_usd=200.0,
        ts=now,
    )
    polymarket = Quote(
        venue="polymarket",
        market_id="p1",
        outcome="YES",
        bid=0.49,
        ask=0.50,
        bid_size_usd=200.0,
        ask_size_usd=200.0,
        depth_usd=200.0,
        ts=now,
    )
    cfg = FilterConfig()
    report = evaluate_ab_filters(
        now_ts=now,
        kalshi_leg=kalshi,
        polymarket_leg=polymarket,
        trade_price_a=kalshi.ask,
        trade_price_b=polymarket.ask,
        edge_gross=0.02,
        config=cfg,
    )
    assert report.passed is False
    assert report.fail_filter == "F_DATA_INTEGRITY"


def test_polymarket_mid_fallback_passes_integrity() -> None:
    now = time.time()
    client = PolymarketClient(PolymarketConfig())
    data = {
        "id": "m1",
        "conditionId": "c1",
        "question": "Test market?",
        "outcomes": '["Yes", "No"]',
        "outcomePrices": "[0.50, 0.50]",
        "clobTokenIds": '["t1", "t2"]',
        "liquidityNum": 1000.0,
        "volumeNum": 1000.0,
        "endDateIso": "2030-01-01T00:00:00Z",
    }
    market = client._parse_market(data)
    assert market is not None
    market.updated_at = datetime.utcnow()

    poly_quote = quote_from_market(market, "yes", 0.2)
    assert poly_quote.bid is not None
    assert poly_quote.ask is not None
    assert poly_quote.bid < poly_quote.ask

    kalshi = Quote(
        venue="kalshi",
        market_id="k1",
        outcome="YES",
        bid=0.55,
        ask=0.56,
        bid_size_usd=200.0,
        ask_size_usd=200.0,
        depth_usd=200.0,
        ts=now,
    )

    report = evaluate_ab_filters(
        now_ts=now,
        kalshi_leg=kalshi,
        polymarket_leg=poly_quote,
        trade_price_a=kalshi.bid,
        trade_price_b=poly_quote.ask,
        edge_gross=kalshi.bid - poly_quote.ask,
        config=FilterConfig(),
    )
    assert report.fail_filter != "F_DATA_INTEGRITY"
