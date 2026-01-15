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
        self.clob_host = config.clob_host.rstrip("/")
        self.clob_api_key = config.clob_api_key or config.api_key

    def fetch_markets(self) -> List[Market]:
        url = f"{self.host}/markets"
        # CRITICAL: Use active=true and closed=false to get only live tradable markets
        # Sort by volume24hr to prioritize liquid markets for arbitrage
        # NOTE: Unlike Kalshi, Polymarket doesn't need category filtering because:
        # 1. It doesn't have sports markets (Kalshi's main filter reason)
        # 2. Smart semantic matching will handle relevance
        # 3. Polymarket tags don't align 1:1 with Kalshi categories
        
        # Use configured limit if available, otherwise default to 10000
        limit = getattr(self.config, 'limit', 10000)
        
        params = {
            "active": "true",
            "closed": "false",
            "limit": limit,
            "order": "volume24hr",
            "ascending": "false"
        }
        try:
            resp = requests.get(url, params=params, timeout=10)
            resp.raise_for_status()
            payload = resp.json()
        except Exception as e:
            logger.error("Failed to fetch markets: %s", e)
            return []
        # Gamma API returns dict with 'data' key
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

            best_bid: Dict[str, float] = {}
            best_ask: Dict[str, float] = {}
            half_spread = 0.001
            for outcome in outcomes:
                label = str(outcome.label).strip().lower()
                if label in ("yes", "no"):
                    mid = float(outcome.price)
                    best_bid[label] = max(0.0, mid - half_spread)
                    best_ask[label] = min(1.0, mid + half_spread)
            
            # Parse end date - Gamma API uses endDate or endDateIso
            expiry = None
            end_date_field = data.get("endDate") or data.get("endDateIso")
            if end_date_field:
                try:
                    expiry = datetime.fromisoformat(end_date_field.replace("Z", "+00:00"))
                except Exception:
                    expiry = None

            updated_at = None
            for key in ("updatedAt", "updated_at", "lastUpdated", "last_updated", "lastTraded", "last_traded"):
                value = data.get(key)
                if value:
                    try:
                        updated_at = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
                        break
                    except Exception:
                        updated_at = None
            if updated_at is None:
                updated_at = datetime.utcnow()
            
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
                updated_at=updated_at,
                best_bid=best_bid,
                best_ask=best_ask,
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

    def fetch_orderbook(self, token_id: str, timeout_s: float = 2.5) -> Optional[Dict[str, Any]]:
        if not token_id:
            return None
        url = f"{self.clob_host}/book"
        headers: Dict[str, str] = {"Accept": "application/json"}
        if self.clob_api_key:
            headers["Authorization"] = f"Bearer {self.clob_api_key}"
            # Some deployments use an API-key header instead of Bearer auth.
            headers["X-API-KEY"] = self.clob_api_key
            headers["x-api-key"] = self.clob_api_key
        try:
            resp = requests.get(url, params={"token_id": token_id}, headers=headers, timeout=timeout_s)
            resp.raise_for_status()
            raw = resp.json()
        except Exception as e:
            logger.warning("Polymarket orderbook fetch failed for %s: %s", token_id, e)
            return None

        if isinstance(raw, dict) and ("bids" in raw or "asks" in raw):
            return raw
        if isinstance(raw, dict) and "orderbook" in raw and isinstance(raw["orderbook"], dict):
            return raw["orderbook"]
        return raw if isinstance(raw, dict) else None
