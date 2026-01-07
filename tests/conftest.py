import json
import sys
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime, timedelta

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from predarb.models import Market, Outcome, Opportunity, Trade, TradeAction
from predarb.config import (
    BrokerConfig,
    RiskConfig,
    FilterConfig,
    DetectorConfig,
)


def pytest_ignore_collect(path, config):
    # Ignore legacy tests from previous implementation to focus on new predarb suite
    basename = Path(path).name
    legacy = {"test_components.py", "test_polymarket_client.py", "test_telegram_notifier.py"}
    if basename in legacy:
        return True
    return False


@pytest.fixture(scope="session")
def markets() -> List[Market]:
    fixture_path = Path(__file__).parent / "fixtures" / "markets.json"
    raw = json.loads(fixture_path.read_text())
    markets: List[Market] = []
    for m in raw:
        # predarb.models.Market accepts legacy keys; pass through raw fixture
        # and let the model validator normalize the shapes.
        market = Market(**m)
        markets.append(market)

    # Synthetic markets to ensure detectors have clear signals.
    markets.append(
        Market(
            id="ladder_low",
            question="Will BTC price exceed $50k by 2026?",
            outcomes=[
                {"id": "y1", "label": "YES", "price": 0.30},
                {"id": "n1", "label": "NO", "price": 0.70},
            ],
            comparator=">",
            threshold=50_000,
            liquidity=50_000,
            volume=100_000,
        )
    )
    markets.append(
        Market(
            id="ladder_high",
            question="Will BTC price exceed $60k by 2026?",
            outcomes=[
                {"id": "y2", "label": "YES", "price": 0.50},
                {"id": "n2", "label": "NO", "price": 0.50},
            ],
            comparator=">",
            threshold=60_000,
            liquidity=50_000,
            volume=100_000,
        )
    )
    markets.append(
        Market(
            id="dup1",
            question="Will ETH be above $3k on Jan 1 2026?",
            outcomes=[
                {"id": "yd1", "label": "YES", "price": 0.55},
                {"id": "nd1", "label": "NO", "price": 0.45},
            ],
            end_date=None,
            liquidity=30_000,
            volume=20_000,
        )
    )
    markets.append(
        Market(
            id="dup2",
            question="Will ETH be above $3k on January 1 2026?",
            outcomes=[
                {"id": "yd2", "label": "YES", "price": 0.38},
                {"id": "nd2", "label": "NO", "price": 0.62},
            ],
            end_date=None,
            liquidity=30_000,
            volume=20_000,
        )
    )
    markets.append(
        Market(
            id="exclusive_sum_test",
            question="Who will win the 2026 championship?",
            outcomes=[
                {"id": "a", "label": "A", "price": 0.5},
                {"id": "b", "label": "B", "price": 0.5},
                {"id": "c", "label": "C", "price": 0.5},
            ],
            liquidity=10_000,
            volume=5_000,
        )
    )
    markets.append(
        Market(
            id="consistency_gt",
            question="Will gold price be above $2000?",
            outcomes=[
                {"id": "yc1", "label": "YES", "price": 0.70},
                {"id": "nc1", "label": "NO", "price": 0.30},
            ],
            comparator=">",
            threshold=2000,
            liquidity=20_000,
            volume=20_000,
        )
    )
    markets.append(
        Market(
            id="consistency_le",
            question="Will gold price be above $2000?",
            outcomes=[
                {"id": "yc2", "label": "YES", "price": 0.55},
                {"id": "nc2", "label": "NO", "price": 0.45},
            ],
            comparator="<=",
            threshold=2000,
            liquidity=20_000,
            volume=20_000,
        )
    )
    markets.append(
        Market(
            id="m1",
            question="Will BTC close above $60k on Jan 1 2026?",
            outcomes=[
                {"id": "ym1", "label": "YES", "price": 0.52},
                {"id": "nm1", "label": "NO", "price": 0.48},
            ],
            end_date="2026-01-02T00:00:00Z",
            liquidity=40_000,
            volume=50_000,
        )
    )
    markets.append(
        Market(
            id="m6",
            question="Will BTC close above $60k on 1 Jan 2026?",
            outcomes=[
                {"id": "ym6", "label": "YES", "price": 0.60},
                {"id": "nm6", "label": "NO", "price": 0.40},
            ],
            end_date="2026-01-02T12:00:00Z",
            liquidity=40_000,
            volume=50_000,
        )
    )
    return markets


# ============================================================================
# INVARIANT TEST FIXTURES
# ============================================================================

# OUTCOME FIXTURES

@pytest.fixture
def valid_binary_outcomes() -> List[Outcome]:
    """Valid YES/NO outcomes for binary prediction market."""
    return [
        Outcome(id="yes", label="Yes", price=0.6, liquidity=10000.0),
        Outcome(id="no", label="No", price=0.4, liquidity=10000.0),
    ]


@pytest.fixture
def valid_multiway_outcomes() -> List[Outcome]:
    """Valid 4-outcome market (sums to 1.0)."""
    return [
        Outcome(id="outcome_a", label="Outcome A", price=0.25, liquidity=5000.0),
        Outcome(id="outcome_b", label="Outcome B", price=0.25, liquidity=5000.0),
        Outcome(id="outcome_c", label="Outcome C", price=0.25, liquidity=5000.0),
        Outcome(id="outcome_d", label="Outcome D", price=0.25, liquidity=5000.0),
    ]


@pytest.fixture
def imbalanced_outcomes() -> List[Outcome]:
    """Outcomes that sum to < 1.0 (arbitrage opportunity)."""
    return [
        Outcome(id="yes", label="Yes", price=0.45, liquidity=10000.0),
        Outcome(id="no", label="No", price=0.45, liquidity=10000.0),
    ]


# MARKET FIXTURES

@pytest.fixture
def valid_market_template() -> Dict:
    """Template for a valid market. Customize as needed."""
    return {
        "id": "market_001",
        "question": "Will BTC close above $50k by end of 2026?",
        "outcomes": [
            {"id": "yes", "label": "Yes", "price": 0.6, "liquidity": 10000.0},
            {"id": "no", "label": "No", "price": 0.4, "liquidity": 10000.0},
        ],
        "end_date": datetime.utcnow() + timedelta(days=30),
        "liquidity": 100000.0,
        "volume": 50000.0,
        "tags": ["crypto", "bitcoin"],
        "resolution_source": "CoinGecko",
        "description": "Based on CoinGecko Bitcoin closing price on Dec 31, 2026.",
        "best_bid": {"yes": 0.59, "no": 0.39},
        "best_ask": {"yes": 0.61, "no": 0.41},
        "updated_at": datetime.utcnow(),
    }


@pytest.fixture
def valid_market(valid_market_template) -> Market:
    """A valid, well-formed market."""
    return Market(**valid_market_template)


@pytest.fixture
def tight_spread_market() -> Market:
    """Market with very tight bid-ask spread (0.001 = 0.1%)."""
    return Market(
        id="tight_spread",
        question="Will it rain tomorrow?",
        outcomes=[
            Outcome(id="yes", label="Yes", price=0.50, liquidity=50000.0),
            Outcome(id="no", label="No", price=0.50, liquidity=50000.0),
        ],
        end_date=datetime.utcnow() + timedelta(days=1),
        liquidity=500000.0,
        volume=100000.0,
        resolution_source="NOAA",
        best_bid={"yes": 0.499, "no": 0.499},
        best_ask={"yes": 0.501, "no": 0.501},
    )


@pytest.fixture
def wide_spread_market() -> Market:
    """Market with very wide bid-ask spread (0.20 = 20%)."""
    return Market(
        id="wide_spread",
        question="Will X happen?",
        outcomes=[
            Outcome(id="yes", label="Yes", price=0.5, liquidity=1000.0),
            Outcome(id="no", label="No", price=0.5, liquidity=1000.0),
        ],
        end_date=datetime.utcnow() + timedelta(days=7),
        liquidity=5000.0,
        volume=1000.0,
        best_bid={"yes": 0.40, "no": 0.40},
        best_ask={"yes": 0.60, "no": 0.60},
    )


@pytest.fixture
def low_liquidity_market() -> Market:
    """Market with very low liquidity ($500)."""
    return Market(
        id="low_liq",
        question="Low liquidity event?",
        outcomes=[
            Outcome(id="yes", label="Yes", price=0.5, liquidity=250.0),
            Outcome(id="no", label="No", price=0.5, liquidity=250.0),
        ],
        end_date=datetime.utcnow() + timedelta(days=30),
        liquidity=500.0,
        volume=100.0,
    )


@pytest.fixture
def high_liquidity_market() -> Market:
    """Market with high liquidity ($1M+)."""
    return Market(
        id="high_liq",
        question="High liquidity event?",
        outcomes=[
            Outcome(id="yes", label="Yes", price=0.55, liquidity=500000.0),
            Outcome(id="no", label="No", price=0.45, liquidity=500000.0),
        ],
        end_date=datetime.utcnow() + timedelta(days=90),
        liquidity=1000000.0,
        volume=500000.0,
    )


@pytest.fixture
def market_expires_tomorrow() -> Market:
    """Market expiring very soon (1 day)."""
    return Market(
        id="expires_soon",
        question="Event tomorrow?",
        outcomes=[
            Outcome(id="yes", label="Yes", price=0.7, liquidity=10000.0),
            Outcome(id="no", label="No", price=0.3, liquidity=10000.0),
        ],
        end_date=datetime.utcnow() + timedelta(days=1),
        liquidity=50000.0,
        volume=10000.0,
    )


@pytest.fixture
def market_expires_in_90_days() -> Market:
    """Market expiring in 90 days."""
    return Market(
        id="expires_far",
        question="Event in 3 months?",
        outcomes=[
            Outcome(id="yes", label="Yes", price=0.5, liquidity=10000.0),
            Outcome(id="no", label="No", price=0.5, liquidity=10000.0),
        ],
        end_date=datetime.utcnow() + timedelta(days=90),
        liquidity=100000.0,
        volume=50000.0,
    )


@pytest.fixture
def market_no_resolution_source() -> Market:
    """Market without resolution source (should be rejected)."""
    return Market(
        id="no_source",
        question="Ambiguous event?",
        outcomes=[
            Outcome(id="yes", label="Yes", price=0.5, liquidity=10000.0),
            Outcome(id="no", label="No", price=0.5, liquidity=10000.0),
        ],
        end_date=datetime.utcnow() + timedelta(days=30),
        liquidity=50000.0,
        volume=20000.0,
        resolution_source=None,  # Missing!
    )


@pytest.fixture
def market_imbalanced_probabilities() -> Market:
    """Market where outcomes don't sum to 1.0 (parity violation)."""
    return Market(
        id="imbalanced",
        question="Imbalanced market?",
        outcomes=[
            Outcome(id="yes", label="Yes", price=0.45, liquidity=10000.0),
            Outcome(id="no", label="No", price=0.45, liquidity=10000.0),
        ],
        end_date=datetime.utcnow() + timedelta(days=30),
        liquidity=50000.0,
        volume=20000.0,
    )


@pytest.fixture
def multiway_market() -> Market:
    """Multi-outcome (4-way) market that sums to 1.0."""
    return Market(
        id="multiway",
        question="Which team wins the championship?",
        outcomes=[
            Outcome(id="teamA", label="Team A", price=0.25, liquidity=25000.0),
            Outcome(id="teamB", label="Team B", price=0.25, liquidity=25000.0),
            Outcome(id="teamC", label="Team C", price=0.25, liquidity=25000.0),
            Outcome(id="teamD", label="Team D", price=0.25, liquidity=25000.0),
        ],
        end_date=datetime.utcnow() + timedelta(days=60),
        liquidity=400000.0,
        volume=100000.0,
        resolution_source="Official League",
    )


@pytest.fixture
def market_list_for_scaling() -> List[Market]:
    """
    List of markets for testing filter scaling invariant.
    Filter result with trade_size=50 should be >= filter result with trade_size=500.
    """
    return [
        Market(
            id=f"market_{i}",
            question=f"Event {i}?",
            outcomes=[
                Outcome(id="yes", label="Yes", price=0.5, liquidity=float(10000 * (i + 1))),
                Outcome(id="no", label="No", price=0.5, liquidity=float(10000 * (i + 1))),
            ],
            end_date=datetime.utcnow() + timedelta(days=30 + i),
            liquidity=float(100000 * (i + 1)),
            volume=float(50000 * (i + 1)),
            resolution_source=f"Source {i}",
        )
        for i in range(10)
    ]


# TRADE ACTION FIXTURES

@pytest.fixture
def buy_action() -> TradeAction:
    """Buy action for YES outcome."""
    return TradeAction(
        market_id="market_001",
        outcome_id="yes",
        side="BUY",
        amount=10.0,
        limit_price=0.6,
    )


@pytest.fixture
def sell_action() -> TradeAction:
    """Sell action for NO outcome."""
    return TradeAction(
        market_id="market_001",
        outcome_id="no",
        side="SELL",
        amount=10.0,
        limit_price=0.4,
    )


# OPPORTUNITY FIXTURES

@pytest.fixture
def parity_opportunity() -> Opportunity:
    """Opportunity from parity detector (YES + NO < 1)."""
    return Opportunity(
        type="PARITY",
        market_ids=["market_001"],
        description="YES (0.45) + NO (0.45) = 0.90, net_edge = 0.095",
        net_edge=0.095,
        actions=[
            TradeAction(market_id="market_001", outcome_id="yes", side="BUY", amount=10.0, limit_price=0.45),
            TradeAction(market_id="market_001", outcome_id="no", side="BUY", amount=10.0, limit_price=0.45),
        ],
        metadata={"gross_cost": 0.90},
    )


@pytest.fixture
def low_edge_opportunity() -> Opportunity:
    """Opportunity with very small edge (near zero)."""
    return Opportunity(
        type="PARITY",
        market_ids=["market_001"],
        description="Almost no edge",
        net_edge=0.001,
        actions=[
            TradeAction(market_id="market_001", outcome_id="yes", side="BUY", amount=1.0, limit_price=0.495),
            TradeAction(market_id="market_001", outcome_id="no", side="BUY", amount=1.0, limit_price=0.495),
        ],
    )


@pytest.fixture
def zero_edge_opportunity() -> Opportunity:
    """Opportunity with zero edge (should be rejected)."""
    return Opportunity(
        type="PARITY",
        market_ids=["market_001"],
        description="No edge",
        net_edge=0.0,
        actions=[
            TradeAction(market_id="market_001", outcome_id="yes", side="BUY", amount=1.0, limit_price=0.5),
            TradeAction(market_id="market_001", outcome_id="no", side="BUY", amount=1.0, limit_price=0.5),
        ],
    )


# CONFIG FIXTURES

@pytest.fixture
def default_broker_config() -> BrokerConfig:
    """Default broker configuration."""
    return BrokerConfig(
        initial_cash=10000.0,
        fee_bps=10,  # 0.1%
        slippage_bps=20,  # 0.2%
        depth_fraction=0.05,
    )


@pytest.fixture
def strict_broker_config() -> BrokerConfig:
    """Broker config with high fees and slippage."""
    return BrokerConfig(
        initial_cash=10000.0,
        fee_bps=50,  # 0.5%
        slippage_bps=100,  # 1.0%
        depth_fraction=0.01,
    )


@pytest.fixture
def default_risk_config() -> RiskConfig:
    """Default risk management configuration."""
    return RiskConfig(
        max_allocation_per_market=0.1,  # 10% per market
        max_open_positions=5,
        min_liquidity_usd=10000.0,
        min_net_edge_threshold=0.01,  # 1%
        kill_switch_drawdown=0.2,  # 20%
    )


@pytest.fixture
def strict_risk_config() -> RiskConfig:
    """Risk config with tighter constraints."""
    return RiskConfig(
        max_allocation_per_market=0.05,  # 5% per market
        max_open_positions=2,
        min_liquidity_usd=50000.0,
        min_net_edge_threshold=0.05,  # 5%
        kill_switch_drawdown=0.1,  # 10%
    )


@pytest.fixture
def default_filter_config() -> FilterConfig:
    """Default market filtering configuration."""
    return FilterConfig(
        max_spread_pct=0.03,  # 3%
        min_volume_24h=10000.0,
        min_liquidity=25000.0,
        min_days_to_expiry=7,
        require_resolution_source=True,
    )


@pytest.fixture
def loose_filter_config() -> FilterConfig:
    """Lenient filtering (allows more markets)."""
    return FilterConfig(
        max_spread_pct=0.10,  # 10%
        min_volume_24h=1000.0,
        min_liquidity=5000.0,
        min_days_to_expiry=1,
        require_resolution_source=False,
    )


@pytest.fixture
def default_detector_config() -> DetectorConfig:
    """Default detector configuration."""
    return DetectorConfig(
        parity_threshold=0.99,  # Trigger if YES + NO < 0.99
        duplicate_price_diff_threshold=0.02,  # 2% difference
        exclusive_sum_tolerance=0.01,  # 1% tolerance
        ladder_tolerance=0.01,  # 1% tolerance
        timelag_price_jump=0.05,  # 5% jump
        timelag_persistence_minutes=5,  # Persist 5+ minutes
    )


# HELPER FUNCTIONS

def create_market(
    market_id: str,
    question: str,
    yes_price: float,
    no_price: float,
    liquidity: float = 50000.0,
    days_to_expiry: int = 30,
    volume: float = 20000.0,
    resolution_source: Optional[str] = "TestSource",
) -> Market:
    """
    Helper to create a market with custom parameters.
    Ensures prices are valid (0 <= price <= 1).
    """
    yes_price = max(0.0, min(1.0, yes_price))
    no_price = max(0.0, min(1.0, no_price))
    
    return Market(
        id=market_id,
        question=question,
        outcomes=[
            Outcome(id="yes", label="Yes", price=yes_price, liquidity=liquidity / 2),
            Outcome(id="no", label="No", price=no_price, liquidity=liquidity / 2),
        ],
        end_date=datetime.utcnow() + timedelta(days=days_to_expiry),
        liquidity=liquidity,
        volume=volume,
        resolution_source=resolution_source,
    )


# Additional fixture used by market invariant tests
@pytest.fixture
def market_with_invalid_price(valid_market_template) -> Dict:
    """Provide a valid market template dict to mutate for invalid price tests."""
    # Return a shallow copy so tests can modify outcome prices
    return valid_market_template.copy()
