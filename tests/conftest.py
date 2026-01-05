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

from predarb.models import Market, Outcome


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
        outcomes = [Outcome(**o) for o in m["outcomes"]]
        markets.append(
            Market(
                id=m["id"],
                question=m["question"],
                outcomes=outcomes,
                liquidity=m.get("liquidity", 0),
                volume=m.get("volume", 0),
                end_date=None,
                expiry=None,
            )
        )
    return markets
