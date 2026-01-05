from predarb.matchers import cluster_duplicates, group_related


def test_duplicate_clustering(markets):
    pairs = cluster_duplicates(markets, title_threshold=0.7)
    ids = {(a.id, b.id) for a, b in pairs}
    assert ("m1", "m6") in ids or ("m6", "m1") in ids


def test_related_grouping(markets):
    groups = group_related(markets)
    # BTC markets should cluster together
    found = any(len(v) >= 3 for v in groups.values())
    assert found
