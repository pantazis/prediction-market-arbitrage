from predarb.models import Market, Outcome
from predarb.llm_verifier import LLMVerifier, LLMVerifierConfig
import logging

# Configure logging
logging.basicConfig(level=logging.ERROR)

def test_forex_separation():
    print("Testing Forex vs Crypto Separation...")
    
    config = LLMVerifierConfig(
        enabled=True,
        provider="ollama",
        model="qwen2.5:1.5b",
        timeout_s=60.0,
        fail_mode="fail_closed"
    )
    
    verifier = LLMVerifier(config)
    
    # Real examples from user logs
    forex_q = "Will the EUR/USD open price be above 1.17979 at Jan 16, 2026 at 10am EST?"
    crypto_q = "Will the price of Bitcoin be above $92,000 on January 16?"
    
    outcomes = [Outcome(id="1", label="Yes", price=0.5), Outcome(id="2", label="No", price=0.5)]
    
    m_forex = Market(id="fx1", title=forex_q, outcomes=outcomes)
    m_crypto = Market(id="btc1", title=crypto_q, outcomes=outcomes)
    
    cat_forex = verifier.classify_market(m_forex)
    cat_crypto = verifier.classify_market(m_crypto)
    
    print(f"Forex Market: '{forex_q}' -> Category: {cat_forex}")
    print(f"Crypto Market: '{crypto_q}' -> Category: {cat_crypto}")
    
    if cat_forex != cat_crypto:
        print("\nSUCCESS: Categories are different! The matcher will NOT compare them.")
    else:
        print("\nFAILURE: Categories are the same. Bad matches will persist.")

if __name__ == "__main__":
    test_forex_separation()
