from __future__ import annotations

from typing import List

from predarb.config import BrokerConfig, DetectorConfig
from predarb.models import Market, Opportunity, TradeAction


class ParityDetector:
    def __init__(self, config: DetectorConfig, broker: BrokerConfig):
        self.config = config
        self.broker = broker

    def detect(self, markets: List[Market]) -> List[Opportunity]:
        opps: List[Opportunity] = []
        for m in markets:
            yes = m.outcome_by_label("yes") or m.outcome_by_label("Yes")
            no = m.outcome_by_label("no") or m.outcome_by_label("No")
            if not yes or not no:
                continue
            gross_cost = yes.price + no.price
            if gross_cost >= self.config.parity_threshold:
                continue
            fees = gross_cost * (self.broker.fee_bps / 10_000)
            slippage = gross_cost * (self.broker.slippage_bps / 10_000)
            net_cost = gross_cost + fees + slippage
            net_edge = 1.0 - net_cost
            if net_edge <= 0:
                continue
            opps.append(
                Opportunity(
                    type="PARITY",
                    market_ids=[m.id],
                    description=f"Yes+No={gross_cost:.4f} net_edge={net_edge:.4f}",
                    net_edge=net_edge,
                    actions=[
                        TradeAction(market_id=m.id, outcome_id=yes.id, side="BUY", amount=1.0, limit_price=yes.price),
                        TradeAction(market_id=m.id, outcome_id=no.id, side="BUY", amount=1.0, limit_price=no.price),
                    ],
                    metadata={"gross_cost": gross_cost},
                )
            )
        return opps
