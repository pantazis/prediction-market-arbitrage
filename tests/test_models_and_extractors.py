import pytest

from predarb.extractors import extract_threshold, parse_number, extract_expiry, extract_entity
from predarb.models import Market, Outcome
from pydantic import ValidationError


def test_outcome_price_validation():
    with pytest.raises(ValidationError):
        Outcome(id="o1", label="Yes", price=1.2)


def test_market_requires_outcomes():
    with pytest.raises(ValidationError):
        Market(id="m", question="q", outcomes=[])


def test_parse_number_variants():
    assert parse_number("90k") == 90000
    assert parse_number("1.2m") == 1200000
    assert parse_number("100000") == 100000


def test_extract_threshold_and_entity():
    comp, thr = extract_threshold("Will BTC be above $90,000 by 2026?")
    assert comp == ">"
    assert thr == 90000
    entity = extract_entity("Will ETH exceed 5k?")
    assert entity in {"eth", "Will"} or entity == "eth"


def test_extract_expiry():
    dt = extract_expiry("Dec 31 2025")
    assert dt.year == 2025
