#!/usr/bin/env python3
"""
Continuous bot runner with mixed real Polymarket + injected stress data.

Combines real Polymarket API calls with injected stress scenarios for
comprehensive testing and monitoring. Uses existing UnifiedReporter and
LiveReporter systems.

Usage:
    python run_continuous_mixed.py --scenario high_volume --days 2
    python run_continuous_mixed.py --scenario happy_path --days 0.1  # 2.4 hours
    python run_continuous_mixed.py --help
"""
import sys
import time
import argparse
from datetime import datetime, timedelta
from pathlib import Path
from typing import List

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from predarb.models import Market
from predarb.polymarket_client import PolymarketClient
from predarb.injection import InjectionSource
from predarb.engine import Engine
from predarb.config import load_config


class MixedMarketProvider:
    """
    Combines real Polymarket data with injected stress scenarios.
    
    Uses existing injection system and Polymarket client.
    """
    
    def __init__(self, polymarket_client, injected_provider, mix_ratio: float = 0.1):
        """
        Args:
            polymarket_client: Real PolymarketClient
            injected_provider: Scenario/file/inline provider
            mix_ratio: Ratio of injected to real markets (0.1 = 10% injected)
        """
        self.polymarket_client = polymarket_client
        self.injected_provider = injected_provider
        self.mix_ratio = mix_ratio
        self.call_count = 0
    
    def fetch_markets(self) -> List[Market]:
        """Fetch and combine real + injected markets."""
        self.call_count += 1
        
        # Get real markets from Polymarket
        real_markets = []
        try:
            real_markets = self.polymarket_client.fetch_markets()
            print(f"[{self.call_count}] ✓ Fetched {len(real_markets)} real Polymarket markets")
        except Exception as e:
            print(f"[{self.call_count}] ⚠ Failed to fetch real markets: {e}")
        
        # Get injected markets from scenario
        injected_markets = []
        try:
            all_injected = self.injected_provider.fetch_markets()
            # Limit based on mix ratio
            if real_markets:
                num_injected = max(1, int(len(real_markets) * self.mix_ratio))
            else:
                num_injected = len(all_injected)
            
            injected_markets = all_injected[:num_injected]
            
            # Prefix IDs to avoid conflicts with real markets
            for i, market in enumerate(injected_markets):
                market.id = f"INJECTED_{i:03d}_{market.id}"
            
            print(f"[{self.call_count}] ✓ Added {len(injected_markets)} injected markets (ratio={self.mix_ratio:.1%})")
        except Exception as e:
            print(f"[{self.call_count}] ⚠ Failed to fetch injected markets: {e}")
        
        # Combine markets
        combined = real_markets + injected_markets
        print(f"[{self.call_count}] → Total: {len(combined)} markets (real={len(real_markets)}, injected={len(injected_markets)})\n")
        
        return combined


def main():
    parser = argparse.ArgumentParser(
        description="Run arbitrage bot continuously with mixed real + injected data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --scenario high_volume --days 2
      Run for 2 days with high_volume scenario (10%% injected)
  
  %(prog)s --scenario happy_path --days 0.1 --mix-ratio 0.2
      Run for 2.4 hours with happy_path scenario (20%% injected)
  
  %(prog)s --scenario many_risk_rejections --days 1
      Run for 1 day with risk rejection stress testing
        """
    )
    
    parser.add_argument(
        "--scenario",
        default="high_volume",
        choices=["high_volume", "happy_path", "many_risk_rejections", 
                 "partial_fill", "latency_freshness", "fee_slippage", "semantic_clustering"],
        help="Stress scenario to inject (default: high_volume)"
    )
    parser.add_argument(
        "--days",
        type=float,
        default=2.0,
        help="Number of days to run (default: 2.0, can be fractional)"
    )
    parser.add_argument(
        "--mix-ratio",
        type=float,
        default=0.1,
        help="Ratio of injected to real markets (default: 0.1 = 10%%)"
    )
    parser.add_argument(
        "--config",
        default="config.yml",
        help="Config file path (default: config.yml)"
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for injected scenarios (default: 42)"
    )
    
    args = parser.parse_args()
    
    # Validate
    if args.mix_ratio < 0 or args.mix_ratio > 1:
        print("ERROR: --mix-ratio must be between 0 and 1")
        sys.exit(1)
    
    print("="*70)
    print("CONTINUOUS MIXED-MODE BOT")
    print("="*70)
    
    # Load config
    print(f"\n[Setup] Loading config from {args.config}")
    config = load_config(args.config)
    
    # Create Polymarket client
    print("[Setup] Creating Polymarket client")
    polymarket_client = PolymarketClient(config.polymarket)
    
    # Create injected provider
    print(f"[Setup] Creating injected provider: scenario={args.scenario}, seed={args.seed}")
    injected_provider = InjectionSource.from_spec(f"scenario:{args.scenario}", seed=args.seed)
    
    # Create mixed provider
    print(f"[Setup] Creating mixed provider: mix_ratio={args.mix_ratio:.1%}")
    mixed_provider = MixedMarketProvider(
        polymarket_client=polymarket_client,
        injected_provider=injected_provider,
        mix_ratio=args.mix_ratio
    )
    
    # Build engine (uses existing UnifiedReporter + LiveReporter)
    print("[Setup] Building engine (with UnifiedReporter + LiveReporter)")
    engine = Engine(config, mixed_provider)
    
    # Calculate timing
    start_time = datetime.now()
    end_time = start_time + timedelta(days=args.days)
    refresh_seconds = config.engine.refresh_seconds
    
    print("\n" + "="*70)
    print("STARTING CONTINUOUS RUN")
    print("="*70)
    print(f"Start time:    {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"End time:      {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Duration:      {args.days} days ({args.days * 24:.1f} hours)")
    print(f"Scenario:      {args.scenario}")
    print(f"Mix ratio:     {args.mix_ratio:.1%} injected")
    print(f"Refresh:       {refresh_seconds}s")
    print(f"Reports:       reports/unified_report.json")
    print(f"               reports/live_summary.csv")
    print("="*70)
    print()
    
    # Run continuously
    iteration = 0
    try:
        while datetime.now() < end_time:
            iteration += 1
            time_left = end_time - datetime.now()
            hours_left = time_left.total_seconds() / 3600
            
            print(f"{'='*70}")
            print(f"ITERATION {iteration} | Time left: {hours_left:.2f}h ({time_left})")
            print(f"{'='*70}")
            
            # Run one iteration (uses existing reporters)
            engine.run_once()
            
            # Report iteration to both reporters
            engine.reporter.report_iteration(
                iteration=iteration,
                all_markets=engine._last_markets,
                detected_opportunities=engine._last_detected,
                approved_opportunities=engine._last_approved,
            )
            
            # Sleep if more time left
            if datetime.now() < end_time:
                print(f"\n[Sleep] Waiting {refresh_seconds}s before next iteration...\n")
                time.sleep(refresh_seconds)
    
    except KeyboardInterrupt:
        print("\n")
        print("="*70)
        print("⏹ STOPPED BY USER (Ctrl+C)")
        print("="*70)
    
    except Exception as e:
        print("\n")
        print("="*70)
        print(f"❌ ERROR: {e}")
        print("="*70)
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    finally:
        # Final summary
        end_actual = datetime.now()
        duration = end_actual - start_time
        
        print()
        print("="*70)
        print("RUN COMPLETED")
        print("="*70)
        print(f"End time:      {end_actual.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Duration:      {duration} ({duration.total_seconds()/3600:.2f}h)")
        print(f"Iterations:    {iteration}")
        print(f"Reports:       reports/unified_report.json")
        print(f"               reports/live_summary.csv")
        print()
        print("To analyze results:")
        print("  python demo_unified_reporting.py")
        print("  cat reports/live_summary.csv | column -t -s,")
        print("  tail -50 reports/live_summary.csv")
        print("="*70)
        print()


if __name__ == "__main__":
    main()
