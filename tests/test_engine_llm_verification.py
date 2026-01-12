from datetime import datetime, timedelta

from predarb.config import AppConfig
from predarb.engine import Engine
from predarb.models import Market, Outcome


def _binary_market(market_id: str, question: str, end_date: datetime) -> Market:
    return Market(
        id=market_id,
        question=question,
        outcomes=[
            Outcome(id=f"{market_id}_yes", label="Yes", price=0.55),
            Outcome(id=f"{market_id}_no", label="No", price=0.45),
        ],
        end_date=end_date,
    )


def test_engine_verify_cross_venue_pairs_uses_llm(tmp_path):
    cfg = AppConfig()
    cfg.llm_verification.enabled = True
    cfg.llm_verification.provider = "mock"
    cfg.llm_verification.min_similarity_to_verify = 0.5
    cfg.llm_verification.max_pairs_per_group = 3
    cfg.llm_verification.cache_path = str(tmp_path / "llm_cache.json")

    engine = Engine(cfg, clients=[], notifier=None)
    now = datetime.utcnow()

    k1 = _binary_market("kalshi_btc", "Will Bitcoin hit $100,000 by year end?", now)
    p1 = _binary_market("poly_btc", "Will BTC reach $100,000 by Dec 31?", now + timedelta(hours=2))

    k2 = _binary_market("kalshi_fed_jan", "Fed rate decision in January", now)
    p2 = _binary_market("poly_fed_mar", "Fed rate decision in March", now + timedelta(hours=3))

    pairs = [(k1, p1, 0.92), (k2, p2, 0.95)]
    results = engine._verify_cross_venue_pairs(pairs)

    assert len(results) == 2
    assert results[0][3].same_event is True
    assert results[1][3].same_event is False
