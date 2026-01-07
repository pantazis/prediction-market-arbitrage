from predarb.matchers import cluster_duplicates, group_related, fingerprint
from predarb.models import Market


def test_duplicate_clustering(markets):
    pairs = cluster_duplicates(markets, title_threshold=0.7)
    ids = {(a.id, b.id) for a, b in pairs}
    assert ("m1", "m6") in ids or ("m6", "m1") in ids


def test_related_grouping(markets):
    groups = group_related(markets)
    # BTC markets should cluster together
    found = any(len(v) >= 3 for v in groups.values())
    assert found


def test_semantic_matches_abbreviations():
    """Test that semantic matching catches abbreviations that string matching misses."""
    m1 = Market(
        id="btc1",
        question="Will Bitcoin reach $100,000 by end of 2026?",
        outcomes=[{"id": "y", "label": "YES", "price": 0.65}],
        liquidity=50000,
    )
    m2 = Market(
        id="btc2",
        question="Will BTC hit 100K by December 31 2026?",
        outcomes=[{"id": "y", "label": "YES", "price": 0.72}],
        liquidity=50000,
    )
    
    # Fingerprints should extract same entity and threshold despite different wording
    fp1 = fingerprint(m1)
    fp2 = fingerprint(m2)
    
    assert fp1["entity"] == fp2["entity"]  # Both should extract "BTC" or "Bitcoin"
    # Thresholds should be normalized to same value
    assert fp1["threshold"] == fp2["threshold"] == 100000


def test_semantic_matches_number_formats():
    """Test that semantic matching handles different number formats."""
    m1 = Market(
        id="eth1",
        question="Will Ethereum exceed $5,000?",
        outcomes=[{"id": "y", "label": "YES", "price": 0.45}],
        liquidity=30000,
    )
    m2 = Market(
        id="eth2",
        question="Will ETH go above 5000 dollars?",
        outcomes=[{"id": "y", "label": "YES", "price": 0.48}],
        liquidity=30000,
    )
    
    fp1 = fingerprint(m1)
    fp2 = fingerprint(m2)
    
    # Should extract same threshold despite different formatting
    assert fp1["threshold"] == fp2["threshold"] == 5000


def test_cluster_with_semantic_variations():
    """Test clustering markets with semantic variations."""
    markets = [
        Market(
            id="var1",
            question="Will Bitcoin price surpass $100K by year end?",
            outcomes=[{"id": "y", "label": "YES", "price": 0.60}],
            liquidity=40000,
        ),
        Market(
            id="var2",
            question="BTC to exceed 100000 USD before 2027?",
            outcomes=[{"id": "y", "label": "YES", "price": 0.65}],
            liquidity=40000,
        ),
        Market(
            id="var3",
            question="Will Ethereum reach $10,000?",
            outcomes=[{"id": "y", "label": "YES", "price": 0.35}],
            liquidity=30000,
        ),
    ]
    
    # With semantic matching enabled and lower threshold, should catch semantic matches
    pairs = cluster_duplicates(markets, title_threshold=0.6, use_semantic=True)
    
    # Should find BTC pair despite different wording
    btc_pair_found = any(
        ("var1" in [a.id, b.id] and "var2" in [a.id, b.id])
        for a, b in pairs
    )
    assert btc_pair_found


def test_fingerprint_extracts_key_features():
    """Test that fingerprint extracts all key market features."""
    m = Market(
        id="test",
        question="Will Bitcoin exceed $50,000 by December 31, 2026?",
        outcomes=[{"id": "y", "label": "YES", "price": 0.55}],
        liquidity=50000,
        comparator=">",
        threshold=50000,
    )
    
    fp = fingerprint(m)
    
    assert "key" in fp  # Normalized question text
    assert "entity" in fp  # Extracted asset (BTC/Bitcoin)
    assert "expiry" in fp  # Extracted date
    assert "comparator" in fp  # Comparison operator
    assert "threshold" in fp  # Numeric threshold
    assert fp["comparator"] == ">"
    assert fp["threshold"] == 50000
