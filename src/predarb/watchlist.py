from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from predarb.ab_filters import (
    FilterConfig,
    evaluate_ab_filters,
    extract_best_bid_ask_from_orderbook,
    quote_from_market,
)
from predarb.models import Market

WATCHLIST_COLUMNS = [
    "pair_id",
    "k_ticker",
    "p_market_id",
    "p_yes_token_id",
    "p_no_token_id",
    "polarity",
    "k_expiration_time",
    "p_endDate",
    "min_edge",
    "min_depth_usd",
    "max_age_sec",
    "status",
    "last_verified_at",
]


@dataclass
class WatchlistRow:
    pair_id: str
    k_ticker: str
    p_market_id: str
    p_yes_token_id: str
    p_no_token_id: str
    polarity: str
    k_expiration_time: str
    p_endDate: str
    min_edge: float
    min_depth_usd: float
    max_age_sec: int
    status: str
    last_verified_at: str


@dataclass
class ScanOutput:
    approve_packets: List[Dict[str, object]]
    scan_log: Dict[str, object]
    rejects: List[Dict[str, object]]
    filter_reports: List[Dict[str, object]]
    arbitrage_cases: List[Dict[str, object]]
    quote_snapshots: List[Dict[str, object]]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _isoformat(dt: Optional[datetime]) -> str:
    if not dt:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def _parse_dt(value: str) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


def _parse_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _parse_int(value: object, default: int = 0) -> int:
    try:
        return int(float(value))
    except Exception:
        return default


def _pair_id(k_ticker: str, p_market_id: str, polarity: str) -> str:
    raw = f"{k_ticker}|{p_market_id}|{polarity}".lower().strip()
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def load_watchlist_csv(path: str | Path) -> List[WatchlistRow]:
    path = Path(path)
    if not path.exists():
        return []
    rows: List[WatchlistRow] = []
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for raw in reader:
            rows.append(
                WatchlistRow(
                    pair_id=str(raw.get("pair_id", "")).strip(),
                    k_ticker=str(raw.get("k_ticker", "")).strip(),
                    p_market_id=str(raw.get("p_market_id", "")).strip(),
                    p_yes_token_id=str(raw.get("p_yes_token_id", "")).strip(),
                    p_no_token_id=str(raw.get("p_no_token_id", "")).strip(),
                    polarity=str(raw.get("polarity", "normal")).strip() or "normal",
                    k_expiration_time=str(raw.get("k_expiration_time", "")).strip(),
                    p_endDate=str(raw.get("p_endDate", "")).strip(),
                    min_edge=_parse_float(raw.get("min_edge"), 0.0),
                    min_depth_usd=_parse_float(raw.get("min_depth_usd"), 0.0),
                    max_age_sec=_parse_int(raw.get("max_age_sec"), 0),
                    status=str(raw.get("status", "active")).strip() or "active",
                    last_verified_at=str(raw.get("last_verified_at", "")).strip(),
                )
            )
    return rows


def write_watchlist_csv(path: str | Path, rows: Sequence[WatchlistRow]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=WATCHLIST_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))


def _extract_pair_fields(item: Dict[str, object]) -> Dict[str, str]:
    kalshi = item.get("kalshi") or item.get("kalshi_market") or {}
    poly = item.get("polymarket") or item.get("polymarket_market") or {}

    k_ticker = (
        item.get("k_ticker")
        or item.get("kalshi_ticker")
        or kalshi.get("ticker")
        or kalshi.get("market_id")
        or kalshi.get("id")
        or ""
    )
    p_market_id = (
        item.get("p_market_id")
        or item.get("polymarket_id")
        or poly.get("id")
        or poly.get("market_id")
        or ""
    )
    tokens = (
        item.get("p_tokens")
        or item.get("polymarket_tokens")
        or poly.get("tokens")
        or poly.get("clobTokenIds")
        or []
    )
    p_yes_token_id = ""
    p_no_token_id = ""
    if isinstance(tokens, dict):
        p_yes_token_id = str(tokens.get("YES") or tokens.get("yes") or "")
        p_no_token_id = str(tokens.get("NO") or tokens.get("no") or "")
    elif isinstance(tokens, list) and len(tokens) >= 2:
        p_yes_token_id = str(tokens[0])
        p_no_token_id = str(tokens[1])

    k_exp = (
        item.get("k_expiration_time")
        or item.get("kalshi_expiration_time")
        or kalshi.get("expiration_time")
        or kalshi.get("expiry")
        or ""
    )
    p_end = (
        item.get("p_endDate")
        or item.get("polymarket_endDate")
        or poly.get("endDate")
        or poly.get("expiry")
        or ""
    )
    polarity = str(item.get("polarity") or "normal").strip() or "normal"
    return {
        "k_ticker": str(k_ticker),
        "p_market_id": str(p_market_id),
        "p_yes_token_id": str(p_yes_token_id),
        "p_no_token_id": str(p_no_token_id),
        "k_expiration_time": str(k_exp),
        "p_endDate": str(p_end),
        "polarity": polarity,
    }


def add_to_watchlist(
    matched_pairs_path: str | Path,
    watchlist_csv_path: str | Path,
    *,
    min_edge: float = 0.006,
    min_depth_usd: float = 50.0,
    max_age_sec: int = 15,
) -> List[WatchlistRow]:
    matched_pairs_path = Path(matched_pairs_path)
    with matched_pairs_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list):
        raise ValueError("matched_pairs_pass.json must be a list of pair objects")

    now = _utc_now()
    existing = {row.pair_id: row for row in load_watchlist_csv(watchlist_csv_path)}
    new_rows: List[WatchlistRow] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        fields = _extract_pair_fields(item)
        if not fields["k_ticker"] or not fields["p_market_id"]:
            continue
        pid = _pair_id(fields["k_ticker"], fields["p_market_id"], fields["polarity"])
        row = WatchlistRow(
            pair_id=pid,
            k_ticker=fields["k_ticker"],
            p_market_id=fields["p_market_id"],
            p_yes_token_id=fields["p_yes_token_id"],
            p_no_token_id=fields["p_no_token_id"],
            polarity=fields["polarity"],
            k_expiration_time=fields["k_expiration_time"],
            p_endDate=fields["p_endDate"],
            min_edge=min_edge,
            min_depth_usd=min_depth_usd,
            max_age_sec=max_age_sec,
            status="active",
            last_verified_at=_isoformat(now),
        )
        existing[pid] = row
        new_rows.append(row)

    write_watchlist_csv(watchlist_csv_path, list(existing.values()))
    return new_rows


def prune_watchlist(
    rows: Sequence[WatchlistRow],
    *,
    now: Optional[datetime] = None,
    inactive_pair_ids: Optional[Sequence[str]] = None,
) -> List[WatchlistRow]:
    now = now or _utc_now()
    inactive = set(inactive_pair_ids or [])
    kept: List[WatchlistRow] = []
    for row in rows:
        if row.status.lower() != "active":
            continue
        if row.pair_id in inactive:
            continue
        k_exp = _parse_dt(row.k_expiration_time)
        p_exp = _parse_dt(row.p_endDate)
        if k_exp and now > k_exp:
            continue
        if p_exp and now > p_exp:
            continue
        kept.append(row)
    return kept


def _kalshi_ticker_from_market_id(market_id: str) -> str:
    if not market_id:
        return ""
    parts = market_id.split(":")
    return parts[-1] if parts else market_id


def _map_outcome(label: str, polarity: str) -> str:
    label = label.lower().strip()
    if polarity.lower() == "inverted":
        return "no" if label == "yes" else "yes"
    return label


def build_watchlist_row(
    kalshi_market: Market,
    polymarket_market: Market,
    *,
    min_edge: float,
    min_depth_usd: float,
    max_age_sec: int,
    polarity: str = "normal",
    verified_at: Optional[datetime] = None,
) -> WatchlistRow:
    k_ticker = _kalshi_ticker_from_market_id(kalshi_market.id)
    yes_outcome = polymarket_market.outcome_by_label("yes")
    no_outcome = polymarket_market.outcome_by_label("no")
    verified_at = verified_at or _utc_now()
    return WatchlistRow(
        pair_id=_pair_id(k_ticker, polymarket_market.id, polarity),
        k_ticker=k_ticker,
        p_market_id=polymarket_market.id,
        p_yes_token_id=str(yes_outcome.id) if yes_outcome else "",
        p_no_token_id=str(no_outcome.id) if no_outcome else "",
        polarity=polarity,
        k_expiration_time=_isoformat(kalshi_market.expiry),
        p_endDate=_isoformat(polymarket_market.expiry),
        min_edge=min_edge,
        min_depth_usd=min_depth_usd,
        max_age_sec=max_age_sec,
        status="active",
        last_verified_at=_isoformat(verified_at),
    )


def upsert_watchlist_rows(
    watchlist_csv_path: str | Path,
    rows: Sequence[WatchlistRow],
) -> None:
    existing = {row.pair_id: row for row in load_watchlist_csv(watchlist_csv_path)}
    for row in rows:
        existing[row.pair_id] = row
    write_watchlist_csv(watchlist_csv_path, list(existing.values()))


def scan_watchlist(
    rows: Sequence[WatchlistRow],
    *,
    kalshi_markets: Sequence[Market],
    polymarket_markets: Sequence[Market],
    fee_bps_kalshi: float = 7.0,
    fee_bps_polymarket: float = 10.0,
    slippage_bps: float = 10.0,
    depth_fraction: float = 0.10,
    orderbook_fetcher: Optional[
        callable
    ] = None,  # (venue, market, outcome_label) -> raw orderbook dict
) -> ScanOutput:
    kalshi_by_ticker = {
        _kalshi_ticker_from_market_id(m.id): m for m in kalshi_markets
    }
    kalshi_by_id = {m.id: m for m in kalshi_markets}
    poly_by_id = {m.id: m for m in polymarket_markets}

    approve_packets: List[Dict[str, object]] = []
    rejects: List[Dict[str, object]] = []
    filter_reports: List[Dict[str, object]] = []
    arbitrage_cases: List[Dict[str, object]] = []
    quote_snapshots: List[Dict[str, object]] = []
    checked = 0

    for row in rows:
        checked += 1
        if row.k_ticker in kalshi_by_id:
            k_market = kalshi_by_id.get(row.k_ticker)
        else:
            k_market = kalshi_by_ticker.get(row.k_ticker)
        p_market = poly_by_id.get(row.p_market_id)
        if not k_market or not p_market:
            rejects.append(
                {
                    "pair_id": row.pair_id,
                    "reason": "missing_market",
                    "detail": {
                        "kalshi_found": bool(k_market),
                        "polymarket_found": bool(p_market),
                    },
                }
            )
            continue

        for outcome in ("yes", "no"):
            k_outcome = outcome
            p_outcome = _map_outcome(outcome, row.polarity)

            k_quote = quote_from_market(k_market, k_outcome, depth_fraction)
            p_quote = quote_from_market(p_market, p_outcome, depth_fraction)
            if orderbook_fetcher is not None:
                k_raw = orderbook_fetcher("kalshi", k_market, k_outcome)
                if k_raw:
                    bid, ask, bid_size, ask_size, _, _ = extract_best_bid_ask_from_orderbook(k_raw)
                    if bid is not None and bid > 1.0:
                        bid = bid / 100.0
                    if ask is not None and ask > 1.0:
                        ask = ask / 100.0
                    if bid is not None:
                        k_quote.bid = bid
                    if ask is not None:
                        k_quote.ask = ask
                    if bid_size:
                        k_quote.bid_size_usd = bid_size
                    if ask_size:
                        k_quote.ask_size_usd = ask_size

                p_raw = orderbook_fetcher("polymarket", p_market, p_outcome)
                if p_raw:
                    bid, ask, bid_size, ask_size, _, _ = extract_best_bid_ask_from_orderbook(p_raw)
                    if bid is not None and bid > 1.0:
                        bid = bid / 100.0
                    if ask is not None and ask > 1.0:
                        ask = ask / 100.0
                    if bid is not None:
                        p_quote.bid = bid
                    if ask is not None:
                        p_quote.ask = ask
                    if bid_size:
                        p_quote.bid_size_usd = bid_size
                    if ask_size:
                        p_quote.ask_size_usd = ask_size

            quote_snapshots.append(
                {
                    "pair_id": row.pair_id,
                    "outcome": outcome,
                    "polarity": row.polarity,
                    "kalshi_market_id": k_market.id,
                    "polymarket_market_id": p_market.id,
                    "kalshi_bid": k_quote.bid,
                    "kalshi_ask": k_quote.ask,
                    "polymarket_bid": p_quote.bid,
                    "polymarket_ask": p_quote.ask,
                }
            )

            if k_quote.bid is None or p_quote.ask is None:
                rejects.append(
                    {
                        "pair_id": row.pair_id,
                        "reason": "missing_prices",
                        "detail": {
                            "kalshi_bid": k_quote.bid,
                            "polymarket_ask": p_quote.ask,
                            "outcome": outcome,
                        },
                    }
                )
                continue

            edge_gross = float(k_quote.bid) - float(p_quote.ask)
            cfg = FilterConfig(
                min_depth_usd=row.min_depth_usd,
                max_staleness_sec=row.max_age_sec,
                min_edge=row.min_edge,
                fee_bps_a=fee_bps_kalshi,
                fee_bps_b=fee_bps_polymarket,
                slippage_bps=slippage_bps,
            )
            report = evaluate_ab_filters(
                now_ts=_utc_now().timestamp(),
                kalshi_leg=k_quote,
                polymarket_leg=p_quote,
                trade_price_a=k_quote.bid,
                trade_price_b=p_quote.ask,
                edge_gross=edge_gross,
                config=cfg,
            )

            if not report.passed:
                rejects.append(
                    {
                        "pair_id": row.pair_id,
                        "reason": report.fail_filter or "filter_failed",
                        "detail": report.fail_reason,
                        "outcome": outcome,
                    }
                )
                continue

            case = {
                "case_name": "YES overpriced on Kalshi" if outcome == "yes" else "NO overpriced on Kalshi",
                "kalshi_action": f"SHORT {outcome.upper()}",
                "polymarket_action": f"BUY {outcome.upper()}",
                "edge_gross": edge_gross,
                "edge_net": report.edge_net,
                "max_size": report.executable_size_usd,
                "guaranteed": True,
                "reason": "watchlist edge passed filters",
            }
            filter_reports.append(
                {
                    "case": case,
                    "filter_report": {
                        "passed": report.passed,
                        "fail_filter": report.fail_filter,
                        "fail_reason": report.fail_reason,
                        "edge_gross": report.edge_gross,
                        "edge_net": report.edge_net,
                        "executable_size_usd": report.executable_size_usd,
                    },
                }
            )
            arbitrage_cases.append(case)

            approve_packets.append(
                {
                    "pair_id": row.pair_id,
                    "polarity": row.polarity,
                    "side": outcome.upper(),
                    "kalshi": {
                        "market_id": k_market.id,
                        "ticker": row.k_ticker,
                        "bid": k_quote.bid,
                        "ask": k_quote.ask,
                        "bid_size_usd": k_quote.bid_size_usd,
                        "ask_size_usd": k_quote.ask_size_usd,
                    },
                    "polymarket": {
                        "market_id": p_market.id,
                        "token_id": row.p_yes_token_id
                        if p_outcome == "yes"
                        else row.p_no_token_id,
                        "bid": p_quote.bid,
                        "ask": p_quote.ask,
                        "bid_size_usd": p_quote.bid_size_usd,
                        "ask_size_usd": p_quote.ask_size_usd,
                    },
                    "edge_gross": edge_gross,
                    "edge_net": report.edge_net,
                    "min_edge": row.min_edge,
                    "min_depth_usd": row.min_depth_usd,
                    "max_age_sec": row.max_age_sec,
                    "k_expiration_time": row.k_expiration_time,
                    "p_endDate": row.p_endDate,
                    "last_verified_at": row.last_verified_at,
                }
            )

    scan_log = {
        "ts": _isoformat(_utc_now()),
        "pairs_checked": checked,
        "candidates": len(approve_packets),
        "rejects": len(rejects),
    }
    return ScanOutput(
        approve_packets=approve_packets,
        scan_log=scan_log,
        rejects=rejects,
        filter_reports=filter_reports,
        arbitrage_cases=arbitrage_cases,
        quote_snapshots=quote_snapshots,
    )


def append_jsonl(path: str | Path, records: Iterable[Dict[str, object]]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=True) + "\n")
