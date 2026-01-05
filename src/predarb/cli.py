import argparse
import logging

from predarb.config import load_config
from predarb.engine import Engine
from predarb.polymarket_client import PolymarketClient


def main():
    parser = argparse.ArgumentParser(description="Predarb Polymarket paper bot")
    parser.add_argument("command", choices=["run", "once"], help="run loop or single pass")
    parser.add_argument("--config", default="config.yml", help="Path to config file")
    parser.add_argument("--iterations", type=int, default=None, help="Override iterations from config for run mode")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")

    config = load_config(args.config)
    client = PolymarketClient(config.polymarket)
    if args.iterations is not None:
        config.engine.iterations = args.iterations
    engine = Engine(config, client)

    if args.command == "once":
        engine.run_once()
    else:
        engine.run()


if __name__ == "__main__":
    main()
