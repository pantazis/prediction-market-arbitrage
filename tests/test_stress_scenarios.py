"""Tests for stress scenarios."""
import pytest
from src.predarb.stress_scenarios import (
    get_scenario,
    list_scenarios,
    HighVolumeScenario,
    ManyRiskRejectionsScenario,
    PartialFillScenario,
    HappyPathScenario,
    LatencyFreshnessScenario,
    FeeSlippageScenario,
    SemanticClusteringScenario,
)


def test_list_scenarios():
    """Test that all expected scenarios are listed."""
    scenarios = list_scenarios()
    
    assert "high_volume" in scenarios
    assert "many_risk_rejections" in scenarios
    assert "partial_fill" in scenarios
    assert "happy_path" in scenarios
    assert "latency_freshness" in scenarios
    assert "fee_slippage" in scenarios
    assert "semantic_clustering" in scenarios
    assert len(scenarios) == 7


def test_get_scenario_happy_path():
    """Test getting happy path scenario."""
    scenario = get_scenario("happy_path", seed=42)
    
    assert isinstance(scenario, HappyPathScenario)
    assert scenario.seed == 42
    
    markets = scenario.get_active_markets()
    assert len(markets) == 15
    assert all(m.id.startswith("happy_") for m in markets)


def test_get_scenario_high_volume():
    """Test high volume scenario generates 1000 markets."""
    scenario = get_scenario("high_volume", seed=100)
    markets = scenario.get_active_markets()
    
    assert len(markets) == 1000
    
    # Check distribution: 990 normal + 10 arb
    normal_count = sum(1 for m in markets if m.id.startswith("norm_"))
    arb_count = sum(1 for m in markets if m.id.startswith("arb_"))
    
    assert normal_count == 990
    assert arb_count == 10


def test_get_scenario_many_risk_rejections():
    """Test risk rejection scenario."""
    scenario = get_scenario("many_risk_rejections", seed=42)
    markets = scenario.get_active_markets()
    
    assert len(markets) == 40  # 20 low liq + 15 low edge + 5 good
    
    # Check market types
    lowliq_count = sum(1 for m in markets if m.id.startswith("lowliq_"))
    lowedge_count = sum(1 for m in markets if m.id.startswith("lowedge_"))
    good_count = sum(1 for m in markets if m.id.startswith("good_"))
    
    assert lowliq_count == 20
    assert lowedge_count == 15
    assert good_count == 5
    
    # Check that low liquidity markets have < 200 liquidity
    lowliq_markets = [m for m in markets if m.id.startswith("lowliq_")]
    assert all(m.liquidity < 200 for m in lowliq_markets)


def test_get_scenario_partial_fill():
    """Test partial fill scenario has asymmetric liquidity."""
    scenario = get_scenario("partial_fill", seed=42)
    markets = scenario.get_active_markets()
    
    assert len(markets) == 10
    assert all(m.id.startswith("partial_") for m in markets)
    
    # Check asymmetric liquidity (YES deep, NO shallow)
    for market in markets:
        yes_outcome = next(o for o in market.outcomes if o.id == "yes")
        no_outcome = next(o for o in market.outcomes if o.id == "no")
        
        assert yes_outcome.liquidity > 15000
        assert no_outcome.liquidity < 1000


def test_get_scenario_latency_freshness():
    """Test latency/freshness scenario has expiring markets."""
    scenario = get_scenario("latency_freshness", seed=42)
    markets = scenario.get_active_markets()
    
    assert len(markets) == 15
    
    expiring_count = sum(1 for m in markets if m.id.startswith("expiring_"))
    fresh_count = sum(1 for m in markets if m.id.startswith("fresh_"))
    
    assert expiring_count == 10
    assert fresh_count == 5


def test_get_scenario_fee_slippage():
    """Test fee/slippage scenario has marginal opportunities."""
    scenario = get_scenario("fee_slippage", seed=42)
    markets = scenario.get_active_markets()
    
    assert len(markets) == 20
    assert all(m.id.startswith("marginal_") for m in markets)
    
    # Check that prices sum to > 0.95 (marginal edge)
    for market in markets:
        total_price = sum(o.price for o in market.outcomes)
        assert 0.95 < total_price < 1.0


def test_get_scenario_invalid_name():
    """Test that invalid scenario name raises ValueError."""
    with pytest.raises(ValueError, match="Unknown scenario"):
        get_scenario("nonexistent_scenario")


def test_scenario_seeded_reproducibility():
    """Test that scenarios with same seed produce same results."""
    scenario1 = get_scenario("happy_path", seed=777)
    markets1 = scenario1.get_active_markets()
    
    scenario2 = get_scenario("happy_path", seed=777)
    markets2 = scenario2.get_active_markets()
    
    assert len(markets1) == len(markets2)
    
    for m1, m2 in zip(markets1, markets2):
        assert m1.id == m2.id
        assert m1.question == m2.question
        assert len(m1.outcomes) == len(m2.outcomes)
        
        for o1, o2 in zip(m1.outcomes, m2.outcomes):
            assert abs(o1.price - o2.price) < 1e-10
            assert abs(o1.liquidity - o2.liquidity) < 1e-6


def test_scenario_different_seeds():
    """Test that different seeds produce different results."""
    scenario1 = get_scenario("happy_path", seed=111)
    markets1 = scenario1.get_active_markets()
    
    scenario2 = get_scenario("happy_path", seed=222)
    markets2 = scenario2.get_active_markets()
    
    # Same number of markets but different prices
    assert len(markets1) == len(markets2)
    
    # At least one market should have different prices
    price_diffs = []
    for m1, m2 in zip(markets1, markets2):
        for o1, o2 in zip(m1.outcomes, m2.outcomes):
            price_diffs.append(abs(o1.price - o2.price))
    
    assert any(diff > 0.01 for diff in price_diffs)


def test_high_volume_scenario_direct():
    """Test HighVolumeScenario directly."""
    scenario = HighVolumeScenario(seed=42)
    markets = scenario.get_active_markets()
    
    assert len(markets) == 1000
    assert scenario.seed == 42


def test_happy_path_scenario_arbitrage_opportunities():
    """Test happy path scenario has good arbitrage opportunities."""
    scenario = HappyPathScenario(seed=42)
    markets = scenario.get_active_markets()
    
    # Check that all markets have sum < 0.95 (strong arbitrage)
    for market in markets:
        total_price = sum(o.price for o in market.outcomes)
        assert total_price < 0.95
        
        # Check sufficient liquidity
        assert market.liquidity > 40000
        assert all(o.liquidity > 20000 for o in market.outcomes)

def test_semantic_clustering_scenario():
    """Test semantic clustering scenario with duplicates and filter violations."""
    scenario = get_scenario("semantic_clustering", seed=42)
    markets = scenario.get_active_markets()
    
    # Total: 5 BTC + 4 election + 2 wide_spread + 2 low_volume + 2 low_liq + 2 expiring + 2 no_source + 3 good_arb + 3 distinct = 25
    assert len(markets) == 25
    
    # Check semantic duplicate groups
    btc_markets = [m for m in markets if m.id.startswith("btc_dup_")]
    election_markets = [m for m in markets if m.id.startswith("election_dup_")]
    assert len(btc_markets) == 5
    assert len(election_markets) == 4
    
    # Verify BTC markets have semantic similarity (all mention Bitcoin/BTC and $100k)
    for market in btc_markets:
        question = market.question.lower()
        assert any(keyword in question for keyword in ["bitcoin", "btc"])
        assert any(threshold in question for threshold in ["100k", "100,000", "100000"])
    
    # Verify election markets have semantic similarity
    for market in election_markets:
        question = market.question.lower()
        assert "democrat" in question or "democratic" in question
        assert "2028" in question
    
    # Check filter violation groups
    wide_spread = [m for m in markets if m.id.startswith("wide_spread_")]
    low_volume = [m for m in markets if m.id.startswith("low_volume_")]
    low_liq = [m for m in markets if m.id.startswith("low_liq_")]
    expiring = [m for m in markets if m.id.startswith("expiring_")]
    no_source = [m for m in markets if m.id.startswith("no_source_")]
    
    assert len(wide_spread) == 2
    assert len(low_volume) == 2
    assert len(low_liq) == 2
    assert len(expiring) == 2
    assert len(no_source) == 2
    
    # Verify wide spread characteristics
    for market in wide_spread:
        total_price = sum(o.price for o in market.outcomes)
        spread = 1.0 - total_price
        assert spread > 0.05  # Spread > 5% (violates typical 3% threshold)
    
    # Verify low volume
    for market in low_volume:
        assert market.volume < 10000  # Below typical $10k min
    
    # Verify low liquidity
    for market in low_liq:
        assert market.liquidity < 25000  # Below typical $25k min
    
    # Verify expiring soon
    from datetime import datetime, timedelta
    now = datetime.utcnow()
    for market in expiring:
        days_to_expiry = (market.end_date - now).days
        assert days_to_expiry < 7  # Expires in < 7 days
    
    # Verify missing resolution source
    for market in no_source:
        assert market.resolution_source == ""
    
    # Check good arbitrage opportunities
    good_arb = [m for m in markets if m.id.startswith("good_arb_")]
    assert len(good_arb) == 3
    for market in good_arb:
        assert market.liquidity > 100000
        assert market.volume > 50000
        assert market.resolution_source != ""
    
    # Check distinct markets (should NOT cluster together despite similar structure)
    distinct = [m for m in markets if m.id.startswith("distinct_")]
    assert len(distinct) == 3
    entities = []
    for market in distinct:
        question = market.question.lower()
        if "apple" in question:
            entities.append("apple")
        elif "tesla" in question:
            entities.append("tesla")
        elif "amazon" in question:
            entities.append("amazon")
    assert len(set(entities)) == 3  # All three different entities


def test_semantic_clustering_deterministic():
    """Test that semantic clustering scenario is deterministic with same seed."""
    scenario1 = get_scenario("semantic_clustering", seed=999)
    scenario2 = get_scenario("semantic_clustering", seed=999)
    
    markets1 = scenario1.get_active_markets()
    markets2 = scenario2.get_active_markets()
    
    assert len(markets1) == len(markets2)
    
    for m1, m2 in zip(markets1, markets2):
        assert m1.id == m2.id
        assert m1.question == m2.question
        assert len(m1.outcomes) == len(m2.outcomes)
        for o1, o2 in zip(m1.outcomes, m2.outcomes):
            assert o1.price == o2.price
            assert o1.liquidity == o2.liquidity


def test_semantic_clustering_different_seeds():
    """Test that different seeds produce different price variations."""
    scenario1 = get_scenario("semantic_clustering", seed=100)
    scenario2 = get_scenario("semantic_clustering", seed=200)
    
    markets1 = scenario1.get_active_markets()
    markets2 = scenario2.get_active_markets()
    
    # Same structure, different random prices
    assert len(markets1) == len(markets2)
    
    # Check that at least some prices differ
    price_diffs = 0
    for m1, m2 in zip(markets1, markets2):
        if m1.outcomes[0].price != m2.outcomes[0].price:
            price_diffs += 1
    
    assert price_diffs > 0  # At least some prices should differ