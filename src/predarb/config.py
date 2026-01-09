from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field, ValidationError, field_validator


class PolymarketConfig(BaseModel):
    host: str = "https://clob.polymarket.com"
    api_key: Optional[str] = Field(default_factory=lambda: os.getenv("POLYMARKET_API_KEY"))
    secret: Optional[str] = Field(default_factory=lambda: os.getenv("POLYMARKET_SECRET"))
    passphrase: Optional[str] = Field(default_factory=lambda: os.getenv("POLYMARKET_PASSPHRASE"))
    private_key: Optional[str] = Field(default_factory=lambda: os.getenv("POLYMARKET_PRIVATE_KEY"))
    chain_id: int = 137
    funder: Optional[str] = Field(default_factory=lambda: os.getenv("POLYMARKET_FUNDER"))


class RiskConfig(BaseModel):
    max_allocation_per_market: float = 0.05
    max_open_positions: int = 20
    min_liquidity_usd: float = 500.0
    min_net_edge_threshold: float = 0.005
    kill_switch_drawdown: float = 0.2
    
    # ==================== SHORT SELLING PREVENTION FILTERS ==================== #
    # Minimum gross edge (before fees/slippage) - default 5%
    min_gross_edge: float = 0.05
    # Minimum BUY price to avoid dust/fake liquidity (default $0.02)
    min_buy_price: float = 0.02
    # BUY-side liquidity multiple: orderbook depth must be >= N × trade_size (default 3x)
    min_liquidity_multiple_strict: float = 3.0
    # Minimum time to market expiry in hours (default 24h)
    min_expiry_hours: float = 24.0
    # Maximum spread percentage for entry (default 10%)
    max_entry_spread_pct: float = 0.10
    
    # ==================== PARTIAL FILL BEHAVIOR ==================== #
    # If True, cancel remaining orders on partial fill and mark as CANCELLED
    # If False, allow partial fills (NOT RECOMMENDED for venues without short selling)
    kill_switch_on_partial: bool = True

    @field_validator("max_allocation_per_market")
    @classmethod
    def _cap_allocation(cls, v: float) -> float:
        if v <= 0 or v > 1:
            raise ValueError("max_allocation_per_market must be in (0,1]")
        return v


class BrokerConfig(BaseModel):
    initial_cash: float = 10000.0
    fee_bps: float = 10.0
    slippage_bps: float = 20.0
    depth_fraction: float = 0.05  # fraction of quoted liquidity available


class EngineConfig(BaseModel):
    refresh_seconds: float = 5.0
    iterations: int = 100
    report_path: str = "reports/paper_trades.csv"


class FilterConfig(BaseModel):
    # Looser defaults so we still scan when live liquidity/volume data is sparse
    max_spread_pct: float = 0.60
    min_volume_24h: float = 0.0
    min_liquidity: float = 0.0
    min_days_to_expiry: int = 0
    min_liquidity_multiple: float = 0.0
    require_resolution_source: bool = False
    allow_missing_end_time: bool = True
    min_rank_score: float = 0.0
    # Target bet size used for liquidity sizing (risk-based filter)
    target_order_size_usd: float = 500.0
    # scoring weights follow predarb.filtering.FilterSettings defaults
    spread_score_weight: float = 0.40
    volume_score_weight: float = 0.20
    liquidity_score_weight: float = 0.30
    frequency_score_weight: float = 0.10

class TelegramConfig(BaseModel):
    enabled: bool = Field(default_factory=lambda: os.getenv("TELEGRAM_ENABLED", "false").lower() == "true")
    bot_token: str = Field(default_factory=lambda: os.getenv("TELEGRAM_BOT_TOKEN", ""))
    chat_id: str = Field(default_factory=lambda: os.getenv("TELEGRAM_CHAT_ID", ""))


class DetectorConfig(BaseModel):
    parity_threshold: float = 0.99
    duplicate_price_diff_threshold: float = 0.05
    exclusive_sum_tolerance: float = 0.03
    ladder_tolerance: float = 0.0
    timelag_price_jump: float = 0.05
    timelag_persistence_minutes: float = 5.0
    # Enable/disable specific detectors
    enable_duplicate: bool = True  # Requires short selling - disable for live Polymarket trading
    enable_ladder: bool = True
    enable_parity: bool = True
    enable_exclusive_sum: bool = True
    enable_timelag: bool = True
    enable_consistency: bool = True


class LLMVerificationConfig(BaseModel):
    """Configuration for LLM-based market verification."""

    enabled: bool = False
    provider: str = "mock"  # "openai", "gemini", "mock"
    model: str = "gpt-3.5-turbo"
    timeout_s: float = 3.0
    max_pairs_per_group: int = 5
    min_similarity_to_verify: float = 0.90
    cache_path: str = "data/llm_verify_cache.json"
    ttl_hours: int = 168
    fail_mode: str = "fail_open"  # "fail_open" or "fail_closed"

    @field_validator("fail_mode")
    @classmethod
    def _validate_fail_mode(cls, v: str) -> str:
        if v not in ("fail_open", "fail_closed"):
            raise ValueError(
                f"fail_mode must be 'fail_open' or 'fail_closed', got {v}"
            )
        return v

    @field_validator("min_similarity_to_verify")
    @classmethod
    def _validate_similarity(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError(
                f"min_similarity_to_verify must be in [0, 1], got {v}"
            )
        return v


class AppConfig(BaseModel):
    polymarket: PolymarketConfig = Field(default_factory=PolymarketConfig)
    risk: RiskConfig = Field(default_factory=RiskConfig)
    broker: BrokerConfig = Field(default_factory=BrokerConfig)
    engine: EngineConfig = Field(default_factory=EngineConfig)
    filter: FilterConfig = Field(default_factory=FilterConfig)
    detectors: DetectorConfig = Field(default_factory=DetectorConfig)
    telegram: TelegramConfig = Field(default_factory=TelegramConfig)
    llm_verification: LLMVerificationConfig = Field(default_factory=LLMVerificationConfig)


def load_config(path: str | Path) -> AppConfig:
    path = Path(path)
    env_path = path.parent / ".env"
    load_dotenv(env_path, override=True)
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    try:
        cfg = AppConfig(**data)
    except ValidationError as e:
        raise RuntimeError(f"Invalid config: {e}") from e
    # If YAML has empty/placeholder values, fill from env
    if not cfg.telegram.bot_token:
        cfg.telegram.bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    if not cfg.telegram.chat_id:
        cfg.telegram.chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    if cfg.telegram.enabled is False:
        cfg.telegram.enabled = os.getenv("TELEGRAM_ENABLED", "false").lower() == "true"
    if not cfg.polymarket.api_key:
        cfg.polymarket.api_key = os.getenv("POLYMARKET_API_KEY", "")
    if not cfg.polymarket.secret:
        cfg.polymarket.secret = os.getenv("POLYMARKET_SECRET", "")
    if not cfg.polymarket.passphrase:
        cfg.polymarket.passphrase = os.getenv("POLYMARKET_PASSPHRASE", "")
    if not cfg.polymarket.private_key:
        cfg.polymarket.private_key = os.getenv("POLYMARKET_PRIVATE_KEY", "")
    if not cfg.polymarket.funder:
        cfg.polymarket.funder = os.getenv("POLYMARKET_FUNDER", "")
    return cfg
