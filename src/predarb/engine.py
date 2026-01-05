from __future__ import annotations

import csv
import logging
import time
from pathlib import Path
from typing import Dict, List, Sequence

from predarb.broker import PaperBroker
from predarb.config import AppConfig
from predarb.models import Market, Opportunity
from predarb.polymarket_client import PolymarketClient
from predarb.risk import RiskManager

from predarb.detectors.parity import ParityDetector
from predarb.detectors.ladder import LadderDetector
from predarb.detectors.duplicates import DuplicateDetector
from predarb.detectors.exclusivesum import ExclusiveSumDetector
from predarb.detectors.timelag import TimeLagDetector
from predarb.detectors.consistency import ConsistencyDetector
from predarb.notifier import TelegramNotifier

logger = logging.getLogger(__name__)


class Engine:
    def __init__(self, config: AppConfig, client: PolymarketClient):
        self.config = config
        self.client = client
        self.broker = PaperBroker(config.broker)
        self.risk = RiskManager(config.risk, self.broker)
        self.notifier = None
        if config.telegram.enabled and config.telegram.bot_token and config.telegram.chat_id:
            self.notifier = TelegramNotifier(config.telegram.bot_token, config.telegram.chat_id)

        self.detectors: Sequence = [
            ParityDetector(config.detectors, config.broker),
            LadderDetector(config.detectors),
            DuplicateDetector(config.detectors),
            ExclusiveSumDetector(config.detectors),
            TimeLagDetector(config.detectors),
            ConsistencyDetector(config.detectors),
        ]
        self.report_path = Path(config.engine.report_path)
        self.report_path.parent.mkdir(parents=True, exist_ok=True)

    def run_once(self) -> List[Opportunity]:
        if self.notifier:
            try:
                self.notifier.notify_startup("Iteration started")
            except Exception as e:
                logger.warning("Notifier startup failed: %s", e)

        markets = self.client.fetch_markets()
        market_lookup: Dict[str, Market] = {m.id: m for m in markets}
        opportunities: List[Opportunity] = []
        for detector in self.detectors:
            try:
                opportunities.extend(detector.detect(markets))
            except Exception as e:
                logger.exception("Detector %s failed: %s", detector.__class__.__name__, e)
                if self.notifier:
                    self.notifier.notify_error(str(e), detector.__class__.__name__)
        executed: List[Opportunity] = []
        for opp in opportunities:
            if not self.risk.approve(market_lookup, opp):
                continue
            self.broker.execute(market_lookup, opp)
            executed.append(opp)
            if self.notifier:
                self.notifier.notify_opportunity(opp)
        if self.notifier and executed:
            self.notifier.notify_trade_summary(len(executed))
        self._write_report(self.broker.trades)
        return executed

    def run_self_test(self, markets: List[Market]) -> List[Opportunity]:
        """Run detectors against supplied markets (e.g., fixtures) to prove pipeline works."""
        opportunities: List[Opportunity] = []
        for detector in self.detectors:
            try:
                opportunities.extend(detector.detect(markets))
            except Exception as e:
                logger.exception("Self-test detector %s failed: %s", detector.__class__.__name__, e)
                if self.notifier:
                    self.notifier.notify_error(str(e), f"SelfTest-{detector.__class__.__name__}")
        if self.notifier:
            self.notifier.notify_trade_summary(len(opportunities))
        return opportunities

    def run(self):
        for i in range(self.config.engine.iterations):
            logger.info("Iteration %s", i + 1)
            self.run_once()
            time.sleep(self.config.engine.refresh_seconds)

    def _write_report(self, trades):
        if not trades:
            return
        write_header = not self.report_path.exists()
        with open(self.report_path, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            if write_header:
                writer.writerow(
                    ["timestamp", "market_id", "outcome_id", "side", "amount", "price", "fees", "slippage", "realized_pnl"]
                )
            for t in trades:
                writer.writerow(
                    [t.timestamp.isoformat(), t.market_id, t.outcome_id, t.side, t.amount, t.price, t.fees, t.slippage, t.realized_pnl]
                )
