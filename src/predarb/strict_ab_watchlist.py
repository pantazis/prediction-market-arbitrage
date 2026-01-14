from __future__ import annotations

import csv
import json
import logging
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from predarb.models import Market

logger = logging.getLogger(__name__)


@dataclass
class WatchlistEntry:
    pair_key: str
    kalshi_ticker: str
    kalshi_market_id: str
    kalshi_title: str
    kalshi_expiry: Optional[str]
    polymarket_id: str
    polymarket_market_id: str
    polymarket_title: str
    polymarket_expiry: Optional[str]
    tags: List[str]
    llm_confidence: float
    llm_reason: str
    last_verified: str


class WatchlistManager:
    def __init__(self, json_path: str, csv_path: str) -> None:
        self.json_path = Path(json_path)
        self.csv_path = Path(csv_path)

    def load(self) -> Dict[str, WatchlistEntry]:
        if not self.json_path.exists():
            return {}
        try:
            data = json.loads(self.json_path.read_text())
            entries = {}
            for item in data:
                entry = WatchlistEntry(**item)
                entries[entry.pair_key] = entry
            return entries
        except Exception as exc:
            logger.warning("Failed to load watchlist: %s", exc)
            return {}

    def save(self, entries: Iterable[WatchlistEntry]) -> None:
        self.json_path.parent.mkdir(parents=True, exist_ok=True)
        items = [asdict(entry) for entry in entries]
        tmp_json = self.json_path.with_suffix(".tmp")
        tmp_json.write_text(json.dumps(items, indent=2))
        tmp_json.replace(self.json_path)

        self.csv_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_csv = self.csv_path.with_suffix(".tmp")
        with tmp_csv.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(items[0].keys()) if items else [])
            if items:
                writer.writeheader()
                writer.writerows(items)
        tmp_csv.replace(self.csv_path)

    @staticmethod
    def _is_expired(market: Market) -> bool:
        expiry = market.expiry or market.end_date
        if not expiry:
            return True
        now = datetime.now(timezone.utc)
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        return expiry <= now

    @staticmethod
    def _is_closed(market: Market) -> bool:
        status = str(getattr(market, "status", "")).lower()
        if status in ("closed", "resolved", "settled"):
            return True
        if getattr(market, "closed", False) is True:
            return True
        return False

    def prune(self, entries: Dict[str, WatchlistEntry], market_lookup: Dict[str, Market]) -> Dict[str, WatchlistEntry]:
        pruned: Dict[str, WatchlistEntry] = {}
        for key, entry in entries.items():
            k_market = market_lookup.get(entry.kalshi_market_id)
            p_market = market_lookup.get(entry.polymarket_market_id)
            if not k_market or not p_market:
                continue
            if self._is_closed(k_market) or self._is_closed(p_market):
                continue
            if self._is_expired(k_market) or self._is_expired(p_market):
                continue
            pruned[key] = entry
        return pruned
