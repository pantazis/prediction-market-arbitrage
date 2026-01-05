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
        self.trades: List[Trade] = []
        self.equity_curve: List[float] = [self.cash]

    def _available_liquidity(self, market: Market, action: TradeAction) -> float:
        # Simple deterministic liquidity model: proportional to market liquidity and depth fraction
        per_outcome_liq = market.liquidity * self.config.depth_fraction / max(len(market.outcomes), 1)
        max_qty = per_outcome_liq / max(action.limit_price, 1e-6)
        return max_qty

    def execute(self, market_lookup: Dict[str, Market], opportunity: Opportunity) -> List[Trade]:
        trades: List[Trade] = []
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
                pnl = -cost
            else:
                position_key = f"{action.market_id}:{action.outcome_id}"
                held = self.positions.get(position_key, 0.0)
                qty = min(qty, held)
                if qty <= 0:
                    continue
                proceeds = action.limit_price * qty - fee - slippage
                self.cash += proceeds
                self.positions[position_key] = held - qty
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
            pnl += qty * outcome.price
        return pnl
