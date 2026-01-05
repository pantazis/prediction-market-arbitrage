from __future__ import annotations

from dataclasses import dataclass
from typing import List

from predarb.models import Trade


@dataclass
class ReportSummary:
    trades: int
    realized_pnl: float
    fees: float


def summarize(trades: List[Trade]) -> ReportSummary:
    return ReportSummary(
        trades=len(trades),
        realized_pnl=sum(t.realized_pnl for t in trades),
        fees=sum(t.fees for t in trades),
    )
