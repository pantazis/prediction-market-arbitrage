from predarb.broker import PaperBroker
from predarb.config import BrokerConfig
from predarb.models import Market, Outcome, Opportunity, TradeAction


def test_broker_executes_with_fees():
    cfg = BrokerConfig(initial_cash=1000.0, fee_bps=10, slippage_bps=20, depth_fraction=1.0)
    broker = PaperBroker(cfg)
    market = Market(id="m", question="q", outcomes=[Outcome(id="y", label="Yes", price=0.5)], liquidity=1000)
    opp = Opportunity(
        type="PARITY",
        market_ids=["m"],
        description="test",
        net_edge=0.1,
        actions=[TradeAction(market_id="m", outcome_id="y", side="BUY", amount=1.0, limit_price=0.5)],
    )
    trades = broker.execute({"m": market}, opp)
    assert trades
    trade = trades[0]
    assert trade.fees > 0
    assert broker.cash < cfg.initial_cash
