from __future__ import annotations

from datetime import datetime, timedelta
from typing import Dict, List, Tuple

from predarb.config import DetectorConfig
from predarb.matchers import group_related
from predarb.models import Market, Opportunity, TradeAction


class TimeLagDetector:
    def __init__(self, config: DetectorConfig, now_fn=datetime.utcnow):
        self.config = config
        self.history: Dict[str, Tuple[float, datetime]] = {}
        self.now_fn = now_fn

    def detect(self, markets: List[Market]) -> List[Opportunity]:
        opps: List[Opportunity] = []
        groups = group_related(markets)
        now = self.now_fn()
        for _, members in groups.items():
            if len(members) < 2:
                continue
            for m in members:
                yes = m.outcome_by_label("yes") or m.outcomes[0]
                prev = self.history.get(m.id)
                if prev:
                    prev_price, prev_time = prev
                    if prev_time < now - timedelta(minutes=self.config.timelag_persistence_minutes):
                        # check divergence vs peers
                        for peer in members:
                            if peer.id == m.id:
                                continue
                            peer_prev = self.history.get(peer.id)
                            if not peer_prev:
                                continue
                            peer_price, peer_time = peer_prev
                            if peer_time > prev_time and abs(peer_price - peer.outcomes[0].price) < 1e-6:
                                continue
                        jump = abs(yes.price - prev_price)
                        if jump >= self.config.timelag_price_jump:
                            opps.append(
                                Opportunity(
                                    type="TIMELAG",
                                    market_ids=[m.id],
                                    description=f"Price jump from {prev_price:.3f} to {yes.price:.3f} without peers updating",
                                    net_edge=jump,
                                    actions=[
                                        TradeAction(
                                            market_id=m.id,
                                            outcome_id=yes.id,
                                            side="BUY" if yes.price < prev_price else "SELL",
                                            amount=1.0,
                                            limit_price=yes.price,
                                        )
                                    ],
                                    metadata={"previous_price": prev_price},
                                )
                            )
                self.history[m.id] = (yes.price, now)
        return opps
