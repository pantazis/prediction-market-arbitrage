"""
Live incremental reporting for arbitrage engine.

Generates append-only CSV reports that track:
- Markets found
- Opportunities detected
- Opportunities after filters/risk approval

Uses deterministic hashing to avoid duplicate reporting.
Restart-safe and designed for continuous live operation.
"""

import csv
import hashlib
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set

from .models import Market, Opportunity

logger = logging.getLogger(__name__)

REPORTS_DIR = Path(__file__).parent.parent.parent / "reports"
STATE_FILE = REPORTS_DIR / ".last_report_state.json"
SUMMARY_CSV = REPORTS_DIR / "live_summary.csv"


class LiveReporter:
    """Manages live incremental reporting with deduplication."""

    def __init__(self, reports_dir: Optional[Path] = None):
        """Initialize reporter.
        
        Args:
            reports_dir: Directory for report files. Defaults to ./reports
        """
        self.reports_dir = reports_dir or REPORTS_DIR
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        self.state_file = self.reports_dir / ".last_report_state.json"
        self.summary_csv = self.reports_dir / "live_summary.csv"
        
        self.last_state = self._load_state()
    
    def _load_state(self) -> Dict:
        """Load the last saved state from disk."""
        if not self.state_file.exists():
            return {
                "market_ids_hash": None,
                "approved_opp_ids_hash": None,
            }
        try:
            with open(self.state_file, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Could not load state file: {e}. Starting fresh.")
            return {
                "market_ids_hash": None,
                "approved_opp_ids_hash": None,
            }
    
    def _save_state(self, market_ids_hash: str, approved_opp_ids_hash: str, 
                    markets_count: int = 0, opps_detected_count: int = 0, 
                    opps_approved_count: int = 0):
        """Save the current state to disk."""
        state = {
            "market_ids_hash": market_ids_hash,
            "approved_opp_ids_hash": approved_opp_ids_hash,
            "last_markets_count": markets_count,
            "last_opps_detected": opps_detected_count,
            "last_opps_approved": opps_approved_count,
            "last_updated": datetime.utcnow().isoformat(),
        }
        try:
            with open(self.state_file, "w") as f:
                json.dump(state, f, indent=2)
        except OSError as e:
            logger.error(f"Failed to save state: {e}")
    
    def _compute_hash(self, items: List[str]) -> str:
        """Compute stable, order-independent hash of a list of IDs.
        
        Args:
            items: List of IDs or identifiers
            
        Returns:
            Hex digest of sorted items
        """
        sorted_items = sorted(set(items))
        combined = "|".join(sorted_items)
        return hashlib.sha256(combined.encode()).hexdigest()
    
    def _get_market_ids(self, markets: List[Market]) -> List[str]:
        """Extract market IDs."""
        return [m.id for m in markets]
    
    def _get_opportunity_ids(self, opportunities: List[Opportunity]) -> List[str]:
        """Extract opportunity IDs. Uses deterministic string from market_ids + type."""
        ids = []
        for i, opp in enumerate(opportunities):
            # Use market_ids and type as unique identifier
            market_ids_str = "|".join(sorted(opp.market_ids)) if hasattr(opp, 'market_ids') else str(i)
            opp_type = getattr(opp, 'type', 'unknown')
            ids.append(f"{opp_type}:{market_ids_str}")
        return ids
    
    def report(
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
            True if a new row was appended, False if state was unchanged
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
            # No change, do not write
            logger.debug(
                f"Iteration {iteration}: No data changes detected. Skipping report."
            )
            return False
        
        # Data changed, append new row
        self._append_csv_row(
            timestamp=datetime.utcnow(),
            iteration=iteration,
            markets_found=len(all_markets),
            opps_found=len(detected_opportunities),
            opps_after_filter=len(approved_opportunities),
        )
        
        # Update in-memory state
        self.last_state["market_ids_hash"] = current_market_hash
        self.last_state["approved_opp_ids_hash"] = current_approved_hash
        self.last_state["last_markets_count"] = len(all_markets)
        self.last_state["last_opps_detected"] = len(detected_opportunities)
        self.last_state["last_opps_approved"] = len(approved_opportunities)
        self._save_state(
            current_market_hash, 
            current_approved_hash,
            len(all_markets),
            len(detected_opportunities),
            len(approved_opportunities),
        )
        
        logger.info(
            f"Iteration {iteration}: Appended report "
            f"(markets={len(all_markets)}, "
            f"detected={len(detected_opportunities)}, "
            f"approved={len(approved_opportunities)})"
        )
        return True
    
    def _append_csv_row(
        self,
        timestamp: datetime,
        iteration: int,
        markets_found: int,
        opps_found: int,
        opps_after_filter: int,
    ):
        """Append a single row to the live_summary.csv file.
        
        Creates the CSV with header if it doesn't exist.
        Includes detailed debugging information.
        """
        write_header = not self.summary_csv.exists()
        
        # Calculate changes from last state
        last_markets_count = self.last_state.get("last_markets_count", 0)
        last_opps_detected = self.last_state.get("last_opps_detected", 0)
        last_opps_approved = self.last_state.get("last_opps_approved", 0)
        
        markets_delta = markets_found - last_markets_count
        opps_detected_delta = opps_found - last_opps_detected
        opps_approved_delta = opps_after_filter - last_opps_approved
        
        # Format deltas with signs
        markets_change = f"{markets_delta:+d}" if markets_delta != 0 else "0"
        opps_detected_change = f"{opps_detected_delta:+d}" if opps_detected_delta != 0 else "0"
        opps_approved_change = f"{opps_approved_delta:+d}" if opps_approved_delta != 0 else "0"
        
        # Human-readable timestamp
        readable_time = timestamp.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        
        # Status indicator
        status = "✓ NEW" if (markets_delta != 0 or opps_approved_delta != 0) else "→ SAME"
        
        # Filter efficiency: what % of detected opportunities passed risk checks
        filter_efficiency = "N/A"
        if opps_found > 0:
            filter_efficiency = f"{(opps_after_filter / opps_found * 100):.1f}%"
        
        try:
            with open(self.summary_csv, "a", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                if write_header:
                    # Header with detailed field descriptions
                    writer.writerow([
                        "TIMESTAMP",
                        "READABLE_TIME",
                        "ITERATION",
                        "MARKETS",
                        "MARKETS_Δ",
                        "DETECTED",
                        "DETECTED_Δ",
                        "APPROVED",
                        "APPROVED_Δ",
                        "APPROVAL%",
                        "STATUS",
                        "MARKET_HASH",
                        "OPP_HASH",
                    ])
                    writer.writerow([
                        "(ISO8601)",
                        "(HH:MM:SS.mmm)",
                        "#",
                        "count",
                        "change",
                        "count",
                        "change",
                        "count",
                        "change",
                        "ratio",
                        "indicator",
                        "sha256",
                        "sha256",
                    ])
                
                # Data row with all details
                writer.writerow([
                    timestamp.isoformat(),
                    readable_time,
                    iteration,
                    markets_found,
                    markets_change,
                    opps_found,
                    opps_detected_change,
                    opps_after_filter,
                    opps_approved_change,
                    filter_efficiency,
                    status,
                    self.last_state.get("market_ids_hash", "")[:16],
                    self.last_state.get("approved_opp_ids_hash", "")[:16],
                ])
        except OSError as e:
            logger.error(f"Failed to append CSV row: {e}")
