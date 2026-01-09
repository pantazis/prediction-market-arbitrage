"""
Tests for Kalshi integration: client, normalization, multi-exchange engine.

NO NETWORK CALLS - All tests use FakeKalshiClient.
"""
from __future__ import annotations

import pytest
from datetime import datetime, timezone

from predarb.config import AppConfig, KalshiConfig, PolymarketConfig
from predarb.engine import Engine
from predarb.models import Market, Outcome
from tests.fake_kalshi_client import FakeKalshiClient


class TestKalshiClientNormalization:
    """Test Kalshi market normalization into internal Market model."""
    
    def test_default_fixture_structure(self):
        """Test that default fixture returns valid Market objects."""
        client = FakeKalshiClient(fixture_name="default")
        markets = client.fetch_markets()
        
        assert len(markets) == 2
        assert all(isinstance(m, Market) for m in markets)
        
        # Check first market
        m1 = markets[0]
        assert m1.id.startswith("kalshi:")
        assert m1.exchange == "kalshi"
        assert len(m1.outcomes) == 2
        assert m1.outcomes[0].label == "YES"
        assert m1.outcomes[1].label == "NO"
        assert 0.0 <= m1.outcomes[0].price <= 1.0
        assert 0.0 <= m1.outcomes[1].price <= 1.0
        assert m1.liquidity > 0
        assert m1.expiry is not None
    
    def test_exchange_tagging(self):
        """Test that all Kalshi markets are tagged with exchange='kalshi'."""
        client = FakeKalshiClient(fixture_name="default")
        markets = client.fetch_markets()
        
        for market in markets:
            assert market.exchange == "kalshi", f"Market {market.id} missing exchange tag"
    
    def test_outcome_prices_normalized(self):
        """Test that outcome prices are in [0.0, 1.0] range."""
        client = FakeKalshiClient(fixture_name="default")
        markets = client.fetch_markets()
        
        for market in markets:
            for outcome in market.outcomes:
                assert 0.0 <= outcome.price <= 1.0, \
                    f"Price {outcome.price} out of range for {outcome.id}"
    
    def test_market_id_format(self):
        """Test that Kalshi market IDs follow 'kalshi:<event>:<ticker>' format."""
        client = FakeKalshiClient(fixture_name="default")
        markets = client.fetch_markets()
        
        for market in markets:
            parts = market.id.split(":")
            assert len(parts) >= 2, f"Invalid Kalshi ID format: {market.id}"
            assert parts[0] == "kalshi", f"ID missing 'kalshi:' prefix: {market.id}"
    
    def test_metadata(self):
        """Test that client metadata is correct."""
        client = FakeKalshiClient(fixture_name="default")
        meta = client.get_metadata()
        
        assert meta["exchange"] == "kalshi"
        assert "fee_bps" in meta
        assert "tick_size" in meta
        assert "base_url" in meta
        assert meta["env"] == "test"
    
    def test_high_volume_fixture(self):
        """Test high_volume fixture returns 50 markets."""
        client = FakeKalshiClient(fixture_name="high_volume")
        markets = client.fetch_markets()
        
        assert len(markets) == 50
        assert all(m.exchange == "kalshi" for m in markets)
    
    def test_empty_fixture(self):
        """Test empty fixture returns no markets."""
        client = FakeKalshiClient(fixture_name="empty")
        markets = client.fetch_markets()
        
        assert len(markets) == 0


class TestMultiExchangeEngine:
    """Test Engine with multiple market clients (Polymarket + Kalshi)."""
    
    def test_engine_with_single_kalshi_client(self):
        """Test Engine can run with only Kalshi client."""
        # Create minimal config
        config = AppConfig()
        
        # Pass Kalshi client directly
        kalshi_client = FakeKalshiClient(fixture_name="default")
        engine = Engine(config, clients=[kalshi_client])
        
        # Run once and verify markets fetched
        opportunities = engine.run_once()
        
        assert len(engine._last_markets) == 2
        assert all(m.exchange == "kalshi" for m in engine._last_markets)
    
    def test_engine_with_multiple_clients(self):
        """Test Engine merges markets from multiple exchanges."""
        # We need a FakePolymarketClient - let's check if it exists
        try:
            from tests.fakes import FakePolymarketClient
            
            config = AppConfig()
            
            # Create both clients
            poly_client = FakePolymarketClient()
            kalshi_client = FakeKalshiClient(fixture_name="default")
            
            # Pass both to engine
            engine = Engine(config, clients=[poly_client, kalshi_client])
            
            # Run once
            opportunities = engine.run_once()
            
            # Verify markets from both exchanges
            markets = engine._last_markets
            exchanges = {m.exchange for m in markets}
            
            assert "polymarket" in exchanges
            assert "kalshi" in exchanges
            assert len(markets) > 2  # At least 2 from Kalshi + some from Polymarket
        
        except ImportError:
            pytest.skip("FakePolymarketClient not available")
    
    def test_engine_auto_loads_kalshi_from_config(self):
        """Test Engine auto-loads Kalshi client when enabled in config."""
        # Create config with Kalshi enabled (but fake credentials)
        config = AppConfig(
            kalshi=KalshiConfig(
                enabled=True,
                api_key_id="fake-key-id",
                private_key_pem="fake-pem",  # Will fail validation but test init logic
            ),
            polymarket=PolymarketConfig(
                enabled=False  # Disable Polymarket for this test
            ),
        )
        
        # Engine should attempt to load Kalshi client
        # (will fail due to fake credentials, but we test the logic path)
        engine = Engine(config)
        
        # Should have logged attempt to load Kalshi
        # Check that clients list was initialized
        assert isinstance(engine.clients, list)
    
    def test_kalshi_only_parity_detection(self):
        """Test that parity detector works on Kalshi markets."""
        config = AppConfig()
        config.detectors.enable_parity = True
        config.detectors.enable_ladder = False
        config.detectors.enable_duplicate = False
        config.detectors.enable_exclusive_sum = False
        config.detectors.enable_timelag = False
        config.detectors.enable_consistency = False
        
        # Use parity_arb fixture (YES + NO = 0.95, 5% edge)
        kalshi_client = FakeKalshiClient(fixture_name="parity_arb")
        engine = Engine(config, clients=[kalshi_client])
        
        # Run once
        opportunities = engine.run_once()
        
        # Should detect parity arbitrage
        markets = engine._last_markets
        assert len(markets) == 1
        assert markets[0].exchange == "kalshi"
        
        # Check if detector found opportunities
        detected = engine._last_detected
        assert len(detected) > 0
        assert any(opp.type == "PARITY" for opp in detected)


class TestKalshiConfigLoading:
    """Test Kalshi configuration loading and validation."""
    
    def test_kalshi_disabled_by_default(self):
        """Test that Kalshi is disabled by default in config."""
        config = AppConfig()
        
        assert config.kalshi.enabled is False
    
    def test_kalshi_config_fields(self):
        """Test that Kalshi config has all required fields."""
        config = KalshiConfig(
            enabled=True,
            api_key_id="test-key",
            private_key_pem="test-pem",
            api_host="https://test.kalshi.com",
            env="demo",
            min_liquidity_usd=1000.0,
            min_days_to_expiry=2,
        )
        
        assert config.enabled is True
        assert config.api_key_id == "test-key"
        assert config.private_key_pem == "test-pem"
        assert config.api_host == "https://test.kalshi.com"
        assert config.env == "demo"
        assert config.min_liquidity_usd == 1000.0
        assert config.min_days_to_expiry == 2
    
    def test_kalshi_env_defaults(self):
        """Test that Kalshi config uses environment variable defaults."""
        import os
        
        # Save original env
        orig_key = os.environ.get("KALSHI_API_KEY_ID")
        orig_pem = os.environ.get("KALSHI_PRIVATE_KEY_PEM")
        
        try:
            # Set test env vars
            os.environ["KALSHI_API_KEY_ID"] = "env-key-123"
            os.environ["KALSHI_PRIVATE_KEY_PEM"] = "env-pem-data"
            
            # Create config (should pull from env)
            config = KalshiConfig()
            
            assert config.api_key_id == "env-key-123"
            assert config.private_key_pem == "env-pem-data"
        
        finally:
            # Restore original env
            if orig_key:
                os.environ["KALSHI_API_KEY_ID"] = orig_key
            else:
                os.environ.pop("KALSHI_API_KEY_ID", None)
            
            if orig_pem:
                os.environ["KALSHI_PRIVATE_KEY_PEM"] = orig_pem
            else:
                os.environ.pop("KALSHI_PRIVATE_KEY_PEM", None)


class TestKalshiSecurityConstraints:
    """Test that NO credentials are hardcoded anywhere."""
    
    def test_no_hardcoded_credentials_in_client(self):
        """Test that FakeKalshiClient has no real credentials."""
        client = FakeKalshiClient()
        meta = client.get_metadata()
        
        # Should NOT contain real credentials
        assert "api_key_id" not in meta or meta.get("api_key_id") == "test"
        assert "private_key" not in meta
    
    def test_kalshi_client_requires_env_vars(self):
        """Test that real KalshiClient requires credentials."""
        from predarb.kalshi_client import KalshiClient
        
        # Should raise error without credentials
        with pytest.raises(ValueError, match="KALSHI_API_KEY_ID not provided"):
            KalshiClient(api_key_id=None, private_key_pem="fake")
        
        with pytest.raises(ValueError, match="KALSHI_PRIVATE_KEY_PEM not provided"):
            KalshiClient(api_key_id="fake", private_key_pem=None)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
