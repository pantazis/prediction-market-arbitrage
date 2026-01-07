"""
Unified JSON reporting for arbitrage engine.

Consolidates all reporting (loop iterations, opportunity executions, trades)
into a single JSON file for simplified management and analysis.
"""

import hashlib
import json
import logging
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .models import Market, Opportunity, Trade, TradeAction

logger = logging.getLogger(__name__)

REPORTS_DIR = Path(__file__).parent.parent.parent / "reports"
UNIFIED_REPORT = REPORTS_DIR / "unified_report.json"


class UnifiedReporter:
    """Manages unified JSON reporting for all arbitrage bot activities."""

    def __init__(self, reports_dir: Optional[Path] = None):
        """Initialize unified reporter.
        
        Args:
            reports_dir: Directory for report files. Defaults to ./reports
        """
        self.reports_dir = reports_dir or REPORTS_DIR
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        self.report_file = self.reports_dir / "unified_report.json"
        
        # Load existing report or create new structure
        self.report_data = self._load_report()
        self.last_state = self.report_data["metadata"]["last_state"]
    
    def _load_report(self) -> Dict[str, Any]:
        """Load existing unified report or create new structure."""
        if not self.report_file.exists():
            return {
                "metadata": {
                    "version": "1.0",
                    "created_at": datetime.utcnow().isoformat(),
                    "last_updated": datetime.utcnow().isoformat(),
                    "description": "Unified arbitrage bot reporting: iterations, opportunities, trades",
                    "last_state": {
                        "market_ids_hash": None,
                        "approved_opp_ids_hash": None,
                        "last_markets_count": 0,
                        "last_opps_detected": 0,
                        "last_opps_approved": 0,
                    }
                },
                "iterations": [],
                "opportunity_executions": [],
                "trades": []
            }
        
        try:
            with open(self.report_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Could not load report file: {e}. Creating new report.")
            return self._load_report()  # Return fresh structure
    
    def _save_report(self):
        """Save report data atomically to disk."""
        self.report_data["metadata"]["last_updated"] = datetime.utcnow().isoformat()
        
        try:
            # Atomic write via temp file
            with tempfile.NamedTemporaryFile(
                mode="w",
                delete=False,
                dir=str(self.reports_dir),
                encoding="utf-8",
                suffix=".json"
            ) as tmp:
                json.dump(self.report_data, tmp, indent=2)
                tmp.flush()
                os.fsync(tmp.fileno())
            
            # Atomic rename (Windows-safe)
            try:
                os.replace(tmp.name, self.report_file)
            except Exception:
                # Fallback for Windows permission issues
                if self.report_file.exists():
                    os.remove(self.report_file)
                os.rename(tmp.name, self.report_file)
                
        except OSError as e:
            logger.error(f"Failed to save unified report: {e}")
    
    def _compute_hash(self, items: List[str]) -> str:
        """Compute stable, order-independent hash of a list of IDs."""
        sorted_items = sorted(set(items))
        combined = "|".join(sorted_items)
        return hashlib.sha256(combined.encode()).hexdigest()
    
    def _get_market_ids(self, markets: List[Market]) -> List[str]:
        """Extract market IDs."""
        return [m.id for m in markets]
    
    def _get_opportunity_ids(self, opportunities: List[Opportunity]) -> List[str]:
        """Extract opportunity IDs using deterministic string from market_ids + type."""
        ids = []
        for i, opp in enumerate(opportunities):
            market_ids_str = "|".join(sorted(opp.market_ids)) if hasattr(opp, 'market_ids') else str(i)
            opp_type = getattr(opp, 'type', 'unknown')
            ids.append(f"{opp_type}:{market_ids_str}")
        return ids
    
    def report_iteration(
        self,
        iteration: int,
        all_markets: List[Market],
        detected_opportunities: List[Opportunity],
        approved_opportunities: List[Opportunity],
    ) -> bool:
        """Report iteration data if it differs from the last state.
        
        Args:
            iteration: Iteration number
            all_markets: All markets fetched
            detected_opportunities: Opportunities found by detectors
            approved_opportunities: Opportunities approved by risk manager
            
        Returns:
            True if a new record was added, False if state was unchanged
        """
        # Compute hashes of current state
        market_ids = self._get_market_ids(all_markets)
        approved_opp_ids = self._get_opportunity_ids(approved_opportunities)
        
        current_market_hash = self._compute_hash(market_ids)
        current_approved_hash = self._compute_hash(approved_opp_ids)
        
        # Check if state changed
        last_market_hash = self.last_state.get("market_ids_hash")
        last_approved_hash = self.last_state.get("approved_opp_ids_hash")
        
        if (current_market_hash == last_market_hash and 
            current_approved_hash == last_approved_hash):
            logger.debug(f"Iteration {iteration}: No data changes detected. Skipping report.")
            return False
        
        # Calculate deltas from last state
        last_markets_count = self.last_state.get("last_markets_count", 0)
        last_opps_detected = self.last_state.get("last_opps_detected", 0)
        last_opps_approved = self.last_state.get("last_opps_approved", 0)
        
        markets_delta = len(all_markets) - last_markets_count
        opps_detected_delta = len(detected_opportunities) - last_opps_detected
        opps_approved_delta = len(approved_opportunities) - last_opps_approved
        
        # Filter efficiency
        filter_efficiency = None
        if len(detected_opportunities) > 0:
            filter_efficiency = round(len(approved_opportunities) / len(detected_opportunities) * 100, 1)
        
        # Add iteration record
        iteration_record = {
            "iteration": iteration,
            "timestamp": datetime.utcnow().isoformat(),
            "markets": {
                "count": len(all_markets),
                "delta": markets_delta
            },
            "opportunities_detected": {
                "count": len(detected_opportunities),
                "delta": opps_detected_delta
            },
            "opportunities_approved": {
                "count": len(approved_opportunities),
                "delta": opps_approved_delta
            },
            "approval_rate_pct": filter_efficiency,
            "hashes": {
                "markets": current_market_hash[:16],
                "approved_opps": current_approved_hash[:16]
            }
        }
        
        self.report_data["iterations"].append(iteration_record)
        
        # Update state
        self.last_state.update({
            "market_ids_hash": current_market_hash,
            "approved_opp_ids_hash": current_approved_hash,
            "last_markets_count": len(all_markets),
            "last_opps_detected": len(detected_opportunities),
            "last_opps_approved": len(approved_opportunities),
        })
        self.report_data["metadata"]["last_state"] = self.last_state
        
        self._save_report()
        
        logger.info(
            f"Iteration {iteration}: Recorded "
            f"(markets={len(all_markets)}, "
            f"detected={len(detected_opportunities)}, "
            f"approved={len(approved_opportunities)})"
        )
        return True
    
    def log_opportunity_execution(
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
    ) -> str:
        """Log a complete opportunity execution trace.
        
        Returns:
            trace_id: Unique identifier for this execution
        """
        # Generate stable trace ID
        base = {
            "opportunity_type": opportunity.type,
            "detector": detector_name,
            "market_ids": sorted(opportunity.market_ids),
            "actions": intended_actions,
        }
        payload = json.dumps(base, sort_keys=True, separators=(",", ":"))
        trace_id = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        
        # Build execution record
        execution_record = {
            "trace_id": trace_id,
            "timestamp": datetime.utcnow().isoformat(),
            "opportunity": {
                "id": f"{opportunity.type}:{'|'.join(sorted(opportunity.market_ids))}",
                "type": opportunity.type,
                "detector": detector_name,
                "market_ids": opportunity.market_ids,
                "expected_profit": getattr(opportunity, 'expected_profit', None)
            },
            "prices_before": prices_before,
            "intended_actions": intended_actions,
            "risk_approval": risk_approval,
            "executions": [
                {
                    "trade_id": t.id,
                    "market_id": t.market_id,
                    "outcome_id": t.outcome_id,
                    "side": t.side,
                    "amount": t.amount,
                    "price": t.price,
                    "fees": t.fees,
                    "slippage": t.slippage,
                    "realized_pnl": t.realized_pnl
                } for t in executions
            ],
            "hedge": hedge,
            "status": status,
            "realized_pnl": realized_pnl,
            "latency_ms": latency_ms,
            "failure_flags": failure_flags or []
        }
        
        self.report_data["opportunity_executions"].append(execution_record)
        self._save_report()
        
        return trace_id
    
    def log_trades(self, trades: List[Trade]):
        """Log individual trades to the unified report.
        
        Args:
            trades: List of trades to log
        """
        if not trades:
            return
        
        for trade in trades:
            trade_record = {
                "trade_id": trade.id,
                "timestamp": trade.timestamp.isoformat(),
                "market_id": trade.market_id,
                "outcome_id": trade.outcome_id,
                "side": trade.side,
                "amount": trade.amount,
                "price": trade.price,
                "fees": trade.fees,
                "slippage": trade.slippage,
                "realized_pnl": trade.realized_pnl
            }
            self.report_data["trades"].append(trade_record)
        
        self._save_report()
        
        logger.info(f"Logged {len(trades)} trades to unified report")
