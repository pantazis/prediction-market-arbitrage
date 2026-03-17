from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator, ConfigDict

from predarb.extractors import extract_entity, extract_threshold


class Outcome(BaseModel):
    id: str
    label: str
    price: float
    liquidity: float = 0.0
    last_updated: Optional[datetime] = None

    @field_validator("price")
    @classmethod
    def _valid_price(cls, v: float) -> float:
        if v is None or v != v:  # NaN
            raise ValueError("price must be real number")
        if v < 0 or v > 1:
            raise ValueError("price must be between 0 and 1")
        return float(v)


class Market(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="allow")

    id: str = Field(alias="market_id")
    question: str = Field(alias="title")
    outcomes: List[Outcome]
    end_date: Optional[datetime] = Field(default=None, alias="end_time")
    liquidity: Optional[float] = Field(default=0.0, alias="liquidity_usd")
    volume: Optional[float] = Field(default=0.0, alias="volume_24h_usd")
    tags: List[str] = Field(default_factory=list)
    resolution_source: Optional[str] = None
    description: Optional[str] = Field(default=None, alias="resolution_rules")
    best_bid: Dict[str, float] = Field(default_factory=dict)
    best_ask: Dict[str, float] = Field(default_factory=dict)
    
    # New Metadata for Category-First Matching
    series_id: Optional[str] = None  # e.g. "GT-CPI" or "fed-rates"
    category: Optional[str] = None   # e.g. "Economics", "Sports"
    slug: Optional[str] = None       # e.g. "inflation-jan-2025"
    
    trades_1h: Optional[int] = None
    updated_at: Optional[datetime] = None
    
    # Exchange identifier (set by client: "polymarket", "kalshi", etc.)
    exchange: Optional[str] = None

    # extracted / normalized fields
    comparator: Optional[str] = None
    threshold: Optional[float] = None
    asset: Optional[str] = None
    expiry: Optional[datetime] = None

    @model_validator(mode="before")
    @classmethod
    def _coerce_input(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        data = data.copy()

        # Support legacy keys
        if "market_id" in data and "id" not in data:
            data["id"] = data["market_id"]
        if "title" in data and "question" not in data:
            data["question"] = data["title"]
        if "end_time" in data and "end_date" not in data:
            data["end_date"] = data["end_time"]
        if "liquidity_usd" in data and "liquidity" not in data:
            data["liquidity"] = data["liquidity_usd"]
        if "volume_24h_usd" in data and "volume" not in data:
            data["volume"] = data["volume_24h_usd"]
        if "resolution_rules" in data and "description" not in data:
            data["description"] = data["resolution_rules"]
        if data.get("liquidity") is None:
            data["liquidity"] = 0.0
        if data.get("volume") is None:
            data["volume"] = 0.0

        outcomes = data.get("outcomes")
        best_bid = data.get("best_bid") or {}
        best_ask = data.get("best_ask") or {}
        if outcomes and all(isinstance(o, str) for o in outcomes):
            converted: List[Dict[str, object]] = []
            for label in outcomes:
                bid = best_bid.get(label)
                ask = best_ask.get(label)
                if bid is not None and ask is not None:
                    price = (bid + ask) / 2
                elif bid is not None:
                    price = bid
                elif ask is not None:
                    price = ask
                else:
                    price = 0.0
                converted.append({"id": label.lower(), "label": label, "price": price})
            data["outcomes"] = converted
        return data

    @field_validator("outcomes")
    @classmethod
    def _nonempty_outcomes(cls, v: List[Outcome]) -> List[Outcome]:
        if not v:
            raise ValueError("market requires outcomes")
        return v

    @model_validator(mode="after")
    def _ensure_defaults(self) -> "Market":
        if self.volume is None:
            object.__setattr__(self, "volume", 0.0)
        if self.liquidity is None:
            object.__setattr__(self, "liquidity", 0.0)
        if self.best_bid is None:
            object.__setattr__(self, "best_bid", {})
        if self.best_ask is None:
            object.__setattr__(self, "best_ask", {})
        if self.comparator is None or self.threshold is None:
            comp, thr = extract_threshold(self.question)
            if self.comparator is None and comp is not None:
                object.__setattr__(self, "comparator", comp)
            if self.threshold is None and thr is not None:
                object.__setattr__(self, "threshold", thr)
        if self.asset is None:
            entity = extract_entity(self.question)
            if entity:
                object.__setattr__(self, "asset", entity)
        if self.expiry is None and self.end_date is not None:
            object.__setattr__(self, "expiry", self.end_date)
        return self

    def outcome_by_label(self, label: str) -> Optional[Outcome]:
        for o in self.outcomes:
            if o.label.lower() == label.lower():
                return o
        return None

    @property
    def market_id(self) -> str:
        return self.id

    @property
    def title(self) -> str:
        return self.question

    @property
    def outcome_sum(self) -> float:
        return float(sum(o.price for o in self.outcomes))


@dataclass
class NormalizedMarket:
    """Unified market representation with normalized prices.

    This dataclass provides a common format for comparing markets across
    different venues (Polymarket, Kalshi). All prices are normalized to
    the [0.0-1.0] probability range.

    Attributes:
        market_id: Unique identifier for the market
        exchange: Exchange name ("kalshi" or "polymarket")
        question: Market question/title
        yes_bid: Best bid price for YES outcome [0.0-1.0]
        yes_ask: Best ask price for YES outcome [0.0-1.0]
        no_bid: Best bid price for NO outcome [0.0-1.0]
        no_ask: Best ask price for NO outcome [0.0-1.0]
        liquidity_usd: Available liquidity in USD
        updated_at: Timestamp of last price update (for staleness checking)
        original: Reference to the original Market object
        is_tradeable: Whether the market can be traded
        non_tradeable_reason: Reason if market is not tradeable
    """
    market_id: str
    exchange: str  # "kalshi" or "polymarket"
    question: str

    # Normalized prices in [0.0-1.0] range
    yes_bid: float
    yes_ask: float
    no_bid: float
    no_ask: float

    # Liquidity in USD
    liquidity_usd: float

    # Timestamp for staleness checking
    updated_at: Optional[datetime] = None

    # Original market reference
    original: Optional["Market"] = None

    # Tradeable flag
    is_tradeable: bool = True
    non_tradeable_reason: Optional[str] = None


@dataclass
class TradeAction:
    market_id: str
    outcome_id: str
    side: str  # BUY or SELL
    amount: float
    limit_price: float


@dataclass
class Opportunity:
    type: str
    market_ids: List[str]
    description: str
    net_edge: float
    actions: List[TradeAction]
    metadata: Dict[str, object] = field(default_factory=dict)
    detected_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class Trade:
    id: str
    timestamp: datetime
    market_id: str
    outcome_id: str
    side: str
    amount: float
    price: float
    fees: float
    slippage: float
    realized_pnl: float
