from __future__ import annotations

from typing import List

from predarb.config import DetectorConfig
from predarb.models import Market, Opportunity, TradeAction


class ExclusiveSumDetector:
    def __init__(self, config: DetectorConfig):
        self.config = config

    def detect(self, markets: List[Market]) -> List[Opportunity]:
        opps: List[Opportunity] = []
        for m in markets:
            if len(m.outcomes) < 3:
                continue
            total = m.outcome_sum
            deviation = abs(1.0 - total)
            if deviation <= self.config.exclusive_sum_tolerance:
                continue
            direction = "BUY" if total < 1.0 else "SELL"
            actions = [
                TradeAction(
                    market_id=m.id,
                    outcome_id=o.id,
                    side=direction,
                    amount=1.0 / len(m.outcomes),
                    limit_price=o.price,
                )
                for o in m.outcomes
            ]
            opps.append(
                Opportunity(
                    type="EXCLUSIVE_SUM",
                    market_ids=[m.id],
                    description=f"Outcome sum {total:.3f} deviates from 1",
                    net_edge=deviation,
                    actions=actions,
                    metadata={"total": total},
                )
            )
        return opps
