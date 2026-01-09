"""Tests for dual-venue injection mechanism."""
import pytest
import json
from pathlib import Path
from src.predarb.dual_injection import (
    DualInjectionClient,
    InjectionFactory,
    FileInjectionProvider,
    InlineInjectionProvider,
)
from src.predarb.models import Market, Outcome
from datetime import datetime, timedelta, timezone


@pytest.fixture
def sample_poly_markets():
    """Sample Polymarket fixtures."""
    expiry = datetime.now(timezone.utc) + timedelta(days=7)
    return [
        Market(
            id="poly:test_1",
            question="Will event 1 occur?",
            outcomes=[
                Outcome(id="poly:1:yes", label="YES", price=0.6, liquidity=5000),
                Outcome(id="poly:1:no", label="NO", price=0.4, liquidity=5000),
            ],
            end_date=expiry,
            liquidity=10000,
            volume=15000,
            tags=["test"],
            exchange="polymarket",
        )
    ]


@pytest.fixture
def sample_kalshi_markets():
    """Sample Kalshi fixtures."""
    expiry = datetime.now(timezone.utc) + timedelta(days=7)
    return [
        Market(
            id="kalshi:TEST-1:T1",
            question="Will event 1 occur?",
            outcomes=[
                Outcome(id="kalshi:T1:YES", label="YES", price=0.55, liquidity=4000),
                Outcome(id="kalshi:T1:NO", label="NO", price=0.45, liquidity=4000),
            ],
            end_date=expiry,
            liquidity=8000,
            volume=12000,
            tags=["test"],
            exchange="kalshi",
        )
    ]


class StaticProvider:
    """Static market provider for testing."""
    def __init__(self, markets, exchange_name="test"):
        self.markets = markets
        self.exchange_name = exchange_name
    
    def fetch_markets(self):
        return self.markets
    
    def get_active_markets(self):
        return self.markets
    
    def get_exchange_name(self):
        return self.exchange_name


def test_dual_injection_client_merges_both_venues(sample_poly_markets, sample_kalshi_markets):
    """Test that DualInjectionClient merges markets from both venues."""
    venue_a = StaticProvider(sample_poly_markets, "polymarket")
    venue_b = StaticProvider(sample_kalshi_markets, "kalshi")
    
    dual_client = DualInjectionClient(
        venue_a_provider=venue_a,
        venue_b_provider=venue_b,
        exchange_a="polymarket",
        exchange_b="kalshi",
    )
    
    markets = dual_client.fetch_markets()
    
    assert len(markets) == 2
    assert markets[0].exchange == "polymarket"
    assert markets[1].exchange == "kalshi"


def test_dual_injection_client_with_only_venue_a(sample_poly_markets):
    """Test DualInjectionClient with only venue A enabled."""
    venue_a = StaticProvider(sample_poly_markets, "polymarket")
    
    dual_client = DualInjectionClient(
        venue_a_provider=venue_a,
        venue_b_provider=None,
        exchange_a="polymarket",
        exchange_b="kalshi",
    )
    
    markets = dual_client.fetch_markets()
    
    assert len(markets) == 1
    assert markets[0].exchange == "polymarket"


def test_dual_injection_client_with_only_venue_b(sample_kalshi_markets):
    """Test DualInjectionClient with only venue B enabled."""
    venue_b = StaticProvider(sample_kalshi_markets, "kalshi")
    
    dual_client = DualInjectionClient(
        venue_a_provider=None,
        venue_b_provider=venue_b,
        exchange_a="polymarket",
        exchange_b="kalshi",
    )
    
    markets = dual_client.fetch_markets()
    
    assert len(markets) == 1
    assert markets[0].exchange == "kalshi"


def test_dual_injection_client_tags_untagged_markets():
    """Test that DualInjectionClient tags markets without exchange tags."""
    expiry = datetime.now(timezone.utc) + timedelta(days=7)
    
    # Create market without exchange tag
    untagged_market = Market(
        id="test:untagged",
        question="Untagged market?",
        outcomes=[
            Outcome(id="test:yes", label="YES", price=0.5, liquidity=1000),
            Outcome(id="test:no", label="NO", price=0.5, liquidity=1000),
        ],
        end_date=expiry,
        liquidity=2000,
        volume=3000,
        tags=["test"],
    )
    
    venue_a = StaticProvider([untagged_market], "polymarket")
    
    dual_client = DualInjectionClient(
        venue_a_provider=venue_a,
        venue_b_provider=None,
        exchange_a="polymarket",
        exchange_b="kalshi",
    )
    
    markets = dual_client.fetch_markets()
    
    assert len(markets) == 1
    assert markets[0].exchange == "polymarket"


def test_dual_injection_client_get_metadata():
    """Test DualInjectionClient metadata."""
    venue_a = StaticProvider([], "polymarket")
    venue_b = StaticProvider([], "kalshi")
    
    dual_client = DualInjectionClient(
        venue_a_provider=venue_a,
        venue_b_provider=venue_b,
    )
    
    metadata = dual_client.get_metadata()
    
    assert metadata["exchange"] == "dual_injection"
    assert metadata["venues"] == ["polymarket", "kalshi"]
    assert metadata["venue_a_enabled"] is True
    assert metadata["venue_b_enabled"] is True


def test_dual_injection_client_get_exchange_name():
    """Test DualInjectionClient exchange name."""
    venue_a = StaticProvider([], "polymarket")
    venue_b = StaticProvider([], "kalshi")
    
    dual_client = DualInjectionClient(
        venue_a_provider=venue_a,
        venue_b_provider=venue_b,
    )
    
    name = dual_client.get_exchange_name()
    
    assert "DualInjection" in name
    assert "polymarket" in name
    assert "kalshi" in name


def test_injection_factory_from_scenario():
    """Test InjectionFactory creates scenario provider."""
    provider = InjectionFactory.from_spec("scenario:happy_path", seed=42)
    
    assert provider is not None
    markets = provider.fetch_markets()
    assert len(markets) > 0


def test_injection_factory_from_file(tmp_path):
    """Test InjectionFactory creates file provider."""
    # Create test fixture file
    fixture_path = tmp_path / "test.json"
    fixture_data = [
        {
            "id": "test:1",
            "question": "Test?",
            "outcomes": [
                {"id": "yes", "label": "YES", "price": 0.5, "liquidity": 1000},
                {"id": "no", "label": "NO", "price": 0.5, "liquidity": 1000},
            ],
            "end_date": "2026-12-31T23:59:59Z",
            "liquidity": 2000,
            "volume": 3000,
            "tags": ["test"],
        }
    ]
    
    with open(fixture_path, 'w') as f:
        json.dump(fixture_data, f)
    
    provider = InjectionFactory.from_spec(f"file:{fixture_path}", exchange="polymarket")
    
    markets = provider.fetch_markets()
    assert len(markets) == 1
    assert markets[0].id == "test:1"
    assert markets[0].exchange == "polymarket"


def test_injection_factory_from_inline():
    """Test InjectionFactory creates inline provider."""
    inline_json = json.dumps([
        {
            "id": "inline:1",
            "question": "Inline test?",
            "outcomes": [
                {"id": "yes", "label": "YES", "price": 0.6, "liquidity": 500},
                {"id": "no", "label": "NO", "price": 0.4, "liquidity": 500},
            ],
            "end_date": "2026-12-31T23:59:59Z",
            "liquidity": 1000,
            "volume": 1500,
            "tags": ["inline"],
        }
    ])
    
    provider = InjectionFactory.from_spec(f"inline:{inline_json}", exchange="kalshi")
    
    markets = provider.fetch_markets()
    assert len(markets) == 1
    assert markets[0].id == "inline:1"
    assert markets[0].exchange == "kalshi"


def test_injection_factory_none():
    """Test InjectionFactory returns None for 'none' spec."""
    provider = InjectionFactory.from_spec("none")
    assert provider is None


def test_injection_factory_invalid_spec():
    """Test InjectionFactory raises error for invalid spec."""
    with pytest.raises(ValueError, match="Invalid injection spec"):
        InjectionFactory.from_spec("invalid:spec")


def test_file_injection_provider(tmp_path):
    """Test FileInjectionProvider loads and tags markets."""
    fixture_path = tmp_path / "markets.json"
    fixture_data = {
        "markets": [
            {
                "id": "file:1",
                "question": "File test?",
                "outcomes": [
                    {"id": "yes", "label": "YES", "price": 0.7, "liquidity": 2000},
                    {"id": "no", "label": "NO", "price": 0.3, "liquidity": 2000},
                ],
                "end_date": "2026-12-31T23:59:59Z",
                "liquidity": 4000,
                "volume": 5000,
                "tags": ["file"],
            }
        ]
    }
    
    with open(fixture_path, 'w') as f:
        json.dump(fixture_data, f)
    
    provider = FileInjectionProvider(str(fixture_path), exchange="polymarket")
    
    markets = provider.fetch_markets()
    assert len(markets) == 1
    assert markets[0].id == "file:1"
    assert markets[0].exchange == "polymarket"


def test_file_injection_provider_not_found():
    """Test FileInjectionProvider raises error for missing file."""
    with pytest.raises(FileNotFoundError):
        FileInjectionProvider("/nonexistent/file.json")


def test_file_injection_provider_invalid_format(tmp_path):
    """Test FileInjectionProvider raises error for invalid format."""
    fixture_path = tmp_path / "invalid.json"
    
    with open(fixture_path, 'w') as f:
        json.dump({"invalid": "format"}, f)
    
    provider = FileInjectionProvider(str(fixture_path))
    
    with pytest.raises(ValueError, match="Invalid fixture format"):
        provider.fetch_markets()


def test_inline_injection_provider():
    """Test InlineInjectionProvider parses and tags markets."""
    inline_json = json.dumps({
        "markets": [
            {
                "id": "inline:2",
                "question": "Inline test 2?",
                "outcomes": [
                    {"id": "yes", "label": "YES", "price": 0.55, "liquidity": 1500},
                    {"id": "no", "label": "NO", "price": 0.45, "liquidity": 1500},
                ],
                "end_date": "2026-12-31T23:59:59Z",
                "liquidity": 3000,
                "volume": 4000,
                "tags": ["inline"],
            }
        ]
    })
    
    provider = InlineInjectionProvider(inline_json, exchange="kalshi")
    
    markets = provider.fetch_markets()
    assert len(markets) == 1
    assert markets[0].id == "inline:2"
    assert markets[0].exchange == "kalshi"


def test_inline_injection_provider_invalid_json():
    """Test InlineInjectionProvider raises error for invalid JSON."""
    provider = InlineInjectionProvider("{not valid json}")
    
    with pytest.raises(json.JSONDecodeError):
        provider.fetch_markets()


def test_inline_injection_provider_invalid_format():
    """Test InlineInjectionProvider raises error for invalid format."""
    provider = InlineInjectionProvider('{"invalid": "format"}')
    
    with pytest.raises(ValueError, match="Invalid inline JSON format"):
        provider.fetch_markets()


def test_injection_factory_tags_scenario_markets():
    """Test that InjectionFactory properly tags scenario markets."""
    provider = InjectionFactory.from_spec("scenario:happy_path", seed=42, exchange="polymarket")
    
    markets = provider.fetch_markets()
    
    # All markets should be tagged with specified exchange
    for market in markets:
        assert market.exchange == "polymarket"


def test_dual_injection_preserves_existing_tags(sample_poly_markets):
    """Test that DualInjectionClient preserves existing exchange tags."""
    venue_a = StaticProvider(sample_poly_markets, "polymarket")
    
    dual_client = DualInjectionClient(
        venue_a_provider=venue_a,
        venue_b_provider=None,
    )
    
    markets = dual_client.fetch_markets()
    
    # Original tag should be preserved
    assert markets[0].exchange == "polymarket"
