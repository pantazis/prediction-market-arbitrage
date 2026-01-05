import time
import logging
from typing import List
from src.config import AppConfig
from src.polymarket_client import PolymarketClient
from src.detectors import detect_opportunities
from src.risk import RiskManager
from src.broker import PaperBroker
from src.models import Opportunity

logger = logging.getLogger(__name__)

class Engine:
    def __init__(self, config: AppConfig, client: PolymarketClient):
        self.config = config
        self.client = client
        self.risk_manager = RiskManager(config.risk)
        self.broker = PaperBroker(config.broker)
        self.running = False

    def run_once(self):
        logger.info("Scanning markets...")
        markets = self.client.get_active_markets()
        logger.info(f"Found {len(markets)} active markets")

        opps = detect_opportunities(markets)
        logger.info(f"Detected {len(opps)} opportunities")

        for opp in opps:
            # We need the market object for risk check
            # Inefficient lookup O(N) here but fine for Phase 1
            market = next((m for m in markets if m.id == opp.market_id), None)
            if not market: continue

            if self.risk_manager.check(opp, market):
                logger.info(f"Executing Opportunity: {opp.description}")
                trades = self.broker.execute_opportunity(opp)
                if trades:
                    self.risk_manager.record_trade(opp.market_id)
                    logger.info(f"Executed {len(trades)} trades")

    def run_loop(self):
        self.running = True
        while self.running:
            try:
                self.run_once()
            except Exception as e:
                logger.exception("Error in main loop")
            
            logger.info(f"Sleeping {self.config.refresh_interval_seconds}s...")
            time.sleep(self.config.refresh_interval_seconds)

    def generate_report(self):
        # Dump stats
        print(f"Total Trades: {len(self.broker.trades)}")
        print(f"Current Cash: {self.broker.cash}")
