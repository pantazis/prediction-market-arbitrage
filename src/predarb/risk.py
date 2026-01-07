from __future__ import annotations

from typing import Dict, List

from predarb.config import RiskConfig
from predarb.models import Market, Opportunity


class RiskManager:
    def __init__(self, config: RiskConfig, broker_state):
        self.config = config
        self.broker_state = broker_state
        # Track sequential approvals within the manager's lifetime to enforce limits
        self._approved_count: int = 0

    def approve(self, market_lookup: Dict[str, Market], opp: Opportunity) -> bool:
        # min edge
        if opp.net_edge < self.config.min_net_edge_threshold:
            return False
        # max open positions (include approvals made in this session to handle sequential checks)
        open_pos = sum(1 for qty in self.broker_state.positions.values() if qty != 0)
        tentative_open = open_pos + self._approved_count
        if tentative_open >= self.config.max_open_positions:
            return False
        # liquidity check per market
        for mid in opp.market_ids:
            market = market_lookup.get(mid)
            if not market:
                continue
            if market.liquidity < self.config.min_liquidity_usd:
                return False
        # allocation check
        total_equity = self.broker_state.cash
        for key, qty in self.broker_state.positions.items():
            if qty == 0:
                continue
            mid, oid = key.split(":")
            market = market_lookup.get(mid)
            if not market:
                continue
            outcome = next((o for o in market.outcomes if o.id == oid), None)
            if not outcome:
                continue
            total_equity += qty * outcome.price
        max_per_market = total_equity * self.config.max_allocation_per_market
        est_cost = sum(a.limit_price * a.amount for a in opp.actions)
        if est_cost > max_per_market:
            return False
        # Passed all checks; increment session approval count
        self._approved_count += 1
        return True
