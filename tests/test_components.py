import pytest
from src.detectors import detect_parity_arb
from src.models import Opportunity
from src.risk import RiskManager, RiskConfig
from src.broker import PaperBroker, BrokerConfig, TradeAction

def test_detect_parity_arb_found(mock_client):
    markets = mock_client.get_active_markets()
    # m1_clean_arb: 0.45 + 0.45 = 0.90 => Edge 0.10
    market = next(m for m in markets if m.id == "m1_clean_arb")
    opps = detect_parity_arb(market)
    
    assert len(opps) == 1
    assert opps[0].type_name == "PARITY"
    assert pytest.approx(opps[0].estimated_edge) == 0.10

def test_detect_parity_arb_none(mock_client):
    markets = mock_client.get_active_markets()
    # m2_no_arb: 0.60 + 0.40 = 1.00 => Edge 0.00
    market = next(m for m in markets if m.id == "m2_no_arb")
    opps = detect_parity_arb(market)
    assert len(opps) == 0

def test_risk_manager_liquidity(mock_client):
    config = RiskConfig(min_liquidity=1000.0)
    rm = RiskManager(config)
    markets = mock_client.get_active_markets()
    
    # m1 has 10000 liq -> OK
    m1 = next(m for m in markets if m.id == "m1_clean_arb")
    opp1 = detect_parity_arb(m1)[0]
    assert rm.check(opp1, m1) == True
    
    # m3 has 10 liq -> Fail
    m3 = next(m for m in markets if m.id == "m3_low_liq")
    opp3 = detect_parity_arb(m3)[0] # It has arb prices
    assert rm.check(opp3, m3) == False

def test_broker_execution():
    config = BrokerConfig(initial_cash=100.0, fee_bps=0, slippage_bps=0)
    broker = PaperBroker(config)
    
    action1 = TradeAction("m1", "o1", "BUY", 1.0, 0.40)
    action2 = TradeAction("m1", "o2", "BUY", 1.0, 0.40)
    
    opp = Opportunity(
        market_id="m1", market_title="T", type_name="TEST", description="D",
        estimated_edge=0.2, required_capital=0.8,
        actions=[action1, action2]
    )
    
    # We expect trade size logic to default to ~10$ or similar.
    # In broker implementation: trade_size_dollars = 10.0
    # Unit cost = 0.8
    # Quantity = 10 / 0.8 = 12.5
    # Total cost = 10.0
    
    trades = broker.execute_opportunity(opp)
    
    assert len(trades) == 2
    assert broker.cash == 90.0
    assert broker.positions["o1"] == 12.5
    assert broker.positions["o2"] == 12.5

def test_broker_insufficient_funds():
    config = BrokerConfig(initial_cash=5.0) # Less than 10 needed
    broker = PaperBroker(config)
    
    action = TradeAction("m1", "o1", "BUY", 1.0, 0.80)
    opp = Opportunity("m1", "T", "TEST", "D", 0.1, 0.8, [action])
    
    trades = broker.execute_opportunity(opp)
    assert len(trades) == 0
    assert broker.cash == 5.0
