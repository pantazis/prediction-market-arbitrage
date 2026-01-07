import json
from pathlib import Path

import pytest

from predarb.config import AppConfig
from predarb.engine import Engine
from predarb.models import Market
from predarb.testing.fake_client import FakePolymarketClient


def _load_fixture_markets(path: Path) -> list[Market]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [Market.model_validate(m) for m in raw]


@pytest.mark.usefixtures()
def test_exec_logger_writes_deterministic_jsonl(tmp_path: Path):
    reports_dir = Path(__file__).parents[1] / "reports"
    jsonl_path = reports_dir / "opportunity_logs.jsonl"
    jsonl_path.unlink(missing_ok=True)

    # Use synthetic fake client to ensure detector opportunities
    cfg = AppConfig()
    client = FakePolymarketClient(num_markets=30, days=1, seed=42)
    client.reset(0)
    engine = Engine(config=cfg, client=client, notifier=None)

    # Run once: detectors + risk + broker + logging
    executed1 = engine.run_once()
    assert jsonl_path.exists()
    lines1 = jsonl_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines1) >= len(executed1)

    # Parse last record and validate schema
    rec1 = json.loads(lines1[-1])
    assert set(["trace_id","timestamp_utc","opportunity_id","detector","markets","prices_before","intended_actions","risk_approval","executions","hedge","status","realized_pnl","latency_ms"]).issubset(rec1.keys())
    assert isinstance(rec1["trace_id"], str) and len(rec1["trace_id"]) == 64
    assert rec1["status"] in {"success","partial","cancelled","error"}
    assert isinstance(rec1["executions"], list)

    # Run again with identical inputs → trace_id should be stable
    executed2 = engine.run_once()
    lines2 = jsonl_path.read_text(encoding="utf-8").strip().splitlines()
    rec2 = json.loads(lines2[-1])
    assert rec2["opportunity_id"] == rec1["opportunity_id"]
    assert rec2["trace_id"] == rec1["trace_id"]
