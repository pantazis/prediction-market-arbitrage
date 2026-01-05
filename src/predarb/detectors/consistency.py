from __future__ import annotations

from typing import List

from predarb.config import DetectorConfig
from predarb.extractors import extract_entity, extract_threshold
from predarb.models import Market, Opportunity, TradeAction


class ConsistencyDetector:
    def __init__(self, config: DetectorConfig):
        self.config = config

    def detect(self, markets: List[Market]) -> List[Opportunity]:
        opps: List[Opportunity] = []
        # rule 1/2: complementary pairs > vs <= same threshold
        for i, m1 in enumerate(markets):
            comp1 = m1.comparator
            thr1 = m1.threshold
            if comp1 is None or thr1 is None:
                comp1, thr1 = extract_threshold(m1.question)
            entity1 = m1.asset or extract_entity(m1.question)
            prob1 = (m1.outcome_by_label("yes") or m1.outcomes[0]).price
            for m2 in markets[i + 1 :]:
                comp2 = m2.comparator
                thr2 = m2.threshold
                if comp2 is None or thr2 is None:
                    comp2, thr2 = extract_threshold(m2.question)
                entity2 = m2.asset or extract_entity(m2.question)
                if entity1 != entity2 or thr1 != thr2:
                    continue
                prob2 = (m2.outcome_by_label("yes") or m2.outcomes[0]).price
                if (comp1 in (">", ">=") and comp2 in ("<", "<=")) or (comp2 in (">", ">=") and comp1 in ("<", "<=")):
                    total = prob1 + prob2
                    if abs(1.0 - total) > self.config.exclusive_sum_tolerance:
                        opps.append(
                            Opportunity(
                                type="CONSISTENCY",
                                market_ids=[m1.id, m2.id],
                                description=f"Complementary probs sum {total:.3f} !=1",
                                net_edge=abs(1.0 - total),
                                actions=[
                                    TradeAction(market_id=m1.id, outcome_id=m1.outcomes[0].id, side="BUY", amount=1.0, limit_price=prob1),
                                    TradeAction(market_id=m2.id, outcome_id=m2.outcomes[0].id, side="SELL", amount=1.0, limit_price=prob2),
                                ],
                            )
                        )
                # rule 3/4: monotonic > thresholds
                if comp1 in (">", ">=") and comp2 in (">", ">=") and thr1 is not None and thr2 is not None:
                    if thr1 < thr2 and prob1 < prob2:
                        opps.append(
                            Opportunity(
                                type="CONSISTENCY",
                                market_ids=[m1.id, m2.id],
                                description=f"Dominance violated {entity1}: {thr1}<{thr2} yet {prob1:.3f}<{prob2:.3f}",
                                net_edge=prob2 - prob1,
                                actions=[
                                    TradeAction(market_id=m1.id, outcome_id=m1.outcomes[0].id, side="BUY", amount=1.0, limit_price=prob1),
                                    TradeAction(market_id=m2.id, outcome_id=m2.outcomes[0].id, side="SELL", amount=1.0, limit_price=prob2),
                                ],
                            )
                        )
                if comp1 in ("<", "<=") and comp2 in ("<", "<=") and thr1 is not None and thr2 is not None:
                    if thr1 < thr2 and prob1 > prob2:
                        opps.append(
                            Opportunity(
                                type="CONSISTENCY",
                                market_ids=[m1.id, m2.id],
                                description=f"Dominance violated {entity1}: {thr1}<{thr2} yet {prob1:.3f}>{prob2:.3f}",
                                net_edge=prob1 - prob2,
                                actions=[
                                    TradeAction(market_id=m1.id, outcome_id=m1.outcomes[0].id, side="SELL", amount=1.0, limit_price=prob1),
                                    TradeAction(market_id=m2.id, outcome_id=m2.outcomes[0].id, side="BUY", amount=1.0, limit_price=prob2),
                                ],
                            )
                        )
        return opps
