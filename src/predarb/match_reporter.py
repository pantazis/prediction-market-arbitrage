"""
Match reporting for the market matching pipeline.

Generates comprehensive reports of matching results including
accepted matches, rejections by stage, and LLM errors.

Requirements: 10.1, 10.2, 10.3, 10.4, 10.5
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from predarb.match_pipeline import MatchCandidate, MatchPipeline, RejectionRecord

logger = logging.getLogger(__name__)


@dataclass
class MatchReport:
    """
    Comprehensive report of matching pipeline results.
    
    Requirements: 10.1, 10.2, 10.3, 10.4
    """
    timestamp: datetime
    run_id: str
    
    # Summary stats
    total_kalshi_markets: int = 0
    total_polymarket_markets: int = 0
    total_candidates_considered: int = 0
    matches_accepted: int = 0
    
    # Rejection breakdown
    rejections_by_stage: Dict[str, int] = field(default_factory=dict)
    
    # Detailed results
    accepted_matches: List[Dict[str, Any]] = field(default_factory=list)
    rejected_matches: List[Dict[str, Any]] = field(default_factory=list)
    
    # LLM errors
    llm_errors: List[Dict[str, Any]] = field(default_factory=list)
    
    # Duplicate handling
    duplicates_detected: int = 0
    duplicates_resolved: List[Dict[str, Any]] = field(default_factory=list)


class MatchReporter:
    """
    Generates detailed match reports from pipeline results.
    
    Requirements: 10.1, 10.2, 10.3, 10.4, 10.5
    """
    
    def __init__(self, output_dir: str = "reports"):
        """
        Initialize the MatchReporter.
        
        Args:
            output_dir: Directory for saving reports
        """
        self.output_dir = Path(output_dir)
    
    def generate(
        self,
        pipeline: "MatchPipeline",
        verified_matches: List["MatchCandidate"],
        llm_errors: Optional[List[Dict]] = None,
        kalshi_count: int = 0,
        poly_count: int = 0,
        duplicates_info: Optional[Dict] = None,
    ) -> MatchReport:
        """
        Generate comprehensive match report from pipeline results.
        
        Args:
            pipeline: The MatchPipeline that processed the markets
            verified_matches: List of accepted MatchCandidates
            llm_errors: Optional list of LLM verification errors
            kalshi_count: Number of Kalshi markets processed
            poly_count: Number of Polymarket markets processed
            duplicates_info: Optional duplicate handling info from DuplicatePreventer
            
        Returns:
            MatchReport with all results
        """
        run_id = str(uuid.uuid4())[:8]
        
        # Build accepted matches list
        accepted = []
        for match in verified_matches:
            accepted.append({
                "kalshi_id": match.kalshi_market.id,
                "polymarket_id": match.polymarket_market.id,
                "confidence": round(match.confidence, 4),
                "semantic_score": round(match.semantic_score, 4),
                "structural_matches": match.structural_matches,
                "matched_fields": [k for k, v in match.structural_matches.items() if v],
            })
        
        # Build rejected matches list
        rejected = []
        for rejection in pipeline.rejections:
            rejected.append({
                "kalshi_id": rejection.kalshi_id,
                "polymarket_id": rejection.polymarket_id,
                "stage": rejection.stage,
                "reason": rejection.reason,
            })
        
        # Handle duplicates info
        duplicates_detected = 0
        duplicates_resolved = []
        if duplicates_info:
            duplicates_detected = duplicates_info.get("total_duplicates_resolved", 0)
            duplicates_resolved = duplicates_info.get("details", [])
        
        return MatchReport(
            timestamp=datetime.utcnow(),
            run_id=run_id,
            total_kalshi_markets=kalshi_count,
            total_polymarket_markets=poly_count,
            total_candidates_considered=kalshi_count * poly_count,
            matches_accepted=len(verified_matches),
            rejections_by_stage=pipeline.get_rejection_summary(),
            accepted_matches=accepted,
            rejected_matches=rejected,
            llm_errors=llm_errors or [],
            duplicates_detected=duplicates_detected,
            duplicates_resolved=duplicates_resolved,
        )
    
    def to_json(self, report: MatchReport) -> str:
        """
        Serialize report to JSON string.
        
        Args:
            report: The MatchReport to serialize
            
        Returns:
            JSON string representation
        """
        data = asdict(report)
        # Convert datetime to ISO format
        data["timestamp"] = report.timestamp.isoformat()
        return json.dumps(data, indent=2, default=str)
    
    def save(self, report: MatchReport, filename: Optional[str] = None) -> Path:
        """
        Save report to file.
        
        Args:
            report: The MatchReport to save
            filename: Optional filename (default: match_report_{run_id}.json)
            
        Returns:
            Path to saved file
        """
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        if filename is None:
            filename = f"match_report_{report.run_id}.json"
        
        filepath = self.output_dir / filename
        filepath.write_text(self.to_json(report))
        
        logger.info(f"Saved match report to {filepath}")
        return filepath
    
    def log_summary(self, report: MatchReport) -> None:
        """
        Log summary statistics at INFO level.
        
        Args:
            report: The MatchReport to summarize
        """
        total_rejected = sum(report.rejections_by_stage.values())
        
        logger.info(
            f"Match Report [{report.run_id}]: "
            f"{report.matches_accepted} matches accepted, "
            f"{total_rejected} rejected"
        )
        
        if report.rejections_by_stage:
            rejection_summary = ", ".join(
                f"{stage}={count}" 
                for stage, count in sorted(report.rejections_by_stage.items())
            )
            logger.info(f"  Rejections by stage: {rejection_summary}")
        
        if report.duplicates_detected > 0:
            logger.info(f"  Duplicates resolved: {report.duplicates_detected}")
        
        if report.llm_errors:
            logger.warning(f"  LLM errors: {len(report.llm_errors)}")
