from pydantic import BaseModel, Field
import yaml
import os
from dotenv import load_dotenv
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

class TelegramConfig(BaseModel):
    enabled: bool = Field(default_factory=lambda: os.getenv("TELEGRAM_ENABLED", "false").lower() == "true")
    bot_token: Optional[str] = Field(default_factory=lambda: os.getenv("TELEGRAM_BOT_TOKEN", ""))
    chat_id: Optional[str] = Field(default_factory=lambda: os.getenv("TELEGRAM_CHAT_ID", ""))

class PolymarketConfig(BaseModel):
    host: str = "https://clob.polymarket.com"
    key: Optional[str] = Field(default_factory=lambda: os.getenv("POLYMARKET_PRIVATE_KEY", ""))
    api_key: Optional[str] = Field(default_factory=lambda: os.getenv("POLYMARKET_API_KEY", ""))
    secret: Optional[str] = Field(default_factory=lambda: os.getenv("POLYMARKET_SECRET", ""))
    passphrase: Optional[str] = Field(default_factory=lambda: os.getenv("POLYMARKET_PASSPHRASE", ""))
    chain_id: int = 137
    funder: Optional[str] = Field(default_factory=lambda: os.getenv("POLYMARKET_FUNDER", ""))

class AppConfig(BaseModel):
    polymarket_api_url: str = "https://gamma-api.polymarket.com"
    polymarket: PolymarketConfig = Field(default_factory=PolymarketConfig)
    refresh_interval_seconds: int = 60
    paper_trading: bool = True
    risk: RiskConfig
    broker: BrokerConfig
    telegram: TelegramConfig = Field(default_factory=TelegramConfig)

def load_config(path: str) -> AppConfig:
    load_dotenv()
    with open(path, 'r') as f:
        data = yaml.safe_load(f)
    
    # Allow env vars to override config file for sensitive data if needed, 
    # but Pydantic default_factory handles it if keys are missing in YAML.
    # However, if keys exist in YAML as empty strings, we might want to ensure env vars take precedence or merge.
    config = AppConfig(**data)
    
    # Explicitly check env overrides if empty in config
    if not config.polymarket.key:
        config.polymarket.key = os.getenv("POLYMARKET_PRIVATE_KEY", "")
    if not config.polymarket.api_key:
        config.polymarket.api_key = os.getenv("POLYMARKET_API_KEY", "")
    if not config.polymarket.secret:
        config.polymarket.secret = os.getenv("POLYMARKET_SECRET", "")
    if not config.polymarket.passphrase:
        config.polymarket.passphrase = os.getenv("POLYMARKET_PASSPHRASE", "")
        
    return config
