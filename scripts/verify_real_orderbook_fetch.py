
import logging
import sys
import os
import json

# Add src to path
sys.path.append(os.path.join(os.getcwd(), "src"))

from predarb.config import load_config
from predarb.kalshi_client import KalshiClient
from predarb.polymarket_client import PolymarketClient

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("REAL_VERIFY")

def main():
    logger.info("--- Verifying REAL Orderbook API Calls ---")
    
    # Load config
    try:
        config = load_config("config_live_paper.yml")
    except Exception as e:
        logger.error(f"Failed to load config: {e}")
        return

    # 1. Test Kalshi
    if config.kalshi.enabled:
        logger.info("Initializing Kalshi Client...")
        try:
            k_client = KalshiClient(
                api_key_id=config.kalshi.api_key_id,
                private_key_pem=config.kalshi.private_key_pem,
                api_host=config.kalshi.api_host,
                env=config.kalshi.env
            )
            
            # Fetch one market ID to test
            logger.info("Fetching markets to find a valid ticker...")
            markets = k_client.fetch_markets()
            if markets:
                target = markets[0]
                ticker = target.id.split(":")[-1]
                logger.info(f"Testing Orderbook Fetch for Kalshi Ticker: {ticker}")
                
                # CALL REAL API
                ob = k_client.fetch_orderbook(ticker)
                
                if ob:
                    logger.info("✅ Kalshi Orderbook Fetched Successfully!")
                    print(json.dumps(ob, indent=2)[:500] + "...") # Print first 500 chars
                else:
                    logger.error("❌ Kalshi Orderbook returned None (but request didn't crash)")
            else:
                logger.warning("No Kalshi markets found to test.")
        except Exception as e:
            logger.error(f"❌ Kalshi Test Failed: {e}")
    else:
        logger.info("Kalshi disabled in config.")

    # 2. Test Polymarket
    if config.polymarket.enabled:
        logger.info("Initializing Polymarket Client...")
        try:
            p_client = PolymarketClient(config.polymarket)
            
            # Fetch one market to get token ID
            logger.info("Fetching markets to find a valid token_id...")
            markets = p_client.fetch_markets()
            if markets:
                target = markets[0]
                # Try to get YES token
                outcome = target.outcomes[0] if target.outcomes else None
                if outcome:
                    token_id = outcome.id
                    logger.info(f"Testing Orderbook Fetch for Polymarket Token: {token_id}")
                    
                    # CALL REAL API
                    ob = p_client.fetch_orderbook(token_id)
                    
                    if ob:
                        logger.info("✅ Polymarket Orderbook Fetched Successfully!")
                        print(json.dumps(ob, indent=2)[:500] + "...")
                    else:
                        logger.error("❌ Polymarket Orderbook returned None")
                else:
                    logger.warning("Target market has no outcomes")
            else:
                logger.warning("No Polymarket markets found to test.")
        except Exception as e:
            logger.error(f"❌ Polymarket Test Failed: {e}")
    else:
        logger.info("Polymarket disabled in config.")

if __name__ == "__main__":
    main()
