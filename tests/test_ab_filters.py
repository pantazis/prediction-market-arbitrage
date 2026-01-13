import time

from predarb.ab_filters import (
    Quote,
    FilterConfig,
    evaluate_ab_filters,
)


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
