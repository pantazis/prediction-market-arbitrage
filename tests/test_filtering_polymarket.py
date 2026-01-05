"""
Unit tests for market filtering module using Polymarket models.

Tests the filtering and prioritization logic with actual predarb.models.Market
and predarb.models.Outcome objects (as returned by PolymarketClient).
"""

import pytest
from datetime import datetime, timedelta

from src.predarb.filtering import (
    FilterSettings,
    MarketFilter,
    filter_markets,
    rank_markets,
    explain_rejection,
)
from src.predarb.models import Market, Outcome


@pytest.fixture
def settings():
    """Default filter settings."""
    return FilterSettings()


# ========== SPREAD FILTER TESTS ==========


class TestSpreadFilter:
    """Tests for spread constraint validation."""
    
    def test_spread_passes_tight_spread(self, settings):
        """Market with tight spread should pass."""
        market = Market(
            id="tight_spread",
            question="Will BTC > $50k?",
            outcomes=[
                Outcome(id="yes", label="YES", price=0.495),
                Outcome(id="no", label="NO", price=0.505),  # Very tight spread
            ],
            end_date=datetime.utcnow() + timedelta(days=30),
            liquidity=50_000,
            volume=50_000,
            resolution_source="Coinbase",
        )
        engine = MarketFilter(settings)
        assert engine._passes_spread_filter(market)
    
    def test_spread_fails_wide_spread(self, settings):
        """Market with wide spread should fail."""
        settings.max_spread_pct = 0.03
        market = Market(
            id="wide_spread",
            question="Will BTC > $100k?",
            outcomes=[
                Outcome(id="yes", label="YES", price=0.30),
                Outcome(id="no", label="NO", price=0.70),
            ],
            end_date=datetime.utcnow() + timedelta(days=30),
            liquidity=50_000,
            volume=50_000,
            resolution_source="Coinbase",
        )
        engine = MarketFilter(settings)
        assert not engine._passes_spread_filter(market)
    
    def test_spread_fails_insufficient_outcomes(self, settings):
        """Market with < 2 outcomes should fail."""
        market = Market(
            id="single_outcome",
            question="Will BTC exist?",
            outcomes=[
                Outcome(id="yes", label="YES", price=0.99),
            ],
            end_date=datetime.utcnow() + timedelta(days=30),
            liquidity=50_000,
            volume=50_000,
            resolution_source="Coinbase",
        )
        engine = MarketFilter(settings)
        assert not engine._passes_spread_filter(market)


# ========== VOLUME & LIQUIDITY FILTER TESTS ==========


class TestVolumeAndLiquidityFilters:
    """Tests for volume and liquidity constraints."""
    
    def test_volume_passes_above_minimum(self, settings):
        """Market with volume > min should pass."""
        market = Market(
            id="good_volume",
            question="Will ETH > $3k?",
            outcomes=[
                Outcome(id="yes", label="YES", price=0.58),
                Outcome(id="no", label="NO", price=0.42),
            ],
            end_date=datetime.utcnow() + timedelta(days=30),
            liquidity=50_000,
            volume=15_000,  # > default 10k
            resolution_source="Coinbase",
        )
        engine = MarketFilter(settings)
        assert engine._passes_volume_filter(market)
    
    def test_volume_fails_below_minimum(self, settings):
        """Market with volume < min should fail."""
        market = Market(
            id="low_volume",
            question="Will ETH > $5k?",
            outcomes=[
                Outcome(id="yes", label="YES", price=0.30),
                Outcome(id="no", label="NO", price=0.70),
            ],
            end_date=datetime.utcnow() + timedelta(days=30),
            liquidity=50_000,
            volume=5_000,  # < default 10k
            resolution_source="Coinbase",
        )
        engine = MarketFilter(settings)
        assert not engine._passes_volume_filter(market)
    
    def test_liquidity_passes_above_minimum(self, settings):
        """Market with liquidity > min should pass."""
        market = Market(
            id="good_liq",
            question="Will TSLA > $300?",
            outcomes=[
                Outcome(id="yes", label="YES", price=0.55),
                Outcome(id="no", label="NO", price=0.45),
            ],
            end_date=datetime.utcnow() + timedelta(days=30),
            liquidity=30_000,  # > default 25k
            volume=50_000,
            resolution_source="Yahoo Finance",
        )
        engine = MarketFilter(settings)
        assert engine._passes_liquidity_filter(market)
    
    def test_liquidity_fails_below_minimum(self, settings):
        """Market with liquidity < min should fail."""
        market = Market(
            id="low_liq",
            question="Will SpaceX launch in 2026?",
            outcomes=[
                Outcome(id="yes", label="YES", price=0.15),
                Outcome(id="no", label="NO", price=0.85),
            ],
            end_date=datetime.utcnow() + timedelta(days=30),
            liquidity=10_000,  # < default 25k
            volume=50_000,
            resolution_source="SpaceX",
        )
        engine = MarketFilter(settings)
        assert not engine._passes_liquidity_filter(market)


# ========== EXPIRY FILTER TESTS ==========


class TestExpiryFilter:
    """Tests for market expiration constraints."""
    
    def test_expiry_passes_far_future(self, settings):
        """Market expiring > min_days should pass."""
        settings.min_days_to_expiry = 7
        market = Market(
            id="far_future",
            question="Will BTC > $100k by EOY?",
            outcomes=[
                Outcome(id="yes", label="YES", price=0.40),
                Outcome(id="no", label="NO", price=0.60),
            ],
            end_date=datetime.utcnow() + timedelta(days=30),
            liquidity=50_000,
            volume=50_000,
            resolution_source="Coinbase",
        )
        engine = MarketFilter(settings)
        assert engine._passes_expiry_filter(market)
    
    def test_expiry_fails_soon(self, settings):
        """Market expiring < min_days should fail."""
        settings.min_days_to_expiry = 7
        market = Market(
            id="expiring_soon",
            question="Will BTC be above $60k tomorrow?",
            outcomes=[
                Outcome(id="yes", label="YES", price=0.68),
                Outcome(id="no", label="NO", price=0.32),
            ],
            end_date=datetime.utcnow() + timedelta(days=2),
            liquidity=50_000,
            volume=50_000,
            resolution_source="Coinbase",
        )
        engine = MarketFilter(settings)
        assert not engine._passes_expiry_filter(market)
    
    def test_expiry_missing_allowed(self, settings):
        """Market with missing end_date passes if allow_missing_end_time=True."""
        settings.allow_missing_end_time = True
        market = Market(
            id="no_expiry",
            question="Will perpetual market exist?",
            outcomes=[
                Outcome(id="yes", label="YES", price=0.90),
                Outcome(id="no", label="NO", price=0.10),
            ],
            end_date=None,
            liquidity=50_000,
            volume=50_000,
            resolution_source="Custom",
        )
        engine = MarketFilter(settings)
        assert engine._passes_expiry_filter(market)


# ========== RESOLUTION SOURCE TESTS ==========


class TestResolutionFilter:
    """Tests for resolution source checks."""
    
    def test_resolution_passes_with_source(self, settings):
        """Market with explicit resolution source passes."""
        market = Market(
            id="clear_resolution",
            question="Will Fed raise rates?",
            outcomes=[
                Outcome(id="yes", label="YES", price=0.45),
                Outcome(id="no", label="NO", price=0.55),
            ],
            end_date=datetime.utcnow() + timedelta(days=90),
            liquidity=50_000,
            volume=50_000,
            resolution_source="Federal Reserve",
        )
        engine = MarketFilter(settings)
        assert engine._passes_resolution_filter(market)
    
    def test_resolution_fails_missing_source(self, settings):
        """Market without resolution source fails if required."""
        settings.require_resolution_source = True
        market = Market(
            id="no_source",
            question="Will something happen?",
            outcomes=[
                Outcome(id="yes", label="YES", price=0.50),
                Outcome(id="no", label="NO", price=0.50),
            ],
            end_date=datetime.utcnow() + timedelta(days=90),
            liquidity=50_000,
            volume=50_000,
            resolution_source=None,
        )
        engine = MarketFilter(settings)
        assert not engine._passes_resolution_filter(market)
    
    def test_resolution_optional(self, settings):
        """Market without source passes if resolution not required."""
        settings.require_resolution_source = False
        market = Market(
            id="optional_source",
            question="Will community decide?",
            outcomes=[
                Outcome(id="yes", label="YES", price=0.50),
                Outcome(id="no", label="NO", price=0.50),
            ],
            end_date=datetime.utcnow() + timedelta(days=90),
            liquidity=50_000,
            volume=50_000,
            resolution_source=None,
        )
        engine = MarketFilter(settings)
        assert engine._passes_resolution_filter(market)


# ========== RISK-BASED FILTERING TESTS ==========


class TestRiskBasedFiltering:
    """Tests for position size and liquidity constraints."""
    
    def test_risk_passes_sufficient_liquidity(self, settings):
        """Market with liquidity >= 20x order size passes."""
        market = Market(
            id="good_size",
            question="Will large order fit?",
            outcomes=[
                Outcome(id="yes", label="YES", price=0.60),
                Outcome(id="no", label="NO", price=0.40),
            ],
            end_date=datetime.utcnow() + timedelta(days=30),
            liquidity=500_000,  # 500k >= 20 * 20k
            volume=100_000,
            resolution_source="Test",
        )
        target_order_size = 20_000
        engine = MarketFilter(settings)
        assert engine._passes_risk_filters(market, target_order_size)
    
    def test_risk_fails_insufficient_liquidity(self, settings):
        """Market with liquidity < 20x order size fails."""
        market = Market(
            id="bad_size",
            question="Will large order fit?",
            outcomes=[
                Outcome(id="yes", label="YES", price=0.60),
                Outcome(id="no", label="NO", price=0.40),
            ],
            end_date=datetime.utcnow() + timedelta(days=30),
            liquidity=300_000,  # 300k < 20 * 20k
            volume=100_000,
            resolution_source="Test",
        )
        target_order_size = 20_000
        engine = MarketFilter(settings)
        assert not engine._passes_risk_filters(market, target_order_size)


# ========== SCORING TESTS ==========


class TestScoringAndRanking:
    """Tests for liquidity quality scoring and ranking."""
    
    def test_score_in_valid_range(self, settings):
        """All scores should be in range [0, 100]."""
        market = Market(
            id="test_score",
            question="Test market?",
            outcomes=[
                Outcome(id="yes", label="YES", price=0.60),
                Outcome(id="no", label="NO", price=0.40),
            ],
            end_date=datetime.utcnow() + timedelta(days=30),
            liquidity=100_000,
            volume=100_000,
            resolution_source="Test",
        )
        engine = MarketFilter(settings)
        score = engine._compute_score(market)
        assert 0 <= score <= 100, f"Score {score} not in [0, 100]"
    
    def test_spread_affects_score(self, settings):
        """Tighter spread should produce higher score."""
        market_tight = Market(
            id="tight",
            question="Test?",
            outcomes=[
                Outcome(id="yes", label="YES", price=0.50),
                Outcome(id="no", label="NO", price=0.50),  # 0% spread
            ],
            end_date=datetime.utcnow() + timedelta(days=30),
            liquidity=100_000,
            volume=100_000,
            resolution_source="Test",
        )
        
        market_wide = Market(
            id="wide",
            question="Test?",
            outcomes=[
                Outcome(id="yes", label="YES", price=0.20),
                Outcome(id="no", label="NO", price=0.80),  # 60% spread
            ],
            end_date=datetime.utcnow() + timedelta(days=30),
            liquidity=100_000,
            volume=100_000,
            resolution_source="Test",
        )
        
        engine = MarketFilter(settings)
        score_tight = engine._compute_score(market_tight)
        score_wide = engine._compute_score(market_wide)
        
        assert score_tight > score_wide, "Tight spread should score higher"
    
    def test_volume_affects_score(self, settings):
        """Higher volume should produce higher score."""
        market_low = Market(
            id="low_vol",
            question="Test?",
            outcomes=[
                Outcome(id="yes", label="YES", price=0.50),
                Outcome(id="no", label="NO", price=0.50),
            ],
            end_date=datetime.utcnow() + timedelta(days=30),
            liquidity=100_000,
            volume=11_000,  # Just above minimum
            resolution_source="Test",
        )
        
        market_high = Market(
            id="high_vol",
            question="Test?",
            outcomes=[
                Outcome(id="yes", label="YES", price=0.50),
                Outcome(id="no", label="NO", price=0.50),
            ],
            end_date=datetime.utcnow() + timedelta(days=30),
            liquidity=100_000,
            volume=500_000,  # Much higher
            resolution_source="Test",
        )
        
        engine = MarketFilter(settings)
        score_low = engine._compute_score(market_low)
        score_high = engine._compute_score(market_high)
        
        assert score_high > score_low, "Higher volume should score higher"
    
    def test_ranking_deterministic(self, settings):
        """Ranking order should be deterministic."""
        market1 = Market(
            id="m1",
            question="Test 1?",
            outcomes=[
                Outcome(id="yes", label="YES", price=0.50),
                Outcome(id="no", label="NO", price=0.50),
            ],
            end_date=datetime.utcnow() + timedelta(days=30),
            liquidity=100_000,
            volume=100_000,
            resolution_source="Test",
        )
        
        market2 = Market(
            id="m2",
            question="Test 2?",
            outcomes=[
                Outcome(id="yes", label="YES", price=0.50),
                Outcome(id="no", label="NO", price=0.50),
            ],
            end_date=datetime.utcnow() + timedelta(days=30),
            liquidity=100_000,
            volume=100_000,
            resolution_source="Test",
        )
        
        engine = MarketFilter(settings)
        ranked1 = engine.rank_markets([market1, market2])
        ranked2 = engine.rank_markets([market2, market1])
        
        ids1 = [m.id for m, _ in ranked1]
        ids2 = [m.id for m, _ in ranked2]
        
        assert ids1 == ids2, "Ranking should be deterministic"


# ========== INTEGRATION TESTS ==========


class TestIntegration:
    """Integration tests for full filtering pipeline."""
    
    def test_filter_and_rank_sample_markets(self, settings):
        """Test filtering and ranking with sample markets."""
        markets = [
            # Good market - liquid, tight spread, good volume
            Market(
                id="good_1",
                question="Will BTC > $60k?",
                outcomes=[
                    Outcome(id="yes", label="YES", price=0.50),
                    Outcome(id="no", label="NO", price=0.50),  # Perfect balance
                ],
                end_date=datetime.utcnow() + timedelta(days=30),
                liquidity=150_000,
                volume=400_000,
                resolution_source="Coinbase",
            ),
            # Poor market - low volume
            Market(
                id="poor_1",
                question="Will XYZ happen?",
                outcomes=[
                    Outcome(id="yes", label="YES", price=0.30),
                    Outcome(id="no", label="NO", price=0.70),
                ],
                end_date=datetime.utcnow() + timedelta(days=30),
                liquidity=50_000,
                volume=5_000,  # Below minimum
                resolution_source="Unknown",
            ),
            # Expiring soon - should still pass hard filters but score lower
            Market(
                id="expiring",
                question="Will ABC happen tomorrow?",
                outcomes=[
                    Outcome(id="yes", label="YES", price=0.50),
                    Outcome(id="no", label="NO", price=0.50),
                ],
                end_date=datetime.utcnow() + timedelta(days=8),  # Just above 7-day minimum
                liquidity=100_000,
                volume=50_000,
                resolution_source="Test",
            ),
        ]
        
        filtered = filter_markets(markets, settings)
        
        # good_1 and expiring should pass, poor_1 should fail (low volume)
        filtered_ids = [m.id for m in filtered]
        assert "good_1" in filtered_ids
        assert "poor_1" not in filtered_ids
        assert "expiring" in filtered_ids  # Just above threshold
    
    def test_explain_rejection(self, settings):
        """Test rejection explanation."""
        market = Market(
            id="bad",
            question="Test?",
            outcomes=[
                Outcome(id="yes", label="YES", price=0.30),
                Outcome(id="no", label="NO", price=0.70),
            ],
            end_date=datetime.utcnow() + timedelta(days=30),
            liquidity=5_000,  # Too low
            volume=5_000,     # Too low
            resolution_source=None,  # Missing
        )
        
        reasons = explain_rejection(market, settings)
        assert len(reasons) > 0
        # Should have multiple reasons
        assert any("liquidity" in r.lower() for r in reasons)
        assert any("volume" in r.lower() for r in reasons)


# ========== EDGE CASE TESTS ==========


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""
    
    def test_empty_market_list(self, settings):
        """Filtering empty list should return empty list."""
        engine = MarketFilter(settings)
        result = engine.filter_markets([])
        assert result == []
    
    def test_multi_outcome_market(self, settings):
        """Test with multi-outcome market (e.g., who will win?)."""
        market = Market(
            id="multi",
            question="Who will win?",
            outcomes=[
                Outcome(id="a", label="Option A", price=0.33),
                Outcome(id="b", label="Option B", price=0.33),
                Outcome(id="c", label="Option C", price=0.34),
            ],
            end_date=datetime.utcnow() + timedelta(days=30),
            liquidity=50_000,
            volume=50_000,
            resolution_source="Voting",
        )
        engine = MarketFilter(settings)
        # Should pass - 3 outcomes, balanced prices
        assert engine._passes_spread_filter(market)
    
    def test_market_near_expiry_penalized_in_score(self, settings):
        """Market near expiry should have reduced score."""
        market_soon = Market(
            id="soon",
            question="Test?",
            outcomes=[
                Outcome(id="yes", label="YES", price=0.50),
                Outcome(id="no", label="NO", price=0.50),
            ],
            end_date=datetime.utcnow() + timedelta(days=15),  # < 30 days
            liquidity=100_000,
            volume=100_000,
            resolution_source="Test",
        )
        
        market_far = Market(
            id="far",
            question="Test?",
            outcomes=[
                Outcome(id="yes", label="YES", price=0.50),
                Outcome(id="no", label="NO", price=0.50),
            ],
            end_date=datetime.utcnow() + timedelta(days=90),
            liquidity=100_000,
            volume=100_000,
            resolution_source="Test",
        )
        
        engine = MarketFilter(settings)
        score_soon = engine._compute_score(market_soon)
        score_far = engine._compute_score(market_far)
        
        assert score_far > score_soon, "Market farther in future should score higher"
