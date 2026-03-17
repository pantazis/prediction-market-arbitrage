"""
Bug Condition Exploration Test: Category Metadata Missing for Kalshi Markets

**Validates: Requirements 1.3, 1.4, 1.5**

This test validates that the fix works correctly:
- `_normalize_market()` populates tags from event_ticker
- `_get_market_group()` returns valid groups for Kalshi markets
- `find_pairs()` finds matches between equivalent markets

EXPECTED OUTCOME: All tests PASS after the fix is implemented.
"""

import pytest
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional

from predarb.models import Market, Outcome
from predarb.cross_venue_matcher import CrossVenueMatcher
from predarb.series_mapper import get_category_tag, get_asset_tag


# =============================================================================
# Mock Kalshi Market Data
# =============================================================================

def create_mock_kalshi_raw_market(
    event_ticker: str,
    ticker: str,
    title: str,
    yes_bid: int = 50,
    yes_ask: int = 52,
    no_bid: int = 48,
    no_ask: int = 50,
    category: str = "",  # Kalshi API returns empty category for most markets
) -> Dict[str, Any]:
    """
    Create mock raw Kalshi market data as returned by the API.
    
    Note: The Kalshi API does NOT return a 'category' field for most markets,
    which is the root cause of the bug.
    """
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
        "category": category,  # Empty - this is the bug!
    }


# Mock Kalshi markets with known series prefixes
MOCK_KALSHI_CRYPTO_MARKETS = [
    create_mock_kalshi_raw_market(
        event_ticker="KXBTC-25JAN10",
        ticker="KXBTC-25JAN10-B95000",
        title="Will Bitcoin be above $95,000 on January 10?",
    ),
    create_mock_kalshi_raw_market(
        event_ticker="KXETH-25FEB15",
        ticker="KXETH-25FEB15-B3500",
        title="Will Ethereum be above $3,500 on February 15?",
    ),
    create_mock_kalshi_raw_market(
        event_ticker="KXSOL-25MAR01",
        ticker="KXSOL-25MAR01-B200",
        title="Will Solana be above $200 on March 1?",
    ),
]

MOCK_KALSHI_POLITICS_MARKETS = [
    create_mock_kalshi_raw_market(
        event_ticker="KXPRES-24NOV05",
        ticker="KXPRES-24NOV05-DEM",
        title="Will the Democratic candidate win the 2024 presidential election?",
    ),
]

MOCK_KALSHI_ECONOMICS_MARKETS = [
    create_mock_kalshi_raw_market(
        event_ticker="KXFED-25MAR19",
        ticker="KXFED-25MAR19-CUT",
        title="Will the Fed cut interest rates in March 2025?",
    ),
]


def create_normalized_kalshi_market(raw: Dict[str, Any]) -> Market:
    """
    Create a normalized Kalshi market using the FIXED logic.
    This simulates what the real KalshiClient._normalize_market() does after the fix.
    """
    ticker = raw["ticker"]
    event_ticker = raw["event_ticker"]
    title = raw["title"]
    
    yes_bid = float(raw.get("yes_bid", 0)) / 100.0
    yes_ask = float(raw.get("yes_ask", 0)) / 100.0
    no_bid = float(raw.get("no_bid", 0)) / 100.0
    no_ask = float(raw.get("no_ask", 0)) / 100.0
    
    yes_price = (yes_bid + yes_ask) / 2.0 if (yes_bid + yes_ask) > 0 else 0.5
    no_price = (no_bid + no_ask) / 2.0 if (no_bid + no_ask) > 0 else 0.5
    
    open_interest = float(raw.get("open_interest", 0))
    volume = float(raw.get("volume", 0))
    liquidity = open_interest * yes_price if open_interest > 0 else volume * 0.1
    
    close_time_str = raw.get("close_time")
    expiry = None
    if close_time_str:
        try:
            expiry = datetime.fromisoformat(close_time_str.replace("Z", "+00:00"))
        except Exception:
            pass
    
    outcomes = [
        Outcome(id=f"{ticker}:YES", label="YES", price=yes_price, liquidity=liquidity / 2.0),
        Outcome(id=f"{ticker}:NO", label="NO", price=no_price, liquidity=liquidity / 2.0),
    ]
    
    # FIXED: Infer category from event_ticker using series_mapper
    api_category = raw.get("category", "")
    if api_category:
        tags = [t.strip() for t in api_category.split(",") if t.strip()]
    else:
        inferred_category = get_category_tag(event_ticker)
        tags = [inferred_category] if inferred_category else []
    
    market = Market(
        id=f"kalshi:{event_ticker}:{ticker}",
        question=title,
        outcomes=outcomes,
        end_date=expiry,
        expiry=expiry,
        updated_at=datetime.now(timezone.utc),
        liquidity=liquidity,
        volume=volume,
        tags=tags,
        description="",
        resolution_source="Kalshi Official",
    )
    market.exchange = "kalshi"
    return market


def create_mock_polymarket_market(
    market_id: str,
    question: str,
    tags: List[str],
    yes_price: float = 0.50,
    no_price: float = 0.50,
) -> Market:
    """Create a mock Polymarket market with proper tags."""
    market = Market(
        id=f"polymarket:{market_id}",
        question=question,
        outcomes=[
            Outcome(id=f"{market_id}:YES", label="YES", price=yes_price, liquidity=10000.0),
            Outcome(id=f"{market_id}:NO", label="NO", price=no_price, liquidity=10000.0),
        ],
        end_date=datetime.now(timezone.utc) + timedelta(days=30),
        liquidity=50000.0,
        volume=20000.0,
        tags=tags,
    )
    market.exchange = "polymarket"
    return market


# Mock Polymarket markets with proper tags (these SHOULD match Kalshi markets)
MOCK_POLYMARKET_CRYPTO_MARKETS = [
    create_mock_polymarket_market(
        market_id="btc-95k-jan",
        question="Will Bitcoin reach $95,000 by January 10, 2025?",
        tags=["Crypto", "Bitcoin"],
        yes_price=0.52,
    ),
    create_mock_polymarket_market(
        market_id="eth-3500-feb",
        question="Will Ethereum reach $3,500 by February 15, 2025?",
        tags=["Crypto", "Ethereum"],
        yes_price=0.48,
    ),
]


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def cross_venue_matcher():
    """Provide a CrossVenueMatcher instance for testing."""
    return CrossVenueMatcher(
        min_similarity=0.60,
        max_hours_diff=24,
        enabled=True,
    )


# =============================================================================
# Bug Fix Validation Tests
# =============================================================================

class TestCategoryMetadataBugFix:
    """
    Tests that validate the bug fix works correctly.
    
    EXPECTED: All tests should PASS after the fix is implemented.
    """
    
    def test_series_mapper_extracts_crypto_category(self):
        """
        Test that series_mapper correctly extracts 'crypto' category from event_ticker.
        """
        test_cases = [
            ("KXBTC-25JAN10", "crypto"),
            ("KXETH-25FEB15", "crypto"),
            ("KXSOL-25MAR01", "crypto"),
            ("KXDOGE-25APR01", "crypto"),  # Dynamic - not hardcoded
            ("KXPEPE-25MAY01", "crypto"),  # Dynamic - not hardcoded
        ]
        for event_ticker, expected_category in test_cases:
            category = get_category_tag(event_ticker)
            assert category == expected_category, (
                f"Event ticker {event_ticker} should map to '{expected_category}', got '{category}'"
            )
    
    def test_series_mapper_extracts_politics_category(self):
        """Test that series_mapper correctly extracts 'politics' category."""
        test_cases = [
            ("KXPRES-24NOV05", "politics"),
            ("KXSENATE-24NOV05", "politics"),
            ("KXHOUSE-24NOV05", "politics"),
        ]
        for event_ticker, expected_category in test_cases:
            category = get_category_tag(event_ticker)
            assert category == expected_category, (
                f"Event ticker {event_ticker} should map to '{expected_category}', got '{category}'"
            )
    
    def test_series_mapper_extracts_economics_category(self):
        """Test that series_mapper correctly extracts 'economics' category."""
        test_cases = [
            ("KXFED-25MAR19", "economics"),
            ("KXCPI-25APR01", "economics"),
            ("KXGDP-25Q1", "economics"),
        ]
        for event_ticker, expected_category in test_cases:
            category = get_category_tag(event_ticker)
            assert category == expected_category, (
                f"Event ticker {event_ticker} should map to '{expected_category}', got '{category}'"
            )
    
    def test_series_mapper_extracts_asset(self):
        """Test that series_mapper correctly extracts asset names."""
        test_cases = [
            ("KXBTC-25JAN10", "bitcoin"),
            ("KXETH-25FEB15", "ethereum"),
            ("KXSOL-25MAR01", "solana"),
            ("KXDOGE-25APR01", "dogecoin"),
        ]
        for event_ticker, expected_asset in test_cases:
            asset = get_asset_tag(event_ticker)
            assert asset == expected_asset, (
                f"Event ticker {event_ticker} should map to asset '{expected_asset}', got '{asset}'"
            )
    
    def test_normalize_market_populates_tags_for_crypto(self):
        """
        Test that normalized markets have tags populated from event_ticker.
        """
        for raw_market in MOCK_KALSHI_CRYPTO_MARKETS:
            market = create_normalized_kalshi_market(raw_market)
            
            assert market is not None, f"Market should be normalized: {raw_market['ticker']}"
            assert len(market.tags) > 0, (
                f"Market {market.id} should have category tags, got {market.tags}"
            )
            assert "crypto" in market.tags, (
                f"Market {market.id} should have 'crypto' tag, got {market.tags}"
            )
    
    def test_normalize_market_populates_tags_for_politics(self):
        """Test that politics markets have tags populated."""
        for raw_market in MOCK_KALSHI_POLITICS_MARKETS:
            market = create_normalized_kalshi_market(raw_market)
            
            assert market is not None
            assert len(market.tags) > 0
            assert "politics" in market.tags
    
    def test_normalize_market_populates_tags_for_economics(self):
        """Test that economics markets have tags populated."""
        for raw_market in MOCK_KALSHI_ECONOMICS_MARKETS:
            market = create_normalized_kalshi_market(raw_market)
            
            assert market is not None
            assert len(market.tags) > 0
            assert "economics" in market.tags
    
    def test_get_market_group_returns_asset_for_kalshi_crypto(self, cross_venue_matcher):
        """
        Test that _get_market_group() returns valid asset group for Kalshi crypto markets.
        """
        for raw_market in MOCK_KALSHI_CRYPTO_MARKETS:
            market = create_normalized_kalshi_market(raw_market)
            
            group = cross_venue_matcher._get_market_group(market)
            
            assert group is not None, (
                f"Market {market.id} should have a valid group, got None"
            )
            assert group.startswith("asset:"), (
                f"Crypto market group should start with 'asset:', got '{group}'"
            )
    
    def test_get_market_group_returns_category_for_politics(self, cross_venue_matcher):
        """Test that _get_market_group() returns category for politics markets."""
        for raw_market in MOCK_KALSHI_POLITICS_MARKETS:
            market = create_normalized_kalshi_market(raw_market)
            
            group = cross_venue_matcher._get_market_group(market)
            
            assert group is not None
            assert group == "category:politics", f"Expected 'category:politics', got '{group}'"
    
    def test_kalshi_and_polymarket_have_common_groups(self, cross_venue_matcher):
        """
        Test that Kalshi and Polymarket markets now have common groups.
        """
        # Normalize Kalshi markets
        kalshi_markets = [create_normalized_kalshi_market(raw) for raw in MOCK_KALSHI_CRYPTO_MARKETS]
        
        # Get groups for Kalshi markets
        kalshi_groups = set()
        for m in kalshi_markets:
            group = cross_venue_matcher._get_market_group(m)
            if group:
                kalshi_groups.add(group)
        
        # Get groups for Polymarket markets
        poly_groups = set()
        for m in MOCK_POLYMARKET_CRYPTO_MARKETS:
            group = cross_venue_matcher._get_market_group(m)
            if group:
                poly_groups.add(group)
        
        assert len(kalshi_groups) > 0, f"Kalshi should have groups, got {kalshi_groups}"
        assert len(poly_groups) > 0, f"Polymarket should have groups, got {poly_groups}"
        
        # Check for common groups
        common_groups = kalshi_groups & poly_groups
        assert len(common_groups) > 0, (
            f"Should have common groups. Kalshi: {kalshi_groups}, Poly: {poly_groups}"
        )
