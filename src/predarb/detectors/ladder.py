from __future__ import annotations

from typing import Dict, List, Tuple

from predarb.config import DetectorConfig
from predarb.models import Market, Opportunity, TradeAction
from predarb.extractors import extract_threshold, extract_entity


def _probability(market: Market) -> float:
    yes = market.outcome_by_label("yes") or market.outcome_by_label("Yes")
    if yes:
        return yes.price
    return market.outcomes[0].price


class LadderDetector:
    def __init__(self, config: DetectorConfig):
        self.config = config

    def detect(self, markets: List[Market]) -> List[Opportunity]:
        opps: List[Opportunity] = []
        grouped: Dict[Tuple[str, str], List[Market]] = {}
        for m in markets:
            comp, threshold = m.comparator, m.threshold
            if not comp or threshold is None:
                comp, threshold = extract_threshold(m.question)
            if comp not in (">", ">=", "<", "<=") or threshold is None:
                continue
            asset = m.asset or extract_entity(m.question) or "unknown"
            grouped.setdefault((asset, comp), []).append(m)
        for (asset, comp), group in grouped.items():
            sorted_group = sorted(group, key=lambda m: m.threshold or 0.0)
            # enforce monotonic depending on comparator
            for i in range(len(sorted_group) - 1):
                m1, m2 = sorted_group[i], sorted_group[i + 1]
                p1, p2 = _probability(m1), _probability(m2)
                if comp in (">", ">="):
                    if p1 + self.config.ladder_tolerance < p2:
                        edge = p2 - p1
                        opps.append(
                            Opportunity(
                                type="LADDER",
                                market_ids=[m1.id, m2.id],
                                description=f"Monotonicity violation {asset}: threshold {m1.threshold}<{m2.threshold} probs {p1:.3f}<{p2:.3f}",
                                net_edge=edge,
                                actions=[
                                    TradeAction(market_id=m1.id, outcome_id=m1.outcomes[0].id, side="BUY", amount=1.0, limit_price=p1),
                                    TradeAction(market_id=m2.id, outcome_id=m2.outcomes[0].id, side="SELL", amount=1.0, limit_price=p2),
                                ],
                                metadata={"asset": asset, "comparator": comp},
                            )
                        )
                else:
                    if p1 - self.config.ladder_tolerance > p2:
                        edge = p1 - p2
                        opps.append(
                            Opportunity(
                                type="LADDER",
                                market_ids=[m1.id, m2.id],
                                description=f"Monotonicity violation {asset}: threshold {m1.threshold}<{m2.threshold} probs {p1:.3f}>{p2:.3f}",
                                net_edge=edge,
                                actions=[
                                    TradeAction(market_id=m1.id, outcome_id=m1.outcomes[0].id, side="SELL", amount=1.0, limit_price=p1),
                                    TradeAction(market_id=m2.id, outcome_id=m2.outcomes[0].id, side="BUY", amount=1.0, limit_price=p2),
                                ],
                                metadata={"asset": asset, "comparator": comp},
                            )
                        )
        return opps
