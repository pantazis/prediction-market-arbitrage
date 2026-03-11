
from predarb.rolling_logger import get_logger
from predarb.category_mapper import CategoryMapper
from predarb.models import Market

logger = get_logger()
mapper = CategoryMapper(rolling_logger=logger)

# Market with NO tags, but keyword in title
m = Market(
    id="test:1",
    title="Will Bitcoin reach 100k?", # Contains 'bitcoin' -> CRYPTO
    exchange="kalshi",
    outcomes=[{"id": "1", "label": "Yes", "price": 0.5}, {"id": "2", "label": "No", "price": 0.5}]
)

bucket = mapper.get_bucket(m, "kalshi")
print(f"Title: '{m.title}' -> Bucket: {bucket}")

if bucket == "CRYPTO":
    print("SUCCESS: Inferred category from title.")
else:
    print(f"FAILURE: Expected CRYPTO, got {bucket}")
