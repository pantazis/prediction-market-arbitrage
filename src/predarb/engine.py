from __future__ import annotations

import csv
import hashlib
import logging
import time
from datetime import datetime
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
from predarb.cross_venue_matcher import CrossVenueMatcher
from predarb.llm_verifier import LLMVerifier, VerificationResult
from predarb.ab_filters import FilterConfig as ABFilterConfig
from predarb.ab_filters import evaluate_ab_filters, quote_from_market

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
        self.filter_settings = FilterSettings(**filter_kwargs)

        # Initialize cross-venue semantic matcher
        cross_venue_config = getattr(config, 'cross_venue_matcher', None)
        print(f"DEBUG: cross_venue_config = {cross_venue_config}")
        print(f"DEBUG: enabled attr = {getattr(cross_venue_config, 'enabled', False) if cross_venue_config else 'N/A'}")
        logger.debug(f"Cross-venue config: {cross_venue_config}")
        logger.debug(f"Cross-venue enabled attr: {getattr(cross_venue_config, 'enabled', False) if cross_venue_config else 'N/A'}")
        if cross_venue_config and getattr(cross_venue_config, 'enabled', False):
            self.cross_venue_matcher = CrossVenueMatcher(
                model_name=getattr(cross_venue_config, 'model_name', 'all-MiniLM-L6-v2'),
                min_similarity=getattr(cross_venue_config, 'min_similarity', 0.60),
                max_hours_diff=getattr(cross_venue_config, 'max_hours_diff', 24),
                batch_size=getattr(cross_venue_config, 'batch_size', 50),
                tagger_enabled=getattr(cross_venue_config, 'tagger_enabled', True),
                require_tag_overlap=getattr(cross_venue_config, 'require_tag_overlap', False),
                min_shared_tags=getattr(cross_venue_config, 'min_shared_tags', 1),
                cluster_by_tags=getattr(cross_venue_config, 'cluster_by_tags', False),
                cluster_tag_prefixes=getattr(cross_venue_config, 'cluster_tag_prefixes', None),
                keyword_index_enabled=getattr(cross_venue_config, 'keyword_index_enabled', False),
                min_keyword_overlap=getattr(cross_venue_config, 'min_keyword_overlap', 1),
                max_keyword_candidates=getattr(cross_venue_config, 'max_keyword_candidates', 200),
                use_faiss=getattr(cross_venue_config, 'use_faiss', False),
                faiss_top_k=getattr(cross_venue_config, 'faiss_top_k', 5),
                enabled=True
            )
            print(f"DEBUG: Created matcher, enabled={self.cross_venue_matcher.enabled}")
            logger.info("Cross-venue semantic matcher enabled")
        else:
            self.cross_venue_matcher = CrossVenueMatcher(enabled=False)
            print(f"DEBUG: Created disabled matcher, enabled={self.cross_venue_matcher.enabled}")
            logger.info("Cross-venue semantic matcher disabled")
        
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
        self._startup_notified = False
        self._last_cross_venue_match_hash: Optional[str] = None
        self._last_cross_venue_verify_hash: Optional[str] = None
        self._last_cross_venue_arb_hash: Optional[str] = None
        self._last_cross_venue_filter_hash: Optional[str] = None

        llm_config = getattr(config, "llm_verification", None)
        if llm_config and getattr(llm_config, "enabled", False):
            self.llm_verifier: Optional[LLMVerifier] = LLMVerifier(llm_config)
        else:
            self.llm_verifier = None

    def _verify_cross_venue_pairs(
        self,
        pairs: List[tuple[Market, Market, float]],
    ) -> List[tuple[Market, Market, float, VerificationResult]]:
        if not self.llm_verifier:
            return []

        min_similarity = float(getattr(self.llm_verifier.config, "min_similarity_to_verify", 0.0))
        max_pairs = int(getattr(self.llm_verifier.config, "max_pairs_per_group", len(pairs)))
        candidates = [p for p in pairs if p[2] >= min_similarity][:max_pairs]

        results: List[tuple[Market, Market, float, VerificationResult]] = []
        for k_market, p_market, score in candidates:
            result = self.llm_verifier.verify_pair(k_market, p_market)
            results.append((k_market, p_market, score, result))
        return results
    
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
                    )
                    clients.append(kalshi)
                    logger.info("Kalshi client enabled")
            except Exception as e:
                logger.error(f"Failed to initialize Kalshi client: {e}")
        
        return clients

    def run_once(self) -> List[Opportunity]:
        if self.notifier and not self._startup_notified:
            self._startup_notified = True
            try:
                self.notifier.notify_startup("Iteration started")
            except Exception as e:
                logger.warning("Notifier startup failed: %s", e)

        # Fetch markets from all enabled clients and merge
        all_markets: List[Market] = []
        kalshi_markets: List[Market] = []
        poly_markets: List[Market] = []
        
        for client in self.clients:
            try:
                exchange = client.get_exchange_name()
                markets = client.fetch_markets()
                logger.info(f"Fetched {len(markets)} markets from {exchange}")
                all_markets.extend(markets)
                
                # Separate by exchange for cross-venue matching
                if exchange.lower() == 'kalshi':
                    kalshi_markets.extend(markets)
                elif exchange.lower() == 'polymarket':
                    poly_markets.extend(markets)
            except Exception as e:
                logger.error(f"Failed to fetch markets from {client.get_exchange_name()}: {e}")
        
        logger.info(f"Total markets across all exchanges: {len(all_markets)}")
        
        # Apply cross-venue semantic matching if enabled
        if self.cross_venue_matcher.enabled and kalshi_markets and poly_markets:
            try:
                pairs = self.cross_venue_matcher.find_pairs(kalshi_markets, poly_markets)
                if pairs:
                    logger.info(f"Cross-venue matcher found {len(pairs)} semantic pairs")
                    # Log top matches
                    for k, p, score in pairs[:3]:
                        logger.debug(
                            f"Pair: {k.question[:50]} <-> {p.question[:50]} "
                            f"(similarity={score:.2f})"
                        )
                    if self.notifier and hasattr(self.notifier, "notify_cross_venue_matches"):
                        signature = "|".join(
                            f"{k.id}:{p.id}:{score:.4f}" for k, p, score in pairs
                        )
                        match_hash = hashlib.sha256(signature.encode("utf-8")).hexdigest()
                        if match_hash != self._last_cross_venue_match_hash:
                            self._last_cross_venue_match_hash = match_hash
                            try:
                                self.notifier.notify_cross_venue_matches(pairs)
                            except Exception as e:
                                logger.warning("Notifier match alert failed: %s", e)

                    verification_results = self._verify_cross_venue_pairs(pairs)
                    if verification_results:
                        arbitrage_results = []
                        filter_reports = []
                        cost_bps = float(self.config.broker.fee_bps + self.config.broker.slippage_bps)
                        depth_fraction = float(self.config.broker.depth_fraction)
                        ab_filter_cfg = ABFilterConfig()
                        for k_market, p_market, score, result in verification_results:
                            verdict = "PASS" if result.same_event else "FAIL"
                            logger.info(
                                "LLM verify %s sim=%.2f conf=%.2f | K=%s | P=%s | reason=%s",
                                verdict,
                                score,
                                result.confidence,
                                k_market.question,
                                p_market.question,
                                result.reason,
                            )
                            if result.same_event and self.llm_verifier:
                                cases = self.llm_verifier.evaluate_arbitrage_cases(
                                    k_market,
                                    p_market,
                                    cost_bps=cost_bps,
                                    depth_fraction=depth_fraction,
                                )
                                if cases:
                                    best_case = max(cases, key=lambda c: float(c.edge_net))
                                    cases = [best_case]
                                    arbitrage_results.append((k_market, p_market, score, cases))
                                    now_ts = time.time()
                                    for case in cases:
                                        action_a = str(case.kalshi_action or "").upper()
                                        action_b = str(case.polymarket_action or "").upper()
                                        outcome_a = "yes" if "YES" in action_a else "no" if "NO" in action_a else None
                                        outcome_b = "yes" if "YES" in action_b else "no" if "NO" in action_b else None
                                        side_a = "SELL" if ("SHORT" in action_a or "SELL" in action_a) else "BUY"
                                        side_b = "SELL" if ("SHORT" in action_b or "SELL" in action_b) else "BUY"

                                        trade_price_a = None
                                        trade_price_b = None
                                        if outcome_a:
                                            key_a = f"kalshi_{outcome_a}_{'bid' if side_a == 'SELL' else 'ask'}"
                                            trade_price_a = case.prices_used.get(key_a)
                                        if outcome_b:
                                            key_b = f"polymarket_{outcome_b}_{'bid' if side_b == 'SELL' else 'ask'}"
                                            trade_price_b = case.prices_used.get(key_b)

                                        quote_a = quote_from_market(k_market, outcome_a or "", depth_fraction)
                                        quote_b = quote_from_market(p_market, outcome_b or "", depth_fraction)

                                        report = evaluate_ab_filters(
                                            now_ts=now_ts,
                                            kalshi_leg=quote_a,
                                            polymarket_leg=quote_b,
                                            trade_price_a=trade_price_a,
                                            trade_price_b=trade_price_b,
                                            edge_gross=case.edge_gross,
                                            config=ab_filter_cfg,
                                        )
                                        filter_reports.append(
                                            {
                                                "kalshi_title": k_market.question,
                                                "polymarket_title": p_market.question,
                                                "case": case.model_dump(),
                                                "filter_report": {
                                                    "passed": report.passed,
                                                    "fail_filter": report.fail_filter,
                                                    "fail_reason": report.fail_reason,
                                                    "edge_gross": report.edge_gross,
                                                    "edge_net": report.edge_net,
                                                    "executable_size_usd": report.executable_size_usd,
                                                    "items": [
                                                        {
                                                            "code": item.code,
                                                            "passed": item.passed,
                                                            "value": item.value,
                                                            "threshold": item.threshold,
                                                            "detail": item.detail,
                                                        }
                                                        for item in report.items
                                                    ],
                                                },
                                            }
                                        )
                        if self.notifier and hasattr(self.notifier, "notify_cross_venue_verification"):
                            signature = "|".join(
                                f"{k.id}:{p.id}:{score:.4f}:{int(result.same_event)}:{result.reason}"
                                for k, p, score, result in verification_results
                            )
                            verify_hash = hashlib.sha256(signature.encode("utf-8")).hexdigest()
                            if verify_hash != self._last_cross_venue_verify_hash:
                                self._last_cross_venue_verify_hash = verify_hash
                                try:
                                    self.notifier.notify_cross_venue_verification(
                                        verification_results
                                    )
                                except Exception as e:
                                    logger.warning("Notifier verify alert failed: %s", e)
                        if self.notifier and hasattr(self.notifier, "notify_cross_venue_arbitrage"):
                            if arbitrage_results:
                                signature = "|".join(
                                    f"{k.id}:{p.id}:{score:.4f}:{case.case_name}:{case.edge_net:.6f}"
                                    for k, p, score, cases in arbitrage_results
                                    for case in cases
                                )
                            else:
                                signature = "no_arbitrage"
                            arbitrage_hash = hashlib.sha256(signature.encode("utf-8")).hexdigest()
                            if arbitrage_hash != self._last_cross_venue_arb_hash:
                                self._last_cross_venue_arb_hash = arbitrage_hash
                                try:
                                    self.notifier.notify_cross_venue_arbitrage(arbitrage_results)
                                except Exception as e:
                                    logger.warning("Notifier arbitrage alert failed: %s", e)
                        if self.notifier and hasattr(self.notifier, "notify_cross_venue_filters"):
                            if filter_reports:
                                signature = "|".join(
                                    f"{entry['case']['case_name']}:{entry['filter_report']['passed']}"
                                    for entry in filter_reports
                                )
                            else:
                                signature = "no_filters"
                            filter_hash = hashlib.sha256(signature.encode("utf-8")).hexdigest()
                            if filter_hash != self._last_cross_venue_filter_hash:
                                self._last_cross_venue_filter_hash = filter_hash
                                try:
                                    self.notifier.notify_cross_venue_filters(filter_reports)
                                except Exception as e:
                                    logger.warning("Notifier filter alert failed: %s", e)
                        if self.notifier and hasattr(self.notifier, "notify_cross_venue_risk"):
                            try:
                                self.notifier.notify_cross_venue_risk(filter_reports)
                            except Exception as e:
                                logger.warning("Notifier risk alert failed: %s", e)
                        if self.notifier and hasattr(self.notifier, "notify_cross_venue_trade"):
                            try:
                                self.notifier.notify_cross_venue_trade(filter_reports)
                            except Exception as e:
                                logger.warning("Notifier trade alert failed: %s", e)
            except Exception as e:
                logger.error(f"Cross-venue matching failed: {e}")
        
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
        
        if len(all_detected_opportunities) > 1:
            def _edge_per_day(opp: Opportunity) -> float:
                expiries = []
                for mid in opp.market_ids:
                    market = market_lookup.get(mid)
                    if market and market.expiry:
                        expiries.append(market.expiry)
                if not expiries:
                    return opp.net_edge
                max_expiry = max(expiries)
                days = (max_expiry - datetime.utcnow()).total_seconds() / 86_400
                if days <= 0:
                    return opp.net_edge
                return opp.net_edge / days

            best_opp = max(all_detected_opportunities, key=_edge_per_day)
            all_detected_opportunities = [best_opp]

        executed: List[Opportunity] = []
        for opp in all_detected_opportunities:
            if not self.risk.approve(market_lookup, opp):
                continue
            start_ns = time.perf_counter_ns()
            trades = self.broker.execute(market_lookup, opp)
            end_ns = time.perf_counter_ns()
            executed.append(opp)
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

            opp.metadata["risk_approval"] = {"approved": True, "reason": "passed"}
            opp.metadata["execution"] = {
                "status": status,
                "total_intended": total_intended,
                "total_filled": total_filled,
                "realized_pnl": realized_pnl,
                "latency_ms": latency_ms,
            }
            opp.metadata["trades"] = [
                {
                    "market_id": t.market_id,
                    "outcome_id": t.outcome_id,
                    "side": t.side,
                    "amount": t.amount,
                    "price": t.price,
                    "fees": t.fees,
                    "slippage": t.slippage,
                    "realized_pnl": t.realized_pnl,
                }
                for t in trades
            ]

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
