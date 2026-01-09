from __future__ import annotations

import math
import uuid
from datetime import datetime
from typing import Dict, List

from predarb.config import BrokerConfig
from predarb.models import Market, Opportunity, Trade, TradeAction


class PaperBroker:
    def __init__(self, config: BrokerConfig):
        self.config = config
        self.cash = config.initial_cash
        self.positions: Dict[str, float] = {}
        # Track average cost basis per position (price-only, excludes fees/slippage)
        self.avg_cost: Dict[str, float] = {}
        self.trades: List[Trade] = []
        self.equity_curve: List[float] = [self.cash]

    def _available_liquidity(self, market: Market, action: TradeAction) -> float:
        # Simple deterministic liquidity model: proportional to market liquidity and depth fraction
        per_outcome_liq = market.liquidity * self.config.depth_fraction / max(len(market.outcomes), 1)
        max_qty = per_outcome_liq / max(action.limit_price, 1e-6)
        return max_qty

    def execute(self, market_lookup: Dict[str, Market], opportunity: Opportunity) -> List[Trade]:
        """Execute trades for an opportunity.
        
        MANDATORY INVARIANT CHECK (FAIL-FAST):
        No SELL action is allowed unless reducing an existing position.
        This prevents short selling attempts from reaching execution.
        """
        trades: List[Trade] = []
        
        # ==================== MANDATORY INVARIANT: NO SELL WITHOUT POSITION ==================== #
        for action in opportunity.actions:
            if action.side.upper() == "SELL":
                position_key = f"{action.market_id}:{action.outcome_id}"
                inventory = self.positions.get(position_key, 0.0)
                if inventory <= 0:
                    error_msg = (
                        f"FATAL INVARIANT VIOLATION: SELL action reached execution without position! "
                        f"Market: {action.market_id}, Outcome: {action.outcome_id}, "
                        f"Inventory: {inventory}, Requested: {action.amount}. "
                        f"Short selling is FORBIDDEN on this venue. This should have been blocked by RiskManager."
                    )
                    raise RuntimeError(error_msg)
                if action.amount > inventory:
                    error_msg = (
                        f"FATAL INVARIANT VIOLATION: SELL amount exceeds position! "
                        f"Market: {action.market_id}, Outcome: {action.outcome_id}, "
                        f"Inventory: {inventory}, Requested: {action.amount}. "
                        f"Cannot sell more than owned. This should have been blocked by RiskManager."
                    )
                    raise RuntimeError(error_msg)
        
        for action in opportunity.actions:
            market = market_lookup.get(action.market_id)
            if not market:
                continue
            max_qty = self._available_liquidity(market, action)
            qty = min(action.amount, max_qty)
            if qty <= 0:
                continue
            fee = action.limit_price * qty * (self.config.fee_bps / 10_000)
            slippage = action.limit_price * qty * (self.config.slippage_bps / 10_000)
            cost = action.limit_price * qty + fee + slippage
            if action.side.upper() == "BUY":
                if cost > self.cash:
                    continue
                self.cash -= cost
                position_key = f"{action.market_id}:{action.outcome_id}"
                self.positions[position_key] = self.positions.get(position_key, 0.0) + qty
                # Update weighted average cost basis (price-only)
                prev_qty = self.positions.get(position_key, 0.0) - qty
                prev_cost = self.avg_cost.get(position_key, 0.0)
                new_total_qty = prev_qty + qty
                if new_total_qty > 0:
                    weighted = (prev_cost * prev_qty + action.limit_price * qty) / new_total_qty
                    self.avg_cost[position_key] = weighted
                else:
                    self.avg_cost[position_key] = action.limit_price
                pnl = -cost
            else:  # SELL
                position_key = f"{action.market_id}:{action.outcome_id}"
                held = self.positions.get(position_key, 0.0)
                # Allow short selling: qty is NOT limited by held position
                # qty = min(qty, held)  # REMOVED: This prevented short selling
                if qty <= 0:
                    continue
                proceeds = action.limit_price * qty - fee - slippage
                self.cash += proceeds
                self.positions[position_key] = held - qty  # Can go negative (short position)
                # Update cost basis for short positions
                if self.positions[position_key] == 0.0:
                    self.avg_cost.pop(position_key, None)
                elif held <= 0:  # Opening or adding to short position
                    prev_cost = self.avg_cost.get(position_key, 0.0)
                    if held < 0:  # Already short, weighted average
                        weighted = (prev_cost * abs(held) + action.limit_price * qty) / abs(held - qty)
                        self.avg_cost[position_key] = weighted
                    else:  # New short position
                        self.avg_cost[position_key] = action.limit_price
                pnl = proceeds
            trade = Trade(
                id=str(uuid.uuid4()),
                timestamp=datetime.utcnow(),
                market_id=action.market_id,
                outcome_id=action.outcome_id,
                side=action.side.upper(),
                amount=qty,
                price=action.limit_price,
                fees=fee,
                slippage=slippage,
                realized_pnl=pnl,
            )
            trades.append(trade)
            self.trades.append(trade)
            self.equity_curve.append(self.cash + self._unrealized_pnl(market_lookup))
        return trades

    def _unrealized_pnl(self, market_lookup: Dict[str, Market]) -> float:
        pnl = 0.0
        for key, qty in self.positions.items():
            if qty == 0:
                continue
            market_id, outcome_id = key.split(":")
            market = market_lookup.get(market_id)
            if not market:
                continue
            outcome = next((o for o in market.outcomes if o.id == outcome_id), None)
            if not outcome:
                continue
            # Mark-to-market against average cost basis (price-only)
            cost_basis = self.avg_cost.get(key, outcome.price)
            pnl += qty * (outcome.price - cost_basis)
        return pnl

    # --- Hedge helpers (simulation safety) ---
    def get_position_qty(self, market_id: str, outcome_id: str) -> float:
        """Return current held quantity for a given market/outcome (0.0 if none)."""
        return self.positions.get(f"{market_id}:{outcome_id}", 0.0)

    def _mark_price(self, market_lookup: Dict[str, Market], market_id: str, outcome_id: str) -> float:
        """Get current mark price for outcome; fallback to average cost if missing."""
        market = market_lookup.get(market_id)
        if market:
            outcome = next((o for o in market.outcomes if o.id == outcome_id), None)
            if outcome:
                return float(outcome.price)
        return float(self.avg_cost.get(f"{market_id}:{outcome_id}", 0.0))

    def close_position(
        self,
        market_lookup: Dict[str, Market],
        market_id: str,
        outcome_id: str,
        qty: float | None = None,
    ) -> List[Trade]:
        """Simulate closing a position (long or short). If qty is None, closes all.
        
        For long positions (qty > 0): SELL to close
        For short positions (qty < 0): BUY to close
        
        Returns list of execution trades produced by the close.
        """
        key = f"{market_id}:{outcome_id}"
        held = self.positions.get(key, 0.0)
        if held == 0:
            return []
        
        # Determine close quantity and side
        if held > 0:  # Long position: SELL to close
            close_qty = held if qty is None else min(qty, held)
            side = "SELL"
        else:  # Short position: BUY to close
            close_qty = abs(held) if qty is None else min(qty, abs(held))
            side = "BUY"
        
        price = self._mark_price(market_lookup, market_id, outcome_id)
        action = TradeAction(market_id=market_id, outcome_id=outcome_id, side=side, amount=close_qty, limit_price=price)
        opp = Opportunity(type="HEDGE", market_ids=[market_id], description="hedge_close", net_edge=0.0, actions=[action])
        return self.execute(market_lookup, opp)

    def flatten_all(self, market_lookup: Dict[str, Market]) -> List[Trade]:
        """Close all open positions across all markets/outcomes (both long and short)."""
        hedges: List[Trade] = []
        for key, qty in list(self.positions.items()):
            if qty == 0:
                continue
            mid, oid = key.split(":")
            hedges.extend(self.close_position(market_lookup, mid, oid, abs(qty)))
        return hedges
