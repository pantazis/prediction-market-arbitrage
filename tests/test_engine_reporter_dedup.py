import json
from pathlib import Path

import pytest

from predarb.config import AppConfig
from predarb.engine import Engine
from predarb.models import Market


def _load_fixture_markets(path: Path) -> list[Market]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [Market.model_validate(m) for m in raw]


@pytest.mark.usefixtures()
def test_engine_reporter_dedup_with_real_detectors(tmp_path: Path):
    # Prepare reports dir clean state
    reports_dir = Path(__file__).parents[1] / "reports"
    (reports_dir / "live_summary.csv").unlink(missing_ok=True)
    (reports_dir / ".last_report_state.json").unlink(missing_ok=True)

    # Load real fixture markets and run detectors
    fixture_path = Path(__file__).parents[0] / "fixtures" / "markets.json"
    markets = _load_fixture_markets(fixture_path)

    cfg = AppConfig()
    # Instantiate engine with a dummy client/notifier since we won't call run()
    engine = Engine(config=cfg, client=None, notifier=None)  # client unused in this test

    # Detected opportunities via real detectors
    detected = engine.run_self_test(markets)
    # Approved opportunities via risk manager
    market_lookup = {m.id: m for m in markets}
    approved = [opp for opp in detected if engine.risk.approve(market_lookup, opp)]

    # First report should write headers + one data row
    wrote = engine.reporter.report(
        iteration=1,
        all_markets=markets,
        detected_opportunities=detected,
        approved_opportunities=approved,
    )
    assert wrote is True

    summary_csv = reports_dir / "live_summary.csv"
    assert summary_csv.exists()
    lines1 = summary_csv.read_text(encoding="utf-8").strip().splitlines()
    # Two header rows + one data row
    assert len(lines1) >= 3

    # Second report with identical inputs should dedup and not append
    wrote2 = engine.reporter.report(
        iteration=2,
        all_markets=markets,
        detected_opportunities=detected,
        approved_opportunities=approved,
    )
    assert wrote2 is False

    lines2 = summary_csv.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines2) == len(lines1)
