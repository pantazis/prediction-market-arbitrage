#!/usr/bin/env python
"""
Comprehensive stress test runner for ALL arbitrage types.

Runs the complete test suite covering every arbitrage detection type
across both venues (Polymarket + Kalshi) with expected results validation.
"""
import sys
import json
from pathlib import Path
from typing import Dict, List, Any
from collections import Counter

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from predarb.config import load_config
from predarb.engine import Engine
from predarb.dual_injection import DualInjectionClient
from predarb.cross_venue_scenarios import get_cross_venue_scenario
from predarb.models import Opportunity


class ScenarioValidator:
    """Validates scenario results against expected outcomes."""
    
    # Expected results for comprehensive cross-venue scenario
    EXPECTED_OPPORTUNITIES = {
        "PARITY": {
            "min_count": 2,  # At least 2 parity violations
            "description": "YES+NO != 1.0 within single venue",
        },
        "LADDER": {
            "min_count": 1,  # At least 1 ladder violation
            "description": "Price monotonicity violations across thresholds",
        },
        "EXCLUSIVE_SUM": {
            "min_count": 1,  # At least 1 exclusive-sum violation
            "description": "Mutually exclusive outcomes sum deviation",
        },
    }
    
    # Note: DUPLICATE detector is disabled in config.yml due to short-selling prevention policy
    # This is intentional and correct for production use
    
    EXPECTED_REJECTIONS = {
        "low_liquidity": {
            "min_count": 2,
            "description": "Markets below minimum liquidity threshold",
        },
        "min_edge": {
            "min_count": 1,
            "description": "Edge too small after fees/slippage",
        },
        "stale_timestamp": {
            "min_count": 1,
            "description": "Market data too old (time-lag rejection)",
        },
    }
    
    def __init__(self, verbose: bool = True):
        self.verbose = verbose
        self.results = {
            "passed": 0,
            "failed": 0,
            "warnings": 0,
            "tests": [],
        }
    
    def validate_detected_opportunities(
        self,
        detected: List[Opportunity],
        approved: List[Opportunity],
    ) -> Dict[str, Any]:
        """Validate detected and approved opportunities."""
        print("\n" + "=" * 80)
        print("VALIDATING DETECTED OPPORTUNITIES")
        print("=" * 80)
        
        # Count by type
        detected_counts = Counter(o.type for o in detected)
        approved_counts = Counter(o.type for o in approved)
        
        print(f"\nTotal detected: {len(detected)}")
        print(f"Total approved: {len(approved)}")
        print(f"Approval rate: {len(approved)/len(detected)*100:.1f}%\n" if detected else "\nNo opportunities detected.\n")
        
        # Validate each expected opportunity type
        for opp_type, expectations in self.EXPECTED_OPPORTUNITIES.items():
            detected_count = detected_counts.get(opp_type, 0)
            approved_count = approved_counts.get(opp_type, 0)
            min_expected = expectations["min_count"]
            description = expectations["description"]
            
            print(f"{opp_type}:")
            print(f"  Description: {description}")
            print(f"  Detected: {detected_count} (expected >= {min_expected})")
            print(f"  Approved: {approved_count}")
            
            # Test: detected count meets minimum
            test_name = f"{opp_type}_detection"
            if detected_count >= min_expected:
                print(f"  ✓ PASS: Detection count meets expectations")
                self._record_pass(test_name, f"Detected {detected_count} >= {min_expected}")
            else:
                print(f"  ✗ FAIL: Expected >= {min_expected}, got {detected_count}")
                self._record_fail(test_name, f"Expected >= {min_expected}, got {detected_count}")
            
            # Test: some opportunities were approved (if any detected)
            if detected_count > 0:
                approval_test = f"{opp_type}_approval"
                if approved_count > 0:
                    print(f"  ✓ PASS: Some opportunities approved ({approved_count}/{detected_count})")
                    self._record_pass(approval_test, f"{approved_count} approved")
                else:
                    print(f"  ⚠ WARNING: No opportunities approved (all filtered out)")
                    self._record_warning(approval_test, "All opportunities rejected by risk filters")
            
            print()
        
        # Check for unexpected opportunity types
        unexpected_types = set(detected_counts.keys()) - set(self.EXPECTED_OPPORTUNITIES.keys())
        if unexpected_types:
            print("Unexpected opportunity types detected:")
            for utype in unexpected_types:
                print(f"  - {utype}: {detected_counts[utype]}")
            print()
        
        return {
            "detected": len(detected),
            "approved": len(approved),
            "by_type": dict(detected_counts),
            "approved_by_type": dict(approved_counts),
        }
    
    def validate_market_counts(
        self,
        poly_count: int,
        kalshi_count: int,
        total_count: int,
    ) -> bool:
        """Validate market counts from both venues."""
        print("\n" + "=" * 80)
        print("VALIDATING MARKET COUNTS")
        print("=" * 80)
        
        print(f"\nPolymarket markets: {poly_count}")
        print(f"Kalshi markets: {kalshi_count}")
        print(f"Total markets: {total_count}")
        
        # Test: market counts add up
        if poly_count + kalshi_count == total_count:
            print("✓ PASS: Market counts add up correctly")
            self._record_pass("market_count_sum", f"{poly_count} + {kalshi_count} = {total_count}")
            return True
        else:
            print(f"✗ FAIL: {poly_count} + {kalshi_count} != {total_count}")
            self._record_fail("market_count_sum", "Market counts don't add up")
            return False
    
    def validate_exchange_tags(self, markets: List) -> bool:
        """Validate that all markets have proper exchange tags."""
        print("\n" + "=" * 80)
        print("VALIDATING EXCHANGE TAGS")
        print("=" * 80)
        
        untagged = [m for m in markets if not getattr(m, 'exchange', None)]
        poly_markets = [m for m in markets if getattr(m, 'exchange', None) == "polymarket"]
        kalshi_markets = [m for m in markets if getattr(m, 'exchange', None) == "kalshi"]
        
        print(f"\nPolymarket-tagged: {len(poly_markets)}")
        print(f"Kalshi-tagged: {len(kalshi_markets)}")
        print(f"Untagged: {len(untagged)}")
        
        if untagged:
            print("\n✗ FAIL: Found markets without exchange tags:")
            for m in untagged[:5]:  # Show first 5
                print(f"  - {m.id}")
            self._record_fail("exchange_tags", f"{len(untagged)} markets without exchange tags")
            return False
        else:
            print("\n✓ PASS: All markets properly tagged")
            self._record_pass("exchange_tags", "All markets have exchange tags")
            return True
    
    def validate_determinism(self, seed: int = 42) -> bool:
        """Validate that same seed produces same results."""
        print("\n" + "=" * 80)
        print("VALIDATING DETERMINISM")
        print("=" * 80)
        
        print(f"\nGenerating scenario twice with seed={seed}...")
        
        poly1, kalshi1 = get_cross_venue_scenario(seed=seed)
        poly2, kalshi2 = get_cross_venue_scenario(seed=seed)
        
        # Check counts match
        if len(poly1) != len(poly2) or len(kalshi1) != len(kalshi2):
            print(f"✗ FAIL: Market counts don't match")
            print(f"  Run 1: {len(poly1)} poly, {len(kalshi1)} kalshi")
            print(f"  Run 2: {len(poly2)} poly, {len(kalshi2)} kalshi")
            self._record_fail("determinism", "Market counts differ between runs")
            return False
        
        # Check market IDs match
        poly1_ids = sorted([m.id for m in poly1])
        poly2_ids = sorted([m.id for m in poly2])
        kalshi1_ids = sorted([m.id for m in kalshi1])
        kalshi2_ids = sorted([m.id for m in kalshi2])
        
        if poly1_ids != poly2_ids or kalshi1_ids != kalshi2_ids:
            print(f"✗ FAIL: Market IDs don't match between runs")
            self._record_fail("determinism", "Market IDs differ between runs")
            return False
        
        # Check prices match (within tolerance)
        for m1, m2 in zip(poly1, poly2):
            for o1, o2 in zip(m1.outcomes, m2.outcomes):
                if abs(o1.price - o2.price) > 1e-6:
                    print(f"✗ FAIL: Prices don't match for {m1.id}")
                    print(f"  {o1.id}: {o1.price} vs {o2.price}")
                    self._record_fail("determinism", f"Prices differ for {m1.id}")
                    return False
        
        print("✓ PASS: Same seed produces identical results")
        self._record_pass("determinism", "Seed produces consistent results")
        return True
    
    def print_summary(self) -> int:
        """Print validation summary and return exit code."""
        print("\n" + "=" * 80)
        print("VALIDATION SUMMARY")
        print("=" * 80)
        
        print(f"\n✓ Passed: {self.results['passed']}")
        print(f"✗ Failed: {self.results['failed']}")
        print(f"⚠ Warnings: {self.results['warnings']}")
        
        total = self.results['passed'] + self.results['failed'] + self.results['warnings']
        if total > 0:
            pass_rate = self.results['passed'] / total * 100
            print(f"\nPass rate: {pass_rate:.1f}%")
        
        if self.verbose and self.results['failed'] > 0:
            print("\nFailed tests:")
            for test in self.results['tests']:
                if test['status'] == 'FAIL':
                    print(f"  - {test['name']}: {test['message']}")
        
        # Return exit code
        if self.results['failed'] > 0:
            print("\n❌ VALIDATION FAILED")
            return 1
        elif self.results['warnings'] > 0:
            print("\n⚠ VALIDATION PASSED WITH WARNINGS")
            return 0
        else:
            print("\n✅ ALL VALIDATIONS PASSED")
            return 0
    
    def _record_pass(self, test_name: str, message: str):
        self.results['passed'] += 1
        self.results['tests'].append({
            'name': test_name,
            'status': 'PASS',
            'message': message,
        })
    
    def _record_fail(self, test_name: str, message: str):
        self.results['failed'] += 1
        self.results['tests'].append({
            'name': test_name,
            'status': 'FAIL',
            'message': message,
        })
    
    def _record_warning(self, test_name: str, message: str):
        self.results['warnings'] += 1
        self.results['tests'].append({
            'name': test_name,
            'status': 'WARNING',
            'message': message,
        })


def run_comprehensive_stress_test(seed: int = 42, verbose: bool = True) -> int:
    """
    Run comprehensive stress test covering all arbitrage types.
    
    Args:
        seed: Random seed for reproducibility
        verbose: Print detailed output
        
    Returns:
        Exit code (0 = success, non-zero = failure)
    """
    print("=" * 80)
    print("COMPREHENSIVE ARBITRAGE STRESS TEST")
    print("=" * 80)
    print(f"\nSeed: {seed}")
    print(f"Testing ALL arbitrage types across BOTH venues\n")
    
    validator = ScenarioValidator(verbose=verbose)
    
    # Step 1: Validate determinism
    if not validator.validate_determinism(seed=seed):
        return validator.print_summary()
    
    # Step 2: Generate scenario
    print("\n" + "=" * 80)
    print("GENERATING CROSS-VENUE SCENARIO")
    print("=" * 80)
    
    poly_markets, kalshi_markets = get_cross_venue_scenario(seed=seed)
    
    print(f"\n✓ Generated {len(poly_markets)} Polymarket markets")
    print(f"✓ Generated {len(kalshi_markets)} Kalshi markets")
    print(f"✓ Total: {len(poly_markets) + len(kalshi_markets)} markets")
    
    # Step 3: Create static providers
    class StaticProvider:
        def __init__(self, markets, exchange_name):
            self.markets = markets
            self.exchange_name = exchange_name
        def fetch_markets(self):
            return self.markets
        def get_active_markets(self):
            return self.markets
        def get_exchange_name(self):
            return f"StaticProvider({self.exchange_name})"
    
    venue_a = StaticProvider(poly_markets, "polymarket")
    venue_b = StaticProvider(kalshi_markets, "kalshi")
    
    # Step 4: Create dual injection client
    dual_client = DualInjectionClient(
        venue_a_provider=venue_a,
        venue_b_provider=venue_b,
        exchange_a="polymarket",
        exchange_b="kalshi",
    )
    
    # Step 5: Load config and create engine
    print("\n" + "=" * 80)
    print("INITIALIZING ENGINE")
    print("=" * 80)
    
    config = load_config("config.yml")
    config.engine.iterations = 1
    config.engine.refresh_seconds = 0.0
    
    engine = Engine(config, clients=[dual_client])
    
    print("\n✓ Engine initialized")
    print(f"✓ Detectors enabled: {', '.join(d.__class__.__name__ for d in engine.detectors)}")
    
    # Step 6: Run detection
    print("\n" + "=" * 80)
    print("RUNNING DETECTION PIPELINE")
    print("=" * 80)
    
    opportunities = engine.run_once()
    
    all_markets = engine._last_markets
    detected_opps = engine._last_detected
    approved_opps = engine._last_approved
    
    print(f"\n✓ Fetched {len(all_markets)} markets")
    print(f"✓ Detected {len(detected_opps)} opportunities")
    print(f"✓ Approved {len(approved_opps)} opportunities")
    
    # Step 7: Validate results
    poly_count = len([m for m in all_markets if getattr(m, 'exchange', None) == "polymarket"])
    kalshi_count = len([m for m in all_markets if getattr(m, 'exchange', None) == "kalshi"])
    
    validator.validate_market_counts(poly_count, kalshi_count, len(all_markets))
    validator.validate_exchange_tags(all_markets)
    validator.validate_detected_opportunities(detected_opps, approved_opps)
    
    # Step 8: Check unified report
    print("\n" + "=" * 80)
    print("CHECKING UNIFIED REPORT")
    print("=" * 80)
    
    report_path = Path("reports/unified_report.json")
    if report_path.exists():
        with open(report_path, 'r') as f:
            report = json.load(f)
        
        print(f"\n✓ Unified report exists")
        print(f"✓ Sessions: {len(report.get('sessions', []))}")
        print(f"✓ Report path: {report_path}")
    else:
        print(f"\n⚠ WARNING: Unified report not found at {report_path}")
    
    # Step 9: Print summary
    return validator.print_summary()


def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Run comprehensive stress test for all arbitrage types"
    )
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    parser.add_argument("--quiet", action="store_true", help="Reduce output verbosity")
    
    args = parser.parse_args()
    
    exit_code = run_comprehensive_stress_test(
        seed=args.seed,
        verbose=not args.quiet,
    )
    
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
