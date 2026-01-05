"""
Core state management for the arbitrage bot.

Defines data classes and enums for tracking:
- Bot operational state (STOPPED, RUNNING, PAUSED)
- Operating mode (live, paper, scan-only)
- Inventory and positions
- PnL tracking
- Risk limits and utilization
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set
from datetime import datetime
import json


class BotState(Enum):
    """Bot operational state machine."""
    STOPPED = "stopped"
    RUNNING = "running"
    PAUSED = "paused"


class OperatingMode(Enum):
    """Bot operating modes."""
    LIVE = "live"
    PAPER = "paper"
    SCAN_ONLY = "scan-only"


@dataclass
class OpenPosition:
    """Represents an open arbitrage position."""
    position_id: str
    event_id: str
    outcome_a: str
    outcome_b: str
    venue_a: str
    venue_b: str
    size: float
    entry_price_a: float
    entry_price_b: float
    entry_time: datetime
    hedge_status: str  # "open", "hedged", "closing"
    unrealized_pnl: float = 0.0
    
    def to_dict(self) -> dict:
        return {
            "position_id": self.position_id,
            "event_id": self.event_id,
            "outcome_a": self.outcome_a,
            "outcome_b": self.outcome_b,
            "venue_a": self.venue_a,
            "venue_b": self.venue_b,
            "size": self.size,
            "entry_price_a": self.entry_price_a,
            "entry_price_b": self.entry_price_b,
            "entry_time": self.entry_time.isoformat(),
            "hedge_status": self.hedge_status,
            "unrealized_pnl": self.unrealized_pnl,
        }


@dataclass
class OutstandingOrder:
    """Represents an outstanding order."""
    order_id: str
    position_id: str
    venue: str
    outcome: str
    size: float
    price: float
    side: str  # "buy" or "sell"
    created_at: datetime
    status: str  # "pending", "partial", "filled", "canceled"
    filled_qty: float = 0.0
    
    def to_dict(self) -> dict:
        return {
            "order_id": self.order_id,
            "position_id": self.position_id,
            "venue": self.venue,
            "outcome": self.outcome,
            "size": self.size,
            "price": self.price,
            "side": self.side,
            "created_at": self.created_at.isoformat(),
            "status": self.status,
            "filled_qty": self.filled_qty,
        }


@dataclass
class RiskLimits:
    """Risk limit configuration."""
    max_position_size: float = 10000.0
    max_inventory_usdc: float = 100000.0
    max_exposure_per_event: float = 50000.0
    max_concurrent_positions: int = 10
    daily_loss_limit: float = 5000.0
    
    def to_dict(self) -> dict:
        return {
            "max_position_size": self.max_position_size,
            "max_inventory_usdc": self.max_inventory_usdc,
            "max_exposure_per_event": self.max_exposure_per_event,
            "max_concurrent_positions": self.max_concurrent_positions,
            "daily_loss_limit": self.daily_loss_limit,
        }


@dataclass
class BotStats:
    """Aggregated bot statistics."""
    uptime_seconds: float = 0.0
    last_scan_time: Optional[datetime] = None
    last_opportunity_time: Optional[datetime] = None
    opportunities_found: int = 0
    opportunities_executed: int = 0
    opportunities_skipped: int = 0
    total_trades: int = 0
    error_count: int = 0
    last_error: Optional[str] = None
    
    def to_dict(self) -> dict:
        return {
            "uptime_seconds": self.uptime_seconds,
            "last_scan_time": self.last_scan_time.isoformat() if self.last_scan_time else None,
            "last_opportunity_time": self.last_opportunity_time.isoformat() if self.last_opportunity_time else None,
            "opportunities_found": self.opportunities_found,
            "opportunities_executed": self.opportunities_executed,
            "opportunities_skipped": self.opportunities_skipped,
            "total_trades": self.total_trades,
            "error_count": self.error_count,
            "last_error": self.last_error,
        }


@dataclass
class PnLSnapshot:
    """Point-in-time PnL snapshot."""
    timestamp: datetime
    realized_pnl: float
    unrealized_pnl: float
    fees_paid: float
    slippage_estimate: float
    
    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "realized_pnl": self.realized_pnl,
            "unrealized_pnl": self.unrealized_pnl,
            "fees_paid": self.fees_paid,
            "slippage_estimate": self.slippage_estimate,
        }


@dataclass
class BotSnapshot:
    """Complete bot state snapshot."""
    timestamp: datetime
    bot_state: BotState
    operating_mode: OperatingMode
    
    # Inventory
    usdc_available: float = 0.0
    usdc_reserved: float = 0.0
    
    # Positions and orders
    open_positions: List[OpenPosition] = field(default_factory=list)
    outstanding_orders: List[OutstandingOrder] = field(default_factory=list)
    
    # Exposures
    exposures_by_event: Dict[str, float] = field(default_factory=dict)
    exposures_by_venue: Dict[str, float] = field(default_factory=dict)
    
    # Freezes
    frozen_events: Set[str] = field(default_factory=set)
    frozen_venues: Set[str] = field(default_factory=set)
    frozen_all: bool = False
    
    # PnL
    pnl_snapshot: Optional[PnLSnapshot] = None
    
    # Stats
    stats: BotStats = field(default_factory=BotStats)
    
    # Risk
    risk_limits: RiskLimits = field(default_factory=RiskLimits)
    risk_limit_breached: Optional[str] = None
    
    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "bot_state": self.bot_state.value,
            "operating_mode": self.operating_mode.value,
            "usdc_available": self.usdc_available,
            "usdc_reserved": self.usdc_reserved,
            "open_positions": [p.to_dict() for p in self.open_positions],
            "outstanding_orders": [o.to_dict() for o in self.outstanding_orders],
            "exposures_by_event": self.exposures_by_event,
            "exposures_by_venue": self.exposures_by_venue,
            "frozen_events": list(self.frozen_events),
            "frozen_venues": list(self.frozen_venues),
            "frozen_all": self.frozen_all,
            "pnl_snapshot": self.pnl_snapshot.to_dict() if self.pnl_snapshot else None,
            "stats": self.stats.to_dict(),
            "risk_limits": self.risk_limits.to_dict(),
            "risk_limit_breached": self.risk_limit_breached,
        }

    def to_json(self) -> str:
        """Serialize to JSON."""
        return json.dumps(self.to_dict(), indent=2)


@dataclass
class Opportunity:
    """Represents a detected arbitrage opportunity."""
    opportunity_id: str
    event_id: str
    market_slug: str
    outcome_a: str
    outcome_b: str
    venue_a: str
    venue_b: str
    price_a: float
    price_b: float
    edge_pct: float
    liquidity_a: float
    liquidity_b: float
    estimated_cost: float
    detected_at: datetime
    decision: str  # "taken", "skipped", "failed"
    decision_reason: str = ""
    
    def to_dict(self) -> dict:
        return {
            "opportunity_id": self.opportunity_id,
            "event_id": self.event_id,
            "market_slug": self.market_slug,
            "outcome_a": self.outcome_a,
            "outcome_b": self.outcome_b,
            "venue_a": self.venue_a,
            "venue_b": self.venue_b,
            "price_a": self.price_a,
            "price_b": self.price_b,
            "edge_pct": self.edge_pct,
            "liquidity_a": self.liquidity_a,
            "liquidity_b": self.liquidity_b,
            "estimated_cost": self.estimated_cost,
            "detected_at": self.detected_at.isoformat(),
            "decision": self.decision,
            "decision_reason": self.decision_reason,
        }
