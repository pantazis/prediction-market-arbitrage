"""
Comprehensive pytest tests for market filtering and prioritization module.

Tests cover:
- Spread filtering (tight, wide, missing prices)
- Volume and liquidity constraints
- Expiry filtering
- Resolution quality checks
- Risk-based position sizing
- Liquidity-based scoring and ranking
- Deterministic sorting and scoring stability

No network calls; all data from fixtures.
"""

import pytest
import json
from datetime import datetime, timedelta
from pathlib import Path

from src.predarb.filtering import (
    Market,
    FilterSettings,
    MarketFilter,
    filter_markets,
    rank_markets,
    explain_rejection,
    RejectionReason,
)


@pytest.fixture
def settings():
    """Default filter settings."""
    return FilterSettings()


@pytest.fixture
def markets_from_fixture():
    """Load test markets from fixtures/markets.json."""
    fixture_path = Path(__file__).parent / "fixtures" / "markets.json"
    with open(fixture_path, "r") as f:
        raw_data = json.load(f)
    
    # Convert JSON to Market objects
    markets = []
    for m in raw_data:
        market = Market(
            market_id=m["market_id"],
            title=m["title"],
            end_time=datetime.fromisoformat(m["end_time"].replace("Z", "+00:00"))
            if m["end_time"]
            else None,
            outcomes=m["outcomes"],
            best_bid=m["best_bid"],
            best_ask=m["best_ask"],
            volume_24h_usd=m["volume_24h_usd"],
            liquidity_usd=m["liquidity_usd"],
            trades_1h=m["trades_1h"],
            updated_at=datetime.fromisoformat(m["updated_at"].replace("Z", "+00:00"))
            if m["updated_at"]
            else None,
            resolution_source=m["resolution_source"],
            resolution_rules=m["resolution_rules"],
        )
        markets.append(market)
    
    return markets


# ========== SPREAD FILTER TESTS ==========


class TestSpreadFilter:
    """Tests for spread constraint validation."""
    
    def test_spread_passes_tight_spread(self, settings):
        """Market with spread <= 1% should pass."""
        market = Market(
            market_id="tight_spread",
            title="Test",
            end_time=datetime.utcnow() + timedelta(days=10),
            outcomes=["YES", "NO"],
            best_bid={"YES": 0.60, "NO": 0.40},
            best_ask={"YES": 0.605, "NO": 0.405},  # 0.83% spread
            volume_24h_usd=50_000,
            liquidity_usd=50_000,
            trades_1h=10,
            updated_at=datetime.utcnow(),
            resolution_source="Test",
            resolution_rules="Test rule with source.",
        )
        engine = MarketFilter(settings)
        assert engine._passes_spread_filter(market)
    
    def test_spread_passes_at_max_threshold(self, settings):
        """Market with spread = max_spread_pct should pass."""
        settings.max_spread_pct = 0.03
        market = Market(
            market_id="at_threshold",
            title="Test",
            end_time=datetime.utcnow() + timedelta(days=10),
            outcomes=["YES", "NO"],
            best_bid={"YES": 0.50, "NO": 0.50},
            best_ask={"YES": 0.5151, "NO": 0.5151},  # 3% spread
            volume_24h_usd=50_000,
            liquidity_usd=50_000,
            trades_1h=10,
            updated_at=datetime.utcnow(),
            resolution_source="Test",
            resolution_rules="Test rule with source.",
        )
        engine = MarketFilter(settings)
        assert engine._passes_spread_filter(market)
    
    def test_spread_fails_wide_spread(self, settings):
        """Market with spread > max_spread_pct should fail."""
        settings.max_spread_pct = 0.03
        market = Market(
            market_id="wide_spread",
            title="Test",
            end_time=datetime.utcnow() + timedelta(days=10),
            outcomes=["YES", "NO"],
            best_bid={"YES": 0.40, "NO": 0.59},
            best_ask={"YES": 0.48, "NO": 0.61},  # 8.8% spread on YES
            volume_24h_usd=50_000,
            liquidity_usd=50_000,
            trades_1h=10,
            updated_at=datetime.utcnow(),
            resolution_source="Test",
            resolution_rules="Test rule with source.",
        )
        engine = MarketFilter(settings)
        assert not engine._passes_spread_filter(market)
    
    def test_spread_fails_missing_ask(self, settings):
        """Market with missing ask prices should fail."""
        market = Market(
            market_id="missing_ask",
            title="Test",
            end_time=datetime.utcnow() + timedelta(days=10),
            outcomes=["YES", "NO"],
            best_bid={"YES": 0.60, "NO": 0.40},
            best_ask={},  # Missing ask
            volume_24h_usd=50_000,
            liquidity_usd=50_000,
            trades_1h=10,
            updated_at=datetime.utcnow(),
            resolution_source="Test",
            resolution_rules="Test rule with source.",
        )
        engine = MarketFilter(settings)
        assert not engine._passes_spread_filter(market)
    
    def test_spread_fails_inverted_prices(self, settings):
        """Market with ask < bid should fail."""
        market = Market(
            market_id="inverted",
            title="Test",
            end_time=datetime.utcnow() + timedelta(days=10),
            outcomes=["YES", "NO"],
            best_bid={"YES": 0.65, "NO": 0.40},
            best_ask={"YES": 0.60, "NO": 0.40},  # ask < bid on YES
            volume_24h_usd=50_000,
            liquidity_usd=50_000,
            trades_1h=10,
            updated_at=datetime.utcnow(),
            resolution_source="Test",
            resolution_rules="Test rule with source.",
        )
        engine = MarketFilter(settings)
        assert not engine._passes_spread_filter(market)


# ========== VOLUME & LIQUIDITY FILTER TESTS ==========


class TestVolumeAndLiquidityFilters:
    """Tests for volume and liquidity constraints."""
    
    def test_volume_passes_above_minimum(self, settings):
        """Market with volume > min should pass."""
        market = Market(
            market_id="good_volume",
            title="Test",
            end_time=datetime.utcnow() + timedelta(days=10),
            outcomes=["YES", "NO"],
            best_bid={"YES": 0.60, "NO": 0.40},
            best_ask={"YES": 0.61, "NO": 0.41},
            volume_24h_usd=15_000,  # > default 10k
            liquidity_usd=50_000,
            trades_1h=10,
            updated_at=datetime.utcnow(),
            resolution_source="Test",
            resolution_rules="Test rule with source.",
        )
        engine = MarketFilter(settings)
        assert engine._passes_volume_filter(market)
    
    def test_volume_fails_below_minimum(self, settings):
        """Market with volume < min should fail."""
        market = Market(
            market_id="low_volume",
            title="Test",
            end_time=datetime.utcnow() + timedelta(days=10),
            outcomes=["YES", "NO"],
            best_bid={"YES": 0.60, "NO": 0.40},
            best_ask={"YES": 0.61, "NO": 0.41},
            volume_24h_usd=5_000,  # < default 10k
            liquidity_usd=50_000,
            trades_1h=10,
            updated_at=datetime.utcnow(),
            resolution_source="Test",
            resolution_rules="Test rule with source.",
        )
        engine = MarketFilter(settings)
        assert not engine._passes_volume_filter(market)
    
    def test_volume_fails_none(self, settings):
        """Market with None volume should fail."""
        market = Market(
            market_id="no_volume",
            title="Test",
            end_time=datetime.utcnow() + timedelta(days=10),
            outcomes=["YES", "NO"],
            best_bid={"YES": 0.60, "NO": 0.40},
            best_ask={"YES": 0.61, "NO": 0.41},
            volume_24h_usd=None,
            liquidity_usd=50_000,
            trades_1h=10,
            updated_at=datetime.utcnow(),
            resolution_source="Test",
            resolution_rules="Test rule with source.",
        )
        engine = MarketFilter(settings)
        assert not engine._passes_volume_filter(market)
    
    def test_liquidity_passes_above_minimum(self, settings):
        """Market with liquidity > min should pass."""
        market = Market(
            market_id="good_liq",
            title="Test",
            end_time=datetime.utcnow() + timedelta(days=10),
            outcomes=["YES", "NO"],
            best_bid={"YES": 0.60, "NO": 0.40},
            best_ask={"YES": 0.61, "NO": 0.41},
            volume_24h_usd=50_000,
            liquidity_usd=30_000,  # > default 25k
            trades_1h=10,
            updated_at=datetime.utcnow(),
            resolution_source="Test",
            resolution_rules="Test rule with source.",
        )
        engine = MarketFilter(settings)
        assert engine._passes_liquidity_filter(market)
    
    def test_liquidity_fails_below_minimum(self, settings):
        """Market with liquidity < min should fail."""
        market = Market(
            market_id="low_liq",
            title="Test",
            end_time=datetime.utcnow() + timedelta(days=10),
            outcomes=["YES", "NO"],
            best_bid={"YES": 0.60, "NO": 0.40},
            best_ask={"YES": 0.61, "NO": 0.41},
            volume_24h_usd=50_000,
            liquidity_usd=10_000,  # < default 25k
            trades_1h=10,
            updated_at=datetime.utcnow(),
            resolution_source="Test",
            resolution_rules="Test rule with source.",
        )
        engine = MarketFilter(settings)
        assert not engine._passes_liquidity_filter(market)
    
    def test_liquidity_fails_none(self, settings):
        """Market with None liquidity should fail."""
        market = Market(
            market_id="no_liq",
            title="Test",
            end_time=datetime.utcnow() + timedelta(days=10),
            outcomes=["YES", "NO"],
            best_bid={"YES": 0.60, "NO": 0.40},
            best_ask={"YES": 0.61, "NO": 0.41},
            volume_24h_usd=50_000,
            liquidity_usd=None,
            trades_1h=10,
            updated_at=datetime.utcnow(),
            resolution_source="Test",
            resolution_rules="Test rule with source.",
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
            market_id="far_future",
            title="Test",
            end_time=datetime.utcnow() + timedelta(days=30),
            outcomes=["YES", "NO"],
            best_bid={"YES": 0.60, "NO": 0.40},
            best_ask={"YES": 0.61, "NO": 0.41},
            volume_24h_usd=50_000,
            liquidity_usd=50_000,
            trades_1h=10,
            updated_at=datetime.utcnow(),
            resolution_source="Test",
            resolution_rules="Test rule with source.",
        )
        engine = MarketFilter(settings)
        assert engine._passes_expiry_filter(market)
    
    def test_expiry_fails_soon(self, settings):
        """Market expiring < min_days should fail."""
        settings.min_days_to_expiry = 7
        market = Market(
            market_id="expiring_soon",
            title="Test",
            end_time=datetime.utcnow() + timedelta(days=2),
            outcomes=["YES", "NO"],
            best_bid={"YES": 0.60, "NO": 0.40},
            best_ask={"YES": 0.61, "NO": 0.41},
            volume_24h_usd=50_000,
            liquidity_usd=50_000,
            trades_1h=10,
            updated_at=datetime.utcnow(),
            resolution_source="Test",
            resolution_rules="Test rule with source.",
        )
        engine = MarketFilter(settings)
        assert not engine._passes_expiry_filter(market)
    
    def test_expiry_missing_allowed(self, settings):
        """Market with missing end_time passes if allow_missing_end_time=True."""
        settings.allow_missing_end_time = True
        market = Market(
            market_id="no_expiry",
            title="Test",
            end_time=None,
            outcomes=["YES", "NO"],
            best_bid={"YES": 0.60, "NO": 0.40},
            best_ask={"YES": 0.61, "NO": 0.41},
            volume_24h_usd=50_000,
            liquidity_usd=50_000,
            trades_1h=10,
            updated_at=datetime.utcnow(),
            resolution_source="Test",
            resolution_rules="Test rule with source.",
        )
        engine = MarketFilter(settings)
        assert engine._passes_expiry_filter(market)
    
    def test_expiry_missing_disallowed(self, settings):
        """Market with missing end_time fails if allow_missing_end_time=False."""
        settings.allow_missing_end_time = False
        market = Market(
            market_id="no_expiry",
            title="Test",
            end_time=None,
            outcomes=["YES", "NO"],
            best_bid={"YES": 0.60, "NO": 0.40},
            best_ask={"YES": 0.61, "NO": 0.41},
            volume_24h_usd=50_000,
            liquidity_usd=50_000,
            trades_1h=10,
            updated_at=datetime.utcnow(),
            resolution_source="Test",
            resolution_rules="Test rule with source.",
        )
        engine = MarketFilter(settings)
        assert not engine._passes_expiry_filter(market)


# ========== RESOLUTION SANITY TESTS ==========


class TestResolutionFilter:
    """Tests for resolution quality and clarity checks."""
    
    def test_resolution_passes_clear_source(self, settings):
        """Market with clear source and no subjective language passes."""
        market = Market(
            market_id="clear_rules",
            title="Test",
            end_time=datetime.utcnow() + timedelta(days=10),
            outcomes=["YES", "NO"],
            best_bid={"YES": 0.60, "NO": 0.40},
            best_ask={"YES": 0.61, "NO": 0.41},
            volume_24h_usd=50_000,
            liquidity_usd=50_000,
            trades_1h=10,
            updated_at=datetime.utcnow(),
            resolution_source="Coinbase",
            resolution_rules="Resolved by official Coinbase API",
        )
        engine = MarketFilter(settings)
        assert engine._passes_resolution_filter(market)
    
    def test_resolution_fails_empty_rules(self, settings):
        """Market with empty resolution rules fails."""
        market = Market(
            market_id="no_rules",
            title="Test",
            end_time=datetime.utcnow() + timedelta(days=10),
            outcomes=["YES", "NO"],
            best_bid={"YES": 0.60, "NO": 0.40},
            best_ask={"YES": 0.61, "NO": 0.41},
            volume_24h_usd=50_000,
            liquidity_usd=50_000,
            trades_1h=10,
            updated_at=datetime.utcnow(),
            resolution_source="Test",
            resolution_rules="",
        )
        engine = MarketFilter(settings)
        assert not engine._passes_resolution_filter(market)
    
    def test_resolution_fails_subjective(self, settings):
        """Market with subjective language fails."""
        market = Market(
            market_id="subjective",
            title="Test",
            end_time=datetime.utcnow() + timedelta(days=10),
            outcomes=["YES", "NO"],
            best_bid={"YES": 0.60, "NO": 0.40},
            best_ask={"YES": 0.61, "NO": 0.41},
            volume_24h_usd=50_000,
            liquidity_usd=50_000,
            trades_1h=10,
            updated_at=datetime.utcnow(),
            resolution_source=None,
            resolution_rules="I believe this will probably happen in my opinion",
        )
        engine = MarketFilter(settings)
        assert not engine._passes_resolution_filter(market)
    
    def test_resolution_passes_source_in_rules(self, settings):
        """Market with 'resolved by' in rules passes without explicit source."""
        market = Market(
            market_id="source_in_text",
            title="Test",
            end_time=datetime.utcnow() + timedelta(days=10),
            outcomes=["YES", "NO"],
            best_bid={"YES": 0.60, "NO": 0.40},
            best_ask={"YES": 0.61, "NO": 0.41},
            volume_24h_usd=50_000,
            liquidity_usd=50_000,
            trades_1h=10,
            updated_at=datetime.utcnow(),
            resolution_source=None,
            resolution_rules="This will be resolved by official announcement",
        )
        engine = MarketFilter(settings)
        assert engine._passes_resolution_filter(market)
    
    def test_resolution_fails_no_source(self, settings):
        """Market without source or source mention fails."""
        market = Market(
            market_id="no_source",
            title="Test",
            end_time=datetime.utcnow() + timedelta(days=10),
            outcomes=["YES", "NO"],
            best_bid={"YES": 0.60, "NO": 0.40},
            best_ask={"YES": 0.61, "NO": 0.41},
            volume_24h_usd=50_000,
            liquidity_usd=50_000,
            trades_1h=10,
            updated_at=datetime.utcnow(),
            resolution_source=None,
            resolution_rules="Something will happen",
        )
        engine = MarketFilter(settings)
        assert not engine._passes_resolution_filter(market)


# ========== RISK-BASED FILTERING TESTS ==========


class TestRiskBasedFiltering:
    """Tests for position size and liquidity constraints."""
    
    def test_risk_passes_sufficient_liquidity(self, settings):
        """Market with liquidity >= 20x order size passes."""
        market = Market(
            market_id="good_size",
            title="Test",
            end_time=datetime.utcnow() + timedelta(days=10),
            outcomes=["YES", "NO"],
            best_bid={"YES": 0.60, "NO": 0.40},
            best_ask={"YES": 0.61, "NO": 0.41},
            volume_24h_usd=100_000,
            liquidity_usd=500_000,  # 500k >= 20 * 20k
            trades_1h=10,
            updated_at=datetime.utcnow(),
            resolution_source="Test",
            resolution_rules="Test rule with source.",
        )
        target_order_size = 20_000
        engine = MarketFilter(settings)
        assert engine._passes_risk_filters(market, target_order_size)
    
    def test_risk_fails_insufficient_liquidity(self, settings):
        """Market with liquidity < 20x order size fails."""
        market = Market(
            market_id="bad_size",
            title="Test",
            end_time=datetime.utcnow() + timedelta(days=10),
            outcomes=["YES", "NO"],
            best_bid={"YES": 0.60, "NO": 0.40},
            best_ask={"YES": 0.61, "NO": 0.41},
            volume_24h_usd=100_000,
            liquidity_usd=300_000,  # 300k < 20 * 20k
            trades_1h=10,
            updated_at=datetime.utcnow(),
            resolution_source="Test",
            resolution_rules="Test rule with source.",
        )
        target_order_size = 20_000
        engine = MarketFilter(settings)
        assert not engine._passes_risk_filters(market, target_order_size)
    
    def test_risk_fails_missing_liquidity(self, settings):
        """Market with None liquidity fails risk check."""
        market = Market(
            market_id="no_liq",
            title="Test",
            end_time=datetime.utcnow() + timedelta(days=10),
            outcomes=["YES", "NO"],
            best_bid={"YES": 0.60, "NO": 0.40},
            best_ask={"YES": 0.61, "NO": 0.41},
            volume_24h_usd=100_000,
            liquidity_usd=None,
            trades_1h=10,
            updated_at=datetime.utcnow(),
            resolution_source="Test",
            resolution_rules="Test rule with source.",
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
            market_id="test_score",
            title="Test",
            end_time=datetime.utcnow() + timedelta(days=10),
            outcomes=["YES", "NO"],
            best_bid={"YES": 0.60, "NO": 0.40},
            best_ask={"YES": 0.62, "NO": 0.42},
            volume_24h_usd=100_000,
            liquidity_usd=100_000,
            trades_1h=10,
            updated_at=datetime.utcnow(),
            resolution_source="Test",
            resolution_rules="Test rule with source.",
        )
        engine = MarketFilter(settings)
        score = engine._compute_score(market)
        assert 0 <= score <= 100, f"Score {score} not in [0, 100]"
    
    def test_spread_affects_score(self, settings):
        """Tighter spread should produce higher score."""
        market_tight = Market(
            market_id="tight",
            title="Test",
            end_time=datetime.utcnow() + timedelta(days=10),
            outcomes=["YES", "NO"],
            best_bid={"YES": 0.60, "NO": 0.40},
            best_ask={"YES": 0.601, "NO": 0.401},  # 0.17% spread
            volume_24h_usd=100_000,
            liquidity_usd=100_000,
            trades_1h=10,
            updated_at=datetime.utcnow(),
            resolution_source="Test",
            resolution_rules="Test rule with source.",
        )
        
        market_wide = Market(
            market_id="wide",
            title="Test",
            end_time=datetime.utcnow() + timedelta(days=10),
            outcomes=["YES", "NO"],
            best_bid={"YES": 0.55, "NO": 0.40},
            best_ask={"YES": 0.62, "NO": 0.47},  # 6% spread
            volume_24h_usd=100_000,
            liquidity_usd=100_000,
            trades_1h=10,
            updated_at=datetime.utcnow(),
            resolution_source="Test",
            resolution_rules="Test rule with source.",
        )
        
        engine = MarketFilter(settings)
        score_tight = engine._compute_score(market_tight)
        score_wide = engine._compute_score(market_wide)
        
        assert score_tight > score_wide, "Tight spread should score higher than wide"
    
    def test_volume_affects_score_logarithmically(self, settings):
        """Higher volume should produce higher score (log-scaled)."""
        market_low_vol = Market(
            market_id="low_vol",
            title="Test",
            end_time=datetime.utcnow() + timedelta(days=10),
            outcomes=["YES", "NO"],
            best_bid={"YES": 0.60, "NO": 0.40},
            best_ask={"YES": 0.61, "NO": 0.41},
            volume_24h_usd=11_000,  # Just above minimum
            liquidity_usd=100_000,
            trades_1h=1,
            updated_at=datetime.utcnow(),
            resolution_source="Test",
            resolution_rules="Test rule with source.",
        )
        
        market_high_vol = Market(
            market_id="high_vol",
            title="Test",
            end_time=datetime.utcnow() + timedelta(days=10),
            outcomes=["YES", "NO"],
            best_bid={"YES": 0.60, "NO": 0.40},
            best_ask={"YES": 0.61, "NO": 0.41},
            volume_24h_usd=500_000,  # Much higher
            liquidity_usd=100_000,
            trades_1h=1,
            updated_at=datetime.utcnow(),
            resolution_source="Test",
            resolution_rules="Test rule with source.",
        )
        
        engine = MarketFilter(settings)
        score_low = engine._compute_score(market_low_vol)
        score_high = engine._compute_score(market_high_vol)
        
        assert score_high > score_low, "Higher volume should score higher"
    
    def test_ranking_deterministic(self, settings):
        """Ranking order should be deterministic and stable."""
        market1 = Market(
            market_id="m1",
            title="Test",
            end_time=datetime.utcnow() + timedelta(days=10),
            outcomes=["YES", "NO"],
            best_bid={"YES": 0.60, "NO": 0.40},
            best_ask={"YES": 0.61, "NO": 0.41},
            volume_24h_usd=100_000,
            liquidity_usd=100_000,
            trades_1h=10,
            updated_at=datetime.utcnow(),
            resolution_source="Test",
            resolution_rules="Test rule with source.",
        )
        
        market2 = Market(
            market_id="m2",
            title="Test",
            end_time=datetime.utcnow() + timedelta(days=10),
            outcomes=["YES", "NO"],
            best_bid={"YES": 0.60, "NO": 0.40},
            best_ask={"YES": 0.61, "NO": 0.41},
            volume_24h_usd=100_000,
            liquidity_usd=100_000,
            trades_1h=10,
            updated_at=datetime.utcnow(),
            resolution_source="Test",
            resolution_rules="Test rule with source.",
        )
        
        engine = MarketFilter(settings)
        ranked1 = engine.rank_markets([market1, market2])
        ranked2 = engine.rank_markets([market2, market1])
        
        # Extract market_ids from ranked results
        ids1 = [m.market_id for m, _ in ranked1]
        ids2 = [m.market_id for m, _ in ranked2]
        
        assert ids1 == ids2, "Ranking order should be deterministic"


# ========== INTEGRATION TESTS ==========


class TestFilterMarketsFull:
    """Integration tests for full filtering pipeline."""
    
    def test_filter_markets_fixture_data(self, settings, markets_from_fixture):
        """Filter should reject ineligible fixture markets correctly."""
        engine = MarketFilter(settings)
        filtered = engine.filter_markets(markets_from_fixture)
        
        # Should contain liquid/tight spread markets
        liquid_ids = [
            "1_liquid_tight_spread",
            "2_liquid_tight_spread",
            "3_liquid_tight_spread",
        ]
        filtered_ids = [m.market_id for m in filtered]
        
        for market_id in liquid_ids:
            assert market_id in filtered_ids, f"{market_id} should be filtered in"
        
        # Should reject low volume markets
        low_vol_ids = ["4_low_volume", "5_low_volume", "6_low_volume"]
        for market_id in low_vol_ids:
            assert market_id not in filtered_ids, f"{market_id} should be filtered out"
        
        # Should reject subjective resolution
        assert "11_subjective_resolution" not in filtered_ids
        
        # Should reject markets missing bid/ask
        assert "9_missing_ask_prices" not in filtered_ids
        assert "10_missing_bid_prices" not in filtered_ids
    
    def test_rank_markets_fixture_data(self, settings, markets_from_fixture):
        """Ranking should correctly prioritize liquid/tight-spread markets."""
        engine = MarketFilter(settings)
        filtered = engine.filter_markets(markets_from_fixture)
        ranked = engine.rank_markets(filtered)
        
        # Top markets should be the tight spread, high liquidity ones
        top_3_ids = [m.market_id for m, _ in ranked[:3]]
        liquid_ids = {
            "1_liquid_tight_spread",
            "2_liquid_tight_spread",
            "3_liquid_tight_spread",
        }
        
        assert len(set(top_3_ids) & liquid_ids) > 0, "Liquid markets should rank high"
    
    def test_explain_rejection_fixture(self, settings, markets_from_fixture):
        """explain_rejection should return human-readable reasons."""
        engine = MarketFilter(settings)
        
        # Get a market that should be rejected
        subjective_market = next(
            m for m in markets_from_fixture if m.market_id == "11_subjective_resolution"
        )
        
        reasons = explain_rejection(subjective_market, settings)
        assert len(reasons) > 0, "Should have rejection reason"
        assert any(
            "subjective" in reason.lower() for reason in reasons
        ), "Should mention subjectivity"


# ========== EDGE CASE TESTS ==========


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""
    
    def test_price_validation_on_creation(self):
        """Market should reject prices outside [0, 1]."""
        with pytest.raises(ValueError):
            Market(
                market_id="bad_price",
                title="Test",
                end_time=datetime.utcnow() + timedelta(days=10),
                outcomes=["YES", "NO"],
                best_bid={"YES": 1.5, "NO": 0.40},  # 1.5 > 1
                best_ask={"YES": 0.61, "NO": 0.41},
                volume_24h_usd=50_000,
                liquidity_usd=50_000,
                trades_1h=10,
                updated_at=datetime.utcnow(),
                resolution_source="Test",
                resolution_rules="Test rule.",
            )
    
    def test_settings_validation_weights(self):
        """FilterSettings should validate scoring weights sum to 1.0."""
        with pytest.raises(ValueError):
            FilterSettings(
                spread_score_weight=0.5,
                volume_score_weight=0.3,
                liquidity_score_weight=0.1,
                frequency_score_weight=0.05,  # Sum = 0.95, not ~1.0
            )
    
    def test_empty_market_list(self, settings):
        """Filtering empty market list should return empty list."""
        engine = MarketFilter(settings)
        result = engine.filter_markets([])
        assert result == []
    
    def test_trading_1h_none_handled(self, settings):
        """Market with None trades_1h should score as 0 for frequency."""
        market = Market(
            market_id="no_trades",
            title="Test",
            end_time=datetime.utcnow() + timedelta(days=10),
            outcomes=["YES", "NO"],
            best_bid={"YES": 0.60, "NO": 0.40},
            best_ask={"YES": 0.61, "NO": 0.41},
            volume_24h_usd=100_000,
            liquidity_usd=100_000,
            trades_1h=None,
            updated_at=datetime.utcnow(),
            resolution_source="Test",
            resolution_rules="Test rule with source.",
        )
        engine = MarketFilter(settings)
        score = engine._compute_score(market)
        assert 0 <= score <= 100
        # Score should be lower due to missing frequency
        frequency_score = engine._score_frequency(market)
        assert frequency_score == 0.0


# ========== CONVENIENCE FUNCTION TESTS ==========


class TestConvenienceFunctions:
    """Tests for module-level convenience functions."""
    
    def test_filter_markets_function(self, markets_from_fixture):
        """Convenience function filter_markets should work."""
        result = filter_markets(markets_from_fixture)
        assert isinstance(result, list)
        assert len(result) > 0
        assert all(isinstance(m, Market) for m in result)
    
    def test_rank_markets_function(self, markets_from_fixture):
        """Convenience function rank_markets should work."""
        # Filter first to get eligible markets
        filtered = filter_markets(markets_from_fixture)
        result = rank_markets(filtered)
        assert isinstance(result, list)
        assert all(isinstance(item, tuple) and len(item) == 2 for item in result)
        assert all(isinstance(m, Market) and isinstance(score, float) for m, score in result)
    
    def test_explain_rejection_function(self, markets_from_fixture):
        """Convenience function explain_rejection should work."""
        # Get a rejected market
        all_markets = markets_from_fixture
        filtered = filter_markets(all_markets)
        filtered_ids = set(m.market_id for m in filtered)
        
        rejected = next(m for m in all_markets if m.market_id not in filtered_ids)
        reasons = explain_rejection(rejected)
        
        assert isinstance(reasons, list)
        assert len(reasons) > 0
