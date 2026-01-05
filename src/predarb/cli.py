import argparse
import logging

from predarb.config import load_config
from predarb.engine import Engine
from predarb.polymarket_client import PolymarketClient


def main():
    parser = argparse.ArgumentParser(description="Predarb Polymarket paper bot")
    parser.add_argument("command", choices=["run", "once", "selftest"], help="run loop, single pass, or self-test with fixtures")
    parser.add_argument("--config", default="config.yml", help="Path to config file")
    parser.add_argument("--iterations", type=int, default=None, help="Override iterations from config for run mode")
    parser.add_argument("--fixtures", default="tests/fixtures/markets.json", help="Path to fixture markets for selftest")
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
    else:
        engine.run()


if __name__ == "__main__":
    main()
