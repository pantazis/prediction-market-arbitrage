
import logging
import sys
from datetime import datetime, timezone
import json

# Add src to path
import os
sys.path.append(os.path.join(os.getcwd(), "src"))

from predarb.ab_filters import (
    FilterConfig,
    evaluate_ab_filters,
    Quote,
    extract_best_bid_ask_from_orderbook
)
from predarb.risk import RiskManager
from predarb.config import RiskConfig
from predarb.models import Opportunity, TradeAction

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("VERIFY")

def test_filters():
    logger.info("--- Testing AB Filters ---")
    
    cfg = FilterConfig(
        min_leg_usd=50.0,
        min_depth_usd=50.0,
        max_staleness_sec=60,
        min_edge=0.01,
        fee_bps_a=0, # Simplify for test
        fee_bps_b=0,
        slippage_bps=0
    )
    
    now = datetime.now(timezone.utc).timestamp()
    
    # Case 1: Perfect Arb
    # A (Kalshi) Bid 0.60, B (Poly) Ask 0.50 -> Edge 0.10
    q_a = Quote(venue="kalshi", market_id="k1", outcome="YES", bid=0.60, ask=0.62, bid_size_usd=100, ask_size_usd=100, depth_usd=100, ts=now)
    q_b = Quote(venue="polymarket", market_id="p1", outcome="YES", bid=0.48, ask=0.50, bid_size_usd=100, ask_size_usd=100, depth_usd=100, ts=now)
    
    report = evaluate_ab_filters(
        now_ts=now,
        kalshi_leg=q_a,
        polymarket_leg=q_b,
        trade_price_a=q_a.bid,
        trade_price_b=q_b.ask,
        edge_gross=q_a.bid - q_b.ask,
        config=cfg
    )
    
    if report.passed:
        logger.info("✅ Case 1 (Valid Arb): PASSED")
    else:
        logger.error(f"❌ Case 1 (Valid Arb): FAILED - {report.fail_reason}")

    # Case 2: Stale Data
    q_stale = Quote(venue="kalshi", market_id="k1", outcome="YES", bid=0.60, ask=0.62, bid_size_usd=100, ask_size_usd=100, depth_usd=100, ts=now - 120)
    report_stale = evaluate_ab_filters(
        now_ts=now,
        kalshi_leg=q_stale,
        polymarket_leg=q_b,
        trade_price_a=q_stale.bid,
        trade_price_b=q_b.ask,
        edge_gross=q_stale.bid - q_b.ask,
        config=cfg
    )
    
    if not report_stale.passed and "stale" in str(report_stale.fail_filter).lower():
        logger.info(f"✅ Case 2 (Stale): REJECTED as expected ({report_stale.fail_reason})")
    else:
        logger.error(f"❌ Case 2 (Stale): Unexpected pass or wrong error: {report_stale.fail_reason}")

    # Case 3: Low Liquidity
    q_small = Quote(venue="kalshi", market_id="k1", outcome="YES", bid=0.60, ask=0.62, bid_size_usd=10, ask_size_usd=10, depth_usd=10, ts=now)
    report_small = evaluate_ab_filters(
        now_ts=now,
        kalshi_leg=q_small,
        polymarket_leg=q_b,
        trade_price_a=q_small.bid,
        trade_price_b=q_b.ask,
        edge_gross=q_small.bid - q_b.ask,
        config=cfg
    )
    
    if not report_small.passed and "size" in str(report_small.fail_filter).lower():
         logger.info(f"✅ Case 3 (Low Size): REJECTED as expected ({report_small.fail_reason})")
    elif not report_small.passed and "depth" in str(report_small.fail_filter).lower():
         logger.info(f"✅ Case 3 (Low Depth): REJECTED as expected ({report_small.fail_reason})")
    else:
         logger.error(f"❌ Case 3 (Low Size): Unexpected pass or wrong error: {report_small.fail_filter}")

def test_risk():
    logger.info("--- Testing Risk Manager ---")
    
    class MockBroker:
        def __init__(self):
            self.positions = {} # "market:outcome" -> qty
            self.cash = 10000.0
            
    r_cfg = RiskConfig(
        max_open_positions=5,
        min_liquidity_usd=100,
        max_allocation_per_market=0.1, # $1000
        min_net_edge_threshold=0.01
    )
    
    broker = MockBroker()
    risk = RiskManager(r_cfg, broker)
    
    # Case 1: Valid Opportunity
    opp = Opportunity(
        type="ARBITRAGE",
        market_ids=["k1", "p1"],
        description="Test Arb",
        net_edge=0.05,
        actions=[
            TradeAction(market_id="k1", outcome_id="YES", side="BUY", amount=10, limit_price=0.50),
            # In purely buy-only arb (long-long), we might buy YES on A and YES on B? No, that's not arb.
            # Arb is Long YES on A and Long NO on B (if binary).
            # risk.py enforces "BUY-only strategy" -> "No SELL without existing inventory".
            # So a valid arb here is BUY YES (A) + BUY NO (B).
            TradeAction(market_id="p1", outcome_id="NO", side="BUY", amount=10, limit_price=0.40)
        ]
    )
    
    # Mock lookup
    class MockMarket:
        def __init__(self, mid, liq):
            self.id = mid
            self.liquidity = liq
            self.exchange = "kalshi" if "k" in mid else "polymarket"
            self.outcomes = []
            self.end_date = datetime.utcnow() +  (datetime.utcnow() - datetime.now())  +  (datetime.now() - datetime.utcnow()) # hack delta
            # Make expiry far future
            from datetime import timedelta
            self.end_date = datetime.utcnow() + timedelta(days=5)

    market_lookup = {
        "k1": MockMarket("k1", 1000),
        "p1": MockMarket("p1", 1000)
    }
    
    if risk.approve(market_lookup, opp):
        logger.info("✅ Case 1 (Valid Risk): APPROVED")
    else:
        logger.error("❌ Case 1 (Valid Risk): REJECTED")

    # Case 2: Risk Limit (Edge too low)
    opp_bad = Opportunity(
        type="ARBITRAGE",
        market_ids=["k1", "p1"],
        description="Bad Arb",
        net_edge=0.005, # < 0.01
        actions=[
             TradeAction(market_id="k1", outcome_id="YES", side="BUY", amount=10, limit_price=0.50),
             TradeAction(market_id="p1", outcome_id="NO", side="BUY", amount=10, limit_price=0.40)
        ]
    )
    
    if not risk.approve(market_lookup, opp_bad):
        logger.info("✅ Case 2 (Low Edge): REJECTED as expected")
    else:
        logger.error("❌ Case 2 (Low Edge): Unexpected APPROVAL")
        
    # Case 3: Sell without inventory
    opp_short = Opportunity(
        type="ARBITRAGE",
        market_ids=["k1"],
        description="Shorting",
        net_edge=0.1,
        actions=[
            TradeAction(market_id="k1", outcome_id="YES", side="SELL", amount=10, limit_price=0.60)
        ]
    )
    # Mock config allows kalshi shorting? Default False.
    if not risk.approve(market_lookup, opp_short):
        logger.info("✅ Case 3 (Naked Short): REJECTED as expected")
    else:
        logger.error("❌ Case 3 (Naked Short): Unexpected APPROVAL")


if __name__ == "__main__":
    test_filters()
    test_risk()
