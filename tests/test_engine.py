import shutil
from pathlib import Path

from predarb.config import AppConfig, BrokerConfig, DetectorConfig, EngineConfig, PolymarketConfig, RiskConfig
from predarb.engine import Engine
from predarb.models import Market, Outcome


class FakeClient:
    def __init__(self, markets):
        self._markets = markets

    def fetch_markets(self):
        return self._markets


def test_engine_runs_once(markets, tmp_path):
    cfg = AppConfig(
        polymarket=PolymarketConfig(),
        risk=RiskConfig(min_liquidity_usd=0, min_net_edge_threshold=0.0),
        broker=BrokerConfig(initial_cash=1000, depth_fraction=1.0),
        engine=EngineConfig(refresh_seconds=0.0, iterations=1, report_path=str(tmp_path / "report.csv")),
        detectors=DetectorConfig(parity_threshold=1.01, duplicate_price_diff_threshold=0.01),
    )
    client = FakeClient(markets)
    engine = Engine(cfg, client)
    opps = engine.run_once()
    assert isinstance(opps, list)
    assert Path(cfg.engine.report_path).exists()
