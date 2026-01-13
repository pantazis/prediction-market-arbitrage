from dotenv import load_dotenv
from predarb.llm_verifier import LLMVerifierConfig, LLMVerifier
from predarb.models import Market, Outcome

load_dotenv()

# Minimal test markets (binary outcomes required by Market schema)
market1 = Market(
    id="1",
    question="Will Donald Trump win the 2024 US Presidential Election?",
    outcomes=[
        Outcome(id="yes", label="Yes", price=0.55),
        Outcome(id="no", label="No", price=0.45),
    ],
)
market2 = Market(
    id="2",
    question="Will Trump win the 2024 US presidential race?",
    outcomes=[
        Outcome(id="yes", label="Yes", price=0.52),
        Outcome(id="no", label="No", price=0.48),
    ],
)

# Use OpenAI provider, enabled, with short timeout
test_config = LLMVerifierConfig(
    enabled=True,
    provider="openai",
    model="gpt-3.5-turbo",
    timeout_s=10.0,
    min_similarity_to_verify=0.8,
    fail_mode="fail_open"
)

verifier = LLMVerifier(config=test_config)
result = verifier.verify_pair(market1, market2)
print("LLM Verification Result:", result)
