import pytest
from unittest.mock import MagicMock, patch
from src.polymarket_client import ClobPolymarketClient
from src.config import PolymarketConfig
from src.models import Market

@pytest.fixture
def mock_clob_client():
    with patch('src.polymarket_client.ClobClient') as MockClient:
        yield MockClient

def test_clob_client_init(mock_clob_client):
    config = PolymarketConfig(host="host", key="key", chain_id=137, funder="funder")
    client = ClobPolymarketClient(config)
    
    mock_clob_client.assert_called_with(
        host="host",
        key="key",
        chain_id=137,
        signature_type=1,
        funder="funder"
    )

def test_get_active_markets_success(mock_clob_client):
    # Setup mock return
    instance = mock_clob_client.return_value
    instance.get_markets.return_value = {
        'data': [
            {
                'condition_id': 'c1',
                'question': 'Q1',
                'active': True,
                'closed': False,
                'tokens': [
                    {'token_id': 't1', 'outcome': 'Yes', 'price': 0.5},
                    {'token_id': 't2', 'outcome': 'No', 'price': 0.5}
                ]
            }
        ]
    }

    config = PolymarketConfig()
    client = ClobPolymarketClient(config)
    markets = client.get_active_markets()

    assert len(markets) == 1
    assert markets[0].id == 'c1'
    assert markets[0].question == 'Q1'
    assert len(markets[0].outcomes) == 2
    assert markets[0].outcomes[0].price == 0.5

def test_get_active_markets_empty(mock_clob_client):
    instance = mock_clob_client.return_value
    instance.get_markets.return_value = {'data': []}

    config = PolymarketConfig()
    client = ClobPolymarketClient(config)
    markets = client.get_active_markets()

    assert len(markets) == 0

def test_get_active_markets_error(mock_clob_client):
    instance = mock_clob_client.return_value
    instance.get_markets.side_effect = Exception("API Error")

    config = PolymarketConfig()
    client = ClobPolymarketClient(config)
    markets = client.get_active_markets()

    assert len(markets) == 0
