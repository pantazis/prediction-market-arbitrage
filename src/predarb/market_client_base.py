"""
Abstract base class for market data clients.

Defines the interface that all market clients (Polymarket, Kalshi, etc.) must implement.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Dict, Any

from predarb.models import Market


class MarketClient(ABC):
    """
    Abstract interface for fetching prediction market data.
    
    All concrete implementations (PolymarketClient, KalshiClient) must:
    - Fetch active markets from their respective APIs
    - Normalize data into the internal Market/Outcome models
    - Provide exchange-specific metadata (fees, tick sizes, exchange name)
    
    CRITICAL: All markets returned MUST set market.exchange field to identify the source.
    """
    
    @abstractmethod
    def fetch_markets(self) -> List[Market]:
        """
        Fetch all active markets from the exchange.
        
        Returns:
            List of Market objects with normalized:
            - id: Prefixed with exchange (e.g., "kalshi:INXD-24JAN09", "polymarket:0x1234...")
            - question: Human-readable question
            - outcomes: List[Outcome] with normalized prices [0.0-1.0]
            - liquidity: Estimated in USD
            - expiry: UTC datetime
            - exchange: Exchange identifier ("polymarket", "kalshi")
        
        Notes:
            - Prices must be normalized to [0.0, 1.0] probability scale
            - Market IDs must be globally unique across exchanges
            - Empty list on failure (errors logged internally)
        """
        pass
    
    @abstractmethod
    def get_metadata(self) -> Dict[str, Any]:
        """
        Return exchange-specific metadata.
        
        Returns:
            Dict containing:
            - exchange: str (e.g., "polymarket", "kalshi")
            - fee_bps: int (fees in basis points, e.g., 10 = 0.1%)
            - tick_size: float (minimum price increment, e.g., 0.01)
            - base_url: str (API base URL)
            - supports_orderbook: bool (whether real orderbook data available)
        """
        pass
    
    def get_exchange_name(self) -> str:
        """
        Convenience method to get exchange identifier.
        
        Returns:
            Exchange name (e.g., "polymarket", "kalshi")
        """
        return self.get_metadata().get("exchange", "unknown")
