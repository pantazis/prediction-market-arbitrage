import argparse
from src.config import load_config
from src.polymarket_client import HttpPolymarketClient
from src.engine import Engine
from src.utils import setup_logging

def main():
    setup_logging()
    parser = argparse.ArgumentParser(description="Polymarket Arb Bot")
    parser.add_argument("command", choices=["run", "test_connection"], help="Command to run")
    parser.add_argument("--config", default="config.yml", help="Path to config file")
    
    args = parser.parse_args()
    
    config = load_config(args.config)
    
    if args.command == "run":
        # Prefer CLOB client
        from src.polymarket_client import ClobPolymarketClient
        client = ClobPolymarketClient(config.polymarket)
             
        engine = Engine(config, client)
        engine.run_loop()
    elif args.command == "test_connection":
        from src.polymarket_client import ClobPolymarketClient
        client = ClobPolymarketClient(config.polymarket)
             
        markets = client.get_active_markets()
        print(f"Connection successful. Found {len(markets)} markets.")

if __name__ == "__main__":
    main()
