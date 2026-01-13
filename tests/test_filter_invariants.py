from datetime import datetime, timedelta

from predarb.models import Market, Outcome
from predarb.filtering import MarketFilter, FilterSettings, RejectionReason


def test_filter_settings_default() -> None:
    settings = FilterSettings()
    assert settings.require_resolution_source is False


def test_requires_resolution_source() -> None:
    settings = FilterSettings(require_resolution_source=True)
    assert settings.require_resolution_source is True


def test_rejects_insufficient_outcomes() -> None:
    market = Market(
        id="insufficient",
        question="Test?",
        outcomes=[Outcome(id="yes", label="Yes", price=0.5)],
        end_date=datetime.utcnow() + timedelta(days=10),
    )
    engine = MarketFilter(FilterSettings(require_resolution_source=False))
    assert not engine.filter_markets([market])
    reasons = engine.explain_rejection(market)
    assert RejectionReason.INSUFFICIENT_OUTCOMES.value in reasons


def test_rejects_subjective_resolution() -> None:
    market = Market(
        id="subjective",
        question="Will something cool happen?",
        outcomes=[
            Outcome(id="yes", label="Yes", price=0.5),
            Outcome(id="no", label="No", price=0.5),
        ],
        end_date=datetime.utcnow() + timedelta(days=10),
        resolution_source="Community Vote",
        description="Subjective community consensus required.",
    )
    engine = MarketFilter(FilterSettings(require_resolution_source=True))
    assert not engine.filter_markets([market])
    reasons = engine.explain_rejection(market)
    assert any("subjective" in reason.lower() for reason in reasons)


def test_accepts_resolution_source() -> None:
    market = Market(
        id="ok",
        question="Will it rain?",
        outcomes=[
            Outcome(id="yes", label="Yes", price=0.5),
            Outcome(id="no", label="No", price=0.5),
        ],
        end_date=datetime.utcnow() + timedelta(days=10),
        resolution_source="Official",
    )
    engine = MarketFilter(FilterSettings(require_resolution_source=True))
    assert engine.filter_markets([market])
