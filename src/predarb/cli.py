import argparse
import logging
import sys

from predarb.config import load_config
from predarb.engine import Engine
from predarb.polymarket_client import PolymarketClient


def main():
    parser = argparse.ArgumentParser(description="Predarb Polymarket paper bot")
    parser.add_argument("command", choices=["run", "once", "selftest", "stress"], help="run loop, single pass, self-test with fixtures, or stress test")
    parser.add_argument("--config", default="config.yml", help="Path to config file")
    parser.add_argument("--iterations", type=int, default=None, help="Override iterations from config for run mode")
    parser.add_argument("--fixtures", default="tests/fixtures/markets.json", help="Path to fixture markets for selftest")
    
    # Stress test arguments
    parser.add_argument("--inject", help="Injection spec: scenario:<name> | file:<path> | inline:<json>")
    parser.add_argument("--scenario", help="Stress scenario name (shorthand for --inject scenario:<name>)")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducible stress tests")
    parser.add_argument("--no-verify", action="store_true", help="Skip report verification after stress test")
    
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
        from predarb.models import Market, Outcome

        with open(args.fixtures, "r", encoding="utf-8") as f:
            data = json.load(f)
        markets = []
        for m in data:
            outs = [Outcome(**o) for o in m["outcomes"]]
            markets.append(
                Market(
                    id=m["id"],
                    question=m["question"],
                    outcomes=outs,
                    liquidity=m.get("liquidity", 0.0),
                    volume=m.get("volume", 0.0),
                )
            )
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
    else:
        engine.run()


if __name__ == "__main__":
    main()
