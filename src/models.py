from __future__ import annotations
from dataclasses import dataclass, field
from decimal import Decimal
from typing import List, Optional
from datetime import datetime

@dataclass
class Outcome:
    """Represents a single outcome in a prediction market (e.g., 'Yes' or 'No')."""
    id: str
    label: str
    price: float
    
    @property
    def price_decimal(self) -> Decimal:
        return Decimal(str(self.price))

@dataclass
class Market:
    """Represents a prediction market."""
    id: str
    question: str
    outcomes: List[Outcome]
    end_date: Optional[datetime]
    liquidity: float
    volume: float
    description: str = ""
    # For numeric markets
    asset: Optional[str] = None
    target_date: Optional[str] = None
    threshold: Optional[float] = None
    comparator: Optional[str] = None  # '>' or '<'

    def get_outcome_by_label(self, label: str) -> Optional[Outcome]:
        for o in self.outcomes:
            if o.label == label:
                return o
        return None

@dataclass
class Opportunity:
    """Represents a detected arbitrage opportunity."""
    market_id: str
    market_title: str
    type_name: str  # 'PARITY' or 'LADDER'
    description: str
    estimated_edge: float  # Absolute edge (e.g. 0.05 for 5%)
    required_capital: float
    actions: List[TradeAction]
    timestamp: datetime = field(default_factory=datetime.now)

@dataclass
class TradeAction:
    """A specific action to take as part of an opportunity."""
    market_id: str
    outcome_id: str
    side: str  # 'BUY' or 'SELL'
    amount: float
    max_price: float

@dataclass
class Trade:
    """Record of an executed trade."""
    id: str
    timestamp: datetime
    market_id: str
    outcome_id: str
    side: str
    amount: float
    price: float
    fees: float
