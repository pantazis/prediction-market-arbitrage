import time
import logging
from typing import List, Optional
from src.config import AppConfig
from src.polymarket_client import PolymarketClient
from src.detectors import detect_opportunities
from src.risk import RiskManager
from src.broker import PaperBroker
from src.models import Opportunity

logger = logging.getLogger(__name__)

class Engine:
    def __init__(self, config: AppConfig, client: PolymarketClient, notifier=None):
        self.config = config
        self.client = client
        self.risk_manager = RiskManager(config.risk)
        self.notifier = notifier
        self.broker = PaperBroker(config.broker, notifier=notifier)
        self.running = False

    def run_once(self):
        logger.info("Scanning markets...")
        markets = self.client.get_active_markets()
        logger.info(f"Found {len(markets)} active markets")

        opps = detect_opportunities(markets)
        logger.info(f"Detected {len(opps)} opportunities")

        for opp in opps:
            # Send opportunity notification
            if self.notifier:
                self.notifier.notify_opportunity(opp)
            
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
        
        # Send startup notification
        if self.notifier:
            config_summary = f"Paper Trading: {self.config.paper_trading}\nRefresh Interval: {self.config.refresh_interval_seconds}s"
            self.notifier.notify_startup(config_summary)
        
        while self.running:
            try:
                self.run_once()
            except Exception as e:
                logger.exception("Error in main loop")
                if self.notifier:
                    self.notifier.notify_error(str(e), "Main Loop")
            
            logger.info(f"Sleeping {self.config.refresh_interval_seconds}s...")
            time.sleep(self.config.refresh_interval_seconds)

    def generate_report(self):
        # Dump stats
        print(f"Total Trades: {len(self.broker.trades)}")
        print(f"Current Cash: {self.broker.cash}")
