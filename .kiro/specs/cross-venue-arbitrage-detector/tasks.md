# Implementation Plan: Cross-Venue Arbitrage Detector

## Overview

Implement a comprehensive cross-venue arbitrage detector that identifies opportunities between matched Polymarket and Kalshi markets. The detector integrates with the existing `src/predarb/detectors/` pattern and outputs `Opportunity` objects compatible with the risk manager and broker.

## Tasks

- [x] 1. Set up configuration and data models
  - [x] 1.1 Create CrossVenueDetectorConfig in config.py
    - Add config class with: min_price_diff_threshold, kalshi_fee_bps, polymarket_fee_bps, slippage_bps, staleness_threshold_seconds, min_liquidity_usd, bucket_sum_threshold
    - Add enable_cross_venue flag to DetectorConfig
    - Register in AppConfig
    - _Requirements: 2.2, 2.3, 7.1, 8.1_

  - [x] 1.2 Create NormalizedMarket dataclass in models.py
    - Fields: market_id, exchange, question, yes_bid, yes_ask, no_bid, no_ask, liquidity_usd, updated_at, original, is_tradeable, non_tradeable_reason
    - _Requirements: 1.1, 1.2, 1.3_

- [x] 2. Implement Market Normalization Layer
  - [x] 2.1 Create MarketNormalizer class in src/predarb/detectors/cross_venue.py
    - Implement normalize() method dispatching to venue-specific handlers
    - Implement normalize_polymarket() extracting YES/NO from outcomes array
    - Implement normalize_kalshi() converting cents to probability and deriving NO prices
    - Implement _validate_prices() marking invalid markets as non-tradeable
    - _Requirements: 1.1, 1.2, 1.3, 1.4_

  - [ ]* 2.2 Write property test for price normalization range invariant
    - **Property 1: Price Normalization Range Invariant**
    - **Validates: Requirements 1.1, 1.2, 1.5**

  - [ ]* 2.3 Write property test for Kalshi NO price derivation
    - **Property 2: Kalshi NO Price Derivation**
    - **Validates: Requirements 1.2**

  - [ ]* 2.4 Write property test for bid/ask structure completeness
    - **Property 3: Bid/Ask Structure Completeness**
    - **Validates: Requirements 1.3**

  - [ ]* 2.5 Write property test for invalid price exclusion
    - **Property 4: Invalid Price Exclusion**
    - **Validates: Requirements 1.4**

  - [x] 2.6 Create PriceExtractor class
    - Implement extract() returning ExtractedPrices or None
    - Implement calculate_mid() for mid price calculation
    - _Requirements: 1.3, 1.5_

- [x] 3. Checkpoint - Normalization layer complete
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Implement Filtering Components
  - [x] 4.1 Create StaleQuoteFilter class
    - Implement check() returning StalenessResult with ages and flags
    - Flag "STALE" if one market exceeds threshold
    - Discard if both markets stale
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_

  - [ ]* 4.2 Write property test for staleness threshold filtering
    - **Property 20: Staleness Threshold Filtering**
    - **Validates: Requirements 7.1, 7.3, 7.4**

  - [x] 4.3 Create LiquidityFilter class
    - Implement check() returning LiquidityResult with liquidity values and flags
    - Calculate max_executable_size as min of both venues
    - Flag "LOW_LIQUIDITY" if one below threshold, discard if both below
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_

  - [ ]* 4.4 Write property test for liquidity threshold filtering
    - **Property 21: Liquidity Threshold Filtering**
    - **Validates: Requirements 8.1, 8.4**

  - [ ]* 4.5 Write property test for maximum executable size calculation
    - **Property 22: Maximum Executable Size Calculation**
    - **Validates: Requirements 8.3**

- [x] 5. Implement Feasibility Checker
  - [x] 5.1 Create FeasibilityChecker class
    - Implement check() validating venue constraints
    - Implement _has_polymarket_sell() detecting Polymarket SELL actions
    - Implement _restructure_as_buy_only() converting SELL Poly YES to BUY Poly NO
    - Implement _generate_strategy() for both price comparison scenarios
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

  - [ ]* 5.2 Write property test for Polymarket short-selling constraint
    - **Property 9: Polymarket Short-Selling Constraint**
    - **Validates: Requirements 3.1, 3.5**

  - [ ]* 5.3 Write property test for Polymarket overpriced strategy
    - **Property 10: Polymarket Overpriced Strategy**
    - **Validates: Requirements 3.3**

  - [ ]* 5.4 Write property test for Kalshi overpriced strategy
    - **Property 11: Kalshi Overpriced Strategy**
    - **Validates: Requirements 3.4**

- [x] 6. Checkpoint - Filters and feasibility complete
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. Implement Price Discrepancy Detection
  - [x] 7.1 Implement _detect_price_discrepancy() in CrossVenueDetector
    - Calculate price difference between equivalent outcomes
    - Apply threshold check (default 2%)
    - Calculate net_edge after fees (Kalshi 7bps, Polymarket 10bps per side)
    - Generate TradeActions with correct venue assignments
    - Discard if net_edge <= 0
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_

  - [ ]* 7.2 Write property test for price discrepancy detection threshold
    - **Property 5: Price Discrepancy Detection Threshold**
    - **Validates: Requirements 2.2**

  - [ ]* 7.3 Write property test for net edge fee calculation
    - **Property 6: Net Edge Fee Calculation**
    - **Validates: Requirements 2.3, 6.5**

  - [ ]* 7.4 Write property test for trade direction correctness
    - **Property 7: Trade Direction Correctness**
    - **Validates: Requirements 2.4**

  - [ ]* 7.5 Write property test for non-positive edge filtering
    - **Property 8: Non-Positive Edge Filtering**
    - **Validates: Requirements 2.5**

- [x] 8. Implement Cross-Venue Parity Violation Detection
  - [x] 8.1 Implement _detect_parity_violation() in CrossVenueDetector
    - Calculate cost of YES on venue A + NO on venue B
    - Detect when total cost < 1.0 minus fees
    - Calculate guaranteed profit
    - Generate two-leg TradeActions
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

  - [ ]* 8.2 Write property test for cross-venue parity violation detection
    - **Property 12: Cross-Venue Parity Violation Detection**
    - **Validates: Requirements 4.2, 4.3, 4.4**

  - [ ]* 8.3 Write property test for parity trade actions completeness
    - **Property 13: Parity Trade Actions Completeness**
    - **Validates: Requirements 4.5**

- [x] 9. Checkpoint - Core detection complete
  - Ensure all tests pass, ask the user if questions arise.

- [x] 10. Implement Range Bucket Analyzer
  - [x] 10.1 Create RangeBucketAnalyzer class
    - Implement identify_bucket_mapping() for Polymarket range to Kalshi buckets
    - Implement detect_bucket_arbitrage() comparing sum of bucket prices
    - Implement _calculate_bucket_sum() for bucket YES prices
    - Implement _generate_bucket_actions() respecting short constraints
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

  - [ ]* 10.2 Write property test for bucket sum arbitrage detection
    - **Property 14: Bucket Sum Arbitrage Detection**
    - **Validates: Requirements 5.2**

  - [ ]* 10.3 Write property test for bucket trade multi-leg fees
    - **Property 15: Bucket Trade Multi-Leg Fees**
    - **Validates: Requirements 5.5**

- [x] 11. Implement Opportunity Classifier and Output Format
  - [x] 11.1 Create OpportunityClassifier class
    - Implement classify() creating Opportunity objects with correct type
    - Implement _build_metadata() with all required fields
    - Support types: CROSS_VENUE_PRICE, CROSS_VENUE_PARITY, RANGE_BUCKET
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

  - [ ]* 11.2 Write property test for opportunity type classification
    - **Property 16: Opportunity Type Classification**
    - **Validates: Requirements 6.1**

  - [ ]* 11.3 Write property test for market IDs completeness
    - **Property 17: Market IDs Completeness**
    - **Validates: Requirements 6.2**

  - [ ]* 11.4 Write property test for TradeAction field completeness
    - **Property 18: TradeAction Field Completeness**
    - **Validates: Requirements 6.3**

  - [ ]* 11.5 Write property test for metadata completeness
    - **Property 19: Metadata Completeness**
    - **Validates: Requirements 6.4, 7.2, 8.2**

  - [ ]* 11.6 Write property test for trade amount liquidity constraint
    - **Property 23: Trade Amount Liquidity Constraint**
    - **Validates: Requirements 8.5**

- [x] 12. Implement Main CrossVenueDetector Class
  - [x] 12.1 Create CrossVenueDetector class orchestrating all components
    - Implement __init__() wiring normalizer, filters, checker, classifier
    - Implement detect() processing matched pairs through full pipeline
    - Integrate with existing detector pattern (same interface as other detectors)
    - _Requirements: 2.1, 3.5, 6.1, 6.2, 6.3, 6.4, 6.5_

  - [ ]* 12.2 Write unit tests for CrossVenueDetector integration
    - Test full pipeline with synthetic matched pairs
    - Test edge cases: empty pairs, all filtered, mix of valid/invalid
    - _Requirements: All_

- [x] 13. Checkpoint - All components complete
  - Ensure all tests pass, ask the user if questions arise.

- [x] 14. Integration with Pipeline
  - [x] 14.1 Register CrossVenueDetector in pipeline.py
    - Add detector instantiation with config
    - Wire to receive matched pairs from CrossVenueMatcher
    - Add opportunities to detection results
    - _Requirements: 6.1, 6.2_

  - [ ]* 14.2 Write integration test for end-to-end detection
    - Test with realistic matched pair data
    - Verify opportunities flow to risk manager
    - _Requirements: All_

- [x] 15. Final checkpoint - Feature complete
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- All code follows existing patterns in src/predarb/detectors/
- NO SHORT SELLING on Polymarket is enforced by FeasibilityChecker
