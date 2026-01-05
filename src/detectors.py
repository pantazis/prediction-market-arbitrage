from typing import List, Optional
from src.models import Market, Opportunity, TradeAction
import logging
import re

logger = logging.getLogger(__name__)

def detect_parity_arb(market: Market) -> List[Opportunity]:
    """
    Detects if sum of YES + NO prices deviates significantly from 1.0 such that
    buying both is cheaper than 1.0 (indicating guaranteed profit if held to expiry).
    
    If YES + NO < 1.0 - fees, we buy both.
    """
    if len(market.outcomes) != 2:
        return []

    # Identify YES/NO outcomes (simplified)
    # usually outcomes are ["No", "Yes"] or similar
    
    yes_outcome = market.get_outcome_by_label("Yes")
    no_outcome = market.get_outcome_by_label("No")
    
    if not yes_outcome or not no_outcome:
        # Try generic index if labels fail (often 0 is No, 1 is Yes)
        # But for safety, strictly look for labels or specific known structures
        return []

    p_yes = yes_outcome.price
    p_no = no_outcome.price
    
    # We strictly look for "Buy both cheaper than payout"
    # Cost = p_yes + p_no
    # Payout = 1.0
    # Profit = 1.0 - Cost
    
    cost = p_yes + p_no
    
    # Simple threshold, raw detection here. Fees applied later or in config threshold check.
    if cost < 0.99: # Arbitrary raw filter
        edge = 1.0 - cost
        return [Opportunity(
            market_id=market.id,
            market_title=market.question,
            type_name="PARITY",
            description=f"Yes({p_yes}) + No({p_no}) = {cost:.3f} < 1.0",
            estimated_edge=edge,
            required_capital=cost, # normalized unit cost
            actions=[
                TradeAction(market.id, yes_outcome.id, "BUY", 1.0, p_yes),
                TradeAction(market.id, no_outcome.id, "BUY", 1.0, p_no)
            ]
        )]
    
    return []

def extract_ladder_info(market: Market) -> Optional[dict]:
    # Regex to extract "Asset > X on Date"
    # Example: "Bitcoin > $100,000 on Dec 31 2024"
    # This is complex/brittle, so kept simple for Phase 1
    # We look for simple numeric extraction if Title contains ">" or "<"
    return None # Placeholder for complex logic, implemented in next step if easy, or skipped for MVP reliability

def detect_opportunities(markets: List[Market]) -> List[Opportunity]:
    opps = []
    for m in markets:
        opps.extend(detect_parity_arb(m))
    return opps
