from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


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
    id: str
    question: str
    outcomes: List[Outcome]
    end_date: Optional[datetime] = None
    liquidity: float = 0.0
    volume: float = 0.0
    tags: List[str] = Field(default_factory=list)
    resolution_source: Optional[str] = None
    description: Optional[str] = None

    # extracted / normalized fields
    comparator: Optional[str] = None
    threshold: Optional[float] = None
    asset: Optional[str] = None
    expiry: Optional[datetime] = None

    @field_validator("outcomes")
    @classmethod
    def _nonempty_outcomes(cls, v: List[Outcome]) -> List[Outcome]:
        if not v:
            raise ValueError("market requires outcomes")
        return v

    def outcome_by_label(self, label: str) -> Optional[Outcome]:
        for o in self.outcomes:
            if o.label.lower() == label.lower():
                return o
        return None

    @property
    def outcome_sum(self) -> float:
        return float(sum(o.price for o in self.outcomes))


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
