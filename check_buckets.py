
from predarb.rolling_logger import get_logger
from predarb.category_mapper import CategoryMapper
from predarb.pipeline import load_markets, SNAPSHOT_FILE

logger = get_logger()
mapper = CategoryMapper(rolling_logger=logger)
markets = load_markets(SNAPSHOT_FILE)

buckets = {}
for m in markets:
    b = mapper.get_bucket(m, m.exchange or "unknown")
    buckets[b] = buckets.get(b, 0) + 1

print("Bucket Distribution:")
for k, v in sorted(buckets.items()):
    print(f"{k}: {v}")
