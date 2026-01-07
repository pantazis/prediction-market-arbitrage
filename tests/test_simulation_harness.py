"""Tests for simulation harness (notifiers, fake client, synthetic data)."""

import pytest
from datetime import datetime, timedelta

from predarb.notifiers import Notifier
from predarb.notifiers.telegram import TelegramNotifierReal, TelegramNotifierMock
from predarb.testing import FakePolymarketClient, generate_synthetic_markets
from predarb.models import Market, Opportunity, TradeAction


class TestNotifierInterface:
    """Test Notifier abstract base class."""

    def test_notifier_is_abstract(self):
        """Verify Notifier cannot be instantiated directly."""
        with pytest.raises(TypeError):
            Notifier()

    def test_notifier_requires_send_method(self):
        """Verify Notifier requires send() method implementation."""

        class BadNotifier(Notifier):
            pass

        with pytest.raises(TypeError):
            BadNotifier()


class TestTelegramNotifierMock:
    """Test TelegramNotifierMock implementation."""

    def test_mock_notifier_initialization(self):
        """Test TelegramNotifierMock initializes correctly."""
        notifier = TelegramNotifierMock()
        assert isinstance(notifier, Notifier)
        assert notifier.messages == []

    def test_mock_notifier_send(self):
        """Test send() stores messages in memory."""
        notifier = TelegramNotifierMock()
        notifier.send("Hello World")
        assert len(notifier.messages) == 1
        assert notifier.messages[0] == "Hello World"

    def test_mock_notifier_multiple_sends(self):
        """Test multiple sends accumulate."""
        notifier = TelegramNotifierMock()
        notifier.send("Message 1")
        notifier.send("Message 2")
        notifier.send("Message 3")
        assert len(notifier.messages) == 3
        assert notifier.messages == ["Message 1", "Message 2", "Message 3"]

    def test_mock_notifier_get_messages(self):
        """Test get_messages() returns copy."""
        notifier = TelegramNotifierMock()
        notifier.send("Message 1")
        messages = notifier.get_messages()
        messages.append("Injected")
        assert len(notifier.messages) == 1  # Original unchanged

    def test_mock_notifier_has_message_containing(self):
        """Test has_message_containing() search."""
        notifier = TelegramNotifierMock()
        notifier.send("Hello World")
        notifier.send("Goodbye World")
        assert notifier.has_message_containing("Hello") is True
        assert notifier.has_message_containing("Goodbye") is True
        assert notifier.has_message_containing("NotPresent") is False

    def test_mock_notifier_clear(self):
        """Test clear() empties messages."""
        notifier = TelegramNotifierMock()
        notifier.send("Message 1")
        notifier.send("Message 2")
        assert len(notifier.messages) == 2
        notifier.clear()
        assert len(notifier.messages) == 0

    def test_mock_notifier_compatibility_notify_startup(self):
        """Test compatibility method notify_startup()."""
        notifier = TelegramNotifierMock()
        notifier.notify_startup("Test startup")
        assert len(notifier.messages) == 1
        assert "Predarb started" in notifier.messages[0]
        assert "Test startup" in notifier.messages[0]

    def test_mock_notifier_compatibility_notify_error(self):
        """Test compatibility method notify_error()."""
        notifier = TelegramNotifierMock()
        notifier.notify_error("Test error", "TestContext")
        assert len(notifier.messages) == 1
        assert "Error" in notifier.messages[0]
        assert "TestContext" in notifier.messages[0]

    def test_mock_notifier_compatibility_notify_opportunity(self):
        """Test compatibility method notify_opportunity()."""
        notifier = TelegramNotifierMock()
        opp = Opportunity(
            type="PARITY",
            market_ids=["market1"],
            description="Test opportunity",
            net_edge=0.05,
            actions=[],
        )
        notifier.notify_opportunity(opp)
        assert len(notifier.messages) == 1
        assert "PARITY" in notifier.messages[0]
        assert "market1" in notifier.messages[0]

    def test_mock_notifier_compatibility_notify_trade_summary(self):
        """Test compatibility method notify_trade_summary()."""
        notifier = TelegramNotifierMock()
        notifier.notify_trade_summary(5)
        assert len(notifier.messages) == 1
        assert "5" in notifier.messages[0]
        assert "Executed" in notifier.messages[0]

    def test_mock_notifier_compatibility_notify_filtering(self):
        """Test compatibility method notify_filtering()."""
        notifier = TelegramNotifierMock()
        notifier.notify_filtering(total=100, eligible=50, ranked=30, high_quality=10)
        assert len(notifier.messages) == 1
        assert "100" in notifier.messages[0]
        assert "50" in notifier.messages[0]


class TestTelegramNotifierReal:
    """Test TelegramNotifierReal implementation."""

    def test_real_notifier_requires_credentials(self):
        """Test TelegramNotifierReal raises ValueError without credentials."""
        with pytest.raises(ValueError, match="TELEGRAM_BOT_TOKEN"):
            TelegramNotifierReal(bot_token=None, chat_id=None)

    def test_real_notifier_with_valid_credentials(self):
        """Test TelegramNotifierReal initializes with valid credentials."""
        # This won't actually send (no Telegram API mocking here)
        notifier = TelegramNotifierReal(bot_token="test_token", chat_id="test_chat")
        assert notifier.bot_token == "test_token"
        assert notifier.chat_id == "test_chat"

    def test_real_notifier_compatibility_methods(self):
        """Test TelegramNotifierReal has compatibility methods."""
        notifier = TelegramNotifierReal(bot_token="test_token", chat_id="test_chat")
        assert hasattr(notifier, "notify_startup")
        assert hasattr(notifier, "notify_error")
        assert hasattr(notifier, "notify_opportunity")
        assert hasattr(notifier, "notify_trade_summary")
        assert hasattr(notifier, "notify_filtering")


class TestSyntheticDataGeneration:
    """Test synthetic market data generation."""

    def test_generate_synthetic_markets_default(self):
        """Test market generation with default parameters."""
        markets = generate_synthetic_markets()
        assert len(markets) > 0
        assert all(isinstance(m, Market) for m in markets)

    def test_generate_synthetic_markets_custom_count(self):
        """Test market generation with custom count."""
        num_markets = 50
        markets = generate_synthetic_markets(num_markets=num_markets)
        assert len(markets) >= num_markets

    def test_generate_synthetic_markets_deterministic(self):
        """Test market generation is deterministic with same seed."""
        markets1 = generate_synthetic_markets(num_markets=20, seed=42)
        markets2 = generate_synthetic_markets(num_markets=20, seed=42)
        assert len(markets1) == len(markets2)
        assert all(m1.id == m2.id for m1, m2 in zip(markets1, markets2))
        assert all(m1.question == m2.question for m1, m2 in zip(markets1, markets2))

    def test_generate_synthetic_markets_different_seeds_differ(self):
        """Test different seeds produce different market distributions."""
        markets1 = generate_synthetic_markets(num_markets=20, seed=1)
        markets2 = generate_synthetic_markets(num_markets=20, seed=2)
        # At least some market prices should differ (due to different seeds)
        price_diffs = []
        for m1, m2 in zip(markets1, markets2):
            for o1, o2 in zip(m1.outcomes, m2.outcomes):
                price_diffs.append(abs(o1.price - o2.price))
        # With different seeds, at least some prices should differ significantly
        assert any(d > 0.01 for d in price_diffs)  # At least 1% price difference somewhere

    def test_generate_synthetic_markets_have_outcomes(self):
        """Test all generated markets have outcomes."""
        markets = generate_synthetic_markets(num_markets=10)
        assert all(len(m.outcomes) > 0 for m in markets)

    def test_generate_synthetic_markets_have_valid_prices(self):
        """Test all outcomes have valid prices."""
        markets = generate_synthetic_markets(num_markets=10)
        for market in markets:
            for outcome in market.outcomes:
                assert 0 <= outcome.price <= 1

    def test_generate_synthetic_markets_includes_opportunity_types(self):
        """Test that generated markets include various opportunity types."""
        markets = generate_synthetic_markets(num_markets=40, seed=123)

        # Check for markets with various tags
        tags_set = set()
        for market in markets:
            for tag in market.tags:
                tags_set.add(tag)

        expected_tags = {"yes/no", "ladder", "duplicate", "multioutcome", "timelag", "illiquid"}
        assert len(tags_set.intersection(expected_tags)) >= 3  # At least 3 types present

    def test_generate_synthetic_markets_includes_rejectable_markets(self):
        """Test that generated markets include rejection cases."""
        markets = generate_synthetic_markets(num_markets=40, seed=123)

        # Look for illiquid or missing resolution source
        rejectable = [
            m for m in markets
            if (m.liquidity and m.liquidity < 500) or (m.resolution_source is None)
        ]
        assert len(rejectable) > 0  # Some should be rejectable


class TestFakePolymarketClient:
    """Test FakePolymarketClient implementation."""

    def test_fake_client_initialization(self):
        """Test FakePolymarketClient initializes correctly."""
        client = FakePolymarketClient(num_markets=20, days=2, seed=42)
        assert client.num_markets == 20
        assert client.days == 2
        assert client.seed == 42

    def test_fake_client_fetch_markets_returns_markets(self):
        """Test fetch_markets() returns Market objects."""
        client = FakePolymarketClient(num_markets=20)
        markets = client.fetch_markets()
        assert len(markets) > 0
        assert all(isinstance(m, Market) for m in markets)

    def test_fake_client_get_active_markets_alias(self):
        """Test get_active_markets() is alias for fetch_markets()."""
        client = FakePolymarketClient(num_markets=20)
        markets1 = client.fetch_markets()
        client.reset()
        markets2 = client.get_active_markets()
        assert len(markets1) == len(markets2)

    def test_fake_client_minute_advancement(self):
        """Test market evolution over minutes."""
        client = FakePolymarketClient(num_markets=10, days=2, seed=42)
        markets1 = client.fetch_markets()  # Minute 0
        markets2 = client.fetch_markets()  # Minute 1

        # Markets should evolve (prices change slightly)
        assert len(markets1) == len(markets2)
        # Some prices should differ between minutes
        price_diffs = []
        for m1, m2 in zip(markets1, markets2):
            for o1, o2 in zip(m1.outcomes, m2.outcomes):
                price_diffs.append(abs(o1.price - o2.price))
        assert any(d > 0 for d in price_diffs)  # At least some price changes

    def test_fake_client_reset(self):
        """Test reset() returns to start."""
        client = FakePolymarketClient(num_markets=10)
        client.fetch_markets()
        client.fetch_markets()
        assert client.current_minute == 2
        client.reset()
        assert client.current_minute == 0

    def test_fake_client_deterministic(self):
        """Test two clients with same seed produce same sequence."""
        client1 = FakePolymarketClient(num_markets=10, seed=123)
        client2 = FakePolymarketClient(num_markets=10, seed=123)

        for _ in range(10):
            markets1 = client1.fetch_markets()
            markets2 = client2.fetch_markets()
            assert len(markets1) == len(markets2)
            assert all(m1.id == m2.id for m1, m2 in zip(markets1, markets2))


class TestSimulationIntegration:
    """Integration tests for full simulation pipeline."""

    def test_engine_with_fake_client_and_mock_notifier(self, tmp_path):
        """Test Engine runs successfully with FakePolymarketClient and mock notifier."""
        from predarb.config import AppConfig, BrokerConfig, EngineConfig
        from predarb.engine import Engine

        # Setup
        config = AppConfig()
        config.engine.report_path = str(tmp_path / "trades.csv")
        config.engine.iterations = 5
        config.engine.refresh_seconds = 0  # No sleep for tests

        client = FakePolymarketClient(num_markets=20, seed=42)
        notifier = TelegramNotifierMock()

        # Run
        engine = Engine(config, client, notifier)
        engine.run()

        # Verify
        assert len(notifier.messages) > 0  # Notifier was called
        assert (tmp_path / "trades.csv").exists()  # Report was written

    def test_mock_notifier_captures_messages(self, tmp_path):
        """Test mock notifier captures all notification messages."""
        from predarb.config import AppConfig
        from predarb.engine import Engine

        config = AppConfig()
        config.engine.report_path = str(tmp_path / "trades.csv")
        config.engine.iterations = 2
        config.engine.refresh_seconds = 0

        client = FakePolymarketClient(num_markets=15, seed=42)
        notifier = TelegramNotifierMock()

        engine = Engine(config, client, notifier)
        engine.run()

        # Check that notifications were sent
        messages = notifier.get_messages()
        assert len(messages) > 0
        # Should have filtering, startup, or other messages
        assert any("market" in msg.lower() or "iteration" in msg.lower() for msg in messages)


# --- New hedge/flatten simulation tests ---

def _ladder_pair(markets_liq=10_000.0):
    from predarb.models import Market, Outcome
    m1 = Market(
        id="m1",
        question="Asset > 10",
        outcomes=[Outcome(id="m1_yes", label="Yes", price=0.30), Outcome(id="m1_no", label="No", price=0.70)],
        liquidity=markets_liq,
        comparator=">",
        threshold=10.0,
    )
    m2 = Market(
        id="m2",
        question="Asset > 20",
        outcomes=[Outcome(id="m2_yes", label="Yes", price=0.60), Outcome(id="m2_no", label="No", price=0.40)],
        liquidity=markets_liq,
        comparator=">",
        threshold=20.0,
    )
    return [m1, m2]


class MiniClient:
    def __init__(self, markets):
        self._markets = markets
    def fetch_markets(self):
        return self._markets
    def get_active_markets(self):
        return self._markets


def test_hedge_on_one_leg_failure(tmp_path):
    """When one leg fails (e.g., SELL without holdings), engine should hedge and return to zero exposure."""
    from predarb.config import AppConfig
    from predarb.engine import Engine
    from predarb.notifiers.telegram import TelegramNotifierMock

    config = AppConfig()
    config.engine.report_path = str(tmp_path / "trades.csv")
    config.engine.iterations = 1
    config.engine.refresh_seconds = 0
    client = MiniClient(_ladder_pair(markets_liq=10_000.0))
    notifier = TelegramNotifierMock()

    engine = Engine(config, client, notifier)
    engine.run_once()

    # After hedging, all positions must be zero
    assert sum(engine.broker.positions.values()) == 0.0

    # Exec trace contains hedge and freeze_state
    import json
    from pathlib import Path
    log_path = Path("reports") / "opportunity_logs.jsonl"
    assert log_path.exists()
    last = None
    with open(log_path, "r", encoding="utf-8") as f:
        for line in f:
            last = line.strip()
    rec = json.loads(last)
    assert rec.get("freeze_state") is True
    assert rec.get("hedge", {}).get("performed") is True
    assert rec.get("status") in ("partial", "cancelled", "success")


def test_abort_and_flatten_when_sell_liquidity_limits(tmp_path):
    """Low liquidity should force partial closes; flatten_all ensures zero exposure and failure_flags mark residual_exposure."""
    from predarb.config import AppConfig
    from predarb.engine import Engine
    from predarb.notifiers.telegram import TelegramNotifierMock

    config = AppConfig()
    config.engine.report_path = str(tmp_path / "trades.csv")
    config.engine.iterations = 1
    config.engine.refresh_seconds = 0

    # Make liquidity extremely low to force partials
    client = MiniClient(_ladder_pair(markets_liq=1.0))
    notifier = TelegramNotifierMock()

    engine = Engine(config, client, notifier)
    engine.run_once()

    # After flatten_all, exposure must be zero
    assert sum(engine.broker.positions.values()) == 0.0

    import json
    from pathlib import Path
    log_path = Path("reports") / "opportunity_logs.jsonl"
    with open(log_path, "r", encoding="utf-8") as f:
        last = None
        for line in f:
            last = line.strip()
    rec = json.loads(last)
    assert "residual_exposure" in rec.get("failure_flags", [])
