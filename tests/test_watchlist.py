from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from predarb.models import Market, Outcome
from predarb.watchlist import (
    WatchlistRow,
    load_watchlist_csv,
    prune_watchlist,
    scan_watchlist,
    write_watchlist_csv,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _make_market(
    *,
    market_id: str,
    question: str,
    exchange: str,
    yes_price: float,
    no_price: float,
    liquidity: float,
    updated_at: datetime,
) -> Market:
    outcomes = [
        Outcome(id=f"{market_id}:YES", label="YES", price=yes_price, liquidity=liquidity),
        Outcome(id=f"{market_id}:NO", label="NO", price=no_price, liquidity=liquidity),
    ]
    market = Market(
        id=market_id,
        question=question,
        outcomes=outcomes,
        updated_at=updated_at,
        best_bid={"yes": yes_price - 0.05, "no": no_price - 0.05},
        best_ask={"yes": yes_price + 0.05, "no": no_price + 0.05},
    )
    market.exchange = exchange
    return market


def test_scan_watchlist_uses_orderbook_prices():
    now = _now()
    kalshi = _make_market(
        market_id="kalshi:EVT:KTEST",
        question="Will test pass?",
        exchange="kalshi",
        yes_price=0.4,
        no_price=0.6,
        liquidity=2000.0,
        updated_at=now,
    )
    polymarket = _make_market(
        market_id="poly123",
        question="Will test pass?",
        exchange="polymarket",
        yes_price=0.3,
        no_price=0.7,
        liquidity=2000.0,
        updated_at=now,
    )

    row = WatchlistRow(
        pair_id="pair1",
        k_ticker="KTEST",
        p_market_id="poly123",
        p_yes_token_id="yes_token",
        p_no_token_id="no_token",
        polarity="normal",
        k_expiration_time=(now + timedelta(days=1)).isoformat(),
        p_endDate=(now + timedelta(days=1)).isoformat(),
        min_edge=0.01,
        min_depth_usd=50.0,
        max_age_sec=60,
        status="active",
        last_verified_at=now.isoformat(),
    )

    def orderbook_fetcher(venue: str, market: Market, outcome_label: str):
        if venue == "kalshi":
            return {
                "bids": [{"price": 70, "size": 100}],
                "asks": [{"price": 80, "size": 100}],
            }
        return {
            "bids": [{"price": 10, "size": 100}],
            "asks": [{"price": 20, "size": 100}],
        }

    output = scan_watchlist(
        [row],
        kalshi_markets=[kalshi],
        polymarket_markets=[polymarket],
        depth_fraction=0.10,
        orderbook_fetcher=orderbook_fetcher,
    )

    assert output.approve_packets, "Expected approve packet from orderbook prices"
    packet = next(p for p in output.approve_packets if p["side"] == "YES")
    assert packet["kalshi"]["bid"] == 0.70
    assert packet["kalshi"]["ask"] == 0.80
    assert packet["polymarket"]["ask"] == 0.20
    assert packet["edge_gross"] == pytest.approx(0.70 - 0.20)


def test_prune_watchlist_removes_expired_rows(tmp_path):
    now = _now()
    active = WatchlistRow(
        pair_id="active",
        k_ticker="KACTIVE",
        p_market_id="P1",
        p_yes_token_id="y1",
        p_no_token_id="n1",
        polarity="normal",
        k_expiration_time=(now + timedelta(days=1)).isoformat(),
        p_endDate=(now + timedelta(days=1)).isoformat(),
        min_edge=0.01,
        min_depth_usd=10.0,
        max_age_sec=60,
        status="active",
        last_verified_at=now.isoformat(),
    )
    expired = WatchlistRow(
        pair_id="expired",
        k_ticker="KEXPIRED",
        p_market_id="P2",
        p_yes_token_id="y2",
        p_no_token_id="n2",
        polarity="normal",
        k_expiration_time=(now - timedelta(hours=1)).isoformat(),
        p_endDate=(now + timedelta(days=1)).isoformat(),
        min_edge=0.01,
        min_depth_usd=10.0,
        max_age_sec=60,
        status="active",
        last_verified_at=now.isoformat(),
    )

    csv_path = tmp_path / "watchlist.csv"
    write_watchlist_csv(csv_path, [active, expired])

    rows = load_watchlist_csv(csv_path)
    pruned = prune_watchlist(rows, now=now)
    write_watchlist_csv(csv_path, pruned)

    final_rows = load_watchlist_csv(csv_path)
    assert len(final_rows) == 1
    assert final_rows[0].pair_id == "active"
