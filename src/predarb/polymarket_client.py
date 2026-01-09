from __future__ import annotations

import logging
from datetime import datetime
from typing import List, Optional, Dict, Any

import requests

from predarb.config import PolymarketConfig
from predarb.extractors import extract_entity, extract_expiry, extract_threshold
from predarb.models import Market, Outcome
from predarb.market_client_base import MarketClient

logger = logging.getLogger(__name__)


class PolymarketClient(MarketClient):
    def __init__(self, config: PolymarketConfig):
        self.config = config
        self.host = config.host.rstrip("/")

    def fetch_markets(self) -> List[Market]:
        url = f"{self.host}/markets"
        params = {"closed": "false", "limit": 1000, "order": "updated_at:desc"}
        try:
            resp = requests.get(url, params=params, timeout=10)
            resp.raise_for_status()
            payload = resp.json()
        except Exception as e:
            logger.error("Failed to fetch markets: %s", e)
            return []
        # Gamma API returns direct array, not wrapped in {data: [...]}
        raw_markets = payload if isinstance(payload, list) else payload.get("data", [])
        markets: List[Market] = []
        for m in raw_markets:
            parsed = self._parse_market(m)
            if parsed:
                markets.append(parsed)
        return markets

    def _parse_market(self, data: dict) -> Optional[Market]:
        try:
            import json
            
            # Gamma API uses JSON strings for outcomes and prices
            outcomes_str = data.get("outcomes", "[]")
            prices_str = data.get("outcomePrices", "[]")
            token_ids_str = data.get("clobTokenIds", "[]")
            
            try:
                outcome_labels = json.loads(outcomes_str) if isinstance(outcomes_str, str) else outcomes_str
                outcome_prices = json.loads(prices_str) if isinstance(prices_str, str) else prices_str
                token_ids = json.loads(token_ids_str) if isinstance(token_ids_str, str) else token_ids_str
            except json.JSONDecodeError:
                logger.warning("Failed to parse outcomes/prices JSON for market %s", data.get("id"))
                return None
            
            outcomes: List[Outcome] = []
            for i, label in enumerate(outcome_labels):
                outcomes.append(
                    Outcome(
                        id=str(token_ids[i]) if i < len(token_ids) else str(i),
                        label=str(label),
                        price=float(outcome_prices[i]) if i < len(outcome_prices) else 0.0,
                        liquidity=float(data.get("liquidityNum", 0.0) or 0.0) / len(outcome_labels) if outcome_labels else 0.0,
                    )
                )
            
            if not outcomes:
                return None
            
            # Parse end date - Gamma API uses endDate or endDateIso
            expiry = None
            end_date_field = data.get("endDate") or data.get("endDateIso")
            if end_date_field:
                try:
                    expiry = datetime.fromisoformat(end_date_field.replace("Z", "+00:00"))
                except Exception:
                    expiry = None
            
            question = data.get("question") or data.get("title") or "Unknown"
            comparator, threshold = extract_threshold(question)
            asset = extract_entity(question)
            
            market = Market(
                id=str(data.get("conditionId") or data.get("id")),
                question=question,
                outcomes=outcomes,
                end_date=expiry,
                expiry=expiry,
                liquidity=float(data.get("liquidityNum", 0.0) or data.get("liquidity", 0.0) or 0.0),
                volume=float(data.get("volumeNum", 0.0) or data.get("volume", 0.0) or 0.0),
                tags=data.get("tags") or [],
                description=data.get("description"),
                comparator=comparator,
                threshold=threshold,
                asset=asset,
                resolution_source=data.get("resolutionSource"),
            )
            # Tag exchange
            market.exchange = "polymarket"  # type: ignore
            return market
        except Exception as e:
            logger.warning("Failed to parse market: %s", e)
            return None
    
    def get_metadata(self) -> Dict[str, Any]:
        """
        Return Polymarket-specific metadata.
        
        Returns:
            Dict with exchange info
        """
        return {
            "exchange": "polymarket",
            "fee_bps": 10,  # Polymarket charges ~0.10% per side
            "tick_size": 0.01,  # $0.01 minimum price increment
            "base_url": self.host,
            "supports_orderbook": False,  # Gamma API doesn't provide full orderbook
        }

