"""
Dry-run arbitrage pipeline tests.

Covers the simulated execution flow using `PaperBroker` and validates:
- Order placement simulation with IDs, timestamps, fees, slippage
- Partial fill behavior respecting available liquidity
- Two-leg hedged trades flatten exposure
- CSV report recording of realized PnL and per-trade fields

Notes:
- The more advanced steps (fill progression over time, hedging-on-failure,
  structured JSON per-opportunity) are not implemented in `predarb` yet.
  A placeholder test is marked xfail to document expected future behavior
  per codebase_schema.json.
"""

from pathlib import Path
from datetime import datetime

import pytest

from predarb.models import TradeAction, Opportunity, Market
from predarb.config import AppConfig
from predarb.broker import PaperBroker
from predarb.engine import Engine


def _make_two_leg_opportunity(market: Market, qty_buy: float, qty_sell: float, price: float) -> Opportunity:
    return Opportunity(
        type="test_two_leg",
        market_ids=[market.id],
        description="Two-leg BUY then SELL on same outcome",
        net_edge=0.01,
        actions=[
            TradeAction(market_id=market.id, outcome_id=market.outcomes[0].id, side="BUY", amount=qty_buy, limit_price=price),
            TradeAction(market_id=market.id, outcome_id=market.outcomes[0].id, side="SELL", amount=qty_sell, limit_price=price),
        ],
    )


def _make_partial_fill_opportunity(market: Market, qty: float, price: float) -> Opportunity:
    return Opportunity(
        type="test_partial",
        market_ids=[market.id],
        description="Single BUY with quantity exceeding available liquidity",
        net_edge=0.02,
        actions=[
            TradeAction(market_id=market.id, outcome_id=market.outcomes[0].id, side="BUY", amount=qty, limit_price=price),
        ],
    )


def test_place_orders_logs_ids_and_costs(markets):
    """Simulate order placement; ensure trades have IDs, timestamps, fees, slippage."""
    cfg = AppConfig()
    broker = PaperBroker(cfg.broker)

    m = markets[0]
    price = m.outcomes[0].price
    opp = _make_partial_fill_opportunity(m, qty=10.0, price=price)

    trades = broker.execute({m.id: m}, opp)
    assert trades, "Expected at least one simulated trade"

    t = trades[0]
    # IDs and timestamps
    assert isinstance(t.id, str) and t.id, "Trade must have a non-empty ID"
    assert isinstance(t.timestamp, datetime), "Trade must have a timestamp"
    # Fees and slippage
    assert t.fees >= 0.0 and t.slippage >= 0.0
    # Realized PnL computed
    assert isinstance(t.realized_pnl, float)
    # Side normalized to BUY/SELL
    assert t.side in {"BUY", "SELL"}


def test_partial_fill_respects_liquidity(markets):
    """Quantity filled should be limited by available liquidity model."""
    cfg = AppConfig()
    broker = PaperBroker(cfg.broker)

    m = markets[0]
    price = m.outcomes[0].price
    # Request a very large amount to force partial fill
    opp = _make_partial_fill_opportunity(m, qty=1_000_000.0, price=price)

    trades = broker.execute({m.id: m}, opp)
    assert trades, "Expected a simulated trade"
    filled_qty = trades[0].amount

    # Available liquidity model in PaperBroker
    per_outcome_liq = m.liquidity * cfg.broker.depth_fraction / max(len(m.outcomes), 1)
    max_qty = per_outcome_liq / max(price, 1e-6)
    assert filled_qty <= max_qty


def test_two_leg_trade_flattens_exposure(markets):
    """Executing BUY then SELL on same outcome should net to zero position."""
    cfg = AppConfig()
    broker = PaperBroker(cfg.broker)

    m = markets[0]
    price = m.outcomes[0].price
    opp = _make_two_leg_opportunity(m, qty_buy=50.0, qty_sell=50.0, price=price)

    trades = broker.execute({m.id: m}, opp)
    assert len(trades) >= 2, "Expected two legs to execute"

    pos_key = f"{m.id}:{m.outcomes[0].id}"
    assert broker.positions.get(pos_key, 0.0) == pytest.approx(0.0)


@pytest.mark.xfail(reason="Hedging/cancel-on-failure not implemented; documented expectation in schema")
def test_failure_does_not_leave_unhedged_exposure(markets):
    """If one leg fails, net exposure should be flattened (future behavior)."""
    cfg = AppConfig()
    broker = PaperBroker(cfg.broker)

    m = markets[0]
    price = m.outcomes[0].price
    # SELL first (no held qty) then BUY -> current implementation leaves exposure
    opp = Opportunity(
        type="test_failure",
        market_ids=[m.id],
        description="SELL fails, BUY succeeds",
        net_edge=0.02,
        actions=[
            TradeAction(market_id=m.id, outcome_id=m.outcomes[0].id, side="SELL", amount=10.0, limit_price=price),
            TradeAction(market_id=m.id, outcome_id=m.outcomes[0].id, side="BUY", amount=10.0, limit_price=price),
        ],
    )
    broker.execute({m.id: m}, opp)
    pos_key = f"{m.id}:{m.outcomes[0].id}"
    # Desired: exposure flattened to 0.0
    assert broker.positions.get(pos_key, 0.0) == pytest.approx(0.0)


def test_report_csv_records_trades(tmp_path, markets):
    """Engine report writes header and rows including PnL, fees, slippage."""
    cfg = AppConfig()
    cfg.engine.report_path = str(tmp_path / "paper_trades.csv")

    # Minimal dummy client/notifier; we won't call run_once
    engine = Engine(cfg, client=None, notifier=None)  # type: ignore[arg-type]

    m = markets[0]
    price = m.outcomes[0].price
    broker = PaperBroker(cfg.broker)
    opp = _make_two_leg_opportunity(m, qty_buy=10.0, qty_sell=10.0, price=price)
    broker.execute({m.id: m}, opp)

    # Write report and validate contents
    engine._write_report(broker.trades)
    report_path = Path(cfg.engine.report_path)
    assert report_path.exists(), "CSV report should be created"
    content = report_path.read_text(encoding="utf-8")
    # Header fields
    assert "timestamp,market_id,outcome_id,side,amount,price,fees,slippage,realized_pnl" in content.splitlines()[0]
    # At least one data row present
    assert len(content.splitlines()) >= 2


def test_live_reporter_headers_and_append(tmp_path, markets):
    """LiveReporter writes two header rows then appends data rows on change."""
    from predarb.reporter import LiveReporter

    reporter = LiveReporter(reports_dir=tmp_path)

    # First report with some markets, no approved opportunities
    appended = reporter.report(
        iteration=1,
        all_markets=markets,
        detected_opportunities=[],
        approved_opportunities=[],
    )
    assert appended is True

    summary_path = tmp_path / "live_summary.csv"
    assert summary_path.exists()
    lines = summary_path.read_text(encoding="utf-8").splitlines()
    # Two header rows + one data row
    assert len(lines) >= 3
    header = lines[0].split(",")
    assert header == [
        "TIMESTAMP","READABLE_TIME","ITERATION","MARKETS","MARKETS_Δ","DETECTED","DETECTED_Δ","APPROVED","APPROVED_Δ","APPROVAL%","STATUS","MARKET_HASH","OPP_HASH"
    ]

    # Second call with identical state should not append (unless CSV missing)
    appended2 = reporter.report(
        iteration=2,
        all_markets=markets,
        detected_opportunities=[],
        approved_opportunities=[],
    )
    assert appended2 is False
