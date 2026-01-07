from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .models import Opportunity, Trade, TradeAction


class ExecLogger:
    """Deterministic per-opportunity execution logger (JSONL).

    Writes one JSON record per opportunity execution to reports/opportunity_logs.jsonl.
    Designed for DRY-RUN mode and deterministic reproduction.
    """

    def __init__(self, reports_dir: Optional[Path] = None, filename: str = "opportunity_logs.jsonl"):
        self.reports_dir = reports_dir or Path(__file__).parent.parent.parent / "reports"
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        self.log_path = self.reports_dir / filename

    def _stable_hash(self, opportunity: Opportunity, detector_name: str, intended_actions: List[Dict[str, Any]]) -> str:
        base: Dict[str, Any] = {
            "opportunity_type": opportunity.type,
            "detector": detector_name,
            "market_ids": sorted(opportunity.market_ids),
            "actions": intended_actions,
        }
        payload = json.dumps(base, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _safe_append(self, line: str) -> None:
        """Append a single line via temp file then atomic rename.
        Falls back to direct append if rename fails (Windows safety).
        """
        try:
            content = ""
            if self.log_path.exists():
                with open(self.log_path, "r", encoding="utf-8") as src:
                    content = src.read()
            with tempfile.NamedTemporaryFile("w", delete=False, dir=str(self.reports_dir), encoding="utf-8") as tmp:
                if content:
                    tmp.write(content)
                    if not content.endswith("\n"):
                        tmp.write("\n")
                tmp.write(line)
                tmp.write("\n")
                tmp.flush()
            os.replace(tmp.name, self.log_path)
        except Exception:
            # Fallback: direct append
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(line)
                f.write("\n")

    def log_trace(
        self,
        opportunity: Opportunity,
        detector_name: str,
        prices_before: Dict[str, float],
        intended_actions: List[Dict[str, Any]],
        risk_approval: Dict[str, Any],
        executions: List[Trade],
        hedge: Optional[Dict[str, Any]],
        status: str,
        realized_pnl: float,
        latency_ms: int,
        failure_flags: Optional[List[str]] = None,
        freeze_state: bool = True,
    ) -> str:
        """Write a single execution trace record and return its trace_id."""
        trace_id = self._stable_hash(opportunity, detector_name, intended_actions)
        record: Dict[str, Any] = {
            "trace_id": trace_id,
            "timestamp_utc": datetime.utcnow().isoformat(),
            "opportunity_id": f"{opportunity.type}:{'|'.join(sorted(opportunity.market_ids))}",
            "detector": detector_name,
            "markets": [{"market_id": a["market_id"], "outcome_id": a["outcome_id"]} for a in intended_actions],
            "prices_before": prices_before,
            "intended_actions": intended_actions,
            "risk_approval": risk_approval,
            "executions": [
                {
                    "side": t.side,
                    "intended_amount": next((a["amount"] for a in intended_actions if a["market_id"] == t.market_id and a["outcome_id"] == t.outcome_id), None),
                    "filled_amount": t.amount,
                    "avg_price": t.price,
                    "fees": t.fees,
                    "slippage": t.slippage,
                }
                for t in executions
            ],
            "hedge": hedge or {"action": "none"},
            "status": status,
            "realized_pnl": realized_pnl,
            "latency_ms": latency_ms,
            "failure_flags": failure_flags or [],
            "freeze_state": bool(freeze_state),
        }
        line = json.dumps(record, sort_keys=True, separators=(",", ":"))
        self._safe_append(line)
        return trace_id

__all__ = ["ExecLogger"]
