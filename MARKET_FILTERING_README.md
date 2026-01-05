# Market Filtering & Prioritization Module

## Overview

The `predarb.filtering` module provides a 3-layer filtering and ranking system for Polymarket prediction markets to identify high-quality arbitrage opportunities based on liquidity, spread, and volume metrics.

### Module Location
- **Implementation:** `src/predarb/filtering.py`
- **Tests:** `tests/test_filtering_polymarket.py`

## Features

### Layer 1: Hard Eligibility Filters
Markets must pass all criteria:
- **Outcome Coverage:** ≥2 outcomes with prices
- **Spread Constraint:** Max spread ≤ 6% (max_spread_pct * 2)
- **Volume Requirement:** 24h volume ≥ $10k (configurable)
- **Liquidity Requirement:** Available liquidity ≥ $25k (configurable)
- **Expiry Constraint:** ≥7 days until market expires (configurable)
- **Resolution Source:** Explicit source required (optional)

### Layer 2: Risk-Based Filters
Markets must support your position size:
- **Liquidity Multiple:** Market liquidity ≥ 20x your order size
- Prevents slippage on large positions

### Layer 3: Liquidity Scoring (0..100)
Ranks eligible markets by quality:
- **Spread Tightness** (40% weight) - Narrower spreads score higher
- **Trade Volume** (20% weight) - Log-scaled; higher volume scores higher
- **Available Liquidity** (30% weight) - Log-scaled; deeper pools score higher
- **Outcome Count** (10% weight) - Binary markets ~70pts, 3+ outcomes ~90pts

**Score Penalties:**
- Markets expiring in <30 days receive progressively lower scores
- Missing expiry date: -5% penalty

## Usage

### Basic Filtering

```python
from src.predarb.filtering import filter_markets
from src.predarb.models import Market, Outcome

# Assuming you've fetched markets from PolymarketClient
markets: List[Market] = client.fetch_markets()

# Filter for eligible markets (default settings)
eligible = filter_markets(markets)
print(f"Eligible markets: {len(eligible)}/{len(markets)}")
```

### Ranking by Liquidity Quality

```python
from src.predarb.filtering import rank_markets

# Rank filtered markets by liquidity score
ranked = rank_markets(eligible)

for market, score in ranked[:10]:
    print(f"{market.question:50} Score: {score:.1f}")
```

### Position Sizing Constraints

```python
from src.predarb.filtering import FilterSettings

settings = FilterSettings(
    min_liquidity_multiple=20.0,  # Require 20x order size in liquidity
)

# Filter markets that can handle $50k positions
your_position_size = 50_000
eligible = filter_markets(
    markets,
    settings=settings,
    account_equity_usd=1_000_000,
    target_order_size_usd=your_position_size,
)
```

### Custom Settings

```python
from src.predarb.filtering import FilterSettings, MarketFilter

settings = FilterSettings(
    max_spread_pct=0.02,           # Max 2% spread (vs 3% default)
    min_volume_24h=50_000,         # Require $50k 24h volume
    min_liquidity=100_000,         # Require $100k liquidity
    min_days_to_expiry=14,         # Require ≥14 days
    min_liquidity_multiple=25.0,   # Require 25x order size
    require_resolution_source=True, # Enforce source requirement
    allow_missing_end_time=False,  # Reject markets without expiry
)

engine = MarketFilter(settings)
filtered = engine.filter_markets(markets)
ranked = engine.rank_markets(filtered)
```

### Rejection Explanations

```python
from src.predarb.filtering import explain_rejection

for market in markets:
    if market.id not in [m.id for m in eligible]:
        reasons = explain_rejection(market)
        print(f"{market.question}: {reasons}")
        # Output:
        # "Will BTC hit $100k?": ['24h volume below minimum', 'Liquidity below minimum']
```

## Running Tests

```bash
# Run all filtering tests
pytest tests/test_filtering_polymarket.py -v

# Run specific test class
pytest tests/test_filtering_polymarket.py::TestSpreadFilter -v

# Run with detailed output
pytest tests/test_filtering_polymarket.py -vv --tb=short
```

### Test Coverage (24 tests)
- ✅ Spread filtering (tight/wide spreads, edge cases)
- ✅ Volume & liquidity constraints
- ✅ Expiry filtering (far future, soon, missing)
- ✅ Resolution source validation
- ✅ Risk-based position sizing
- ✅ Scoring consistency and ranking
- ✅ Integration tests with real Polymarket market structure
- ✅ Edge cases (empty markets, multi-outcome, near-expiry)

## Data Compatibility

The module works directly with **Polymarket API** structures:

```python
from src.predarb.models import Market, Outcome

# Market object (from PolymarketClient):
market = Market(
    id="0xabcd...",
    question="Will BTC hit $100k by Dec 2026?",
    outcomes=[
        Outcome(id="yes_token", label="YES", price=0.68),
        Outcome(id="no_token", label="NO", price=0.32),
    ],
    end_date=datetime(2026, 12, 31, tzinfo=timezone.utc),
    liquidity=150000.0,
    volume=500000.0,
    resolution_source="Coinbase",
    # ... other fields
)

# Works with PolymarketClient directly:
from src.predarb.polymarket_client import PolymarketClient
from src.predarb.config import PolymarketConfig

config = PolymarketConfig(host="https://...")
client = PolymarketClient(config)
all_markets = client.fetch_markets()

# Apply filtering to fetched markets
eligible = filter_markets(all_markets)
ranked = rank_markets(eligible)
```

## API Reference

### Main Functions

#### `filter_markets(markets, settings=None, account_equity_usd=None, target_order_size_usd=None) → List[Market]`
Filters markets by all eligibility criteria. Returns sorted list by market ID for determinism.

#### `rank_markets(markets, settings=None) → List[Tuple[Market, float]]`
Ranks eligible markets by liquidity score (0..100), highest first.

#### `explain_rejection(market, settings=None) → List[str]`
Returns human-readable rejection reasons for debugging.

### Classes

#### `FilterSettings`
Configuration dataclass with defaults:
```python
max_spread_pct: float = 0.03              # 3%
min_volume_24h: float = 10_000            # $10k
min_liquidity: float = 25_000             # $25k
min_days_to_expiry: int = 7               # days
min_liquidity_multiple: float = 20.0      # 20x order size
require_resolution_source: bool = True
allow_missing_end_time: bool = True

# Scoring weights (must sum to ~1.0)
spread_score_weight: float = 0.40
volume_score_weight: float = 0.20
liquidity_score_weight: float = 0.30
frequency_score_weight: float = 0.10
```

#### `MarketFilter`
Core filtering engine:
```python
engine = MarketFilter(settings)
filtered = engine.filter_markets(markets)
ranked = engine.rank_markets(filtered)
score = engine._compute_score(market)
reasons = engine._get_rejection_reasons(market)
```

## Performance Notes

- **Deterministic:** Sorting by market ID ensures reproducible results
- **No Network Calls:** All data must be fetched separately
- **Timezone Safe:** Handles both naive and timezone-aware datetimes
- **Log Scaling:** Volume/liquidity scores use log scale for realistic weighting

## Integration Example

```python
# Typical workflow in your bot
from src.predarb.filtering import filter_markets, rank_markets, FilterSettings
from src.predarb.polymarket_client import PolymarketClient

# Fetch markets
client = PolymarketClient(config)
all_markets = client.fetch_markets()  # ~1000 markets

# Configure filtering for your account
settings = FilterSettings(min_volume_24h=20_000)

# Filter and rank
eligible = filter_markets(all_markets, settings)        # ~50 markets
ranked = rank_markets(eligible, settings)               # sorted by score

# Trade only top opportunities
for market, score in ranked[:20]:
    if score > 70:  # High-quality opportunities
        # Your arbitrage detection logic here
        detect_arbitrage(market)
```

---

**Last Updated:** January 2026  
**Compatibility:** Works with Polymarket API via `predarb.models.Market` and `predarb.polymarket_client.PolymarketClient`
