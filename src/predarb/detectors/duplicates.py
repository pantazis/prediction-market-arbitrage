from __future__ import annotations

from typing import List

from predarb.config import DetectorConfig
from predarb.matchers import cluster_duplicates
from predarb.models import Market, Opportunity, TradeAction


class DuplicateDetector:
    def __init__(self, config: DetectorConfig):
        self.config = config

    def detect(self, markets: List[Market]) -> List[Opportunity]:
        opps: List[Opportunity] = []
        pairs = cluster_duplicates(markets)
        for m1, m2 in pairs:
            p1 = m1.outcome_by_label("yes") or m1.outcomes[0]
            p2 = m2.outcome_by_label("yes") or m2.outcomes[0]
            diff = abs(p1.price - p2.price)
            if diff < self.config.duplicate_price_diff_threshold:
                continue
            better, worse = (m1, m2) if p1.price > p2.price else (m2, m1)
            # Format description with % and $ for better readability
            price1_pct = p1.price * 100
            price2_pct = p2.price * 100
            gap_pct = diff * 100
            gain_per_100 = diff * 100
            description = f"Duplicate: {price1_pct:.1f}% vs {price2_pct:.1f}% (gap: {gap_pct:.1f}%, ${gain_per_100:.2f}/$100)"
            
            opps.append(
                Opportunity(
                    type="DUPLICATE",
                    market_ids=[m1.id, m2.id],
                    description=description,
                    net_edge=diff,
                    actions=[
                        TradeAction(market_id=better.id, outcome_id=better.outcomes[0].id, side="SELL", amount=1.0, limit_price=better.outcomes[0].price),
                        TradeAction(market_id=worse.id, outcome_id=worse.outcomes[0].id, side="BUY", amount=1.0, limit_price=worse.outcomes[0].price),
                    ],
                    metadata={"price_diff": diff},
                )
            )
        return opps
