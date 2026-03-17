from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field, ValidationError, field_validator


class PolymarketConfig(BaseModel):
    enabled: bool = True  # Enable/disable Polymarket client
    host: str = "https://gamma-api.polymarket.com"  # Gamma API for market metadata
    clob_host: str = Field(default_factory=lambda: os.getenv("POLYMARKET_CLOB_HOST", "https://clob.polymarket.com"))
    clob_api_key: Optional[str] = Field(
        default_factory=lambda: os.getenv("POLYMARKET_CLOB_API_KEY")
        or os.getenv("POLYMARKET_API_KEY")
    )
    api_key: Optional[str] = Field(default_factory=lambda: os.getenv("POLYMARKET_API_KEY"))
    secret: Optional[str] = Field(default_factory=lambda: os.getenv("POLYMARKET_SECRET"))
    passphrase: Optional[str] = Field(default_factory=lambda: os.getenv("POLYMARKET_PASSPHRASE"))
    private_key: Optional[str] = Field(default_factory=lambda: os.getenv("POLYMARKET_PRIVATE_KEY"))
    chain_id: int = 137
    funder: Optional[str] = Field(default_factory=lambda: os.getenv("POLYMARKET_FUNDER"))
    limit: int = 10000  # Default limit for API requests


class KalshiConfig(BaseModel):
    enabled: bool = False  # Enable/disable Kalshi client
    api_key_id: Optional[str] = Field(default_factory=lambda: os.getenv("KALSHI_API_KEY_ID"))
    private_key_pem: Optional[str] = Field(default_factory=lambda: os.getenv("KALSHI_PRIVATE_KEY_PEM"))
    api_host: str = Field(default_factory=lambda: os.getenv("KALSHI_API_HOST", "https://api.elections.kalshi.com"))
    env: str = Field(default_factory=lambda: os.getenv("KALSHI_ENV", "prod"))
    min_liquidity_usd: float = 0.0  # Disabled - smart matcher handles quality
    min_days_to_expiry: int = 0  # Disabled - smart matcher handles quality

    def model_post_init(self, __context):
        """Load PEM from file if private_key_pem looks like a filename."""
        if self.private_key_pem and not self.private_key_pem.startswith("-----BEGIN"):
            # Assume it's a file path
            pem_path = Path(self.private_key_pem)
            if pem_path.exists():
                self.private_key_pem = pem_path.read_text()
            elif (Path.cwd() / pem_path).exists():
                self.private_key_pem = (Path.cwd() / pem_path).read_text()


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
    # Allow shorting only on Kalshi (useful for cross-venue A+B paper simulation).
    allow_kalshi_shorting: bool = False

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
    allow_kalshi_shorting: bool = False


class EngineConfig(BaseModel):
    refresh_seconds: float = 5.0
    iterations: int = 100
    report_path: str = "reports/paper_trades.csv"


class FilterConfig(BaseModel):
    require_resolution_source: bool = False

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
    enable_composite: bool = True
    enable_cross_venue: bool = False  # Cross-venue arbitrage detection


class LLMVerificationConfig(BaseModel):
    """Configuration for LLM-based market verification."""

    enabled: bool = False
    provider: str = "mock"  # "openai", "gemini", "ollama", "mock"
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


class CrossVenueMatcherConfig(BaseModel):
    """Configuration for cross-venue semantic matching."""

    enabled: bool = False
    model_name: str = "all-MiniLM-L6-v2"
    min_similarity: float = 0.10
    max_hours_diff: int = 24
    batch_size: int = 50  # Process markets in batches to avoid memory issues
    top_k: int = 5  # Candidates per market before thresholding
    encode_batch_size: int = 32  # Embedding batch size


class CrossVenueDetectorConfig(BaseModel):
    """Configuration for cross-venue arbitrage detection."""

    enabled: bool = False  # Disabled by default

    # Price discrepancy detection
    min_price_diff_threshold: float = 0.02  # 2% minimum price difference

    # Fee configuration (basis points)
    kalshi_fee_bps: float = 7.0
    polymarket_fee_bps: float = 10.0

    # Slippage configuration
    slippage_bps: float = 20.0

    # Staleness filtering
    staleness_threshold_seconds: int = 300  # 5 minutes

    # Liquidity filtering
    min_liquidity_usd: float = 100.0

    # Range bucket detection
    bucket_sum_threshold: float = 0.02  # 2% difference threshold





class WatchlistConfig(BaseModel):
    """Configuration for watchlist polling after LLM PASS."""

    enabled: bool = False
    csv_path: str = "data/watchlist_pairs.csv"
    scan_log_path: str = "data/scan_log.jsonl"
    reject_log_path: str = "data/reject_reasons.jsonl"
    approve_log_path: str = "data/approve_packets.jsonl"
    min_edge: float = 0.006
    min_depth_usd: float = 50.0
    max_age_sec: int = 15
    depth_fraction: float = 0.10
    orderbook_enabled: bool = False
    orderbook_timeout_s: float = 2.5
    price_change_threshold_pct: float = 0.002
    execute_paper_trades: bool = False
    max_trades_per_loop: int = 1


class WebBrowsingLLMConfig(BaseModel):
    """Configuration for web-browsing LLM (Stage 1 of topic selector).
    
    Supports LLMs with web search/browsing capabilities like Gemini with
    Google Search grounding or Perplexity with online search.
    """

    provider: str = "gemini"  # "gemini", "perplexity"
    model: str = "gemini-1.5-pro"
    api_key_env: str = "GEMINI_API_KEY"
    timeout_s: float = 60.0
    max_retries: int = 3

    @field_validator("provider")
    @classmethod
    def _validate_provider(cls, v: str) -> str:
        valid_providers = ("gemini", "perplexity")
        if v not in valid_providers:
            raise ValueError(f"provider must be one of {valid_providers}, got {v}")
        return v

    @field_validator("timeout_s")
    @classmethod
    def _validate_timeout(cls, v: float) -> float:
        if v <= 0:
            raise ValueError(f"timeout_s must be positive, got {v}")
        return v

    @field_validator("max_retries")
    @classmethod
    def _validate_max_retries(cls, v: int) -> int:
        if v < 0:
            raise ValueError(f"max_retries must be non-negative, got {v}")
        return v


class PairVerificationConfig(BaseModel):
    """Configuration for pair verification (Stage 2 of topic selector).
    
    Uses internal LLM (via existing llm_verifier infrastructure) to verify
    that candidate market pairs are truly equivalent for arbitrage purposes.
    """

    min_confidence: float = 0.7
    use_existing_verifier: bool = True  # Use llm_verifier infrastructure
    cache_results: bool = True

    @field_validator("min_confidence")
    @classmethod
    def _validate_min_confidence(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError(f"min_confidence must be in [0.0, 1.0], got {v}")
        return v


class TopicSelectorConfig(BaseModel):
    """Configuration for daily category/topic selector.
    
    Two-stage LLM system for discovering hot topics across Polymarket and Kalshi:
    - Stage 1: Web browsing LLM discovers trending topics on both platforms
    - Stage 2: Internal LLM verifies market pair equivalence for arbitrage
    """

    enabled: bool = False
    execution_time_utc: str = "00:00"  # Daily execution time (HH:MM format)
    output_path: str = "data/daily_hot_topics.json"
    usage_stats_path: str = "data/topic_selector_usage.json"
    prompt_path: str = "data/topic_selector_prompt.txt"
    verification_prompt_path: str = "data/pair_verification_prompt.txt"
    max_hot_topics: int = 10
    default_fallback_category: str = "Politics"
    excluded_categories: List[str] = Field(default_factory=lambda: ["Sports"])

    # Stage 1 config
    llm: WebBrowsingLLMConfig = Field(default_factory=WebBrowsingLLMConfig)

    # Stage 2 config
    verification: PairVerificationConfig = Field(default_factory=PairVerificationConfig)

    # Target URLs
    polymarket_url: str = "polymarket.com"
    kalshi_url: str = "kalshi.com"

    @field_validator("execution_time_utc")
    @classmethod
    def _validate_execution_time(cls, v: str) -> str:
        # Validate HH:MM format
        parts = v.split(":")
        if len(parts) != 2:
            raise ValueError(f"execution_time_utc must be in HH:MM format, got {v}")
        try:
            hour, minute = int(parts[0]), int(parts[1])
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                raise ValueError(f"Invalid time: hour must be 0-23, minute must be 0-59")
        except ValueError as e:
            raise ValueError(f"execution_time_utc must be in HH:MM format, got {v}: {e}")
        return v

    @field_validator("max_hot_topics")
    @classmethod
    def _validate_max_hot_topics(cls, v: int) -> int:
        if v < 1:
            raise ValueError(f"max_hot_topics must be at least 1, got {v}")
        return v


class AppConfig(BaseModel):
    polymarket: PolymarketConfig = Field(default_factory=PolymarketConfig)
    kalshi: KalshiConfig = Field(default_factory=KalshiConfig)
    risk: RiskConfig = Field(default_factory=RiskConfig)
    broker: BrokerConfig = Field(default_factory=BrokerConfig)
    engine: EngineConfig = Field(default_factory=EngineConfig)
    filter: FilterConfig = Field(default_factory=FilterConfig)
    detectors: DetectorConfig = Field(default_factory=DetectorConfig)
    telegram: TelegramConfig = Field(default_factory=TelegramConfig)
    llm_verification: LLMVerificationConfig = Field(default_factory=LLMVerificationConfig)
    cross_venue_matcher: CrossVenueMatcherConfig = Field(default_factory=CrossVenueMatcherConfig)
    watchlist: WatchlistConfig = Field(default_factory=WatchlistConfig)
    cross_venue_detector: CrossVenueDetectorConfig = Field(default_factory=CrossVenueDetectorConfig)
    topic_selector: TopicSelectorConfig = Field(default_factory=TopicSelectorConfig)


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
    # Keep semantic match threshold consistent across retrieval and LLM verification.
    cfg.llm_verification.min_similarity_to_verify = cfg.cross_venue_matcher.min_similarity
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
    # Kalshi environment overrides
    if not cfg.kalshi.api_key_id:
        cfg.kalshi.api_key_id = os.getenv("KALSHI_API_KEY_ID", "")
    if not cfg.kalshi.private_key_pem:
        cfg.kalshi.private_key_pem = os.getenv("KALSHI_PRIVATE_KEY_PEM", "")
    return cfg
