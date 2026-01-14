from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import requests

from predarb.ab_filters import FilterConfig, FilterReport, Quote, evaluate_ab_filters
from predarb.config import AppConfig
from predarb.models import Market
from predarb.strict_ab_llm import StrictABLLMResult, StrictABLLMVerifier, build_llm_provider
from predarb.strict_ab_watchlist import WatchlistEntry, WatchlistManager
from predarb.tagging import fast_tag_market, normalize_tag

logger = logging.getLogger(__name__)


@dataclass
class CandidatePair:
    pair_key: str
    kalshi_market: Market
    polymarket_market: Market
    shared_tags: List[str]
    expiry_diff_hours: float


@dataclass
class ArbitrageCase:
    case_name: str
    kalshi_action: str
    polymarket_action: str
    edge_gross: float
    edge_net: float
    trade_price_a: float
    trade_price_b: float
    max_size_usd: float
    reason: str
    prices_used: Dict[str, Any]


@dataclass
class StrictABResult:
    pair_key: str
    case: ArbitrageCase
    filter_report: FilterReport


class AuditLogger:
    def __init__(self, path: str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def log(self, stage: str, payload: Dict[str, Any]) -> None:
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "stage": stage,
            **payload,
        }
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry) + "\n")


class StrictABPipeline:
    def __init__(self, config: AppConfig, notifier: Optional[object] = None) -> None:
        self.config = config
        self.strict_cfg = config.strict_ab
        self.notifier = notifier
        self.audit = AuditLogger(self.strict_cfg.audit_log)
        self.watchlist = WatchlistManager(
            self.strict_cfg.watchlist_json,
            self.strict_cfg.watchlist_csv,
        )
        llm_cfg = self.strict_cfg.llm
        if self.strict_cfg.dry_run:
            provider = build_llm_provider("mock", llm_cfg.model, llm_cfg.timeout_s)
        else:
            provider = build_llm_provider(llm_cfg.provider, llm_cfg.model, llm_cfg.timeout_s)
        self.llm = StrictABLLMVerifier(
            provider=provider,
            cache_path=llm_cfg.cache_path,
            daily_limit=llm_cfg.daily_limit,
        )
        self._market_lookup: Dict[str, Market] = {}
        self._last_markets: List[Market] = []

    def run_once(self) -> List[StrictABResult]:
        kalshi_raw, poly_raw, kalshi_markets, poly_markets = self._stage0_fetch()
        self._last_markets = kalshi_markets + poly_markets
        self._market_lookup = {m.id: m for m in self._last_markets}
        self._stage1_tag(kalshi_markets)
        self._stage1_tag(poly_markets)
        candidates = self._stage2_pairs(kalshi_markets, poly_markets)
        if self.strict_cfg.llm.enabled:
            passed_pairs = self._stage3_verify(candidates)
            watchlist_entries = self._stage4_watchlist(passed_pairs, kalshi_markets + poly_markets)
        else:
            existing = self.watchlist.load()
            watchlist_entries = list(self.watchlist.prune(existing, self._market_lookup).values())
        results = self._stage5_to_7_scan(watchlist_entries)
        return results

    def _stage0_fetch(self) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Market], List[Market]]:
        kalshi_raw = self._fetch_kalshi_raw()
        poly_raw = self._fetch_polymarket_raw()
        dump_dir = self._dump_raw(kalshi_raw, poly_raw)
        self.audit.log("stage0", {"kalshi": len(kalshi_raw), "polymarket": len(poly_raw), "dump_dir": dump_dir})
        kalshi_markets = [m for m in (self._normalize_kalshi(m) for m in kalshi_raw) if m]
        poly_markets = [m for m in (self._normalize_polymarket(m) for m in poly_raw) if m]
        return kalshi_raw, poly_raw, kalshi_markets, poly_markets

    def _dump_raw(self, kalshi_raw: List[Dict[str, Any]], poly_raw: List[Dict[str, Any]]) -> str:
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_UTC")
        out_dir = Path(self.strict_cfg.raw_dump_dir) / ts
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "kalshi_markets.json").write_text(json.dumps(kalshi_raw, indent=2))
        (out_dir / "polymarket_markets.json").write_text(json.dumps(poly_raw, indent=2))
        self._write_jsonl(out_dir / "kalshi_markets.jsonl", kalshi_raw)
        self._write_jsonl(out_dir / "polymarket_markets.jsonl", poly_raw)
        return str(out_dir)

    @staticmethod
    def _write_jsonl(path: Path, rows: Iterable[Dict[str, Any]]) -> None:
        with path.open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row) + "\n")

    def _fetch_kalshi_raw(self) -> List[Dict[str, Any]]:
        base_url = self.config.kalshi.api_host.rstrip("/") + "/trade-api/v2/markets"
        markets: List[Dict[str, Any]] = []
        cursor = None
        while True:
            params = {"status": "open", "limit": 200, "mve_filter": "exclude"}
            if cursor:
                params["cursor"] = cursor
            try:
                resp = requests.get(base_url, params=params, timeout=15)
                resp.raise_for_status()
                data = resp.json()
            except Exception as exc:
                logger.warning("Kalshi raw fetch failed: %s", exc)
                break
            batch = data.get("markets", []) if isinstance(data, dict) else []
            markets.extend(batch)
            cursor = data.get("cursor") if isinstance(data, dict) else None
            if not cursor or not batch:
                break
        return markets

    def _fetch_polymarket_raw(self) -> List[Dict[str, Any]]:
        base_url = self.config.polymarket.host.rstrip("/") + "/markets"
        markets: List[Dict[str, Any]] = []
        offset = 0
        limit = 1000
        while True:
            params = {"closed": "false", "limit": limit, "offset": offset}
            try:
                resp = requests.get(base_url, params=params, timeout=15)
                resp.raise_for_status()
                data = resp.json()
            except Exception as exc:
                logger.warning("Polymarket raw fetch failed: %s", exc)
                break
            batch = data if isinstance(data, list) else data.get("data", [])
            if not batch:
                break
            markets.extend(batch)
            offset += limit
        return markets

    def _normalize_kalshi(self, data: Dict[str, Any]) -> Optional[Market]:
        try:
            ticker = data.get("ticker")
            if not ticker:
                return None
            market_type = str(data.get("market_type") or data.get("type") or "").lower()
            if market_type and market_type != "binary":
                return None
            yes_bid = self._safe_price(data.get("yes_bid"))
            yes_ask = self._safe_price(data.get("yes_ask"))
            no_bid = self._safe_price(data.get("no_bid"))
            no_ask = self._safe_price(data.get("no_ask"))
            yes_price = self._mid_price(yes_bid, yes_ask)
            no_price = self._mid_price(no_bid, no_ask)
            expiry = self._parse_dt(data.get("close_time"))
            outcomes = [
                {"id": f"{ticker}:YES", "label": "YES", "price": yes_price},
                {"id": f"{ticker}:NO", "label": "NO", "price": no_price},
            ]
            market = Market(
                id=f"kalshi:{data.get('event_ticker', '')}:{ticker}",
                question=data.get("title") or data.get("name") or ticker,
                outcomes=outcomes,
                end_date=expiry,
                expiry=expiry,
                liquidity=float(data.get("liquidity", 0.0) or data.get("open_interest", 0.0) or 0.0),
                volume=float(data.get("volume", 0.0) or 0.0),
                description=data.get("rules_primary") or data.get("subtitle"),
                resolution_source=data.get("resolution_source") or "Kalshi",
                best_bid={"yes": yes_bid, "no": no_bid},
                best_ask={"yes": yes_ask, "no": no_ask},
                ticker=ticker,
                event_ticker=data.get("event_ticker"),
                status=data.get("status"),
            )
            market.exchange = "kalshi"  # type: ignore
            return market
        except Exception as exc:
            logger.debug("Kalshi normalize failed: %s", exc)
            return None

    def _normalize_polymarket(self, data: Dict[str, Any]) -> Optional[Market]:
        try:
            outcomes_raw = data.get("outcomes", "[]")
            prices_raw = data.get("outcomePrices", "[]")
            token_ids_raw = data.get("clobTokenIds", "[]")
            outcomes = json.loads(outcomes_raw) if isinstance(outcomes_raw, str) else outcomes_raw
            prices = json.loads(prices_raw) if isinstance(prices_raw, str) else prices_raw
            token_ids = json.loads(token_ids_raw) if isinstance(token_ids_raw, str) else token_ids_raw
            if not isinstance(outcomes, list) or len(outcomes) != 2:
                return None
            parsed_outcomes = []
            for i, label in enumerate(outcomes):
                price = float(prices[i]) if i < len(prices) else 0.0
                parsed_outcomes.append(
                    {
                        "id": str(token_ids[i]) if i < len(token_ids) else str(i),
                        "label": str(label),
                        "price": price,
                    }
                )
            best_bid: Dict[str, float] = {}
            best_ask: Dict[str, float] = {}
            for outcome in parsed_outcomes:
                label = str(outcome["label"]).strip().lower()
                if label in ("yes", "no"):
                    mid = float(outcome["price"]) if outcome["price"] is not None else 0.0
                    best_bid[label] = max(0.0, mid - 0.001)
                    best_ask[label] = min(1.0, mid + 0.001)
            expiry = self._parse_dt(data.get("endDate") or data.get("endDateIso"))
            market = Market(
                id=str(data.get("conditionId") or data.get("id")),
                question=data.get("question") or data.get("title") or "Unknown",
                outcomes=parsed_outcomes,
                end_date=expiry,
                expiry=expiry,
                liquidity=float(data.get("liquidityNum", 0.0) or data.get("liquidity", 0.0) or 0.0),
                volume=float(data.get("volumeNum", 0.0) or data.get("volume", 0.0) or 0.0),
                description=data.get("description"),
                resolution_source=data.get("resolutionSource"),
                tags=data.get("tags") or [],
                status=data.get("status"),
                closed=data.get("closed"),
                active=data.get("active"),
                best_bid=best_bid,
                best_ask=best_ask,
                clob_token_ids=token_ids,
            )
            market.exchange = "polymarket"  # type: ignore
            return market
        except Exception as exc:
            logger.debug("Polymarket normalize failed: %s", exc)
            return None

    @staticmethod
    def _safe_price(value: Any) -> float:
        try:
            if value is None:
                return 0.0
            price = float(value)
            if price > 1:
                price = price / 100.0
            return max(0.0, min(price, 1.0))
        except Exception:
            return 0.0

    @staticmethod
    def _mid_price(bid: float, ask: float) -> float:
        if bid and ask:
            return (bid + ask) / 2.0
        return bid or ask or 0.0

    @staticmethod
    def _parse_dt(value: Any) -> Optional[datetime]:
        if not value:
            return None
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except Exception:
            return None

    def _stage1_tag(self, markets: List[Market]) -> None:
        for market in markets:
            market.tags = fast_tag_market(market)
        self.audit.log("stage1", {"count": len(markets)})

    def _stage2_pairs(self, kalshi: List[Market], poly: List[Market]) -> List[CandidatePair]:
        tag_index: Dict[str, List[Market]] = {}
        for market in poly:
            for tag in market.tags:
                norm = normalize_tag(tag)
                if not norm:
                    continue
                tag_index.setdefault(norm, []).append(market)

        pairs: Dict[str, CandidatePair] = {}
        for k_market in kalshi:
            k_tags = {normalize_tag(t) for t in k_market.tags}
            if not k_tags:
                continue
            k_expiry = k_market.expiry or k_market.end_date
            if not k_expiry:
                continue
            for tag in k_tags:
                for p_market in tag_index.get(tag, []):
                    p_expiry = p_market.expiry or p_market.end_date
                    if not p_expiry:
                        continue
                    diff_hours = abs((k_expiry - p_expiry).total_seconds()) / 3600.0
                    if diff_hours > self.strict_cfg.max_hours_diff:
                        continue
                    shared = sorted(k_tags.intersection({normalize_tag(t) for t in p_market.tags}))
                    if len(shared) < self.strict_cfg.min_shared_tags:
                        continue
                    pair_key = f"{self._kalshi_ticker(k_market)}::{p_market.id}"
                    pairs[pair_key] = CandidatePair(
                        pair_key=pair_key,
                        kalshi_market=k_market,
                        polymarket_market=p_market,
                        shared_tags=shared,
                        expiry_diff_hours=diff_hours,
                    )
        self.audit.log("stage2", {"candidate_pairs": len(pairs)})
        return list(pairs.values())

    def _stage3_verify(self, candidates: List[CandidatePair]) -> List[Tuple[CandidatePair, StrictABLLMResult]]:
        results = []
        skipped = 0
        for candidate in candidates:
            result = self.llm.verify_pair(candidate.pair_key, candidate.kalshi_market, candidate.polymarket_market)
            if result is None:
                skipped += 1
                continue
            if result.passed:
                results.append((candidate, result))
        self.audit.log("stage3", {"verified": len(results), "skipped": skipped})
        return results

    def _stage4_watchlist(
        self,
        verified: List[Tuple[CandidatePair, StrictABLLMResult]],
        markets: List[Market],
    ) -> List[WatchlistEntry]:
        existing = self.watchlist.load()
        market_lookup = {m.id: m for m in markets}
        existing = self.watchlist.prune(existing, market_lookup)
        updated = dict(existing)
        now = datetime.now(timezone.utc).isoformat()
        for candidate, verdict in verified:
            k = candidate.kalshi_market
            p = candidate.polymarket_market
            entry = WatchlistEntry(
                pair_key=candidate.pair_key,
                kalshi_ticker=self._kalshi_ticker(k),
                kalshi_market_id=k.id,
                kalshi_title=k.question,
                kalshi_expiry=(k.expiry or k.end_date).isoformat() if (k.expiry or k.end_date) else None,
                polymarket_id=p.id,
                polymarket_market_id=p.id,
                polymarket_title=p.question,
                polymarket_expiry=(p.expiry or p.end_date).isoformat() if (p.expiry or p.end_date) else None,
                tags=candidate.shared_tags,
                llm_confidence=verdict.confidence,
                llm_reason=verdict.reason,
                last_verified=now,
            )
            updated[entry.pair_key] = entry
        entries = list(updated.values())
        self.watchlist.save(entries)
        self.audit.log("stage4", {"watchlist_size": len(entries)})
        return entries

    def _stage5_to_7_scan(self, entries: List[WatchlistEntry]) -> List[StrictABResult]:
        results: List[StrictABResult] = []
        now_ts = time.time()
        for entry in entries:
            k_market = self._load_market(entry.kalshi_market_id)
            p_market = self._load_market(entry.polymarket_market_id)
            if not k_market or not p_market:
                continue
            if self.strict_cfg.dry_run:
                orderbook_a = self._fake_orderbook(k_market)
                orderbook_b = {
                    "yes": self._fake_orderbook(p_market, "yes"),
                    "no": self._fake_orderbook(p_market, "no"),
                }
            else:
                orderbook_a = self._fetch_kalshi_orderbook(entry.kalshi_ticker)
                orderbook_b = self._fetch_polymarket_orderbook(p_market)
            cases = self._compute_cases(k_market, p_market)
            for case in cases:
                report = self._apply_filters(
                    now_ts,
                    k_market,
                    p_market,
                    orderbook_a,
                    orderbook_b,
                    case,
                )
                results.append(StrictABResult(pair_key=entry.pair_key, case=case, filter_report=report))
                if report.passed:
                    self._notify_pass(entry, case, report)
                    self.audit.log(
                        "stage7",
                        {
                            "pair_key": entry.pair_key,
                            "case": case.case_name,
                            "edge_net": report.edge_net,
                            "size": report.executable_size_usd,
                            "depth": min(report.depth_a or 0.0, report.depth_b or 0.0),
                            "reason": case.reason,
                        },
                    )
        self.audit.log("stage5_7", {"results": len(results)})
        return results

    def _load_market(self, market_id: str) -> Optional[Market]:
        # Stage5 reads latest data; currently relies on cached watchlist IDs.
        # Fallback to None if missing.
        return self._market_lookup.get(market_id)

    def _fetch_kalshi_orderbook(self, ticker: str) -> Optional[Dict[str, Any]]:
        base_url = self.config.kalshi.api_host.rstrip("/") + f"/trade-api/v2/markets/{ticker}/orderbook"
        try:
            resp = requests.get(base_url, timeout=10)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            logger.debug("Kalshi orderbook fetch failed: %s", exc)
            return None

    def _fetch_polymarket_orderbook(self, market: Market) -> Optional[Dict[str, Any]]:
        token_ids = list(getattr(market, "clob_token_ids", []) or [])
        if not token_ids:
            return None
        try:
            from py_clob_client.client import ClobClient
            from py_clob_client.clob_types import ApiCreds
        except Exception:
            ClobClient = None

        if ClobClient:
            creds = None
            if self.config.polymarket.api_key and self.config.polymarket.secret and self.config.polymarket.passphrase:
                creds = ApiCreds(
                    api_key=self.config.polymarket.api_key,
                    api_secret=self.config.polymarket.secret,
                    api_passphrase=self.config.polymarket.passphrase,
                )
            client = ClobClient(
                host="https://clob.polymarket.com",
                key=self.config.polymarket.private_key,
                chain_id=self.config.polymarket.chain_id,
                creds=creds,
                funder=self.config.polymarket.funder,
            )
            try:
                return {"yes": client.get_orderbook(token_ids[0]), "no": client.get_orderbook(token_ids[1])}
            except Exception as exc:
                logger.debug("Polymarket CLOB orderbook failed: %s", exc)

        return None

    def _fake_orderbook(self, market: Market, label: str = "yes") -> Dict[str, Any]:
        bid = market.best_bid.get(label) or 0.0
        ask = market.best_ask.get(label) or min(1.0, bid + 0.01)
        size = max(self.strict_cfg.trade_size_usd * self.strict_cfg.min_depth_multiple, 1000.0)
        return {
            "best_bid": bid,
            "best_ask": ask,
            "bids": [{"price": bid, "size": size}],
            "asks": [{"price": ask, "size": size}],
            "depth": size * 5,
        }

    def _compute_cases(self, k_market: Market, p_market: Market) -> List[ArbitrageCase]:
        cases: List[ArbitrageCase] = []
        k_yes_bid = k_market.best_bid.get("yes")
        k_no_bid = k_market.best_bid.get("no")
        k_yes_ask = k_market.best_ask.get("yes")
        k_no_ask = k_market.best_ask.get("no")
        p_yes_bid = p_market.best_bid.get("yes")
        p_no_bid = p_market.best_bid.get("no")
        p_yes_ask = p_market.best_ask.get("yes")
        p_no_ask = p_market.best_ask.get("no")

        fee_rate = (self.config.broker.fee_bps + self.config.broker.slippage_bps) / 10_000.0

        if k_yes_bid is not None and p_yes_ask is not None:
            edge_gross = k_yes_bid - p_yes_ask
            edge_net = k_yes_bid * (1 - fee_rate) - p_yes_ask * (1 + fee_rate)
            cases.append(
                ArbitrageCase(
                    case_name="YES overpriced on A",
                    kalshi_action="SHORT YES",
                    polymarket_action="BUY YES",
                    edge_gross=edge_gross,
                    edge_net=edge_net,
                    trade_price_a=k_yes_bid,
                    trade_price_b=p_yes_ask,
                    max_size_usd=self.strict_cfg.trade_size_usd,
                    reason="Kalshi YES bid above Polymarket YES ask",
                    prices_used={"kalshi_yes_bid": k_yes_bid, "polymarket_yes_ask": p_yes_ask},
                )
            )

        if k_no_bid is not None and p_no_ask is not None:
            edge_gross = k_no_bid - p_no_ask
            edge_net = k_no_bid * (1 - fee_rate) - p_no_ask * (1 + fee_rate)
            cases.append(
                ArbitrageCase(
                    case_name="NO overpriced on A",
                    kalshi_action="SHORT NO",
                    polymarket_action="BUY NO",
                    edge_gross=edge_gross,
                    edge_net=edge_net,
                    trade_price_a=k_no_bid,
                    trade_price_b=p_no_ask,
                    max_size_usd=self.strict_cfg.trade_size_usd,
                    reason="Kalshi NO bid above Polymarket NO ask",
                    prices_used={"kalshi_no_bid": k_no_bid, "polymarket_no_ask": p_no_ask},
                )
            )

        if k_yes_ask is not None and p_no_ask is not None:
            gross_cost = k_yes_ask + p_no_ask
            edge_gross = 1.0 - gross_cost
            net_cost = k_yes_ask * (1 + fee_rate) + p_no_ask * (1 + fee_rate)
            edge_net = 1.0 - net_cost
            cases.append(
                ArbitrageCase(
                    case_name="YES+NO cross-complement",
                    kalshi_action="BUY YES",
                    polymarket_action="BUY NO",
                    edge_gross=edge_gross,
                    edge_net=edge_net,
                    trade_price_a=k_yes_ask,
                    trade_price_b=p_no_ask,
                    max_size_usd=self.strict_cfg.trade_size_usd,
                    reason="YES on Kalshi plus NO on Polymarket",
                    prices_used={"kalshi_yes_ask": k_yes_ask, "polymarket_no_ask": p_no_ask},
                )
            )

        k_end = k_market.expiry or k_market.end_date
        p_end = p_market.expiry or p_market.end_date
        if k_end and p_end and k_end < p_end and k_yes_bid is not None and p_yes_ask is not None:
            edge_gross = k_yes_bid - p_yes_ask
            edge_net = k_yes_bid * (1 - fee_rate) - p_yes_ask * (1 + fee_rate)
            cases.append(
                ArbitrageCase(
                    case_name="Time-ladder",
                    kalshi_action="SHORT YES",
                    polymarket_action="BUY YES",
                    edge_gross=edge_gross,
                    edge_net=edge_net,
                    trade_price_a=k_yes_bid,
                    trade_price_b=p_yes_ask,
                    max_size_usd=self.strict_cfg.trade_size_usd,
                    reason="Earlier deadline priced above later deadline",
                    prices_used={"kalshi_yes_bid": k_yes_bid, "polymarket_yes_ask": p_yes_ask},
                )
            )

        return cases

    def _apply_filters(
        self,
        now_ts: float,
        k_market: Market,
        p_market: Market,
        orderbook_a: Optional[Dict[str, Any]],
        orderbook_b: Optional[Dict[str, Any]],
        case: ArbitrageCase,
    ) -> FilterReport:
        if case.polymarket_action.startswith("SHORT"):
            report = FilterReport(passed=False, fail_filter="F_POLY_SHORT", fail_reason="Polymarket cannot short")
            return report

        if orderbook_a is None or orderbook_b is None:
            return FilterReport(passed=False, fail_filter="F_ORDERBOOK", fail_reason="orderbook missing")

        k_quote = self._quote_from_orderbook("kalshi", k_market, case.kalshi_action, orderbook_a)
        p_quote = self._quote_from_orderbook("polymarket", p_market, case.polymarket_action, orderbook_b)

        expiry_ok, expiry_reason = self._check_expiry(k_market, p_market)
        if not expiry_ok:
            report = FilterReport(passed=False, fail_filter="F_EXPIRY", fail_reason=expiry_reason)
            return report

        cfg = FilterConfig(
            min_leg_usd=self.strict_cfg.trade_size_usd,
            min_depth_usd=self.strict_cfg.trade_size_usd * self.strict_cfg.min_depth_multiple,
            min_edge=self.strict_cfg.min_net_edge,
            min_price=0.000001,
            max_price=0.999999,
            fee_bps_a=self.config.broker.fee_bps,
            fee_bps_b=self.config.broker.fee_bps,
            slippage_bps=self.config.broker.slippage_bps,
        )

        report = evaluate_ab_filters(
            now_ts=now_ts,
            kalshi_leg=k_quote,
            polymarket_leg=p_quote,
            trade_price_a=case.trade_price_a,
            trade_price_b=case.trade_price_b,
            edge_gross=case.edge_gross,
            config=cfg,
            schema_hint_a=orderbook_a,
            schema_hint_b=orderbook_b,
        )
        if report.passed and report.edge_net is not None and report.edge_net < self.strict_cfg.min_net_edge:
            report.passed = False
            report.fail_filter = "F_MIN_EDGE"
            report.fail_reason = "net edge below threshold"
        return report

    def _quote_from_orderbook(self, venue: str, market: Market, action: str, raw: Optional[Dict[str, Any]]) -> Quote:
        outcome = "YES" if "YES" in action else "NO"
        label = outcome.lower()
        bid = market.best_bid.get(label)
        ask = market.best_ask.get(label)
        bid_size = None
        ask_size = None
        depth = None
        ts = time.time()

        if raw and isinstance(raw, dict):
            if venue == "polymarket" and label in raw and isinstance(raw[label], dict):
                raw_view = raw[label]
            else:
                raw_view = raw
            bid = raw_view.get("best_bid") or raw_view.get("bestBid") or bid
            ask = raw_view.get("best_ask") or raw_view.get("bestAsk") or ask
            bids = raw_view.get("bids") or []
            asks = raw_view.get("asks") or []
            if bids:
                bid = bid or bids[0].get("price")
                bid_size = bids[0].get("size")
            if asks:
                ask = ask or asks[0].get("price")
                ask_size = asks[0].get("size")
            depth = raw_view.get("depth") or raw_view.get("liquidity")

        return Quote(
            venue=venue,
            market_id=market.id,
            outcome=outcome,
            bid=self._safe_float(bid),
            ask=self._safe_float(ask),
            bid_size_usd=self._safe_float(bid_size),
            ask_size_usd=self._safe_float(ask_size),
            depth_usd=self._safe_float(depth),
            ts=ts,
        )

    def _check_expiry(self, k_market: Market, p_market: Market) -> Tuple[bool, str]:
        k_exp = k_market.expiry or k_market.end_date
        p_exp = p_market.expiry or p_market.end_date
        if not k_exp or not p_exp:
            return False, "missing expiry"
        now = datetime.now(timezone.utc)
        if k_exp.tzinfo is None:
            k_exp = k_exp.replace(tzinfo=timezone.utc)
        if p_exp.tzinfo is None:
            p_exp = p_exp.replace(tzinfo=timezone.utc)
        if (k_exp - now).total_seconds() < self.strict_cfg.min_expiry_hours * 3600:
            return False, "kalshi expiry too soon"
        if (p_exp - now).total_seconds() < self.strict_cfg.min_expiry_hours * 3600:
            return False, "polymarket expiry too soon"
        return True, "ok"

    @staticmethod
    def _safe_float(value: Any) -> Optional[float]:
        try:
            if value is None:
                return None
            return float(value)
        except Exception:
            return None

    @staticmethod
    def _kalshi_ticker(market: Market) -> str:
        return str(getattr(market, "ticker", "") or market.id)

    def _notify_pass(self, entry: WatchlistEntry, case: ArbitrageCase, report: FilterReport) -> None:
        if not self.notifier or not hasattr(self.notifier, "notify_strict_ab_pass"):
            return
        try:
            self.notifier.notify_strict_ab_pass(entry, case, report)
        except Exception as exc:
            logger.warning("Strict A+B notifier failed: %s", exc)
