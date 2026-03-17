# Crypto Market Category Filtering Bugfix Design

## Overview

The cross-venue market matching system fails to find equivalent crypto markets between Kalshi and Polymarket despite both venues having active crypto markets. The root cause is a combination of:
1. Bulk fetching all 5000+ Kalshi markets without series-based filtering
2. No tag-based filtering on Polymarket API calls
3. Missing category metadata extraction from Kalshi market responses

The fix adds optional series-based filtering for Kalshi (KXBTC, KXETH, KXSOL) and tag-based filtering for Polymarket, plus improved market group extraction from Kalshi event tickers.

## Glossary

- **Bug_Condition (C)**: Markets are fetched without category/series filtering, causing crypto markets to be buried in 99% sports parlays
- **Property (P)**: When category filtering is enabled, only relevant markets are fetched and properly grouped for matching
- **Preservation**: Existing bulk fetch behavior, sports exclusion, price normalization, and binary market filtering must remain unchanged
- **series_ticker**: Kalshi's grouping identifier (e.g., KXBTC for Bitcoin markets)
- **tag_id**: Polymarket's category filter parameter for the `/markets` endpoint
- **event_ticker**: Kalshi's event grouping field that contains series information (e.g., KXBTC-25JAN10)

## Bug Details

### Fault Condition

The bug manifests when the system attempts to find cross-venue crypto market pairs. The `fetch_markets()` methods return all markets without category filtering, and `_get_market_group()` fails to extract asset information from Kalshi markets because they lack the `category` field in API responses.

**Formal Specification:**
```
FUNCTION isBugCondition(input)
  INPUT: input of type FetchMarketsRequest
  OUTPUT: boolean
  
  RETURN (input.venue == "kalshi" AND input.target_series IS EMPTY)
         OR (input.venue == "polymarket" AND input.target_tags IS EMPTY)
         OR (input.venue == "kalshi" AND market.event_ticker CONTAINS crypto_series 
             AND _get_market_group(market) RETURNS None)
END FUNCTION
```

### Examples

- Kalshi fetch returns 5000+ markets, 99% are KXMVECROSSCATEGORY sports parlays, only ~50 are crypto (KXBTC, KXETH)
- Polymarket fetch returns 10000+ markets across all categories, crypto markets mixed with politics/sports
- `_get_market_group()` on Kalshi market `kalshi:KXBTC-25JAN10:KXBTC-25JAN10-B95000` returns `None` instead of `asset:bitcoin`
- `find_pairs()` returns empty list because Kalshi groups are `[]` while Polymarket has `['asset:bitcoin']`

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- Sports markets must continue to be excluded via `excluded_sports_prefixes` filter
- Polymarket must continue to support fetching all markets when no tag filter is specified
- Kalshi price normalization (cents to probability 0.0-1.0) must remain unchanged
- Polymarket JSON outcome/price parsing must remain unchanged
- Binary market filtering (YES/NO only) must remain unchanged
- 5-stage match pipeline (category, asset, threshold, date, semantic) must remain unchanged
- Empty pairs list returned gracefully when no common groups exist

**Scope:**
All inputs that do NOT involve category/series filtering should be completely unaffected by this fix. This includes:
- Bulk fetch mode (when no target_series/target_tags configured)
- Sports exclusion logic
- Price normalization
- Semantic matching algorithm

## Hypothesized Root Cause

Based on the bug description, the most likely issues are:

1. **Missing Series-Based Filtering in Kalshi Client**: The `fetch_markets()` method does bulk fetch without using the `series_ticker` parameter. The API supports filtering by series (e.g., `KXBTC` for Bitcoin), but this is not utilized.

2. **Missing Tag-Based Filtering in Polymarket Client**: The `fetch_markets()` method doesn't use the `tag_id` parameter available in the Gamma API. This causes all 10000+ markets to be fetched instead of category-specific subsets.

3. **Incomplete Market Group Extraction**: The `_get_market_group()` method in `cross_venue_matcher.py` relies on `_extract_asset()` which doesn't parse Kalshi's `event_ticker` format. For example, `KXBTC-25JAN10` should map to `asset:bitcoin` but currently returns `None`.

4. **Missing Category Metadata**: Kalshi API responses don't include a `category` field in the market object. The `_normalize_market()` method sets `tags=[]` when `data.get("category")` is empty, losing the series information that could be inferred from `event_ticker`.

## Correctness Properties

Property 1: Fault Condition - Series/Tag Filtering Returns Relevant Markets

_For any_ fetch request where target series (Kalshi) or target tags (Polymarket) are configured, the fixed `fetch_markets()` function SHALL return only markets matching those series/tags, significantly reducing the result set from 5000+ to the relevant subset (typically 50-200 markets).

**Validates: Requirements 2.1, 2.3**

Property 2: Fault Condition - Market Group Extraction Returns Valid Groups

_For any_ Kalshi crypto market with an event_ticker containing a known series prefix (KXBTC, KXETH, KXSOL), the fixed `_get_market_group()` function SHALL return a valid group key (e.g., `asset:bitcoin`) by parsing the series prefix from the event_ticker.

**Validates: Requirements 2.2, 2.4**

Property 3: Preservation - Bulk Fetch Mode Unchanged

_For any_ fetch request where no target series/tags are configured, the fixed code SHALL produce exactly the same behavior as the original code, fetching all markets via bulk pagination.

**Validates: Requirements 3.1, 3.2**

Property 4: Preservation - Price Normalization Unchanged

_For any_ market normalization operation, the fixed code SHALL produce exactly the same price values as the original code, preserving cents-to-probability conversion for Kalshi and JSON parsing for Polymarket.

**Validates: Requirements 3.3, 3.4**

Property 5: Preservation - Match Pipeline Unchanged

_For any_ pair of market lists passed to `find_pairs()`, the fixed code SHALL apply the same 5-stage filtering pipeline, preserving binary market filtering, category matching, asset matching, threshold matching, date filtering, and semantic similarity.

**Validates: Requirements 3.5, 3.6, 3.7**

Property 6: Idempotency of Grouping

_For any_ market M, `_get_market_group(M)` SHALL return the same value regardless of whether M was fetched via Bulk or Series-based filtering. This ensures the improved market group extraction isn't accidentally dependent on the API parameters used to find the market.

**Validates: Requirements 2.4, 3.6**

## Fix Implementation

### Strategic Refinements (Future-Proofing)

**A. Avoid Hardcoded Mapping Trap**

Instead of hardcoded `{"KXBTC": "bitcoin"}` mappings that require code changes when Kalshi adds new assets (KXPEPE, KXDOGE), use regex-based extraction:

```python
# Extract asset from event_ticker dynamically
series = event_ticker.split('-')[0]  # "KXBTC-25JAN10" -> "KXBTC"
if series.startswith('KX'):
    asset = series[2:].lower()  # "KXBTC" -> "btc"
```

For category inference, maintain a minimal `SERIES_PREFIX_TO_CATEGORY` map that groups by prefix pattern rather than exact ticker.

**B. Handle Event Ticker vs Market Ticker Hierarchy**

Kalshi's hierarchy: Series → Event → Market. The event_ticker can contain strike prices (e.g., `KXBTC-25JAN10-B95000`).

Use greedy match to isolate Series part:
```python
# Greedy extraction - take first segment only
parts = event_ticker.split('-')
series = parts[0] if parts else None  # Always gets "KXBTC"
```

**C. Polymarket Tag Stability**

Polymarket `tag_id` values can change. Add secondary filter checking `group_id` or `slug` for keywords like "crypto", "bitcoin" to prevent pipeline breakage if tags are reorganized.

**D. Idempotency Guarantee**

The `_get_market_group()` function must produce identical results regardless of fetch method. This is achieved by deriving the group solely from market data (ID, question, tags) rather than any fetch-time metadata.

### Changes Required

Assuming our root cause analysis is correct:

**File**: `src/predarb/config.py`

**Changes**:
1. **Add target_series to KalshiConfig**: New optional field `target_series: List[str] = []` for series-based filtering (e.g., `["KXBTC", "KXETH", "KXSOL"]`)
2. **Add target_tags to PolymarketConfig**: New optional field `target_tags: List[str] = []` for tag-based filtering (e.g., `["crypto"]`)

---

**File**: `src/predarb/kalshi_client.py`

**Function**: `fetch_markets()`

**Changes**:
1. **Add series-based fetch mode**: When `target_series` is configured, iterate over each series and fetch markets using `series_ticker` parameter instead of bulk fetch
2. **Preserve bulk fetch fallback**: When `target_series` is empty, use existing bulk fetch logic unchanged
3. **Pass config to constructor**: Accept optional `KalshiConfig` to access `target_series`

**Function**: `_normalize_market()`

**Changes**:
4. **Infer category from event_ticker using regex**: Parse series prefix from `event_ticker` using `split('-')[0]` (e.g., `KXBTC-25JAN10` → `KXBTC`), then extract asset via `series[2:].lower()` (→ `btc`)
5. **Add prefix-to-category mapping**: Minimal map grouping by category type, not individual assets:
   - `KX` + crypto asset patterns → `crypto`
   - `KXPRES`, `KXSENATE`, `KXHOUSE`, `KXGOV` → `politics`
   - `KXFED`, `KXCPI`, `KXGDP`, `KXJOBS` → `economics`
   - `KXHIGH`, `KXLOW`, `KXRAIN` → `weather`

---

**File**: `src/predarb/polymarket_client.py`

**Function**: `fetch_markets()`

**Changes**:
1. **Add tag-based filtering**: When `target_tags` is configured, add `tag_id` parameter to API request
2. **Preserve bulk fetch fallback**: When `target_tags` is empty, use existing pagination logic unchanged

---

**File**: `src/predarb/cross_venue_matcher.py`

**Function**: `_get_market_group()`

**Changes**:
1. **Parse Kalshi event_ticker for series using regex**: Extract series prefix from market ID (format: `kalshi:EVENT_TICKER:TICKER`) using `split('-')[0]`, then derive asset via `series[2:].lower()`
2. **Dynamic asset extraction**: Instead of hardcoded map, use pattern: `KXBTC` → `btc`, `KXETH` → `eth`, `KXSOL` → `sol`, etc.
3. **Secondary Polymarket filter**: Check `slug` or `group_id` for crypto keywords as fallback if tags are unreliable

## Testing Strategy

### Validation Approach

The testing strategy follows a two-phase approach: first, surface counterexamples that demonstrate the bug on unfixed code, then verify the fix works correctly and preserves existing behavior.

### Exploratory Fault Condition Checking

**Goal**: Surface counterexamples that demonstrate the bug BEFORE implementing the fix. Confirm or refute the root cause analysis. If we refute, we will need to re-hypothesize.

**Test Plan**: Write tests that call `fetch_markets()` and `_get_market_group()` on real or mock Kalshi crypto markets. Run these tests on the UNFIXED code to observe failures and understand the root cause.

**Test Cases**:
1. **Kalshi Bulk Fetch Test**: Call `fetch_markets()` without series filter, count crypto vs sports markets (will show 99% sports on unfixed code)
2. **Kalshi Market Group Test**: Call `_get_market_group()` on a market with `event_ticker="KXBTC-25JAN10"` (will return `None` on unfixed code)
3. **Polymarket Bulk Fetch Test**: Call `fetch_markets()` without tag filter, count crypto vs other markets (will show mixed categories on unfixed code)
4. **Cross-Venue Pair Test**: Call `find_pairs()` with crypto markets from both venues (will return empty list on unfixed code)

**Expected Counterexamples**:
- `_get_market_group()` returns `None` for Kalshi crypto markets
- `find_pairs()` returns `[]` despite equivalent markets existing
- Possible causes: missing series parsing, missing category inference

### Fix Checking

**Goal**: Verify that for all inputs where the bug condition holds, the fixed function produces the expected behavior.

**Pseudocode:**
```
FOR ALL input WHERE isBugCondition(input) DO
  IF input.venue == "kalshi" AND target_series IS NOT EMPTY THEN
    result := fetch_markets_fixed(input)
    ASSERT all markets in result have event_ticker starting with target_series
  END IF
  
  IF input.market.event_ticker CONTAINS crypto_series THEN
    group := _get_market_group_fixed(input.market)
    ASSERT group IS NOT None
    ASSERT group STARTS WITH "asset:"
  END IF
END FOR
```

### Preservation Checking

**Goal**: Verify that for all inputs where the bug condition does NOT hold, the fixed function produces the same result as the original function.

**Pseudocode:**
```
FOR ALL input WHERE NOT isBugCondition(input) DO
  ASSERT fetch_markets_original(input) = fetch_markets_fixed(input)
  ASSERT _normalize_market_original(input) = _normalize_market_fixed(input)
  ASSERT find_pairs_original(input) = find_pairs_fixed(input)
END FOR
```

**Testing Approach**: Property-based testing is recommended for preservation checking because:
- It generates many test cases automatically across the input domain
- It catches edge cases that manual unit tests might miss
- It provides strong guarantees that behavior is unchanged for all non-buggy inputs

**Test Plan**: Observe behavior on UNFIXED code first for bulk fetch mode and non-crypto markets, then write property-based tests capturing that behavior.

**Test Cases**:
1. **Bulk Fetch Preservation**: Verify `fetch_markets()` with empty `target_series` returns same results as original
2. **Sports Exclusion Preservation**: Verify sports markets (KXNBA, KXNFL, etc.) continue to be filtered out
3. **Price Normalization Preservation**: Verify Kalshi cents-to-probability conversion unchanged
4. **Binary Market Preservation**: Verify non-binary markets continue to be filtered out
5. **Match Pipeline Preservation**: Verify 5-stage filtering produces same results for non-crypto markets

### Unit Tests

- Test `KalshiClient.fetch_markets()` with `target_series=["KXBTC"]` returns only Bitcoin markets
- Test `PolymarketClient.fetch_markets()` with `target_tags=["crypto"]` returns only crypto markets
- Test `_get_market_group()` on Kalshi market with `event_ticker="KXBTC-25JAN10"` returns `asset:bitcoin`
- Test `_get_market_group()` on Kalshi market with `event_ticker="KXETH-25JAN10"` returns `asset:ethereum`
- Test `_normalize_market()` sets `tags=["crypto"]` for KXBTC markets
- Test bulk fetch mode unchanged when `target_series=[]`

### Property-Based Tests

- Generate random Kalshi event_tickers with known series prefixes, verify `_get_market_group()` returns correct asset
- Generate random market configurations, verify bulk fetch mode produces identical results to original
- Generate random price values, verify normalization produces identical results to original
- Test that all non-crypto markets continue to work across many scenarios

### Integration Tests

- Test full pipeline: Kalshi series fetch → Polymarket tag fetch → cross-venue matching → pairs found
- Test config loading with new `target_series` and `target_tags` fields
- Test graceful degradation when series/tag filtering returns empty results
