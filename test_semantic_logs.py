
from predarb.rolling_logger import get_logger
from predarb.matcher import SmartMatcher
from predarb.models import Market
from datetime import datetime

# Init logger
logger = get_logger()
logger.info("MATCH", "--- START FORCED MATCH TEST ---")

# Create dummy markets that SHOULD match
# Ensure they map to the same bucket (e.g. CRYPTO via 'Bitcoin')
m1 = Market(
    id="kalshi:123",
    title="Will Bitcoin hit $100k in 2024?",
    description="Bitcoin price prediction",
    exchange="kalshi",
    end_date=datetime.now(),
    outcomes=[{"id": "yes", "label": "Yes", "price": 0.5}, {"id": "no", "label": "No", "price": 0.5}],
    tags=["Crypto", "Bitcoin"]
)

m2 = Market(
    id="polymarket:456",
    question="Bitcoin $100k 2024", 
    description="BTC to 100k",
    exchange="polymarket",
    end_date=datetime.now(),
    outcomes=[{"id": "yes", "label": "Yes", "price": 0.5}, {"id": "no", "label": "No", "price": 0.5}],
    tags=["Crypto"]
)

# Init matcher with logger
matcher = SmartMatcher(rolling_logger=logger)

# Run match with low threshold to ensure hit
logger.info("MATCH", "Running test match with forced pair...")
matches = matcher.find_matches([m1], [m2], min_similarity=0.1)

print(f"Found {len(matches)} matches.")
logger.info("MATCH", "--- END FORCED MATCH TEST ---")
