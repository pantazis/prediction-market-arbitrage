import logging
import sys
from predarb.llm_verifier import LLMVerifier, LLMVerifierConfig

# Setup logging
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger("predarb")
logger.setLevel(logging.INFO)

from predarb.models import Market, Outcome

def test_verify():
    print("Testing LLM Verifier...")
    
    # Configure to use the same settings as live bot
    config = LLMVerifierConfig(
        enabled=True,
        fail_mode="fail_closed",
        provider="mock", 
        model="mock-model"
    )
    
    verifier = LLMVerifier(config)
    
    # Test case that should pass
    o1 = [Outcome(id="1", label="Yes", price=0.5), Outcome(id="2", label="No", price=0.5)]
    m1 = Market(id="k1", title="Will Donald Trump be inaugurated as US President on Jan 20, 2029?", outcomes=o1)
    m2 = Market(id="p1", title="Trump inaugurated President Jan 20, 2029?", outcomes=o1)
    
    print(f"Verifying: {m1.question} vs {m2.question}")
    result = verifier.verify_pair(m1, m2)
    print(f"Result: {result}")
    
    # Test case that should fail
    m3 = Market(id="k2", title="Will GPT-5 be released in 2025?", outcomes=o1)
    m4 = Market(id="p2", title="Will Gemini Ultra be released in 2025?", outcomes=o1)
    
    print(f"Verifying: {m3.question} vs {m4.question}")
    result2 = verifier.verify_pair(m3, m4)
    print(f"Result: {result2}")

if __name__ == "__main__":
    test_verify()
