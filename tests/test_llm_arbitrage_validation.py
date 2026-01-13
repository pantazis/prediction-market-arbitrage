from datetime import datetime, timedelta

from predarb.llm_verifier import LLMVerifier, LLMVerifierConfig
from predarb.models import Market, Outcome


def _make_market(
    market_id: str,
    question: str,
    yes_bid: float,
    yes_ask: float,
    no_bid: float,
    no_ask: float,
    yes_liquidity: float,
    no_liquidity: float,
    end_date: datetime,
    resolution_source: str | None = None,
    description: str | None = None,
) -> Market:
    return Market(
        id=market_id,
        question=question,
        outcomes=[
            Outcome(id=f"{market_id}:yes", label="YES", price=(yes_bid + yes_ask) / 2, liquidity=yes_liquidity),
            Outcome(id=f"{market_id}:no", label="NO", price=(no_bid + no_ask) / 2, liquidity=no_liquidity),
        ],
        end_date=end_date,
        resolution_source=resolution_source,
        description=description,
        best_bid={"yes": yes_bid, "no": no_bid},
        best_ask={"yes": yes_ask, "no": no_ask},
    )


def test_evaluate_arbitrage_cases_basic() -> None:
    config = LLMVerifierConfig(enabled=True, provider="mock")
    verifier = LLMVerifier(config)
    now = datetime.utcnow()

    kalshi = _make_market(
        market_id="kalshi:case",
        question="Will X happen?",
        yes_bid=0.60,
        yes_ask=0.62,
        no_bid=0.35,
        no_ask=0.36,
        yes_liquidity=1000.0,
        no_liquidity=1000.0,
        end_date=now + timedelta(days=3),
        resolution_source="Official",
    )
    polymarket = _make_market(
        market_id="poly:case",
        question="Will X happen?",
        yes_bid=0.39,
        yes_ask=0.40,
        no_bid=0.29,
        no_ask=0.30,
        yes_liquidity=1000.0,
        no_liquidity=1000.0,
        end_date=now + timedelta(days=10),
        resolution_source="Official",
    )

    results = verifier.evaluate_arbitrage_cases(
        kalshi_market=kalshi,
        poly_market=polymarket,
        cost_bps=0.0,
        depth_fraction=0.1,
    )

    case_names = {result.case_name for result in results}
    assert "YES overpriced on Kalshi" in case_names
    assert "NO overpriced on Kalshi" in case_names
    assert "Cross complement (YES + NO < 1)" in case_names
    assert "Synthetic YES (equivalent complement)" in case_names
    assert "Synthetic NO" in case_names
    assert "Time-ladder (same event, different deadlines)" in case_names


def test_evaluate_arbitrage_cases_resolution_mismatch() -> None:
    config = LLMVerifierConfig(enabled=True, provider="mock")
    verifier = LLMVerifier(config)
    now = datetime.utcnow()

    kalshi = _make_market(
        market_id="kalshi:strict",
        question="Will Y happen?",
        yes_bid=0.60,
        yes_ask=0.61,
        no_bid=0.40,
        no_ask=0.41,
        yes_liquidity=1000.0,
        no_liquidity=1000.0,
        end_date=now + timedelta(days=10),
        resolution_source="Kalshi Official",
        description="Official final result as reported by the federal government.",
    )
    polymarket = _make_market(
        market_id="poly:loose",
        question="Will Y happen?",
        yes_bid=0.39,
        yes_ask=0.40,
        no_bid=0.60,
        no_ask=0.61,
        yes_liquidity=1000.0,
        no_liquidity=1000.0,
        end_date=now + timedelta(days=10),
        resolution_source="Community",
        description="Resolved by consensus.",
    )

    results = verifier.evaluate_arbitrage_cases(
        kalshi_market=kalshi,
        poly_market=polymarket,
        cost_bps=0.0,
        depth_fraction=0.1,
    )

    case_names = {result.case_name for result in results}
    assert "Resolution mismatch" in case_names
    mismatch = next(r for r in results if r.case_name == "Resolution mismatch")
    assert mismatch.guaranteed is False
