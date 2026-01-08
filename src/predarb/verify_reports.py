"""
Report verification tool for stress testing and validation.

Validates reports/unified_report.json and returns meaningful exit codes.
"""
import sys
import json
from pathlib import Path
from typing import Dict, Any, Tuple, List
from datetime import datetime


# Exit codes
EXIT_OK = 0
EXIT_MISSING = 2
EXIT_INVALID_SCHEMA = 3
EXIT_NO_ITERATIONS = 4
EXIT_MISSING_DATA = 5
EXIT_INVARIANT_FAILED = 6


class ReportVerifier:
    """Verify unified_report.json structure and invariants."""
    
    def __init__(self, report_path: str = "reports/unified_report.json"):
        self.report_path = Path(report_path)
        self.report_data: Dict[str, Any] = {}
        self.errors: List[str] = []
        self.warnings: List[str] = []
    
    def verify(self) -> int:
        """
        Run all verification checks.
        
        Returns:
            Exit code (0 = success, 2-6 = various failures)
        """
        # Check 1: File exists and readable
        if not self._check_file_exists():
            return EXIT_MISSING
        
        # Check 2: Valid JSON and schema
        if not self._check_valid_json():
            return EXIT_INVALID_SCHEMA
        
        # Check 3: Metadata exists
        if not self._check_metadata():
            return EXIT_INVALID_SCHEMA
        
        # Check 4: Iterations recorded
        if not self._check_iterations():
            return EXIT_NO_ITERATIONS
        
        # Check 5: Expected executions/trades
        if not self._check_executions_and_trades():
            return EXIT_MISSING_DATA
        
        # Check 6: Invariants (residual exposure, hedging)
        if not self._check_invariants():
            return EXIT_INVARIANT_FAILED
        
        return EXIT_OK
    
    def _check_file_exists(self) -> bool:
        """Check if report file exists and is readable."""
        if not self.report_path.exists():
            self.errors.append(f"Report file not found: {self.report_path}")
            return False
        
        if not self.report_path.is_file():
            self.errors.append(f"Report path is not a file: {self.report_path}")
            return False
        
        try:
            with open(self.report_path, 'r', encoding='utf-8') as f:
                f.read()
            return True
        except Exception as e:
            self.errors.append(f"Cannot read report file: {e}")
            return False
    
    def _check_valid_json(self) -> bool:
        """Check if report is valid JSON with expected structure."""
        try:
            with open(self.report_path, 'r', encoding='utf-8') as f:
                self.report_data = json.load(f)
        except json.JSONDecodeError as e:
            self.errors.append(f"Invalid JSON: {e}")
            return False
        except Exception as e:
            self.errors.append(f"Error loading JSON: {e}")
            return False
        
        # Check for expected top-level keys
        required_keys = {'metadata', 'iterations', 'opportunity_executions', 'trades'}
        missing_keys = required_keys - set(self.report_data.keys())
        
        if missing_keys:
            self.errors.append(f"Missing required keys: {missing_keys}")
            return False
        
        return True
    
    def _check_metadata(self) -> bool:
        """Verify metadata section exists and is valid."""
        metadata = self.report_data.get('metadata', {})
        
        if not metadata:
            self.errors.append("Metadata section is empty or missing")
            return False
        
        required_fields = {'version', 'created_at', 'last_updated'}
        missing_fields = required_fields - set(metadata.keys())
        
        if missing_fields:
            self.errors.append(f"Metadata missing fields: {missing_fields}")
            return False
        
        # Check last_updated is recent (not stale)
        try:
            last_updated = datetime.fromisoformat(metadata['last_updated'].replace('Z', '+00:00'))
            age = datetime.now(last_updated.tzinfo) - last_updated
            if age.total_seconds() > 3600:  # More than 1 hour old
                self.warnings.append(f"Report is {age.total_seconds():.0f}s old (may be stale)")
        except Exception as e:
            self.warnings.append(f"Could not parse last_updated timestamp: {e}")
        
        return True
    
    def _check_iterations(self) -> bool:
        """Verify at least one iteration was recorded."""
        iterations = self.report_data.get('iterations', [])
        
        if not iterations:
            self.errors.append("No iterations recorded (expected at least 1)")
            return False
        
        if not isinstance(iterations, list):
            self.errors.append(f"Iterations should be a list, got: {type(iterations)}")
            return False
        
        # Verify iteration structure
        for i, iteration in enumerate(iterations):
            required_fields = {'iteration', 'timestamp', 'markets', 'opportunities_detected', 'opportunities_approved'}
            missing_fields = required_fields - set(iteration.keys())
            
            if missing_fields:
                self.warnings.append(f"Iteration {i} missing fields: {missing_fields}")
        
        return True
    
    def _check_executions_and_trades(self) -> bool:
        """Verify executions and trades data consistency."""
        executions = self.report_data.get('opportunity_executions', [])
        trades = self.report_data.get('trades', [])
        
        # If there are iterations with approved opportunities, expect some executions
        iterations = self.report_data.get('iterations', [])
        total_approved = sum(
            iter_data.get('opportunities_approved', {}).get('count', 0)
            for iter_data in iterations
        )
        
        if total_approved > 0 and len(executions) == 0:
            self.errors.append(
                f"Found {total_approved} approved opportunities but 0 executions recorded"
            )
            return False
        
        # Verify execution structure
        for i, exec_data in enumerate(executions):
            required_fields = {'trace_id', 'timestamp', 'status'}
            missing_fields = required_fields - set(exec_data.keys())
            
            if missing_fields:
                self.warnings.append(f"Execution {i} missing fields: {missing_fields}")
            
            # If status is success, expect at least one execution in 'executions' list
            if exec_data.get('status') == 'success':
                exec_trades = exec_data.get('executions', [])
                if not exec_trades:
                    self.warnings.append(
                        f"Execution {i} has status='success' but no trades in 'executions'"
                    )
        
        return True
    
    def _check_invariants(self) -> bool:
        """Check critical invariants (residual exposure, hedging logic)."""
        executions = self.report_data.get('opportunity_executions', [])
        
        for i, exec_data in enumerate(executions):
            status = exec_data.get('status')
            failure_flags = exec_data.get('failure_flags', [])
            hedge = exec_data.get('hedge', {})
            
            # Invariant 1: Non-success executions should have hedge performed
            if status in ['partial', 'cancelled']:
                if not hedge.get('performed', False):
                    self.errors.append(
                        f"Execution {i} status={status} but hedge not performed"
                    )
                    return False
            
            # Invariant 2: If 'residual_exposure' flag, flatten_all should have been attempted
            if 'residual_exposure' in failure_flags:
                hedge_executions = hedge.get('hedge_executions', [])
                if not hedge_executions:
                    self.errors.append(
                        f"Execution {i} has 'residual_exposure' flag but no hedge executions"
                    )
                    return False
            
            # Invariant 3: Success with extremely low liquidity should be flagged
            if status == 'success' and 'residual_exposure' in failure_flags:
                # This is OK - it's a warning flag for low liquidity success
                self.warnings.append(
                    f"Execution {i} succeeded but flagged for residual_exposure (low liquidity)"
                )
        
        return True
    
    def print_summary(self):
        """Print human-readable verification summary."""
        print("\n" + "=" * 60)
        print("REPORT VERIFICATION SUMMARY")
        print("=" * 60)
        
        if self.report_path.exists():
            print(f"Report: {self.report_path}")
            print(f"Size: {self.report_path.stat().st_size} bytes")
        else:
            print(f"Report: {self.report_path} (NOT FOUND)")
        
        if self.report_data:
            metadata = self.report_data.get('metadata', {})
            iterations = self.report_data.get('iterations', [])
            executions = self.report_data.get('opportunity_executions', [])
            trades = self.report_data.get('trades', [])
            
            print(f"\nMetadata:")
            print(f"  Version: {metadata.get('version', 'N/A')}")
            print(f"  Created: {metadata.get('created_at', 'N/A')}")
            print(f"  Updated: {metadata.get('last_updated', 'N/A')}")
            
            print(f"\nIterations: {len(iterations)}")
            if iterations:
                total_markets = sum(iter_data.get('markets', {}).get('count', 0) for iter_data in iterations)
                total_detected = sum(iter_data.get('opportunities_detected', {}).get('count', 0) for iter_data in iterations)
                total_approved = sum(iter_data.get('opportunities_approved', {}).get('count', 0) for iter_data in iterations)
                
                print(f"  Total markets processed: {total_markets}")
                print(f"  Total opportunities detected: {total_detected}")
                print(f"  Total opportunities approved: {total_approved}")
                if total_detected > 0:
                    print(f"  Overall approval rate: {100 * total_approved / total_detected:.1f}%")
            
            print(f"\nOpportunity Executions: {len(executions)}")
            if executions:
                status_counts = {}
                for exec_data in executions:
                    status = exec_data.get('status', 'unknown')
                    status_counts[status] = status_counts.get(status, 0) + 1
                
                for status, count in sorted(status_counts.items()):
                    print(f"  {status}: {count}")
            
            print(f"\nTrades: {len(trades)}")
            if trades:
                total_pnl = sum(t.get('realized_pnl', 0) for t in trades)
                print(f"  Total realized P&L: ${total_pnl:.2f}")
        
        if self.warnings:
            print(f"\n⚠️  WARNINGS ({len(self.warnings)}):")
            for warning in self.warnings:
                print(f"  - {warning}")
        
        if self.errors:
            print(f"\n❌ ERRORS ({len(self.errors)}):")
            for error in self.errors:
                print(f"  - {error}")
        else:
            print("\n✅ All checks passed")
        
        print("=" * 60 + "\n")


def verify_reports(report_path: str = "reports/unified_report.json", verbose: bool = True) -> int:
    """
    Verify unified report and return exit code.
    
    Args:
        report_path: Path to unified_report.json
        verbose: Print summary to stdout
        
    Returns:
        Exit code (0=OK, 2-6=various failures)
    """
    verifier = ReportVerifier(report_path)
    exit_code = verifier.verify()
    
    if verbose:
        verifier.print_summary()
    
    return exit_code


def main():
    """CLI entry point for report verification."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Verify unified_report.json structure and invariants"
    )
    parser.add_argument(
        "--report",
        default="reports/unified_report.json",
        help="Path to unified_report.json (default: reports/unified_report.json)"
    )
    parser.add_argument(
        "-q", "--quiet",
        action="store_true",
        help="Quiet mode (no summary output)"
    )
    
    args = parser.parse_args()
    
    exit_code = verify_reports(args.report, verbose=not args.quiet)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
