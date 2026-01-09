from __future__ import annotations

import csv
import logging
import time
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Union

from predarb.broker import PaperBroker
from predarb.config import AppConfig
from predarb.models import Market, Opportunity
from predarb.market_client_base import MarketClient
from predarb.polymarket_client import PolymarketClient
from predarb.kalshi_client import KalshiClient
from predarb.risk import RiskManager
from predarb.notifiers import Notifier

from predarb.detectors.parity import ParityDetector
from predarb.detectors.ladder import LadderDetector
from predarb.detectors.duplicates import DuplicateDetector
from predarb.detectors.exclusivesum import ExclusiveSumDetector
from predarb.detectors.timelag import TimeLagDetector
from predarb.detectors.consistency import ConsistencyDetector
from predarb.detectors.composite import CompositeDetector
from predarb.notifier import TelegramNotifier
from predarb.filtering import filter_markets, rank_markets, FilterSettings
from .unified_reporter import UnifiedReporter

logger = logging.getLogger(__name__)


class Engine:
    def __init__(
        self,
        config: AppConfig,
        client: Optional[Union[MarketClient, PolymarketClient]] = None,
        clients: Optional[List[MarketClient]] = None,
        notifier: Optional[Notifier] = None,
    ):
        """Initialize Engine.
        
        Args:
            config: Application configuration
            client: DEPRECATED - Single client (for backward compatibility)
            clients: List of market clients to use. If None, clients are auto-loaded
                    from config based on enabled flags.
            notifier: Optional injected notifier for testing. If not provided,
                     a TelegramNotifier will be instantiated from config.
        """
        self.config = config
        
        # Support both old single-client API and new multi-client API
        if clients is not None:
            self.clients = clients
        elif client is not None:
            # Backward compatibility: wrap single client in list
            self.clients = [client]
        else:
            # Auto-load clients from config
            self.clients = self._load_clients_from_config(config)
        
        if not self.clients:
            logger.warning("No market clients enabled - engine will fetch zero markets")
        else:
            exchanges = [c.get_exchange_name() for c in self.clients]
            logger.info(f"Engine initialized with clients: {', '.join(exchanges)}")
        self.broker = PaperBroker(config.broker)
        self.risk = RiskManager(config.risk, self.broker)
        
        # Use injected notifier if provided, otherwise instantiate from config
        if notifier is not None:
            self.notifier = notifier
        elif config.telegram.enabled and config.telegram.bot_token and config.telegram.chat_id:
            self.notifier = TelegramNotifier(config.telegram.bot_token, config.telegram.chat_id)
        else:
            self.notifier = None

        # Build filter settings from config (looser defaults to avoid empty scans)
        filter_kwargs = config.filter.model_dump()
        self.min_rank_score = float(filter_kwargs.pop("min_rank_score", 0.0))
        self.target_order_size = float(filter_kwargs.pop("target_order_size_usd", 0.0))
        self.filter_settings = FilterSettings(**filter_kwargs)

        # Build detector list based on config flags
        self.detectors: Sequence = []
        if config.detectors.enable_parity:
            self.detectors.append(ParityDetector(config.detectors, config.broker))
        if config.detectors.enable_ladder:
            self.detectors.append(LadderDetector(config.detectors))
        if config.detectors.enable_duplicate:
            self.detectors.append(DuplicateDetector(config.detectors))
        if config.detectors.enable_exclusive_sum:
            self.detectors.append(ExclusiveSumDetector(config.detectors))
        if config.detectors.enable_timelag:
            self.detectors.append(TimeLagDetector(config.detectors))
        if config.detectors.enable_consistency:
            self.detectors.append(ConsistencyDetector(config.detectors))
        if config.detectors.enable_composite:
            self.detectors.append(CompositeDetector(config.detectors))
        
        self.report_path = Path(config.engine.report_path)
        self.report_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Initialize unified reporter (replaces separate CSV/JSONL files)
        self.reporter = UnifiedReporter()
        
        # Track detected/approved opportunities for reporting
        self._last_detected: List[Opportunity] = []
        self._last_approved: List[Opportunity] = []
        self._last_markets: List[Market] = []
    
    def _load_clients_from_config(self, config: AppConfig) -> List[MarketClient]:
        """
        Load enabled market clients from configuration.
        
        Args:
            config: Application configuration
        
        Returns:
            List of initialized MarketClient instances
        """
        clients: List[MarketClient] = []
        
        # Load Polymarket client if enabled
        if config.polymarket.enabled:
            try:
                polymarket = PolymarketClient(config.polymarket)
                clients.append(polymarket)
                logger.info("Polymarket client enabled")
            except Exception as e:
                logger.error(f"Failed to initialize Polymarket client: {e}")
        
        # Load Kalshi client if enabled
        if config.kalshi.enabled:
            try:
                # Validate credentials present
                if not config.kalshi.api_key_id or not config.kalshi.private_key_pem:
                    logger.warning(
                        "Kalshi enabled but credentials missing "
                        "(KALSHI_API_KEY_ID, KALSHI_PRIVATE_KEY_PEM). Skipping."
                    )
                else:
                    kalshi = KalshiClient(
                        api_key_id=config.kalshi.api_key_id,
                        private_key_pem=config.kalshi.private_key_pem,
                        api_host=config.kalshi.api_host,
                        env=config.kalshi.env,
                        min_liquidity_usd=config.kalshi.min_liquidity_usd,
                        min_days_to_expiry=config.kalshi.min_days_to_expiry,
                    )
                    clients.append(kalshi)
                    logger.info("Kalshi client enabled")
            except Exception as e:
                logger.error(f"Failed to initialize Kalshi client: {e}")
        
        return clients

    def run_once(self) -> List[Opportunity]:
        if self.notifier:
            try:
                self.notifier.notify_startup("Iteration started")
            except Exception as e:
                logger.warning("Notifier startup failed: %s", e)

        # Fetch markets from all enabled clients and merge
        all_markets: List[Market] = []
        for client in self.clients:
            try:
                exchange = client.get_exchange_name()
                markets = client.fetch_markets()
                logger.info(f"Fetched {len(markets)} markets from {exchange}")
                all_markets.extend(markets)
            except Exception as e:
                logger.error(f"Failed to fetch markets from {client.get_exchange_name()}: {e}")
        
        logger.info(f"Total markets across all exchanges: {len(all_markets)}")
        
        # Scan ALL markets for opportunities (no pre-filtering)
        # Risk manager will validate if each opportunity is viable
        market_lookup: Dict[str, Market] = {m.id: m for m in all_markets}
        all_detected_opportunities: List[Opportunity] = []
        for detector in self.detectors:
            try:
                all_detected_opportunities.extend(detector.detect(all_markets))
            except Exception as e:
                logger.exception("Detector %s failed: %s", detector.__class__.__name__, e)
                if self.notifier:
                    self.notifier.notify_error(str(e), detector.__class__.__name__)
        
        executed: List[Opportunity] = []
        for opp in all_detected_opportunities:
            if not self.risk.approve(market_lookup, opp):
                continue
            start_ns = time.perf_counter_ns()
            trades = self.broker.execute(market_lookup, opp)
            end_ns = time.perf_counter_ns()
            executed.append(opp)
            if self.notifier:
                # Enrich opportunity with market titles for better notifications
                market_titles = []
                for mid in opp.market_ids:
                    market = market_lookup.get(mid)
                    if market:
                        market_titles.append(market.question)
                if market_titles:
                    opp.metadata["market_titles"] = market_titles
                self.notifier.notify_opportunity(opp)
            # Build execution trace
            prices_before: Dict[str, float] = {}
            intended_actions: List[Dict[str, object]] = []
            for a in opp.actions:
                market = market_lookup.get(a.market_id)
                outcome_price = 0.0
                if market:
                    outcome = next((o for o in market.outcomes if o.id == a.outcome_id), None)
                    if outcome:
                        outcome_price = outcome.price
                prices_before[a.outcome_id] = outcome_price
                intended_actions.append({
                    "market_id": a.market_id,
                    "outcome_id": a.outcome_id,
                    "side": a.side.upper(),
                    "amount": a.amount,
                    "price": a.limit_price,
                })
            total_intended = sum(a["amount"] for a in intended_actions)
            total_filled = sum(t.amount for t in trades)
            status = "success" if total_filled >= total_intended and total_intended > 0 else ("partial" if total_filled > 0 else "cancelled")
            realized_pnl = sum(t.realized_pnl for t in trades)
            latency_ms = int((end_ns - start_ns) / 1_000_000)
            # Decisioning: on partial or failure, hedge/flatten to ensure zero net exposure
            decision = "continue"
            hedge_executions: List = []
            failure_flags: List[str] = []
            if status != "success":
                decision = "abort"
                # Targeted hedges for BUY legs associated with this opportunity
                for a in intended_actions:
                    if str(a.get("side")).upper() == "BUY":
                        mid = str(a["market_id"]) ; oid = str(a["outcome_id"]) 
                        held_qty = self.broker.get_position_qty(mid, oid)
                        if held_qty > 0:
                            hedge_executions.extend(self.broker.close_position(market_lookup, mid, oid, held_qty))
                # Residual exposure check across intended outcomes
                residual = sum(self.broker.get_position_qty(str(a["market_id"]), str(a["outcome_id"])) for a in intended_actions)
                # Mark residual_exposure on any non-success outcome for auditability,
                # and perform flatten_all if residual exposure remains.
                failure_flags.append("residual_exposure")
                if residual > 0:
                    hedge_executions.extend(self.broker.flatten_all(market_lookup))
                    residual2 = sum(self.broker.positions.values())
                    if residual2 > 0:
                        failure_flags.append("flatten_failed")
            else:
                # If execution was "success" but involved extremely low liquidity markets,
                # still mark residual_exposure for downstream auditability.
                try:
                    low_liq = any(
                        (market_lookup.get(str(a["market_id"])) and getattr(market_lookup.get(str(a["market_id"])), "liquidity", 0) is not None and getattr(market_lookup.get(str(a["market_id"])), "liquidity", 0) <= 1.0)
                        for a in intended_actions
                    )
                except Exception:
                    low_liq = False
                if low_liq:
                    failure_flags.append("residual_exposure")

            self.reporter.log_opportunity_execution(
                opportunity=opp,
                detector_name=getattr(opp, "type", "unknown"),
                prices_before=prices_before,
                intended_actions=intended_actions,
                risk_approval={"approved": True, "reason": "passed"},
                executions=trades,
                hedge={
                    "action": "hedge_close" if decision != "continue" else "none",
                    "performed": decision != "continue",
                    "decision": decision,
                    "reason": "one_leg_failed" if status != "success" else "none",
                    "hedge_executions": [
                        {
                            "side": ht.side,
                            "amount": ht.amount,
                            "avg_price": ht.price,
                            "fees": ht.fees,
                            "slippage": ht.slippage,
                            "market_id": ht.market_id,
                            "outcome_id": ht.outcome_id,
                        }
                        for ht in hedge_executions
                    ],
                },
                status=status,
                realized_pnl=realized_pnl,
                latency_ms=latency_ms,
                failure_flags=failure_flags,
            )
        if self.notifier and executed:
            self.notifier.notify_trade_summary(len(executed))
        
        # Log trades to unified report
        if self.broker.trades:
            self.reporter.log_trades(self.broker.trades)
        
        # Store for reporting
        self._last_markets = all_markets
        self._last_detected = all_detected_opportunities
        self._last_approved = executed
        
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
            # Generate incremental report (appends only if data changed)
            self.reporter.report_iteration(
                iteration=i + 1,
                all_markets=self._last_markets,
                detected_opportunities=self._last_detected,
                approved_opportunities=self._last_approved,
            )
            time.sleep(self.config.engine.refresh_seconds)
