from typing import List, Dict
from src.models import Opportunity, Trade, TradeAction
from src.config import BrokerConfig
from datetime import datetime
import uuid
import logging

logger = logging.getLogger(__name__)

class PaperBroker:
    def __init__(self, config: BrokerConfig):
        self.config = config
        self.cash = config.initial_cash
        self.positions: Dict[str, float] = {} # outcome_id -> amount
        self.trades: List[Trade] = []

    def execute_opportunity(self, opportunity: Opportunity) -> List[Trade]:
        executed_trades = []
        
        # Calculate sizing (simplified: use fixed capital per opp, or min of required)
        # Using a fixed size from logic for now, or defaulting to $10 stake roughly
        # In real bot this is complex. Here, assumes opportunity.actions has raw 1.0 amounts
        # We assume we want to put e.g. $10 into the trade.
        
        trade_size_dollars = 10.0
        
        # Calculate cost per unit
        unit_cost = sum(a.max_price for a in opportunity.actions if a.side == 'BUY')
        if unit_cost <= 0: return []
        
        quantity = trade_size_dollars / unit_cost
        
        # Check if we have enough cash
        total_cost = quantity * unit_cost
        if total_cost > self.cash:
            logger.warning(f"Not enough cash for trade. Needed {total_cost}, have {self.cash}")
            return []

        # Execute
        for action in opportunity.actions:
            trade = self._execute_action(action, quantity)
            if trade:
                executed_trades.append(trade)
                
        return executed_trades

    def _execute_action(self, action: TradeAction, quantity: float) -> Trade:
        # Simulate slippage
        # Price increases by slippage_bps for buys
        slippage_mult = 1.0 + (self.config.slippage_bps / 10000.0) if action.side == 'BUY' else 1.0 - (self.config.slippage_bps / 10000.0)
        
        execution_price = action.max_price * slippage_mult
        
        # Calculate fees
        fee_rate = self.config.fee_bps / 10000.0
        cost = execution_price * quantity
        fees = cost * fee_rate
        
        total_cost = cost + fees # For buy
        
        if action.side == 'BUY':
            self.cash -= total_cost
            self.positions[action.outcome_id] = self.positions.get(action.outcome_id, 0.0) + quantity
        
        t = Trade(
            id=str(uuid.uuid4()),
            timestamp=datetime.now(),
            market_id=action.market_id,
            outcome_id=action.outcome_id,
            side=action.side,
            amount=quantity,
            price=execution_price,
            fees=fees
        )
        self.trades.append(t)
        return t

    def get_portfolio_value(self) -> float:
        # Simple mark-to-market is hard without live prices updates on positions
        # For now just return cash + cost basis of positions (very rough) or just cash
        return self.cash # Placeholder
