import pytest
import json
import os
from typing import List
from src.models import Market, Outcome
from src.polymarket_client import PolymarketClient
from src.config import AppConfig, RiskConfig, BrokerConfig
from src.engine import Engine

class MockPolymarketClient:
    def __init__(self, markets_data):
        self.markets_data = markets_data

    def get_active_markets(self) -> List[Market]:
        markets = []
        for d in self.markets_data:
            # Replicate simpler parsing logic for test
            outcomes_raw = d.get('outcomes', [])
            prices_raw = d.get('outcomePrices', [])
            
            if len(outcomes_raw) != len(prices_raw): continue
            
            outcomes = []
            for i, label in enumerate(outcomes_raw):
                outcomes.append(Outcome(
                    id=f"{d['id']}_{i}",
                    label=label,
                    price=float(prices_raw[i])
                ))
            
            markets.append(Market(
                id=d['id'],
                question=d['question'],
                outcomes=outcomes,
                end_date=None,
                liquidity=float(d.get('liquidity', 0)) or 0.0,
                volume=float(d.get('volume', 0)) or 0.0
            ))
        return markets

@pytest.fixture
def mock_markets_data():
    path = os.path.join(os.path.dirname(__file__), 'fixtures', 'markets.json')
    with open(path, 'r') as f:
        return json.load(f)

@pytest.fixture
def mock_client(mock_markets_data):
    return MockPolymarketClient(mock_markets_data)

@pytest.fixture
def test_config():
    return AppConfig(
        polymarket_api_url="http://mock",
        refresh_interval_seconds=1,
        risk=RiskConfig(min_liquidity=100.0, min_edge=0.01),
        broker=BrokerConfig(initial_cash=1000.0)
    )

@pytest.fixture
def engine(test_config, mock_client):
    return Engine(test_config, mock_client)
