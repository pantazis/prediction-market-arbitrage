from __future__ import annotations

import csv
import hashlib
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Union

def _utc_now() -> datetime:
    return datetime.now(timezone.utc)

def _isoformat(dt: Optional[datetime]) -> str:
    if not dt:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()

from predarb.broker import PaperBroker
from predarb.config import AppConfig
from predarb.models import Market, Opportunity
from predarb.models import TradeAction
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
from predarb.watchlist import (
    append_jsonl,
    build_watchlist_row,
    load_watchlist_csv,
    prune_watchlist,
    scan_watchlist,
    upsert_watchlist_rows,
    write_watchlist_csv,
)

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
                top_k=getattr(cross_venue_config, 'top_k', 5),
                encode_batch_size=getattr(cross_venue_config, 'encode_batch_size', 32),
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
        self._last_watchlist_hash: Optional[str] = None
        self._last_watchlist_quotes: Dict[str, Dict[str, Optional[float]]] = {}

        llm_config = getattr(config, "llm_verification", None)
        if llm_config and getattr(llm_config, "enabled", False):
            self.llm_verifier: Optional[LLMVerifier] = LLMVerifier(llm_config)
        else:
            self.llm_verifier = None

    def _fee_bps_for_exchange(self, name: str) -> float:
        for client in self.clients:
            if client.get_exchange_name().lower() == name.lower():
                return float(client.get_metadata().get("fee_bps", self.config.broker.fee_bps))
        return float(self.config.broker.fee_bps)

    def _get_client_by_exchange(self, name: str) -> Optional[MarketClient]:
        for client in self.clients:
            if client.get_exchange_name().lower() == name.lower():
                return client
        return None

    @staticmethod
    def _market_ticker(market: Market) -> str:
        return str(getattr(market, "id", "")).split(":")[-1]

    def _build_cross_venue_opportunity_from_approve_packet(
        self,
        packet: Dict[str, object],
        market_lookup: Dict[str, Market],
    ) -> Optional[Opportunity]:
        try:
            kalshi_block = packet.get("kalshi") or {}
            poly_block = packet.get("polymarket") or {}
            k_market_id = str(kalshi_block.get("market_id") or "")
            p_market_id = str(poly_block.get("market_id") or "")
            side = str(packet.get("side") or "").strip().lower()
            if side not in ("yes", "no"):
                return None

            k_market = market_lookup.get(k_market_id)
            p_market = market_lookup.get(p_market_id)
            if not k_market or not p_market:
                return None

            k_outcome = k_market.outcome_by_label(side)
            p_outcome = p_market.outcome_by_label(side)
            if not k_outcome or not p_outcome:
                return None

            k_bid = kalshi_block.get("bid")
            p_ask = poly_block.get("ask")
            if k_bid is None or p_ask is None:
                return None

            # Use tiny size by default; risk manager / allocation caps will constrain.
            amount = 1.0
            actions = [
                TradeAction(
                    market_id=k_market.id,
                    outcome_id=k_outcome.id,
                    side="SELL",
                    amount=amount,
                    limit_price=float(k_bid),
                ),
                TradeAction(
                    market_id=p_market.id,
                    outcome_id=p_outcome.id,
                    side="BUY",
                    amount=amount,
                    limit_price=float(p_ask),
                ),
            ]
            edge_net = float(packet.get("edge_net") or 0.0)
            desc = (
                f"Watchlist cross-venue {side.upper()} | "
                f"K={self._market_ticker(k_market)} bid={float(k_bid):.4f} "
                f"P={p_market.id} ask={float(p_ask):.4f} | edge_net={edge_net:.6f}"
            )
            return Opportunity(
                type="CROSS_VENUE_WATCHLIST",
                market_ids=[k_market.id, p_market.id],
                description=desc,
                net_edge=edge_net,
                actions=actions,
                metadata={"approve_packet": packet},
            )
        except Exception:
            return None

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
                
                # Separate by exchange for cross-venue matching.
                # Prefer per-market exchange tag so dual injection works.
                for market in markets:
                    ex = str(getattr(market, "exchange", "") or "").lower()
                    if ex == "kalshi":
                        kalshi_markets.append(market)
                    elif ex == "polymarket":
                        poly_markets.append(market)
            except Exception as e:
                logger.error(f"Failed to fetch markets from {client.get_exchange_name()}: {e}")
        
        logger.info(f"Total markets across all exchanges: {len(all_markets)}")

        # SNAPSHOT: Save all markets to JSON for inspection (User Request)
        try:
            snapshot_path = Path("data/markets_snapshot.json")
            snapshot_path.parent.mkdir(parents=True, exist_ok=True)
            # Use model_dump to serialize Pydantic models
            snapshot_data = [m.model_dump(mode="json") for m in all_markets]
            with snapshot_path.open("w", encoding="utf-8") as f:
                json.dump(snapshot_data, f, indent=2)
            logger.info(f"Saved snapshot of {len(all_markets)} markets to {snapshot_path}")
        except Exception as e:
            logger.warning(f"Failed to save market snapshot: {e}")
        
        # Apply cross-venue semantic matching if enabled
        # Apply cross-venue semantic matching if enabled
        if self.cross_venue_matcher.enabled and kalshi_markets and poly_markets:
            try:
                # --- START BATCH PRUNING ---
                # Prune watchlist AT THE START to ensure clean state
                watch_cfg = getattr(self.config, "watchlist", None)
                if watch_cfg and getattr(watch_cfg, "enabled", False):
                    try:
                        # Ensure we can import locally if top-level failed or just for safety
                        from predarb.watchlist import load_watchlist_csv, prune_watchlist, write_watchlist_csv
                        rows = load_watchlist_csv(watch_cfg.csv_path)
                        pruned = prune_watchlist(rows)
                        if len(pruned) != len(rows):
                            removed = len(rows) - len(pruned)
                            logger.info(f"Pruned {removed} expired pairs from watchlist (Start of Loop)")
                            write_watchlist_csv(watch_cfg.csv_path, pruned)
                    except Exception as e:
                        logger.warning(f"Watchlist prune failed: {e}")
                # --- END BATCH PRUNING ---

                # Pre-compute Polymarket embeddings ONCE
                poly_emb_data = None
                if hasattr(self.cross_venue_matcher, "precompute_embeddings"):
                    try:
                        poly_emb_data = self.cross_venue_matcher.precompute_embeddings(poly_markets)
                    except Exception as e:
                        logger.error(f"Failed to precompute embeddings: {e}")

                # Setup Orderbook Fetcher (Reusable)
                orderbook_fetcher = None
                if watch_cfg and getattr(watch_cfg, "enabled", False):
                    orderbook_fetcher = None
                    if getattr(watch_cfg, "orderbook_enabled", False):
                        kalshi_client = self._get_client_by_exchange("kalshi")
                        poly_client = self._get_client_by_exchange("polymarket")
                        kalshi_cache: Dict[str, Dict[str, object]] = {}
                        poly_cache: Dict[str, Dict[str, object]] = {}
                        
                        def _extract_kalshi_book(raw: Dict[str, object], outcome_label: str) -> Optional[Dict[str, object]]:
                            if not raw: return None
                            if "orderbook" in raw and isinstance(raw.get("orderbook"), dict): raw = raw["orderbook"]
                            key = outcome_label.lower()
                            for candidate in (key, key.upper(), key.capitalize()):
                                if isinstance(raw.get(candidate), dict): return raw[candidate]
                            if "yes" in raw or "no" in raw:
                                block = raw.get("yes" if key == "yes" else "no")
                                if isinstance(block, dict): return block
                            if "bids" in raw or "asks" in raw: return raw
                            return None

                        def _fetch_orderbook(venue: str, market: Market, outcome_label: str):
                            if venue == "kalshi" and kalshi_client and hasattr(kalshi_client, "fetch_orderbook"):
                                ticker = market.id.split(":")[-1]
                                if ticker not in kalshi_cache:
                                    raw = kalshi_client.fetch_orderbook(ticker, timeout_s=float(getattr(watch_cfg, "orderbook_timeout_s", 2.5)))
                                    kalshi_cache[ticker] = raw or {}
                                return _extract_kalshi_book(kalshi_cache.get(ticker, {}), outcome_label)
                            if venue == "polymarket" and poly_client and hasattr(poly_client, "fetch_orderbook"):
                                outcome = market.outcome_by_label(outcome_label)
                                if not outcome: return None
                                token_id = str(outcome.id)
                                if token_id not in poly_cache:
                                    raw = poly_client.fetch_orderbook(token_id, timeout_s=float(getattr(watch_cfg, "orderbook_timeout_s", 2.5)))
                                    poly_cache[token_id] = raw or {}
                                return poly_cache.get(token_id)
                            return None
                        
                        orderbook_fetcher = _fetch_orderbook

                # Process in Batches
                chunk_size = 50
                total_kalshi = len(kalshi_markets)
                
                logger.info(f"Starting Batch Processing: {total_kalshi} Kalshi markets in chunks of {chunk_size}")

                for i in range(0, total_kalshi, chunk_size):
                    chunk = kalshi_markets[i : i + chunk_size]
                    batch_num = (i // chunk_size) + 1
                    total_batches = (total_kalshi + chunk_size - 1) // chunk_size
                    
                    logger.info(f"--- Processing Batch {batch_num}/{total_batches} ({len(chunk)} items) ---")
                    
                    # Match Batch
                    pairs = []
                    if poly_emb_data:
                         pairs = self.cross_venue_matcher.find_pairs(chunk, poly_markets, precomputed_poly=poly_emb_data)
                    else:
                         pairs = self.cross_venue_matcher.find_pairs(chunk, poly_markets)

                    if not pairs:
                        continue

                    # Verify Batch
                    batch_verification_results = []
                    for k, p, score in pairs:
                        # Default result
                        is_match, reason = True, "Semantic match"
                        
                        # LLM Verification
                        if self.llm_verifier:
                             # The verifier checks if they are the Same Event
                             # Returns a VerificationResult object
                             v_result = self.llm_verifier.verify_pair(k, p)
                             # Use the returned object directly
                             batch_verification_results.append((k, p, score, v_result))
                        else:
                             # Fallback for no verifier (create manual result)
                             # VerificationResult requires: same_event, confidence, reason
                             # We must import VerificationResult if not available, or use a dummy
                             pass
                             # If llm_verifier is None, we default to True? 
                             # The original code: is_match, reason = True, "Semantic match"
                             # But we need a VerificationResult object matching the signature.
                             # Let's check imports. Yes, VerificationResult is imported.
                             # We need to construct it properly.
                             res = VerificationResult(
                                 same_event=True,
                                 confidence=1.0,
                                 reason="Semantic match (No LLM)"
                             )
                             batch_verification_results.append((k, p, score, res))
                    
                    # Filter & Write Batch
                    pairs_to_add = []
                    for k, p, score, result in batch_verification_results:
                        if result.same_event:
                            # Add to watchlist IMMEDIATELY
                            if watch_cfg and getattr(watch_cfg, "enabled", False):
                                try:
                                    from predarb.watchlist import WatchlistRow, upsert_watchlist_rows
                                    
                                    # Setup default polarity
                                    polarity = "normal"
                                    
                                    # Simple ID generation
                                    pair_id = hashlib.sha256(f"{k.id}|{p.id}|{polarity}".encode()).hexdigest()[:16]

                                    # Get token IDs
                                    p_yes = ""
                                    p_no = ""
                                    if p.outcomes and len(p.outcomes) >= 2:
                                        p_yes = str(p.outcomes[0].id)
                                        p_no = str(p.outcomes[1].id)
                                    
                                    # Create row
                                    new_row = WatchlistRow(
                                        pair_id=pair_id,
                                        k_ticker=k.id.split(":")[-1] if ":" in k.id else k.id,
                                        p_market_id=p.id,
                                        p_yes_token_id=p_yes,
                                        p_no_token_id=p_no,
                                        polarity=polarity,
                                        k_question=str(getattr(k, "question", "")).strip(),
                                        p_question=str(getattr(p, "question", "")).strip(),
                                        k_expiration_time=_isoformat(k.end_date),
                                        p_endDate=_isoformat(p.end_date),
                                        min_edge=float(getattr(watch_cfg, "min_edge", 0.01)),
                                        min_depth_usd=float(getattr(watch_cfg, "min_depth_usd", 50.0)),
                                        max_age_sec=int(getattr(watch_cfg, "max_age_sec", 15)),
                                        status="active",
                                        last_verified_at=_isoformat(_utc_now()),
                                    )
                                    pairs_to_add.append(new_row)
                                except Exception as e:
                                    logger.warning(f"Failed to prepare watchlist row: {e}")

                    # Write Batch to Disk
                    if pairs_to_add and watch_cfg:
                        try:
                            from predarb.watchlist import upsert_watchlist_rows
                            upsert_watchlist_rows(watch_cfg.csv_path, pairs_to_add)
                            logger.info(f"Batch {batch_num}: Added {len(pairs_to_add)} pairs to watchlist")
                            
                            # FAST LOOP: Scan Watchlist IMMEDIATELY
                            if watch_cfg and getattr(watch_cfg, "enabled", False):
                                logger.info(f"Batch {batch_num}: Scanning watchlist for arb (Fast Loop)...")
                                try:
                                    from predarb.watchlist import load_watchlist_csv, scan_watchlist, append_jsonl
                                    # Reload full watchlist to include new items
                                    current_list = load_watchlist_csv(watch_cfg.csv_path)
                                    
                                    scan_output = scan_watchlist(
                                        current_list,
                                        kalshi_markets=kalshi_markets,
                                        polymarket_markets=poly_markets,
                                        fee_bps_kalshi=self._fee_bps_for_exchange("kalshi"),
                                        fee_bps_polymarket=self._fee_bps_for_exchange("polymarket"),
                                        slippage_bps=float(self.config.broker.slippage_bps),
                                        depth_fraction=float(watch_cfg.depth_fraction),
                                        orderbook_fetcher=orderbook_fetcher,
                                    )
                                    if scan_output.scan_log: append_jsonl(watch_cfg.scan_log_path, [scan_output.scan_log])
                                    if scan_output.rejects: append_jsonl(watch_cfg.reject_log_path, scan_output.rejects)
                                    if scan_output.approve_packets: append_jsonl(watch_cfg.approve_log_path, scan_output.approve_packets)
                                    
                                    # Execute Paper Trades
                                    if getattr(watch_cfg, "execute_paper_trades", False) and scan_output.approve_packets:
                                        max_trades = max(int(getattr(watch_cfg, "max_trades_per_loop", 1)), 0)
                                        market_lookup_all: Dict[str, Market] = {m.id: m for m in all_markets}
                                        executed_count = 0
                                        for packet in scan_output.approve_packets:
                                            if executed_count >= max_trades: break
                                            opp = self._build_cross_venue_opportunity_from_approve_packet(packet, market_lookup_all)
                                            if not opp: continue
                                            if not self.risk.approve(market_lookup_all, opp): continue
                                            trades = self.broker.execute(market_lookup_all, opp)
                                            # Update metadata with trade results
                                            opp.metadata["trades"] = [{"market_id": t.market_id, "side": t.side, "amount": t.amount, "price": t.price, "realized_pnl": t.realized_pnl} for t in trades]
                                            executed_count += 1
                                            if self.notifier and hasattr(self.notifier, "notify_opportunity"):
                                                try: self.notifier.notify_opportunity(opp)
                                                except Exception as e: logger.warning(f"Notifier failed: {e}")
                                    
                                    if scan_output.quote_snapshots:
                                        # (Optional) Quote snapshot logic if needed inside loop
                                        pass

                                except Exception as e:
                                    logger.error(f"Fast Loop Scan failed: {e}")

                        except Exception as e:
                            logger.error(f"Failed to write batch to CSV: {e}")

            except Exception as e:
                logger.error(f"Cross-venue matching/batching failed: {e}")

        # End of Loop
        logger.info("Batch processing complete.")

        
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
