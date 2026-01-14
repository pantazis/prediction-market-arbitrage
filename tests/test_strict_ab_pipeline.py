from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from predarb.config import AppConfig
from predarb.strict_ab_llm import StrictABLLMVerifier, StrictABMockProvider
from predarb.strict_ab_pipeline import StrictABPipeline
from predarb.tagging import fast_tag_market
from predarb.models import Market


def _future_iso(hours: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat().replace("+00:00", "Z")


def _kalshi_raw() -> list[dict]:
    return [
        {
            "ticker": "KALSHI1",
            "event_ticker": "EVT1",
            "title": "Will BTC be above 50,000 by next week?",
            "yes_bid": 70,
            "yes_ask": 71,
            "no_bid": 29,
            "no_ask": 30,
            "close_time": _future_iso(72),
            "market_type": "binary",
            "status": "open",
        }
    ]


def _poly_raw() -> list[dict]:
    return [
        {
            "conditionId": "POLY1",
            "question": "Will Bitcoin trade above $50k next week?",
            "outcomes": ["Yes", "No"],
            "outcomePrices": [0.60, 0.40],
            "clobTokenIds": ["111", "222"],
            "endDate": _future_iso(72),
            "closed": False,
            "active": True,
        }
    ]


def _orderbook(bid: float, ask: float) -> dict:
    return {
        "best_bid": bid,
        "best_ask": ask,
        "bids": [{"price": bid, "size": 1000}],
        "asks": [{"price": ask, "size": 1000}],
        "depth": 5000,
    }


def test_fast_tag_market_expiry_bucket():
    market = Market(
        id="m1",
        question="Will BTC rise?",
        outcomes=[{"id": "yes", "label": "YES", "price": 0.5}, {"id": "no", "label": "NO", "price": 0.5}],
        end_date=datetime.now(timezone.utc) + timedelta(hours=5),
    )
    tags = fast_tag_market(market)
    assert any(t.startswith("expiry:") for t in tags)


def test_strict_ab_pipeline_end_to_end(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = AppConfig()
    cfg.strict_ab.watchlist_json = str(tmp_path / "watchlist.json")
    cfg.strict_ab.watchlist_csv = str(tmp_path / "watchlist.csv")
    cfg.strict_ab.audit_log = str(tmp_path / "audit.jsonl")
    cfg.strict_ab.raw_dump_dir = str(tmp_path / "raw")
    cfg.strict_ab.llm.cache_path = str(tmp_path / "llm_cache.json")

    pipeline = StrictABPipeline(cfg)

    monkeypatch.setattr(pipeline, "_fetch_kalshi_raw", _kalshi_raw)
    monkeypatch.setattr(pipeline, "_fetch_polymarket_raw", _poly_raw)
    monkeypatch.setattr(pipeline, "_fetch_kalshi_orderbook", lambda ticker: _orderbook(0.70, 0.71))
    monkeypatch.setattr(pipeline, "_fetch_polymarket_orderbook", lambda market: {"yes": _orderbook(0.59, 0.60), "no": _orderbook(0.39, 0.40)})

    results = pipeline.run_once()

    assert results
    assert any(r.filter_report.passed for r in results)
    assert Path(cfg.strict_ab.watchlist_json).exists()
    assert Path(cfg.strict_ab.watchlist_csv).exists()

    audit_lines = Path(cfg.strict_ab.audit_log).read_text().strip().splitlines()
    stages = {json.loads(line)["stage"] for line in audit_lines}
    assert "stage0" in stages
    assert "stage3" in stages
    assert "stage4" in stages
    assert "stage5_7" in stages


def test_llm_daily_limit_skips(tmp_path: Path) -> None:
    cache_path = tmp_path / "llm_cache.json"
    verifier = StrictABLLMVerifier(
        provider=StrictABMockProvider(),
        cache_path=str(cache_path),
        daily_limit=0,
    )
    market = Market(
        id="m1",
        question="Will BTC rise?",
        outcomes=[{"id": "yes", "label": "YES", "price": 0.5}, {"id": "no", "label": "NO", "price": 0.5}],
    )
    assert verifier.verify_pair("k::p", market, market) is None
