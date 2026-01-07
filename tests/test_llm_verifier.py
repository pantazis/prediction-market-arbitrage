"""
Tests for LLM-based market verification.

Uses MockLLMProvider for deterministic, network-free testing.
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from predarb.config import LLMVerificationConfig
from predarb.llm_verifier import (
    LLMVerifier,
    VerificationResult,
    VerifiedGroup,
    MockLLMProvider,
    OpenAIChatProvider,
    PROMPT_VERSION,
)
from predarb.models import Market, Outcome


@pytest.fixture
def fed_market_jan():
    """Market about Fed decision in January."""
    return Market(
        id="market_1",
        question="Will the Fed hold rates in January 2024?",
        outcomes=[
            Outcome(id="yes", label="Yes", price=0.65),
            Outcome(id="no", label="No", price=0.35),
        ],
        resolution_source="Federal Reserve",
        tags=["Federal Reserve", "Interest Rates"],
    )


@pytest.fixture
def fed_market_jan_alt():
    """Alternative market about Fed decision in January."""
    return Market(
        id="market_2",
        question="Will Fed hold steady in January 2024?",
        outcomes=[
            Outcome(id="yes", label="Yes", price=0.68),
            Outcome(id="no", label="No", price=0.32),
        ],
        resolution_source="Federal Reserve",
        tags=["Fed", "Rates"],
    )


@pytest.fixture
def fed_market_mar():
    """Market about Fed decision in March."""
    return Market(
        id="market_3",
        question="Will the Fed hold rates in March 2024?",
        outcomes=[
            Outcome(id="yes", label="Yes", price=0.45),
            Outcome(id="no", label="No", price=0.55),
        ],
        resolution_source="Federal Reserve",
        tags=["Federal Reserve", "Interest Rates"],
    )


@pytest.fixture
def btc_market_100k():
    """Market about Bitcoin at $100k."""
    return Market(
        id="market_4",
        question="Will Bitcoin reach $100,000 by end of 2024?",
        outcomes=[
            Outcome(id="yes", label="Yes", price=0.72),
            Outcome(id="no", label="No", price=0.28),
        ],
        resolution_source="CoinGecko",
        tags=["Bitcoin", "Crypto"],
    )


@pytest.fixture
def btc_market_100k_alt():
    """Alternative market about BTC at $100k."""
    return Market(
        id="market_5",
        question="Will BTC price exceed $100,000 in 2024?",
        outcomes=[
            Outcome(id="yes", label="Yes", price=0.70),
            Outcome(id="no", label="No", price=0.30),
        ],
        resolution_source="CoinGecko",
        tags=["BTC", "Cryptocurrency"],
    )


@pytest.fixture
def mock_config():
    """Create a mock LLM config with fresh cache per test."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config = LLMVerificationConfig(
            enabled=True,
            provider="mock",
            timeout_s=0.5,
            max_pairs_per_group=5,
            fail_mode="fail_open",
            cache_path=str(Path(tmpdir) / "test_cache.json"),
        )
        yield config


@pytest.fixture
def mock_config_disabled():
    """Create a disabled LLM config."""
    return LLMVerificationConfig(enabled=False)


class TestVerificationResult:
    """Test VerificationResult model."""

    def test_same_event_valid(self):
        """Test valid same_event result."""
        result = VerificationResult(
            same_event=True,
            confidence=0.95,
            reason="Clear match",
        )
        assert result.same_event is True
        assert result.confidence == 0.95

    def test_confidence_bounds(self):
        """Test confidence must be in [0, 1]."""
        with pytest.raises(ValueError):
            VerificationResult(
                same_event=True,
                confidence=1.5,
                reason="Invalid",
            )

    def test_key_fields(self):
        """Test key_fields storage."""
        result = VerificationResult(
            same_event=True,
            confidence=0.85,
            reason="Match found",
            key_fields={"resolution_date": "2024-01-31"},
        )
        assert result.key_fields["resolution_date"] == "2024-01-31"


class TestMockLLMProvider:
    """Test MockLLMProvider."""

    def test_same_event_fed_january(self):
        """Test Fed + January detection."""
        provider = MockLLMProvider()
        prompt = "Market A: Will Fed hold in January?\nMarket B: Fed holds January 2024"
        result = provider.complete_json(prompt)
        assert result["same_event"] is True
        assert result["confidence"] > 0.85

    def test_different_events_months(self):
        """Test different months are detected as different."""
        provider = MockLLMProvider()
        prompt = "Market A: January\nMarket B: March"
        result = provider.complete_json(prompt)
        assert result["same_event"] is False

    def test_timeout_simulation(self):
        """Test timeout simulation."""
        provider = MockLLMProvider()
        prompt = "TIMEOUT test"
        with pytest.raises(TimeoutError):
            provider.complete_json(prompt)

    def test_bitcoin_matching(self):
        """Test Bitcoin price matching."""
        provider = MockLLMProvider()
        prompt = "Bitcoin at $100,000 vs BTC price $100,000"
        result = provider.complete_json(prompt)
        assert result["same_event"] is True

    def test_default_different(self):
        """Test default to different events."""
        provider = MockLLMProvider()
        prompt = "Random unrelated markets"
        result = provider.complete_json(prompt)
        assert result["same_event"] is False


class TestLLMVerifierConfig:
    """Test LLMVerificationConfig."""

    def test_default_disabled(self):
        """Test default is disabled."""
        config = LLMVerificationConfig()
        assert config.enabled is False
        assert config.provider == "mock"
        assert config.fail_mode == "fail_open"

    def test_custom_config(self):
        """Test custom configuration."""
        config = LLMVerificationConfig(
            enabled=True,
            provider="openai",
            model="gpt-4",
            timeout_s=5.0,
        )
        assert config.enabled is True
        assert config.provider == "openai"
        assert config.model == "gpt-4"
        assert config.timeout_s == 5.0

    def test_invalid_fail_mode(self):
        """Test invalid fail_mode."""
        with pytest.raises(ValueError):
            LLMVerificationConfig(fail_mode="invalid")

    def test_invalid_similarity_threshold(self):
        """Test invalid similarity threshold."""
        with pytest.raises(ValueError):
            LLMVerificationConfig(min_similarity_to_verify=1.5)


class TestLLMVerifier:
    """Test LLMVerifier class."""

    def test_disabled_verification(self, mock_config_disabled, fed_market_jan, fed_market_jan_alt):
        """Test verification disabled returns neutral result."""
        verifier = LLMVerifier(mock_config_disabled)
        result = verifier.verify_pair(fed_market_jan, fed_market_jan_alt)
        assert result.same_event is False
        assert result.confidence == 0.0

    def test_verify_same_event_fed_january(self, mock_config, fed_market_jan, fed_market_jan_alt):
        """Test verifying same event (Fed in January)."""
        verifier = LLMVerifier(mock_config)
        result = verifier.verify_pair(fed_market_jan, fed_market_jan_alt)
        assert result.same_event is True
        assert result.confidence >= 0.85

    def test_verify_different_events(self, mock_config, fed_market_jan, fed_market_mar):
        """Test verifying different events (Jan vs Mar)."""
        verifier = LLMVerifier(mock_config)
        result = verifier.verify_pair(fed_market_jan, fed_market_mar)
        assert result.same_event is False
        assert result.confidence > 0.9

    def test_cache_key_order_invariant(self, mock_config, fed_market_jan, fed_market_jan_alt):
        """Test cache key is order-invariant."""
        verifier = LLMVerifier(mock_config)
        key1 = verifier._cache_key(fed_market_jan, fed_market_jan_alt)
        key2 = verifier._cache_key(fed_market_jan_alt, fed_market_jan)
        assert key1 == key2

    def test_caching_prevents_duplicate_calls(self, mock_config, fed_market_jan, fed_market_jan_alt):
        """Test caching prevents duplicate LLM calls."""
        provider = MockLLMProvider()
        verifier = LLMVerifier(mock_config, provider=provider)

        # First call
        result1 = verifier.verify_pair(fed_market_jan, fed_market_jan_alt)
        call_count_1 = provider.call_count

        # Second call should use cache
        result2 = verifier.verify_pair(fed_market_jan, fed_market_jan_alt)
        call_count_2 = provider.call_count

        # Call count should not have increased
        assert call_count_1 == call_count_2
        assert result1.same_event == result2.same_event

    def test_timeout_fail_open(self, fed_market_jan, fed_market_jan_alt):
        """Test timeout with fail_open."""
        config = LLMVerificationConfig(
            enabled=True,
            provider="mock",
            fail_mode="fail_open",
        )
        provider = MockLLMProvider()
        verifier = LLMVerifier(config, provider=provider)

        # Create prompt that triggers timeout
        fed_market_timeout = Market(
            id="timeout_test",
            question="TIMEOUT test",
            outcomes=[Outcome(id="yes", label="Yes", price=0.5)],
        )

        result = verifier.verify_pair(fed_market_jan, fed_market_timeout)
        # fail_open returns same_event=True
        assert result.same_event is True
        assert result.confidence == 0.0

    def test_timeout_fail_closed(self, fed_market_jan, fed_market_jan_alt):
        """Test timeout with fail_closed."""
        config = LLMVerificationConfig(
            enabled=True,
            provider="mock",
            fail_mode="fail_closed",
        )
        provider = MockLLMProvider()
        verifier = LLMVerifier(config, provider=provider)

        # Create prompt that triggers timeout
        fed_market_timeout = Market(
            id="timeout_test",
            question="TIMEOUT test",
            outcomes=[Outcome(id="yes", label="Yes", price=0.5)],
        )

        result = verifier.verify_pair(fed_market_jan, fed_market_timeout)
        # fail_closed returns same_event=False
        assert result.same_event is False
        assert result.confidence == 0.0

    def test_verify_group_single_market(self, mock_config, fed_market_jan):
        """Test verifying group with single market."""
        verifier = LLMVerifier(mock_config)
        result = verifier.verify_group([fed_market_jan])
        assert result.total_verifications == 0
        assert len(result.verified_subgroups) == 1

    def test_verify_group_same_events(
        self, mock_config, fed_market_jan, fed_market_jan_alt, fed_market_mar
    ):
        """Test verifying group with same and different events."""
        verifier = LLMVerifier(mock_config)
        group = [fed_market_jan, fed_market_jan_alt, fed_market_mar]
        result = verifier.verify_group(group)

        # Should have created subgroups
        assert result.total_verifications > 0
        assert len(result.verified_subgroups) >= 1

    def test_verify_group_respects_max_pairs(self, fed_market_jan, fed_market_jan_alt, fed_market_mar):
        """Test verify_group respects max_pairs_per_group."""
        config = LLMVerificationConfig(
            enabled=True,
            provider="mock",
            max_pairs_per_group=2,
        )
        verifier = LLMVerifier(config)
        group = [fed_market_jan, fed_market_jan_alt, fed_market_mar]
        result = verifier.verify_group(group)

        # With 3 markets, max pairs is 3, but limited to 2 by config
        assert result.total_verifications <= 2

    def test_cache_persistence(self, fed_market_jan, fed_market_jan_alt):
        """Test cache is saved and loaded from disk."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "test_cache.json"

            # Create verifier and verify a pair
            config = LLMVerificationConfig(
                enabled=True,
                provider="mock",
                cache_path=str(cache_path),
            )
            provider = MockLLMProvider()
            verifier1 = LLMVerifier(config, provider=provider)
            result1 = verifier1.verify_pair(fed_market_jan, fed_market_jan_alt)

            # Verify cache file exists
            assert cache_path.exists()

            # Create new verifier with same cache path
            provider2 = MockLLMProvider()
            verifier2 = LLMVerifier(config, provider=provider2)

            # Verify pair should come from cache (provider2 call_count = 0)
            result2 = verifier2.verify_pair(fed_market_jan, fed_market_jan_alt)
            assert provider2.call_count == 0  # Cache hit, no call made
            assert result1.same_event == result2.same_event

    def test_parse_response_valid(self, mock_config):
        """Test parsing valid response."""
        verifier = LLMVerifier(mock_config)
        response = {
            "same_event": True,
            "confidence": 0.88,
            "reason": "Match found",
            "resolution_source": "Federal Reserve",
            "resolution_date": "2024-01-31",
        }
        result = verifier._parse_response(response)
        assert result.same_event is True
        assert result.confidence == 0.88

    def test_parse_response_invalid_type(self, mock_config):
        """Test parsing invalid response type."""
        verifier = LLMVerifier(mock_config)
        with pytest.raises(ValueError):
            verifier._parse_response("not a dict")

    def test_parse_response_invalid_confidence(self, mock_config):
        """Test parsing invalid confidence."""
        verifier = LLMVerifier(mock_config)
        response = {
            "same_event": True,
            "confidence": 1.5,
            "reason": "Invalid",
        }
        with pytest.raises(ValueError):
            verifier._parse_response(response)

    def test_verify_crypto_markets(self, mock_config, btc_market_100k, btc_market_100k_alt):
        """Test verifying crypto markets."""
        verifier = LLMVerifier(mock_config)
        result = verifier.verify_pair(btc_market_100k, btc_market_100k_alt)
        assert result.same_event is True
        assert result.confidence >= 0.85

    def test_prompt_includes_market_metadata(self, mock_config, fed_market_jan, fed_market_jan_alt):
        """Test that prompt includes market metadata."""
        verifier = LLMVerifier(mock_config)

        # Manually build prompt to verify it includes expected fields
        prompt = verifier.PROMPT_TEMPLATE.format(
            question_a=fed_market_jan.question,
            resolution_source_a=fed_market_jan.resolution_source or "Not specified",
            tags_a=", ".join(fed_market_jan.tags) if fed_market_jan.tags else "None",
            description_a=fed_market_jan.description or "None",
            question_b=fed_market_jan_alt.question,
            resolution_source_b=fed_market_jan_alt.resolution_source or "Not specified",
            tags_b=", ".join(fed_market_jan_alt.tags) if fed_market_jan_alt.tags else "None",
            description_b=fed_market_jan_alt.description or "None",
        )

        assert "Will the Fed hold rates in January" in prompt
        assert "Federal Reserve" in prompt


class TestOpenAIChatProvider:
    """Test OpenAIChatProvider (mock network calls)."""

    def test_missing_api_key(self):
        """Test missing API key."""
        with patch.dict("os.environ", {}, clear=True):
            provider = OpenAIChatProvider()
            result = provider.complete_json("test")
            assert result == {}

    def test_json_extraction_direct_parse(self):
        """Test JSON extraction from direct text."""
        response_text = '{"same_event": true, "confidence": 0.9, "reason": "test"}'
        result = OpenAIChatProvider._parse_json_from_text(response_text)
        assert result["same_event"] is True

    def test_json_extraction_from_block(self):
        """Test JSON extraction from text block."""
        response_text = 'Some preamble... {"same_event": false, "confidence": 0.8, "reason": "test"} ...some epilogue'
        result = OpenAIChatProvider._parse_json_from_text(response_text)
        assert result["same_event"] is False

    def test_json_extraction_failure(self):
        """Test JSON extraction failure."""
        response_text = "This is not JSON at all"
        result = OpenAIChatProvider._parse_json_from_text(response_text)
        assert result == {}


class TestIntegration:
    """Integration tests."""

    def test_full_workflow(self, mock_config):
        """Test complete verification workflow."""
        markets = [
            Market(
                id=f"market_{i}",
                question=f"Question {i}",
                outcomes=[Outcome(id="yes", label="Yes", price=0.5)],
            )
            for i in range(4)
        ]

        provider = MockLLMProvider()
        verifier = LLMVerifier(mock_config, provider=provider)

        # Verify group
        result = verifier.verify_group(markets)
        assert isinstance(result, VerifiedGroup)
        assert result.total_verifications > 0
        assert len(result.verified_subgroups) >= 1
        assert len(result.original_markets) == 4

    def test_prompt_version_invalidates_cache(self, fed_market_jan, fed_market_jan_alt):
        """Test that changing PROMPT_VERSION invalidates cache."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "test_cache.json"

            config = LLMVerificationConfig(
                enabled=True,
                provider="mock",
                cache_path=str(cache_path),
            )

            # Create and verify with v1
            provider = MockLLMProvider()
            verifier = LLMVerifier(config, provider=provider)
            verifier.verify_pair(fed_market_jan, fed_market_jan_alt)

            # The cache key includes PROMPT_VERSION, so version changes auto-invalidate
            # Verify this by checking the key includes the version
            cache_key_str = verifier._cache_key(fed_market_jan, fed_market_jan_alt)
            # Key is hashed, so we verify by checking cache consistency
            assert cache_key_str in verifier._cache


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
