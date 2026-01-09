"""
Kalshi market client with RSA authentication and market normalization.

SECURITY:
- All credentials loaded from environment variables only
- NO hardcoded API keys or private keys
- Private key can be passed as PEM string or file path

Environment Variables:
- KALSHI_API_KEY_ID: API key ID (UUID format)
- KALSHI_PRIVATE_KEY_PEM: RSA private key (PEM format, multiline)
- KALSHI_API_HOST: API host (default: https://trading-api.kalshi.com)
- KALSHI_ENV: "prod" or "demo" (default: prod)
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional

import requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.backends import default_backend

from predarb.market_client_base import MarketClient
from predarb.models import Market, Outcome

logger = logging.getLogger(__name__)


class KalshiClient(MarketClient):
    """
    Kalshi prediction market client.
    
    Authentication: RSA request signing (HMAC-SHA256 with private key)
    Market Normalization:
    - Market IDs: "kalshi:<event_ticker>:<market_ticker>"
    - Outcomes: Always YES/NO with prices [0.0-1.0]
    - Liquidity: Estimated from orderbook depth
    """
    
    def __init__(
        self,
        api_key_id: Optional[str] = None,
        private_key_pem: Optional[str] = None,
        api_host: Optional[str] = None,
        env: str = "prod",
        min_liquidity_usd: float = 500.0,
        min_days_to_expiry: int = 1,
    ):
        """
        Initialize Kalshi client.
        
        Args:
            api_key_id: API key ID (defaults to KALSHI_API_KEY_ID env var)
            private_key_pem: RSA private key in PEM format or path to file
                            (defaults to KALSHI_PRIVATE_KEY_PEM env var)
            api_host: API host URL (defaults to KALSHI_API_HOST or production)
            env: "prod" or "demo" (defaults to KALSHI_ENV or "prod")
            min_liquidity_usd: Minimum market liquidity filter
            min_days_to_expiry: Minimum days until expiry filter
        
        Raises:
            ValueError: If credentials not provided and not in environment
        """
        # Load credentials from environment if not provided
        self.api_key_id = api_key_id or os.getenv("KALSHI_API_KEY_ID")
        private_key_input = private_key_pem or os.getenv("KALSHI_PRIVATE_KEY_PEM")
        self.api_host = (api_host or os.getenv("KALSHI_API_HOST") or 
                        "https://trading-api.kalshi.com").rstrip("/")
        self.env = env or os.getenv("KALSHI_ENV", "prod")
        
        if not self.api_key_id:
            raise ValueError(
                "KALSHI_API_KEY_ID not provided. Set environment variable or pass to constructor."
            )
        
        if not private_key_input:
            raise ValueError(
                "KALSHI_PRIVATE_KEY_PEM not provided. Set environment variable or pass to constructor."
            )
        
        # Load private key (handle both PEM string and file path)
        self.private_key = self._load_private_key(private_key_input)
        
        # Filters
        self.min_liquidity_usd = min_liquidity_usd
        self.min_days_to_expiry = min_days_to_expiry
        
        # Session for connection pooling
        self.session = requests.Session()
        
        logger.info(
            f"KalshiClient initialized: env={self.env}, host={self.api_host}, "
            f"min_liquidity={min_liquidity_usd}, min_expiry_days={min_days_to_expiry}"
        )
    
    def _load_private_key(self, pem_input: str):
        """
        Load RSA private key from PEM string or file path.
        
        Args:
            pem_input: PEM-formatted key string or path to .pem file
        
        Returns:
            Cryptography private key object
        """
        # Check if it's a file path
        if not pem_input.startswith("-----BEGIN"):
            pem_path = Path(pem_input)
            if pem_path.exists():
                pem_input = pem_path.read_text()
            else:
                raise ValueError(f"Private key file not found: {pem_input}")
        
        # Parse PEM
        try:
            private_key = serialization.load_pem_private_key(
                pem_input.encode("utf-8"),
                password=None,
                backend=default_backend()
            )
            return private_key
        except Exception as e:
            raise ValueError(f"Failed to parse RSA private key: {e}")
    
    def _sign_request(self, method: str, path: str, body: str = "") -> str:
        """
        Generate RSA signature for Kalshi API request.
        
        Kalshi Signature Format:
        - Timestamp (milliseconds since epoch)
        - HTTP method (uppercase)
        - Path (with query params)
        - Body (empty string for GET)
        - Sign with RSA-SHA256
        
        Args:
            method: HTTP method (GET, POST, etc.)
            path: Request path (e.g., "/trade-api/v2/markets")
            body: Request body (empty for GET requests)
        
        Returns:
            Base64-encoded signature
        """
        timestamp_ms = str(int(time.time() * 1000))
        
        # Build signing message
        message_parts = [
            timestamp_ms,
            method.upper(),
            path,
            body
        ]
        message = "\n".join(message_parts)
        
        # Sign with private key
        signature = self.private_key.sign(
            message.encode("utf-8"),
            padding.PKCS1v15(),
            hashes.SHA256()
        )
        
        # Base64 encode
        signature_b64 = base64.b64encode(signature).decode("utf-8")
        
        return signature_b64
    
    def _make_request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        json_body: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Make authenticated request to Kalshi API.
        
        Args:
            method: HTTP method
            endpoint: API endpoint (e.g., "/trade-api/v2/markets")
            params: Query parameters
            json_body: JSON request body
        
        Returns:
            Response JSON or None on error
        """
        url = f"{self.api_host}{endpoint}"
        
        # Build query string for signature
        query_string = ""
        if params:
            query_string = "?" + "&".join(f"{k}={v}" for k, v in sorted(params.items()))
        
        path_with_query = endpoint + query_string
        body_str = json.dumps(json_body) if json_body else ""
        
        # Generate signature
        signature = self._sign_request(method, path_with_query, body_str)
        
        # Build headers
        headers = {
            "KALSHI-ACCESS-KEY": self.api_key_id,
            "KALSHI-ACCESS-SIGNATURE": signature,
            "KALSHI-ACCESS-TIMESTAMP": str(int(time.time() * 1000)),
            "Content-Type": "application/json",
        }
        
        try:
            response = self.session.request(
                method=method,
                url=url,
                params=params,
                json=json_body,
                headers=headers,
                timeout=10
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Kalshi API request failed: {method} {endpoint} - {e}")
            return None
    
    def fetch_markets(self) -> List[Market]:
        """
        Fetch active markets from Kalshi.
        
        Returns:
            List of normalized Market objects
        """
        endpoint = "/trade-api/v2/markets"
        params = {
            "status": "open",
            "limit": 200,
        }
        
        response = self._make_request("GET", endpoint, params=params)
        if not response or "markets" not in response:
            logger.warning("Kalshi returned no markets")
            return []
        
        raw_markets = response["markets"]
        logger.info(f"Fetched {len(raw_markets)} markets from Kalshi")
        
        # Normalize markets
        normalized: List[Market] = []
        for raw in raw_markets:
            market = self._normalize_market(raw)
            if market and self._passes_filters(market):
                normalized.append(market)
        
        logger.info(f"After filtering: {len(normalized)} Kalshi markets")
        return normalized
    
    def _normalize_market(self, data: Dict[str, Any]) -> Optional[Market]:
        """
        Normalize Kalshi market into internal Market model.
        
        Kalshi Structure:
        - ticker: "INXD-24JAN09-T4044" (unique market ID)
        - event_ticker: "INXD-24JAN09" (event grouping)
        - title: "Will the Nasdaq-100 close at or above $20,440 on January 9?"
        - yes_bid, yes_ask, no_bid, no_ask: Prices in cents (0-100)
        - open_time, close_time: ISO8601 timestamps
        - volume, open_interest: Trading stats
        
        Normalization Rules:
        - Market ID: "kalshi:<event_ticker>:<ticker>"
        - Outcomes: YES and NO with prices [0.0-1.0]
        - Liquidity: Estimated from orderbook depth (open_interest * avg_price)
        - Expiry: Parse close_time to UTC datetime
        
        Args:
            data: Raw Kalshi market dict
        
        Returns:
            Normalized Market or None if invalid
        """
        try:
            ticker = data.get("ticker")
            event_ticker = data.get("event_ticker", "")
            title = data.get("title", "Unknown")
            
            if not ticker:
                return None
            
            # Parse prices (Kalshi uses cents, need to convert to probability)
            yes_bid = float(data.get("yes_bid", 0)) / 100.0
            yes_ask = float(data.get("yes_ask", 0)) / 100.0
            no_bid = float(data.get("no_bid", 0)) / 100.0
            no_ask = float(data.get("no_ask", 0)) / 100.0
            
            # Mid prices
            yes_price = (yes_bid + yes_ask) / 2.0 if (yes_bid + yes_ask) > 0 else 0.5
            no_price = (no_bid + no_ask) / 2.0 if (no_bid + no_ask) > 0 else 0.5
            
            # Estimate liquidity (open_interest * average price)
            open_interest = float(data.get("open_interest", 0))
            volume = float(data.get("volume", 0))
            liquidity = open_interest * yes_price if open_interest > 0 else volume * 0.1
            
            # Parse expiry
            close_time_str = data.get("close_time")
            expiry = None
            if close_time_str:
                try:
                    expiry = datetime.fromisoformat(close_time_str.replace("Z", "+00:00"))
                except Exception:
                    pass
            
            # Build outcomes
            outcomes = [
                Outcome(
                    id=f"{ticker}:YES",
                    label="YES",
                    price=yes_price,
                    liquidity=liquidity / 2.0,
                ),
                Outcome(
                    id=f"{ticker}:NO",
                    label="NO",
                    price=no_price,
                    liquidity=liquidity / 2.0,
                ),
            ]
            
            # Build market
            market = Market(
                id=f"kalshi:{event_ticker}:{ticker}",
                question=title,
                outcomes=outcomes,
                end_date=expiry,
                expiry=expiry,
                liquidity=liquidity,
                volume=volume,
                tags=data.get("category", "").split(",") if data.get("category") else [],
                description=data.get("subtitle"),
                resolution_source="Kalshi Official",
            )
            
            # Tag exchange
            market.exchange = "kalshi"  # type: ignore
            
            return market
            
        except Exception as e:
            logger.warning(f"Failed to normalize Kalshi market {data.get('ticker')}: {e}")
            return None
    
    def _passes_filters(self, market: Market) -> bool:
        """
        Apply client-side filters to reduce noise.
        
        Args:
            market: Normalized market
        
        Returns:
            True if market passes filters
        """
        # Liquidity filter
        if market.liquidity < self.min_liquidity_usd:
            return False
        
        # Expiry filter
        if market.expiry:
            now = datetime.now(timezone.utc)
            days_to_expiry = (market.expiry - now).total_seconds() / 86400
            if days_to_expiry < self.min_days_to_expiry:
                return False
        
        return True
    
    def get_metadata(self) -> Dict[str, Any]:
        """
        Return Kalshi-specific metadata.
        
        Returns:
            Dict with exchange info
        """
        return {
            "exchange": "kalshi",
            "fee_bps": 7,  # Kalshi charges ~0.07% per side
            "tick_size": 0.01,  # $0.01 minimum price increment
            "base_url": self.api_host,
            "supports_orderbook": True,
            "env": self.env,
        }
