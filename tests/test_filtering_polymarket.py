from datetime import datetime, timedelta

from src.predarb.filtering import FilterSettings, MarketFilter, rank_markets
from src.predarb.models import Market, Outcome


def test_filter_markets_resolution_required() -> None:
    market = Market(
        id="ok",
        question="Will BTC > $50k?",
        outcomes=[
            Outcome(id="yes", label="YES", price=0.5),
            Outcome(id="no", label="NO", price=0.5),
        ],
        end_date=datetime.utcnow() + timedelta(days=30),
        resolution_source="Coinbase",
    )
    engine = MarketFilter(FilterSettings(require_resolution_source=True))
    assert engine.filter_markets([market])


def test_rank_markets_returns_zero_score() -> None:
    market1 = Market(
        id="m1",
        question="Will BTC > $50k?",
        outcomes=[
            Outcome(id="yes", label="YES", price=0.5),
            Outcome(id="no", label="NO", price=0.5),
        ],
        end_date=datetime.utcnow() + timedelta(days=30),
    )
    market2 = Market(
        id="m2",
        question="Will ETH > $3k?",
        outcomes=[
            Outcome(id="yes", label="YES", price=0.5),
            Outcome(id="no", label="NO", price=0.5),
        ],
        end_date=datetime.utcnow() + timedelta(days=30),
    )
    ranked = rank_markets([market2, market1], FilterSettings())
    assert [m.id for m, _ in ranked] == ["m1", "m2"]
    assert all(score == 0.0 for _, score in ranked)
