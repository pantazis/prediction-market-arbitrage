from predarb.models import Market, Outcome
from predarb.llm_verifier import LLMVerifier, LLMVerifierConfig
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)

def test_ollama():
    print("Testing Local LLM (Ollama)...")
    
    config = LLMVerifierConfig(
        enabled=True,
        provider="ollama",
        model="qwen2.5:1.5b",
        timeout_s=300.0, # Generous timeout for first load
        fail_mode="fail_closed"
    )
    
    verifier = LLMVerifier(config)
    
    # Test case: Same Event
    o1 = [Outcome(id="1", label="Yes", price=0.5), Outcome(id="2", label="No", price=0.5)]
    m1 = Market(id="k1", title="Will Donald Trump be inaugurated as US President on Jan 20, 2029?", outcomes=o1)
    m2 = Market(id="p1", title="Trump inaugurated President Jan 20, 2029?", outcomes=o1)
    
    print(f"\nVerifying MATCH: {m1.question} vs {m2.question}")
    result = verifier.verify_pair(m1, m2)
    print(f"Result: {result}")
    
    # Test case: Different Event
    m3 = Market(id="k2", title="Will GPT-5 be released in 2025?", outcomes=o1)
    m4 = Market(id="p2", title="Will Gemini Ultra be released in 2025?", outcomes=o1)
    
    print(f"\nVerifying MISMATCH: {m3.question} vs {m4.question}")
    result2 = verifier.verify_pair(m3, m4)
    print(f"Result: {result2}")

if __name__ == "__main__":
    test_ollama()
