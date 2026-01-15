from __future__ import annotations

from datetime import datetime, timedelta, timezone

from predarb.config import AppConfig, BrokerConfig, CrossVenueMatcherConfig, EngineConfig, KalshiConfig, PolymarketConfig, RiskConfig, WatchlistConfig
from predarb.dual_injection import DualInjectionClient
from predarb.engine import Engine
from predarb.models import Market, Outcome
from predarb.watchlist import build_watchlist_row, write_watchlist_csv


class CapturingNotifier:
    def __init__(self):
        self.opportunities = []

    def notify_opportunity(self, opp):
        self.opportunities.append(opp)


class StaticProvider:
    def __init__(self, markets):
        self._markets = markets

    def fetch_markets(self):
        return self._markets

    def get_exchange_name(self):
        return "static"

    def get_metadata(self):
        return {"exchange": "static"}


def _market(exchange: str, market_id: str, question: str, yes: float, no: float) -> Market:
    now = datetime.now(timezone.utc)
    expiry = now + timedelta(days=10)
    m = Market(
        id=market_id,
        question=question,
        outcomes=[
            Outcome(id=f"{market_id}:YES", label="YES", price=yes, liquidity=10_000.0),
            Outcome(id=f"{market_id}:NO", label="NO", price=no, liquidity=10_000.0),
        ],
        updated_at=now,
        end_date=expiry,
        expiry=expiry,
        liquidity=20_000.0,
        best_bid={"yes": max(0.0, yes - 0.01), "no": max(0.0, no - 0.01)},
        best_ask={"yes": min(1.0, yes + 0.01), "no": min(1.0, no + 0.01)},
        resolution_source="Fixture",
        description="Fixture scenario",
        exchange=exchange,
    )
    return m


def test_watchlist_executes_paper_trade_from_csv(tmp_path):
    # Construct a single cross-venue pair with a clear edge:
    # Kalshi YES bid ~0.60 vs Polymarket YES ask ~0.45 => positive edge.
    kalshi = _market("kalshi", "kalshi:EVT:KTEST", "Will Fed hold rates?", 0.60, 0.40)
    polymarket = _market("polymarket", "poly:TEST", "Will Fed hold rates?", 0.45, 0.55)

    watch_csv = tmp_path / "watchlist_pairs.csv"
    row = build_watchlist_row(
        kalshi,
        polymarket,
        min_edge=0.001,
        min_depth_usd=0.0,
        max_age_sec=10_000,
    )
    write_watchlist_csv(watch_csv, [row])

    cfg = AppConfig(
        polymarket=PolymarketConfig(enabled=False),
        kalshi=KalshiConfig(enabled=False),
        engine=EngineConfig(iterations=1, refresh_seconds=0.1, report_path=str(tmp_path / "r.csv")),
        broker=BrokerConfig(initial_cash=10_000.0, fee_bps=0.0, slippage_bps=0.0, depth_fraction=0.10, allow_kalshi_shorting=True),
        risk=RiskConfig(
            min_net_edge_threshold=0.0,
            min_gross_edge=0.0,
            min_liquidity_usd=0.0,
            min_expiry_hours=0.0,
            allow_kalshi_shorting=True,
        ),
        cross_venue_matcher=CrossVenueMatcherConfig(enabled=False),
        watchlist=WatchlistConfig(
            enabled=True,
            csv_path=str(watch_csv),
            scan_log_path=str(tmp_path / "scan_log.jsonl"),
            reject_log_path=str(tmp_path / "rejects.jsonl"),
            approve_log_path=str(tmp_path / "approve.jsonl"),
            min_edge=0.001,
            min_depth_usd=0.0,
            max_age_sec=10_000,
            orderbook_enabled=False,
            execute_paper_trades=True,
            max_trades_per_loop=1,
        ),
    )

    dual = DualInjectionClient(
        venue_a_provider=StaticProvider([polymarket]),
        venue_b_provider=StaticProvider([kalshi]),
        exchange_a="polymarket",
        exchange_b="kalshi",
    )
    notifier = CapturingNotifier()
    engine = Engine(cfg, clients=[dual], notifier=notifier)  # type: ignore[arg-type]
    engine.run_once()

    assert notifier.opportunities, "Expected at least one executed watchlist opportunity"
    opp = notifier.opportunities[0]
    assert opp.type == "CROSS_VENUE_WATCHLIST"
    assert len(opp.metadata.get("trades") or []) >= 1
