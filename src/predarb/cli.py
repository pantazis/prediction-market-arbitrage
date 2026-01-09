import argparse
import logging
import sys

from predarb.config import load_config
from predarb.engine import Engine
from predarb.polymarket_client import PolymarketClient


def main():
    parser = argparse.ArgumentParser(description="Predarb Polymarket paper bot")
    parser.add_argument("command", choices=["run", "once", "selftest", "stress", "dual-stress"], help="run loop, single pass, self-test with fixtures, stress test, or dual-venue stress test")
    parser.add_argument("--config", default="config.yml", help="Path to config file")
    parser.add_argument("--iterations", type=int, default=None, help="Override iterations from config for run mode")
    parser.add_argument("--fixtures", default="tests/fixtures/markets.json", help="Path to fixture markets for selftest")
    
    # Stress test arguments
    parser.add_argument("--inject", help="Injection spec: scenario:<name> | file:<path> | inline:<json>")
    parser.add_argument("--scenario", help="Stress scenario name (shorthand for --inject scenario:<name>)")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducible stress tests")
    parser.add_argument("--no-verify", action="store_true", help="Skip report verification after stress test")
    
    # Dual-venue injection arguments
    parser.add_argument("--inject-a", help="Injection spec for venue A (Polymarket): scenario:<name> | file:<path> | inline:<json> | none")
    parser.add_argument("--inject-b", help="Injection spec for venue B (Kalshi): scenario:<name> | file:<path> | inline:<json> | none")
    parser.add_argument("--cross-venue", action="store_true", help="Use built-in cross-venue arbitrage scenario")
    
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")

    config = load_config(args.config)
    client = PolymarketClient(config.polymarket)
    if args.iterations is not None:
        config.engine.iterations = args.iterations
    engine = Engine(config, client)

    if args.command == "once":
        engine.run_once()
    elif args.command == "selftest":
        import json
        from predarb.models import Market

        with open(args.fixtures, "r", encoding="utf-8") as f:
            data = json.load(f)
        markets = []
        for m in data:
            # Market model handles conversion of string outcomes to Outcome objects
            markets.append(Market(**m))
        opps = engine.run_self_test(markets)
        print(f"Self-test detected {len(opps)} opportunities")
    elif args.command == "stress":
        # Stress test mode with injected data
        from predarb.injection import InjectionSource
        from predarb.verify_reports import verify_reports
        
        # Determine injection spec
        if args.scenario:
            inject_spec = f"scenario:{args.scenario}"
        elif args.inject:
            inject_spec = args.inject
        else:
            print("ERROR: stress mode requires --scenario or --inject")
            print("\nAvailable scenarios:")
            from predarb.stress_scenarios import list_scenarios
            for scenario in list_scenarios():
                print(f"  - {scenario}")
            sys.exit(1)
        
        # Create injected client
        try:
            injected_provider = InjectionSource.from_spec(inject_spec, seed=args.seed)
        except Exception as e:
            print(f"ERROR: Failed to create injection source: {e}")
            sys.exit(1)
        
        # Replace client with injected provider
        engine.client = injected_provider
        
        # Set iterations if not specified
        if args.iterations is None:
            config.engine.iterations = 1  # Default to 1 for stress tests
        
        # Run the stress test
        print(f"Running stress test: {inject_spec}")
        print(f"Seed: {args.seed}")
        print(f"Iterations: {config.engine.iterations}")
        print("-" * 60)
        
        if config.engine.iterations == 1:
            engine.run_once()
            # Manually report the iteration since run_once() doesn't call reporter
            engine.reporter.report_iteration(
                iteration=1,
                all_markets=engine._last_markets,
                detected_opportunities=engine._last_detected,
                approved_opportunities=engine._last_approved,
            )
        else:
            engine.run()
        
        print("-" * 60)
        print("Stress test completed")
        
        # Verify reports unless disabled
        if not args.no_verify:
            print("\nVerifying reports...")
            exit_code = verify_reports(verbose=True)
            sys.exit(exit_code)
        else:
            sys.exit(0)
    elif args.command == "dual-stress":
        # Dual-venue stress test mode with independent injection for each venue
        from predarb.dual_injection import DualInjectionClient, InjectionFactory
        from predarb.cross_venue_scenarios import get_cross_venue_scenario
        
        print("=" * 80)
        print("DUAL-VENUE STRESS TEST: Injecting markets into BOTH venues")
        print("=" * 80)
        
        # Determine injection specs
        if args.cross_venue:
            # Use built-in cross-venue arbitrage scenario
            print("\nUsing built-in cross-venue arbitrage scenario")
            print(f"Seed: {args.seed}\n")
            
            poly_markets, kalshi_markets = get_cross_venue_scenario(seed=args.seed)
            
            # Create wrapper providers
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
            
            print(f"✓ Generated {len(poly_markets)} Polymarket markets")
            print(f"✓ Generated {len(kalshi_markets)} Kalshi markets")
            print(f"✓ Total: {len(poly_markets) + len(kalshi_markets)} markets\n")
            
        else:
            # Use explicit injection specs
            inject_a = args.inject_a or "none"
            inject_b = args.inject_b or "none"
            
            if inject_a == "none" and inject_b == "none":
                print("ERROR: dual-stress mode requires --inject-a and/or --inject-b, or --cross-venue")
                print("\nExamples:")
                print("  python -m predarb dual-stress --cross-venue")
                print("  python -m predarb dual-stress --inject-a scenario:happy_path --inject-b scenario:high_volume")
                print("  python -m predarb dual-stress --inject-a file:poly.json --inject-b file:kalshi.json")
                sys.exit(1)
            
            print(f"\nVenue A (Polymarket): {inject_a}")
            print(f"Venue B (Kalshi): {inject_b}")
            print(f"Seed: {args.seed}\n")
            
            # Create providers
            venue_a = InjectionFactory.from_spec(inject_a, seed=args.seed, exchange="polymarket") if inject_a != "none" else None
            venue_b = InjectionFactory.from_spec(inject_b, seed=args.seed, exchange="kalshi") if inject_b != "none" else None
        
        # Create dual injection client
        dual_client = DualInjectionClient(
            venue_a_provider=venue_a,
            venue_b_provider=venue_b,
            exchange_a="polymarket",
            exchange_b="kalshi",
        )
        
        # Create engine with dual client
        config.engine.iterations = args.iterations or 1
        engine = Engine(config, clients=[dual_client])
        
        print("-" * 80)
        print(f"Running {config.engine.iterations} iteration(s)...")
        print("-" * 80)
        
        # Run test
        if config.engine.iterations == 1:
            opps = engine.run_once()
            print(f"\n✓ Detected {len(opps)} opportunities")
            
            # Show breakdown by type
            from collections import Counter
            type_counts = Counter(o.type for o in opps)
            if type_counts:
                print("\nOpportunities by type:")
                for opp_type, count in sorted(type_counts.items()):
                    print(f"  {opp_type}: {count}")
            
            # Manually report since run_once doesn't call reporter
            engine.reporter.report_iteration(
                iteration=1,
                all_markets=engine._last_markets,
                detected_opportunities=engine._last_detected,
                approved_opportunities=engine._last_approved,
            )
        else:
            engine.run()
        
        print("\n" + "=" * 80)
        print("DUAL-VENUE STRESS TEST COMPLETED")
        print("=" * 80)
        print(f"\n✓ Reports written to: {config.engine.report_path}")
        print(f"✓ Unified report: reports/unified_report.json")
        
        sys.exit(0)
    else:
        engine.run()


if __name__ == "__main__":
    main()
