import json
import sys
from pathlib import Path
from typing import List

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from predarb.models import Market


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
