from __future__ import annotations

import logging
from datetime import datetime
from typing import List, Optional

import requests

from predarb.config import PolymarketConfig
from predarb.extractors import extract_entity, extract_expiry, extract_threshold
from predarb.models import Market, Outcome

logger = logging.getLogger(__name__)


class PolymarketClient:
    def __init__(self, config: PolymarketConfig):
        self.config = config
        self.host = config.host.rstrip("/")

    def fetch_markets(self) -> List[Market]:
        url = f"{self.host}/markets"
        params = {"active": "true", "closed": "false", "archived": "false", "limit": 1000}
        try:
            resp = requests.get(url, params=params, timeout=10)
            resp.raise_for_status()
            payload = resp.json()
        except Exception as e:
            logger.error("Failed to fetch markets: %s", e)
            return []
        raw_markets = payload.get("data", []) if isinstance(payload, dict) else payload
        markets: List[Market] = []
        for m in raw_markets:
            parsed = self._parse_market(m)
            if parsed:
                markets.append(parsed)
        return markets

    def _parse_market(self, data: dict) -> Optional[Market]:
        try:
            tokens = data.get("tokens", [])
            outcomes: List[Outcome] = []
            for t in tokens:
                if "price" not in t or "outcome" not in t:
                    continue
                outcomes.append(
                    Outcome(
                        id=str(t.get("token_id") or t.get("id")),
                        label=str(t.get("outcome")),
                        price=float(t.get("price", 0.0)),
                        liquidity=float(t.get("liquidity", 0.0) or 0.0),
                    )
                )
            if not outcomes:
                return None
            expiry = None
            if data.get("end_date_iso"):
                try:
                    expiry = datetime.fromisoformat(data["end_date_iso"].replace("Z", "+00:00"))
                except Exception:
                    expiry = None
            question = data.get("question") or data.get("title") or "Unknown"
            comparator, threshold = extract_threshold(question)
            asset = extract_entity(question)
            market = Market(
                id=str(data.get("condition_id") or data.get("id")),
                question=question,
                outcomes=outcomes,
                end_date=expiry,
                expiry=expiry,
                liquidity=float(data.get("liquidity", 0.0) or 0.0),
                volume=float(data.get("volume", 0.0) or 0.0),
                tags=data.get("tags") or [],
                description=data.get("description"),
                comparator=comparator,
                threshold=threshold,
                asset=asset,
                resolution_source=data.get("resolution_source"),
            )
            return market
        except Exception as e:
            logger.warning("Failed to parse market: %s", e)
            return None
