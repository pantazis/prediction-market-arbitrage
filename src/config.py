from pydantic import BaseModel
import yaml
from typing import Optional

class RiskConfig(BaseModel):
    max_capital_per_market: float = 100.0
    max_open_markets: int = 10
    min_liquidity: float = 1000.0
    min_edge: float = 0.01

class BrokerConfig(BaseModel):
    initial_cash: float = 1000.0
    fee_bps: float = 10.0  # Basis points (0.1%)
    slippage_bps: float = 10.0 # Basis points

class AppConfig(BaseModel):
    polymarket_api_url: str = "https://clob.polymarket.com"
    refresh_interval_seconds: int = 60
    risk: RiskConfig
    broker: BrokerConfig

def load_config(path: str) -> AppConfig:
    with open(path, 'r') as f:
        data = yaml.safe_load(f)
    return AppConfig(**data)
