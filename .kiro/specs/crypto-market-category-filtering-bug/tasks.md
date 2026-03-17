# Implementation Plan

- [x] 1. Write bug condition exploration test
  - **Property 1: Fault Condition** - Category Metadata Missing for Kalshi Markets
  - **CRITICAL**: This test MUST FAIL on unfixed code - failure confirms the bug exists
  - **DO NOT attempt to fix the test or the code when it fails**
  - **NOTE**: This test encodes the expected behavior - it will validate the fix when it passes after implementation
  - **GOAL**: Surface counterexamples that demonstrate the bug exists
  - **Scoped PBT Approach**: Scope the property to Kalshi markets with known series prefixes (KXBTC, KXETH, KXSOL, KXPRES, KXFED, etc.)
  - Test that `_get_market_group()` returns `None` for Kalshi markets with event_ticker containing known series prefixes
  - Test that `_normalize_market()` produces markets with empty `tags=[]` for Kalshi crypto/politics/economics markets
  - Test that `find_pairs()` returns empty list when both venues have equivalent markets but Kalshi lacks category metadata
  - Create mock Kalshi market data with event_ticker formats: `KXBTC-25JAN10`, `KXETH-25FEB15`, `KXPRES-24NOV05`, `KXFED-25MAR19`
  - Run test on UNFIXED code
  - **EXPECTED OUTCOME**: Test FAILS (this is correct - it proves the bug exists)
  - Document counterexamples found: `_get_market_group()` returns `None` for markets that should return `asset:bitcoin`, `category:politics`, etc.
  - _Requirements: 1.3, 1.4, 1.5_

- [x] 2. Write preservation property tests (BEFORE implementing fix)
  - **Property 2: Preservation** - Existing Behavior Unchanged for Non-Category-Filtered Operations
  - **IMPORTANT**: Follow observation-first methodology
  - Observe: Sports markets (KXNBA, KXNFL, KXMLB prefixes) are excluded by `_normalize_market()`
  - Observe: Kalshi price normalization converts cents to probability (50 cents → 0.5)
  - Observe: Binary market filtering (YES/NO only) works correctly
  - Observe: 5-stage match pipeline produces consistent results for markets with existing category metadata
  - Observe: Empty pairs list returned gracefully when no common groups exist
  - Write property-based tests:
    - For all sports market event_tickers, `_normalize_market()` returns `None`
    - For all Kalshi price values (0-100 cents), normalized price equals value/100.0
    - For all market pairs without common groups, `find_pairs()` returns empty list
    - For all Polymarket markets with existing tags, `_get_market_group()` returns valid group
  - Verify tests pass on UNFIXED code
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7_

- [x] 3. Add comprehensive series-to-category mapping

  - [-] 3.1 Create series-to-category mapping constant
    - Add `SERIES_TO_CATEGORY` dict in `kalshi_client.py` or new `src/predarb/series_mapper.py`
    - Map crypto series: `KXBTC → crypto`, `KXETH → crypto`, `KXSOL → crypto`
    - Map politics series: `KXPRES → politics`, `KXSENATE → politics`, `KXHOUSE → politics`, `KXGOV → politics`
    - Map economics series: `KXFED → economics`, `KXCPI → economics`, `KXGDP → economics`, `KXJOBS → economics`
    - Map weather series: `KXHIGHNY → weather`, `KXLOWNY → weather`, `KXRAIN → weather`
    - Map other known series as discovered
    - _Bug_Condition: Kalshi markets lack category metadata because API doesn't return category field_
    - _Expected_Behavior: All Kalshi markets with known series prefixes get proper category tags_
    - _Requirements: 2.2_

  - [ ] 3.2 Create series-to-asset mapping constant
    - Add `SERIES_TO_ASSET` dict alongside category mapping
    - Map crypto assets: `KXBTC → bitcoin`, `KXETH → ethereum`, `KXSOL → solana`
    - Map financial assets: `INXD → nasdaq`, `INXU → sp500` (if applicable)
    - _Expected_Behavior: Kalshi crypto markets get proper asset tags for cross-venue matching_
    - _Requirements: 2.4_

- [x] 4. Update Kalshi client to infer category from event_ticker

  - [ ] 4.1 Add helper function to extract series prefix from event_ticker
    - Parse event_ticker format: `KXBTC-25JAN10` → `KXBTC`
    - Handle edge cases: missing event_ticker, malformed format
    - Return `None` for unrecognized formats
    - _Requirements: 2.2_

  - [ ] 4.2 Update `_normalize_market()` to populate tags from series prefix
    - Call series prefix extraction on `event_ticker`
    - Look up category in `SERIES_TO_CATEGORY` mapping
    - Set `tags=[category]` if found, otherwise keep existing behavior `tags=[]`
    - Preserve existing sports exclusion logic unchanged
    - Preserve existing price normalization unchanged
    - _Bug_Condition: `tags=data.get("category", "").split(",")` returns empty when API has no category_
    - _Expected_Behavior: `tags` populated from series prefix mapping_
    - _Preservation: Sports exclusion, price normalization unchanged_
    - _Requirements: 2.2, 3.1, 3.3_

- [x] 5. Update cross-venue matcher to extract asset from Kalshi market ID

  - [ ] 5.1 Update `_get_market_group()` to parse Kalshi event_ticker
    - Check if market ID starts with `kalshi:`
    - Extract event_ticker from ID format `kalshi:EVENT_TICKER:TICKER`
    - Parse series prefix from event_ticker (e.g., `KXBTC-25JAN10` → `KXBTC`)
    - Look up asset in `SERIES_TO_ASSET` mapping
    - Return `asset:{asset}` if found
    - Fall back to existing `_extract_asset()` and category inference logic
    - _Bug_Condition: `_get_market_group()` returns `None` for Kalshi crypto markets_
    - _Expected_Behavior: Returns `asset:bitcoin` for KXBTC markets, `asset:ethereum` for KXETH, etc._
    - _Preservation: Existing category inference for non-Kalshi markets unchanged_
    - _Requirements: 2.4, 3.6_

  - [ ] 5.2 Update `_extract_asset()` to use series-to-asset mapping for Kalshi
    - Add early check for Kalshi market ID format
    - Extract and map series prefix to asset
    - Preserve existing ticker_parser and text extraction fallbacks
    - _Requirements: 2.4_

- [x] 6. Verify bug condition exploration test now passes

  - [ ] 6.1 Re-run bug condition exploration test
    - **Property 1: Expected Behavior** - Category Metadata Populated for Kalshi Markets
    - **IMPORTANT**: Re-run the SAME test from task 1 - do NOT write a new test
    - The test from task 1 encodes the expected behavior
    - When this test passes, it confirms the expected behavior is satisfied
    - Run bug condition exploration test from step 1
    - **EXPECTED OUTCOME**: Test PASSES (confirms bug is fixed)
    - Verify `_get_market_group()` returns valid groups for all known series prefixes
    - Verify `_normalize_market()` populates tags for crypto/politics/economics markets
    - _Requirements: 2.2, 2.4, 2.5_

  - [ ] 6.2 Verify preservation tests still pass
    - **Property 2: Preservation** - Existing Behavior Unchanged
    - **IMPORTANT**: Re-run the SAME tests from task 2 - do NOT write new tests
    - Run preservation property tests from step 2
    - **EXPECTED OUTCOME**: Tests PASS (confirms no regressions)
    - Confirm sports exclusion still works
    - Confirm price normalization unchanged
    - Confirm binary market filtering unchanged
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7_

- [ ] 7. Checkpoint - Ensure all tests pass
  - Run full test suite: `pytest tests/ -v`
  - Verify no regressions in existing functionality
  - Verify new category/asset mapping works across all categories (crypto, politics, economics, weather)
  - Ask the user if questions arise
