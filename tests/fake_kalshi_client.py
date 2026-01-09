"""
Fake Kalshi client for deterministic testing (no network calls).
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any

from predarb.market_client_base import MarketClient
from predarb.models import Market, Outcome


class FakeKalshiClient(MarketClient):
    """
    Deterministic Kalshi client for testing.
    
    Returns fixed market fixtures with NO network calls.
    """
    
    def __init__(self, fixture_name: str = "default"):
        """
        Initialize fake client with specified fixture.
        
        Args:
            fixture_name: Fixture to load ("default", "high_volume", "parity_arb")
        """
        self.fixture_name = fixture_name
        self.call_count = 0
    
    def fetch_markets(self) -> List[Market]:
        """
        Return deterministic Kalshi market fixtures.
        
        Returns:
            List of fake Market objects
        """
        self.call_count += 1
        
        if self.fixture_name == "default":
            return self._default_fixture()
        elif self.fixture_name == "high_volume":
            return self._high_volume_fixture()
        elif self.fixture_name == "parity_arb":
            return self._parity_arb_fixture()
        elif self.fixture_name == "empty":
            return []
        else:
            return self._default_fixture()
    
    def _default_fixture(self) -> List[Market]:
        """Default fixture with 2 Kalshi markets."""
        now = datetime.now(timezone.utc)
        expiry_1 = now + timedelta(days=7)
        expiry_2 = now + timedelta(days=14)
        
        markets = [
            Market(
                id="kalshi:INXD-24JAN09:INXD-24JAN09-T4044",
                question="Will the Nasdaq-100 close at or above $20,440 on January 9?",
                outcomes=[
                    Outcome(id="INXD-24JAN09-T4044:YES", label="YES", price=0.52, liquidity=5000.0),
                    Outcome(id="INXD-24JAN09-T4044:NO", label="NO", price=0.48, liquidity=5000.0),
                ],
                end_date=expiry_1,
                expiry=expiry_1,
                liquidity=10000.0,
                volume=25000.0,
                tags=["finance", "stocks"],
                description="Nasdaq-100 index binary prediction",
                resolution_source="Kalshi Official",
            ),
            Market(
                id="kalshi:KXBTC-24JAN16:KXBTC-24JAN16-T95000",
                question="Will Bitcoin close at or above $95,000 on January 16?",
                outcomes=[
                    Outcome(id="KXBTC-24JAN16-T95000:YES", label="YES", price=0.35, liquidity=8000.0),
                    Outcome(id="KXBTC-24JAN16-T95000:NO", label="NO", price=0.65, liquidity=8000.0),
                ],
                end_date=expiry_2,
                expiry=expiry_2,
                liquidity=16000.0,
                volume=50000.0,
                tags=["crypto", "bitcoin"],
                description="Bitcoin price binary prediction",
                resolution_source="Kalshi Official",
            ),
        ]
        
        # Tag all as Kalshi
        for m in markets:
            m.exchange = "kalshi"  # type: ignore
        
        return markets
    
    def _high_volume_fixture(self) -> List[Market]:
        """Fixture with 50 Kalshi markets for stress testing."""
        now = datetime.now(timezone.utc)
        markets: List[Market] = []
        
        for i in range(50):
            expiry = now + timedelta(days=i + 1)
            ticker = f"TEST-24JAN{i:02d}-T{i * 100}"
            
            market = Market(
                id=f"kalshi:TEST-24JAN{i:02d}:{ticker}",
                question=f"Test market #{i} - will outcome occur?",
                outcomes=[
                    Outcome(id=f"{ticker}:YES", label="YES", price=0.50 + (i % 10) * 0.01, liquidity=1000.0),
                    Outcome(id=f"{ticker}:NO", label="NO", price=0.50 - (i % 10) * 0.01, liquidity=1000.0),
                ],
                end_date=expiry,
                expiry=expiry,
                liquidity=2000.0,
                volume=5000.0,
                tags=["test"],
                description=f"Test market {i}",
                resolution_source="Kalshi Official",
            )
            market.exchange = "kalshi"  # type: ignore
            markets.append(market)
        
        return markets
    
    def _parity_arb_fixture(self) -> List[Market]:
        """Fixture with a parity arbitrage opportunity (YES + NO ≠ 1.0)."""
        now = datetime.now(timezone.utc)
        expiry = now + timedelta(days=3)
        
        # Deliberate parity violation: YES + NO = 0.95 (5% edge)
        market = Market(
            id="kalshi:PARITY-24JAN09:PARITY-24JAN09-TEST",
            question="Will parity test resolve YES?",
            outcomes=[
                Outcome(id="PARITY-24JAN09-TEST:YES", label="YES", price=0.45, liquidity=10000.0),
                Outcome(id="PARITY-24JAN09-TEST:NO", label="NO", price=0.50, liquidity=10000.0),
            ],
            end_date=expiry,
            expiry=expiry,
            liquidity=20000.0,
            volume=10000.0,
            tags=["test"],
            description="Parity arbitrage test market",
            resolution_source="Kalshi Official",
        )
        market.exchange = "kalshi"  # type: ignore
        
        return [market]
    
    def get_metadata(self) -> Dict[str, Any]:
        """Return fake Kalshi metadata."""
        return {
            "exchange": "kalshi",
            "fee_bps": 7,
            "tick_size": 0.01,
            "base_url": "https://fake-kalshi-api.test",
            "supports_orderbook": True,
            "env": "test",
            "fixture_name": self.fixture_name,
            "call_count": self.call_count,
        }
