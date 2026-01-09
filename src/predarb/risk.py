from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Set, Tuple

from predarb.config import RiskConfig
from predarb.models import Market, Opportunity

logger = logging.getLogger(__name__)


class RiskManager:
    def __init__(self, config: RiskConfig, broker_state):
        self.config = config
        self.broker_state = broker_state
        # Track sequential approvals within the manager's lifetime to enforce limits
        self._approved_count: int = 0

    def approve(self, market_lookup: Dict[str, Market], opp: Opportunity) -> bool:
        """
        Returns True if the opportunity is safe to execute.
        
        HARD FILTERS (NON-NEGOTIABLE):
        1. DUPLICATE arbitrage completely disabled
        2. No SELL without existing inventory (no short selling)
        3. No same-outcome BUY+SELL combinations
        4. BUY-only strategy enforcement
        5. Minimum edge requirements
        6. Micro-price filter
        7. BUY-side liquidity check
        8. Time-to-expiry filter
        9. Risk limits (allocation, position count)
        10. Hedge logic disabled (implicit - no hedging in strategies)
        """
        
        # ==================== FILTER 1: GLOBAL DISABLE DUPLICATE ==================== #
        if opp.type.upper() == "DUPLICATE":
            logger.info(
                f"REJECTED {opp.type} opportunity: "
                "DUPLICATE arbitrage requires short selling — disabled on this venue."
            )
            return False
        
        # ==================== FILTER 2 & 4: NO SELL-FIRST / BUY-ONLY ENFORCEMENT ==================== #
        # Verify all SELL actions have existing inventory (no short selling allowed)
        # and enforce BUY-only strategy for entries
        for action in opp.actions:
            position_key = f"{action.market_id}:{action.outcome_id}"
            inventory = self.broker_state.positions.get(position_key, 0.0)
            
            if action.side.upper() == "SELL":
                if inventory <= 0:
                    logger.info(
                        f"REJECTED {opp.type} opportunity: "
                        f"SELL required for {action.market_id}:{action.outcome_id} but inventory={inventory}. "
                        "Short selling not supported on this venue."
                    )
                    return False
                # Additional check: SELL amount cannot exceed inventory
                if action.amount > inventory:
                    logger.info(
                        f"REJECTED {opp.type} opportunity: "
                        f"SELL amount {action.amount} exceeds inventory {inventory} for {action.market_id}:{action.outcome_id}."
                    )
                    return False
        
        # ==================== FILTER 3: NO SAME-OUTCOME BUY+SELL ==================== #
        # Check for same (market_id, outcome_id) appearing in both BUY and SELL
        buy_positions: Set[Tuple[str, str]] = set()
        sell_positions: Set[Tuple[str, str]] = set()
        
        for action in opp.actions:
            key = (action.market_id, action.outcome_id)
            if action.side.upper() == "BUY":
                buy_positions.add(key)
            elif action.side.upper() == "SELL":
                sell_positions.add(key)
        
        conflicting_positions = buy_positions.intersection(sell_positions)
        if conflicting_positions:
            logger.info(
                f"REJECTED {opp.type} opportunity: "
                f"Contains both BUY and SELL for same position(s): {conflicting_positions}. "
                "This creates unnecessary round-trips and is forbidden."
            )
            return False
        
        # ==================== FILTER 5: MINIMUM EDGE (BUY-ONLY) ==================== #
        # Enforce minimum gross edge threshold (net edge already accounts for fees/slippage)
        if opp.net_edge < self.config.min_net_edge_threshold:
            logger.info(
                f"REJECTED {opp.type} opportunity: "
                f"Net edge {opp.net_edge:.4f} below threshold {self.config.min_net_edge_threshold:.4f}"
            )
            return False
        
        # Enforce minimum gross edge (5% configurable via min_gross_edge)
        if hasattr(self.config, 'min_gross_edge'):
            gross_edge = getattr(opp, 'gross_edge', opp.net_edge)  # fallback to net_edge if gross not available
            if gross_edge < self.config.min_gross_edge:
                logger.info(
                    f"REJECTED {opp.type} opportunity: "
                    f"Gross edge {gross_edge:.4f} below threshold {self.config.min_gross_edge:.4f}"
                )
                return False
        
        # ==================== FILTER 6: MICRO-PRICE FILTER ==================== #
        # Reject BUY prices below minimum threshold (dust liquidity / fake edge)
        min_buy_price = getattr(self.config, 'min_buy_price', 0.02)
        for action in opp.actions:
            if action.side.upper() == "BUY" and action.limit_price < min_buy_price:
                logger.info(
                    f"REJECTED {opp.type} opportunity: "
                    f"BUY price {action.limit_price:.4f} below minimum {min_buy_price:.4f} (micro-price filter)"
                )
                return False
        
        # ==================== FILTER 7: BUY-SIDE LIQUIDITY CHECK ==================== #
        # Verify orderbook depth >= 3x trade size (no partial fills allowed)
        min_liquidity_multiple = getattr(self.config, 'min_liquidity_multiple_strict', 3.0)
        for action in opp.actions:
            if action.side.upper() == "BUY":
                market = market_lookup.get(action.market_id)
                if not market:
                    logger.info(f"REJECTED {opp.type} opportunity: Market {action.market_id} not found")
                    return False
                
                # Estimate available liquidity for this outcome
                # Use market.liquidity as proxy (assumes even distribution across outcomes)
                per_outcome_liquidity = market.liquidity / max(len(market.outcomes), 1)
                required_liquidity = action.limit_price * action.amount * min_liquidity_multiple
                
                if per_outcome_liquidity < required_liquidity:
                    logger.info(
                        f"REJECTED {opp.type} opportunity: "
                        f"Insufficient BUY-side liquidity for {action.market_id}:{action.outcome_id}. "
                        f"Available: ${per_outcome_liquidity:.2f}, Required: ${required_liquidity:.2f} "
                        f"(3x trade size: ${action.limit_price * action.amount:.2f})"
                    )
                    return False
        
        # ==================== FILTER 9: TIME-TO-EXPIRY FILTER ==================== #
        # Reject if time to expiry < MIN_EXPIRY_HOURS (default 24h)
        min_expiry_hours = getattr(self.config, 'min_expiry_hours', 24)
        if min_expiry_hours > 0:
            for mid in opp.market_ids:
                market = market_lookup.get(mid)
                if market and market.end_date:
                    time_to_expiry = market.end_date - datetime.utcnow()
                    if time_to_expiry < timedelta(hours=min_expiry_hours):
                        logger.info(
                            f"REJECTED {opp.type} opportunity: "
                            f"Market {mid} expires in {time_to_expiry.total_seconds()/3600:.1f}h, "
                            f"below minimum {min_expiry_hours}h"
                        )
                        return False
        
        # ==================== FILTER 10: EXISTING RISK LIMITS ==================== #
        # max open positions (include approvals made in this session to handle sequential checks)
        open_pos = sum(1 for qty in self.broker_state.positions.values() if qty != 0)
        tentative_open = open_pos + self._approved_count
        if tentative_open >= self.config.max_open_positions:
            logger.info(
                f"REJECTED {opp.type} opportunity: "
                f"Max open positions reached ({tentative_open} >= {self.config.max_open_positions})"
            )
            return False
        
        # liquidity check per market
        for mid in opp.market_ids:
            market = market_lookup.get(mid)
            if not market:
                continue
            if market.liquidity < self.config.min_liquidity_usd:
                logger.info(
                    f"REJECTED {opp.type} opportunity: "
                    f"Market {mid} liquidity ${market.liquidity:.2f} below threshold ${self.config.min_liquidity_usd:.2f}"
                )
                return False
        
        # allocation check
        total_equity = self.broker_state.cash
        for key, qty in self.broker_state.positions.items():
            if qty == 0:
                continue
            # Split on first colon only - outcome_id may contain colons
            parts = key.split(":", 1)
            if len(parts) != 2:
                continue
            mid, oid = parts
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
            logger.info(
                f"REJECTED {opp.type} opportunity: "
                f"Estimated cost ${est_cost:.2f} exceeds max allocation ${max_per_market:.2f}"
            )
            return False
        
        # ==================== ALL FILTERS PASSED ==================== #
        # Passed all checks; increment session approval count
        self._approved_count += 1
        logger.info(f"APPROVED {opp.type} opportunity: {opp.description}")
        return True
