from datetime import datetime, timedelta

from src.predarb.filtering import (
    FilterSettings,
    MarketFilter,
    filter_markets,
    rank_markets,
    explain_rejection,
    RejectionReason,
)
from src.predarb.models import Market, Outcome


def test_filter_markets_minimal() -> None:
    market_ok = Market(
        id="ok",
        question="Test?",
        outcomes=[
            Outcome(id="yes", label="YES", price=0.5),
            Outcome(id="no", label="NO", price=0.5),
        ],
        end_date=datetime.utcnow() + timedelta(days=10),
        resolution_source="Official",
    )
    market_bad = Market(
        id="bad",
        question="Test?",
        outcomes=[Outcome(id="yes", label="YES", price=0.5)],
        end_date=datetime.utcnow() + timedelta(days=10),
        resolution_source="Official",
    )
    engine = MarketFilter(FilterSettings(require_resolution_source=True))
    filtered = engine.filter_markets([market_ok, market_bad])
    assert [m.id for m in filtered] == ["ok"]


def test_explain_rejection_minimal() -> None:
    market = Market(
        id="missing",
        question="Test?",
        outcomes=[Outcome(id="yes", label="YES", price=0.5)],
        end_date=datetime.utcnow() + timedelta(days=10),
        resolution_source="Official",
    )
    reasons = explain_rejection(market, FilterSettings(require_resolution_source=False))
    assert RejectionReason.INSUFFICIENT_OUTCOMES.value in reasons


def test_rank_markets_constant_score() -> None:
    market1 = Market(
        id="a",
        question="A?",
        outcomes=[
            Outcome(id="yes", label="YES", price=0.5),
            Outcome(id="no", label="NO", price=0.5),
        ],
        end_date=datetime.utcnow() + timedelta(days=10),
    )
    market2 = Market(
        id="b",
        question="B?",
        outcomes=[
            Outcome(id="yes", label="YES", price=0.5),
            Outcome(id="no", label="NO", price=0.5),
        ],
        end_date=datetime.utcnow() + timedelta(days=10),
    )
    ranked = rank_markets([market2, market1])
    assert [m.id for m, _ in ranked] == ["a", "b"]
    assert all(score == 0.0 for _, score in ranked)


def test_filter_markets_function() -> None:
    market = Market(
        id="ok",
        question="Test?",
        outcomes=[
            Outcome(id="yes", label="YES", price=0.5),
            Outcome(id="no", label="NO", price=0.5),
        ],
        end_date=datetime.utcnow() + timedelta(days=10),
        resolution_source="Official",
    )
    result = filter_markets([market], FilterSettings(require_resolution_source=True))
    assert len(result) == 1
