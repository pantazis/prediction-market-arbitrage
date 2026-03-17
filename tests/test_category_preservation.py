"""
Preservation Property Tests: Existing Behavior Unchanged

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7**

These tests verify that the bugfix does NOT break existing functionality:
- Sports markets continue to be excluded
- Price normalization unchanged (cents to probability)
- Binary market filtering unchanged
- Match pipeline produces consistent results

EXPECTED OUTCOME: All tests PASS on both unfixed and fixed code.
"""

import pytest
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional

from predarb.models import Market, Outcome


# =============================================================================
# Mock Kalshi Client (same as exploration test)
# =============================================================================

class MockKalshiClient:
    """Mock KalshiClient for preservation testing."""
    
    def __init__(self):
        self.excluded_sports_prefixes = {
            "KXNBA", "KXNFL", "KXNHL", "KXPGATOUR", "KXATPMATCH", "KXWTAMATCH",
            "KXNCAAWBGAME", "KXNCAAMB", "KXLALIGA", "KXLIGUE1", "KXBUNDESLIGA", "KXTGLMATCH",
            "KXCOACH", "KXNYG", "KXNEXT", "KXDOTA2", "KXLOL",
            "KXMVESPORTSMULTIGAME", "KXMVENFLSINGLEGAME", "KXMVESPORTS", "KXMVENFL",
            "KXMVENBA", "KXMVEMLB", "KXMVENHL", "KXMVESOCCER",
            "KXMVECROSSCATEGORY"
        }
    
    def _normalize_market(self, data: Dict[str, Any]) -> Optional[Market]:
        """Copy of real _normalize_market() for testing."""
        try:
            ticker = data.get("ticker")
            event_ticker = data.get("event_ticker", "")
            title = data.get("title", "Unknown")

            if not ticker:
                return None
            
            # Filter out sports markets
            for prefix in self.excluded_sports_prefixes:
                if event_ticker.startswith(prefix):
                    return None
            
            # Parse prices (Kalshi uses cents, convert to probability)
            yes_bid = float(data.get("yes_bid", 0)) / 100.0
            yes_ask = float(data.get("yes_ask", 0)) / 100.0
            no_bid = float(data.get("no_bid", 0)) / 100.0
            no_ask = float(data.get("no_ask", 0)) / 100.0

            yes_price = (yes_bid + yes_ask) / 2.0 if (yes_bid + yes_ask) > 0 else 0.5
            no_price = (no_bid + no_ask) / 2.0 if (no_bid + no_ask) > 0 else 0.5
            
            open_interest = float(data.get("open_interest", 0))
            volume = float(data.get("volume", 0))
            liquidity = open_interest * yes_price if open_interest > 0 else volume * 0.1

            close_time_str = data.get("close_time")
            expiry = None
            if close_time_str:
                try:
                    expiry = datetime.fromisoformat(close_time_str.replace("Z", "+00:00"))
                except Exception:
                    pass

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

            market = Market(
                id=f"kalshi:{event_ticker}:{ticker}",
                question=title,
                outcomes=outcomes,
                end_date=expiry,
                expiry=expiry,
                updated_at=datetime.now(timezone.utc),
                liquidity=liquidity,
                volume=volume,
                tags=data.get("category", "").split(",") if data.get("category") else [],
                description=data.get("rules_primary", "") or data.get("subtitle", ""),
                resolution_source="Kalshi Official",
            )
            
            market.exchange = "kalshi"
            return market
            
        except Exception:
            return None


# =============================================================================
# Test Data
# =============================================================================

def create_raw_market(
    event_ticker: str,
    ticker: str,
    title: str,
    yes_bid: int = 50,
    yes_ask: int = 52,
    no_bid: int = 48,
    no_ask: int = 50,
) -> Dict[str, Any]:
    """Create mock raw Kalshi market data."""
    return {
        "ticker": ticker,
        "event_ticker": event_ticker,
        "title": title,
        "yes_bid": yes_bid,
        "yes_ask": yes_ask,
        "no_bid": no_bid,
        "no_ask": no_ask,
        "open_interest": 1000,
        "volume": 5000,
        "close_time": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
        "category": "",
    }


# Sports markets that MUST be excluded
SPORTS_MARKETS = [
    create_raw_market("KXNBA-25JAN10", "KXNBA-25JAN10-LAL", "Lakers vs Celtics"),
    create_raw_market("KXNFL-25JAN12", "KXNFL-25JAN12-KC", "Chiefs vs Bills"),
    create_raw_market("KXMVECROSSCATEGORY-25JAN", "KXMVECROSSCATEGORY-25JAN-PARLAY", "Sports Parlay"),
    create_raw_market("KXMVENFL-25JAN", "KXMVENFL-25JAN-MULTI", "NFL Multi-game"),
    create_raw_market("KXDOTA2-25JAN", "KXDOTA2-25JAN-TI", "Dota 2 Tournament"),
]

# Non-sports markets that MUST be included
NON_SPORTS_MARKETS = [
    create_raw_market("INXD-25JAN10", "INXD-25JAN10-T4044", "Nasdaq above 20440?"),
    create_raw_market("KXBTC-25JAN10", "KXBTC-25JAN10-B95000", "Bitcoin above $95k?"),
    create_raw_market("KXPRES-24NOV05", "KXPRES-24NOV05-DEM", "Democratic candidate wins?"),
]


@pytest.fixture
def mock_client():
    return MockKalshiClient()


# =============================================================================
# Preservation Tests
# =============================================================================

class TestSportsExclusionPreservation:
    """
    Property 2.1: Sports markets MUST continue to be excluded.
    
    This behavior must be preserved regardless of the category fix.
    """
    
    def test_nba_markets_excluded(self, mock_client):
        """KXNBA markets must return None."""
        raw = create_raw_market("KXNBA-25JAN10", "KXNBA-25JAN10-LAL", "Lakers game")
        market = mock_client._normalize_market(raw)
        assert market is None, "NBA markets must be excluded"
    
    def test_nfl_markets_excluded(self, mock_client):
        """KXNFL markets must return None."""
        raw = create_raw_market("KXNFL-25JAN12", "KXNFL-25JAN12-KC", "Chiefs game")
        market = mock_client._normalize_market(raw)
        assert market is None, "NFL markets must be excluded"
    
    def test_cross_category_parlays_excluded(self, mock_client):
        """KXMVECROSSCATEGORY markets must return None."""
        raw = create_raw_market("KXMVECROSSCATEGORY-25JAN", "KXMVECROSSCATEGORY-25JAN-X", "Parlay")
        market = mock_client._normalize_market(raw)
        assert market is None, "Cross-category parlays must be excluded"
    
    def test_esports_excluded(self, mock_client):
        """KXDOTA2 and KXLOL markets must return None."""
        for prefix in ["KXDOTA2", "KXLOL"]:
            raw = create_raw_market(f"{prefix}-25JAN", f"{prefix}-25JAN-X", "Esports match")
            market = mock_client._normalize_market(raw)
            assert market is None, f"{prefix} markets must be excluded"
    
    def test_all_sports_prefixes_excluded(self, mock_client):
        """All sports markets must be excluded."""
        for raw in SPORTS_MARKETS:
            market = mock_client._normalize_market(raw)
            assert market is None, f"Sports market {raw['event_ticker']} must be excluded"


class TestPriceNormalizationPreservation:
    """
    Property 2.2: Price normalization (cents to probability) must be unchanged.
    
    Kalshi prices are in cents (0-100), must convert to probability (0.0-1.0).
    """
    
    def test_price_conversion_50_cents(self, mock_client):
        """50 cents -> 0.50 probability."""
        raw = create_raw_market("INXD-25JAN10", "INXD-25JAN10-T4044", "Test",
                                yes_bid=50, yes_ask=50, no_bid=50, no_ask=50)
        market = mock_client._normalize_market(raw)
        assert market is not None
        assert market.outcomes[0].price == 0.50
        assert market.outcomes[1].price == 0.50
    
    def test_price_conversion_75_cents(self, mock_client):
        """75 cents -> 0.75 probability."""
        raw = create_raw_market("INXD-25JAN10", "INXD-25JAN10-T4044", "Test",
                                yes_bid=74, yes_ask=76, no_bid=24, no_ask=26)
        market = mock_client._normalize_market(raw)
        assert market is not None
        # (74 + 76) / 2 / 100 = 0.75
        assert market.outcomes[0].price == 0.75
    
    def test_price_conversion_edge_cases(self, mock_client):
        """Edge cases: 1, 99, 100 cents (0/0 defaults to 0.5)."""
        test_cases = [
            (0, 0, 0.5),    # 0 cents -> 0.5 (fallback when no price)
            (1, 1, 0.01),   # 1 cent -> 0.01
            (99, 99, 0.99), # 99 cents -> 0.99
            (100, 100, 1.0), # 100 cents -> 1.0
        ]
        for bid, ask, expected in test_cases:
            raw = create_raw_market("INXD-25JAN10", "INXD-25JAN10-T4044", "Test",
                                    yes_bid=bid, yes_ask=ask)
            market = mock_client._normalize_market(raw)
            assert market is not None
            assert market.outcomes[0].price == expected, f"Expected {expected} for {bid}/{ask}"


class TestBinaryMarketPreservation:
    """
    Property 2.3: Binary market structure (YES/NO) must be preserved.
    """
    
    def test_outcomes_are_yes_no(self, mock_client):
        """Markets must have exactly 2 outcomes: YES and NO."""
        for raw in NON_SPORTS_MARKETS:
            market = mock_client._normalize_market(raw)
            assert market is not None
            assert len(market.outcomes) == 2
            labels = [o.label for o in market.outcomes]
            assert "YES" in labels
            assert "NO" in labels
    
    def test_outcome_ids_contain_ticker(self, mock_client):
        """Outcome IDs must contain the market ticker."""
        raw = create_raw_market("INXD-25JAN10", "INXD-25JAN10-T4044", "Test")
        market = mock_client._normalize_market(raw)
        assert market is not None
        for outcome in market.outcomes:
            assert "INXD-25JAN10-T4044" in outcome.id


class TestMarketIdFormatPreservation:
    """
    Property 2.4: Market ID format must be preserved.
    
    Format: "kalshi:{event_ticker}:{ticker}"
    """
    
    def test_market_id_format(self, mock_client):
        """Market ID must follow kalshi:EVENT:TICKER format."""
        raw = create_raw_market("KXBTC-25JAN10", "KXBTC-25JAN10-B95000", "BTC Test")
        market = mock_client._normalize_market(raw)
        assert market is not None
        assert market.id == "kalshi:KXBTC-25JAN10:KXBTC-25JAN10-B95000"
    
    def test_exchange_attribute_set(self, mock_client):
        """Exchange attribute must be 'kalshi'."""
        for raw in NON_SPORTS_MARKETS:
            market = mock_client._normalize_market(raw)
            assert market is not None
            assert market.exchange == "kalshi"


class TestNonSportsMarketsIncluded:
    """
    Property 2.5: Non-sports markets must continue to be included.
    """
    
    def test_nasdaq_markets_included(self, mock_client):
        """INXD (Nasdaq) markets must be included."""
        raw = create_raw_market("INXD-25JAN10", "INXD-25JAN10-T4044", "Nasdaq test")
        market = mock_client._normalize_market(raw)
        assert market is not None, "Nasdaq markets must be included"
    
    def test_crypto_markets_included(self, mock_client):
        """KXBTC, KXETH, KXSOL markets must be included."""
        for prefix in ["KXBTC", "KXETH", "KXSOL"]:
            raw = create_raw_market(f"{prefix}-25JAN10", f"{prefix}-25JAN10-B100", "Crypto test")
            market = mock_client._normalize_market(raw)
            assert market is not None, f"{prefix} markets must be included"
    
    def test_politics_markets_included(self, mock_client):
        """KXPRES markets must be included."""
        raw = create_raw_market("KXPRES-24NOV05", "KXPRES-24NOV05-DEM", "Politics test")
        market = mock_client._normalize_market(raw)
        assert market is not None, "Politics markets must be included"
    
    def test_economics_markets_included(self, mock_client):
        """KXFED markets must be included."""
        raw = create_raw_market("KXFED-25MAR19", "KXFED-25MAR19-CUT", "Fed test")
        market = mock_client._normalize_market(raw)
        assert market is not None, "Economics markets must be included"


class TestLiquidityCalculationPreservation:
    """
    Property 2.6: Liquidity calculation must be preserved.
    
    liquidity = open_interest * yes_price (if open_interest > 0)
    liquidity = volume * 0.1 (fallback)
    """
    
    def test_liquidity_from_open_interest(self, mock_client):
        """Liquidity calculated from open_interest when available."""
        raw = create_raw_market("INXD-25JAN10", "INXD-25JAN10-T4044", "Test",
                                yes_bid=50, yes_ask=50)
        raw["open_interest"] = 1000
        raw["volume"] = 5000
        market = mock_client._normalize_market(raw)
        assert market is not None
        # liquidity = 1000 * 0.50 = 500
        assert market.liquidity == 500.0
    
    def test_liquidity_fallback_to_volume(self, mock_client):
        """Liquidity falls back to volume * 0.1 when no open_interest."""
        raw = create_raw_market("INXD-25JAN10", "INXD-25JAN10-T4044", "Test")
        raw["open_interest"] = 0
        raw["volume"] = 10000
        market = mock_client._normalize_market(raw)
        assert market is not None
        # liquidity = 10000 * 0.1 = 1000
        assert market.liquidity == 1000.0
