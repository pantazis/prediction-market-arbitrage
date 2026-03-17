# Bugfix Requirements Document

## Introduction

The cross-venue market matching system fails to find equivalent crypto markets between Kalshi and Polymarket. Despite both venues having active crypto markets (Bitcoin, Ethereum price predictions), the matcher returns zero pairs because:

1. Kalshi API bulk fetch returns 99% sports parlay markets without category filtering
2. Polymarket API fetches all markets without tag-based filtering
3. Kalshi markets lack category metadata, causing `_get_market_group()` to return `None`

This bug prevents the arbitrage bot from detecting cross-venue opportunities in the crypto category, which is a primary use case.

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN `kalshi_client.fetch_markets()` is called THEN the system fetches all 5000+ markets without category filtering, returning 99% sports parlays (KXMVECROSSCATEGORY prefix)

1.2 WHEN `polymarket_client.fetch_markets()` is called THEN the system fetches all markets without tag-based filtering, returning mixed categories

1.3 WHEN `_get_market_group()` is called on a Kalshi market THEN the system returns `None` because Kalshi markets lack category metadata in the `tags` field

1.4 WHEN `find_pairs()` compares market groups THEN the system finds no common groups because Kalshi groups are empty `[]` while Polymarket has groups like `['category:CRYPTO', 'asset:bitcoin']`

1.5 WHEN both venues have equivalent crypto markets (e.g., "Will BTC reach $100k?") THEN the system returns 0 matched pairs

### Expected Behavior (Correct)

2.1 WHEN `kalshi_client.fetch_markets()` is called with crypto category enabled THEN the system SHALL use series_ticker filtering (e.g., KXBTC, KXETH) to fetch crypto-specific markets

2.2 WHEN `kalshi_client.fetch_markets()` is called THEN the system SHALL populate market category metadata from the API response or infer it from series_ticker

2.3 WHEN `polymarket_client.fetch_markets()` is called with tag filtering enabled THEN the system SHALL use the `tag_id` parameter to fetch category-specific markets

2.4 WHEN `_get_market_group()` is called on a Kalshi crypto market THEN the system SHALL return a valid group key (e.g., `asset:bitcoin`) by parsing the series_ticker or event metadata

2.5 WHEN both venues have equivalent crypto markets THEN the system SHALL find common groups and return matched pairs with similarity scores

### Unchanged Behavior (Regression Prevention)

3.1 WHEN fetching markets from Kalshi THEN the system SHALL CONTINUE TO exclude sports markets via the `excluded_sports_prefixes` filter

3.2 WHEN fetching markets from Polymarket THEN the system SHALL CONTINUE TO support fetching all markets when no tag filter is specified

3.3 WHEN normalizing Kalshi markets THEN the system SHALL CONTINUE TO convert prices from cents to probability (0.0-1.0)

3.4 WHEN normalizing Polymarket markets THEN the system SHALL CONTINUE TO parse JSON-encoded outcomes and prices

3.5 WHEN matching markets THEN the system SHALL CONTINUE TO require binary (YES/NO) markets only

3.6 WHEN matching markets THEN the system SHALL CONTINUE TO apply the 5-stage pipeline (category, asset, threshold, date, semantic)

3.7 WHEN no common groups exist between venues THEN the system SHALL CONTINUE TO return an empty pairs list gracefully
