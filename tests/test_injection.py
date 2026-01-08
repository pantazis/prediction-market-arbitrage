"""Tests for injection layer."""
import json
import pytest
from pathlib import Path
from src.predarb.injection import (
    InjectionSource,
    FileMarketProvider,
    InlineMarketProvider,
)
from src.predarb.models import Market, Outcome


def test_injection_from_scenario(tmp_path):
    """Test injection from built-in scenario."""
    provider = InjectionSource.from_spec("scenario:happy_path", seed=42)
    markets = provider.get_active_markets()
    
    assert len(markets) == 15
    assert all(isinstance(m, Market) for m in markets)
    assert all(m.id.startswith("happy_") for m in markets)


def test_injection_from_file(tmp_path):
    """Test injection from fixture file."""
    # Create test fixture
    fixture_path = tmp_path / "test_markets.json"
    test_data = [
        {
            "id": "test_1",
            "question": "Will test pass?",
            "outcomes": [
                {"id": "yes", "label": "Yes", "price": 0.45, "liquidity": 5000},
                {"id": "no", "label": "No", "price": 0.45, "liquidity": 5000},
            ],
            "end_date": "2026-12-31T23:59:59Z",
            "liquidity": 10000,
            "volume": 5000,
            "tags": ["test"],
            "resolution_source": "test",
        }
    ]
    
    with open(fixture_path, 'w') as f:
        json.dump(test_data, f)
    
    provider = InjectionSource.from_spec(f"file:{fixture_path}")
    markets = provider.get_active_markets()
    
    assert len(markets) == 1
    assert markets[0].id == "test_1"
    assert markets[0].question == "Will test pass?"
    assert len(markets[0].outcomes) == 2


def test_injection_from_file_with_markets_key(tmp_path):
    """Test injection from file with 'markets' key wrapper."""
    fixture_path = tmp_path / "wrapped_markets.json"
    test_data = {
        "markets": [
            {
                "id": "wrapped_1",
                "question": "Wrapped test?",
                "outcomes": [
                    {"id": "yes", "label": "Yes", "price": 0.5, "liquidity": 1000},
                    {"id": "no", "label": "No", "price": 0.5, "liquidity": 1000},
                ],
                "end_date": "2026-12-31T23:59:59Z",
                "liquidity": 2000,
                "volume": 1000,
                "tags": [],
                "resolution_source": "test",
            }
        ]
    }
    
    with open(fixture_path, 'w') as f:
        json.dump(test_data, f)
    
    provider = InjectionSource.from_spec(f"file:{fixture_path}")
    markets = provider.get_active_markets()
    
    assert len(markets) == 1
    assert markets[0].id == "wrapped_1"


def test_injection_from_inline():
    """Test injection from inline JSON string."""
    inline_json = '''[
        {
            "id": "inline_1",
            "question": "Inline test?",
            "outcomes": [
                {"id": "yes", "label": "Yes", "price": 0.4, "liquidity": 3000},
                {"id": "no", "label": "No", "price": 0.5, "liquidity": 3000}
            ],
            "end_date": "2026-12-31T23:59:59Z",
            "liquidity": 6000,
            "volume": 2000,
            "tags": ["inline"],
            "resolution_source": "test"
        }
    ]'''
    
    provider = InjectionSource.from_spec(f"inline:{inline_json}")
    markets = provider.get_active_markets()
    
    assert len(markets) == 1
    assert markets[0].id == "inline_1"
    assert markets[0].question == "Inline test?"


def test_injection_invalid_spec():
    """Test that invalid spec raises ValueError."""
    with pytest.raises(ValueError, match="Invalid injection spec"):
        InjectionSource.from_spec("invalid:spec")


def test_injection_file_not_found():
    """Test that missing file raises FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        InjectionSource.from_spec("file:/nonexistent/path.json")


def test_injection_scenario_not_found():
    """Test that unknown scenario raises ValueError."""
    with pytest.raises(ValueError, match="Unknown scenario"):
        InjectionSource.from_spec("scenario:nonexistent_scenario")


def test_injection_seeded_reproducibility():
    """Test that same seed produces same results."""
    provider1 = InjectionSource.from_spec("scenario:happy_path", seed=999)
    markets1 = provider1.get_active_markets()
    
    provider2 = InjectionSource.from_spec("scenario:happy_path", seed=999)
    markets2 = provider2.get_active_markets()
    
    assert len(markets1) == len(markets2)
    for m1, m2 in zip(markets1, markets2):
        assert m1.id == m2.id
        assert m1.question == m2.question
        # Prices should match for seeded generation
        assert len(m1.outcomes) == len(m2.outcomes)
        for o1, o2 in zip(m1.outcomes, m2.outcomes):
            assert abs(o1.price - o2.price) < 1e-6


def test_file_provider_invalid_format(tmp_path):
    """Test that invalid JSON format raises ValueError."""
    fixture_path = tmp_path / "invalid.json"
    
    with open(fixture_path, 'w') as f:
        json.dump({"invalid": "format"}, f)
    
    provider = FileMarketProvider(str(fixture_path))
    
    with pytest.raises(ValueError, match="Invalid fixture format"):
        provider.get_active_markets()


def test_inline_provider_invalid_format():
    """Test that invalid inline JSON raises ValueError."""
    provider = InlineMarketProvider('{"invalid": "format"}')
    
    with pytest.raises(ValueError, match="Invalid inline JSON format"):
        provider.get_active_markets()


def test_inline_provider_malformed_json():
    """Test that malformed JSON raises JSONDecodeError."""
    provider = InlineMarketProvider('{not valid json}')
    
    with pytest.raises(json.JSONDecodeError):
        provider.get_active_markets()
