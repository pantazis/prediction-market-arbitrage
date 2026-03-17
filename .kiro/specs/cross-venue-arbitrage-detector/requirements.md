# Requirements Document

## Introduction

This document specifies requirements for a comprehensive Cross-Venue Arbitrage Detector that identifies arbitrage opportunities between matched Polymarket and Kalshi prediction markets. The system normalizes different market structures (token-based vs contract-based), handles venue-specific constraints (no short selling on Polymarket), and detects multiple arbitrage types including price discrepancies, parity violations, and range market bucket arbitrage.

## Glossary

- **Cross_Venue_Detector**: The arbitrage detection system that analyzes matched market pairs across Polymarket and Kalshi to identify profitable opportunities
- **Market_Normalizer**: Component that converts venue-specific market formats into a unified structure for comparison
- **Opportunity_Classifier**: Component that categorizes detected arbitrage opportunities by type and feasibility
- **Price_Extractor**: Component that extracts bid/ask/mid prices from both venue formats
- **Range_Bucket_Analyzer**: Component that maps Polymarket range markets to equivalent Kalshi bucket contracts
- **Feasibility_Checker**: Component that validates opportunities against venue constraints (e.g., no short selling on Polymarket)
- **Matched_Pair**: A tuple of semantically equivalent markets from Kalshi and Polymarket identified by the CrossVenueMatcher
- **Normalized_Market**: A market converted to the unified internal format with prices in [0.0-1.0] range
- **Arbitrage_Opportunity**: A detected price discrepancy with calculated edge, required actions, and feasibility status

## Requirements

### Requirement 1: Market Structure Normalization

**User Story:** As an arbitrage system, I want to normalize Polymarket and Kalshi market structures into a common format, so that I can compare prices across venues accurately.

#### Acceptance Criteria

1. WHEN a Polymarket market is received, THE Market_Normalizer SHALL extract YES and NO token prices from the outcomes array and convert them to the [0.0-1.0] range
2. WHEN a Kalshi market is received, THE Market_Normalizer SHALL convert yes_bid/yes_ask from cents (0-100) to probability (0.0-1.0) and derive NO prices as (1.0 - YES_price)
3. THE Market_Normalizer SHALL populate best_bid and best_ask dictionaries for both YES and NO outcomes on all Normalized_Markets
4. IF a market has missing or invalid price data, THEN THE Market_Normalizer SHALL mark the market as non-tradeable and exclude it from arbitrage detection
5. FOR ALL valid markets, normalizing then extracting prices SHALL produce values within [0.0-1.0] range (round-trip property)

### Requirement 2: Cross-Venue Price Discrepancy Detection

**User Story:** As a trader, I want to detect when the same event has different prices on Kalshi vs Polymarket, so that I can profit from the price gap.

#### Acceptance Criteria

1. WHEN a Matched_Pair is provided, THE Cross_Venue_Detector SHALL calculate the price difference between equivalent outcomes
2. THE Cross_Venue_Detector SHALL detect opportunities where Kalshi YES price differs from Polymarket YES price by more than the configured threshold (default: 2%)
3. WHEN a price discrepancy is detected, THE Cross_Venue_Detector SHALL calculate net_edge after accounting for fees on both venues (Kalshi: 7bps, Polymarket: 10bps per side)
4. THE Cross_Venue_Detector SHALL generate TradeActions specifying which venue to buy and which to sell based on price comparison
5. IF the net_edge after fees is less than or equal to zero, THEN THE Cross_Venue_Detector SHALL discard the opportunity

### Requirement 3: Polymarket Short-Selling Constraint Handling

**User Story:** As a risk manager, I want the system to respect Polymarket's no-short-selling constraint, so that only executable strategies are proposed.

#### Acceptance Criteria

1. THE Feasibility_Checker SHALL reject any opportunity requiring a SELL action on Polymarket without existing inventory
2. WHEN an arbitrage requires selling on Polymarket, THE Feasibility_Checker SHALL check if the strategy can be restructured as BUY-only
3. WHEN Polymarket YES is overpriced vs Kalshi YES, THE Opportunity_Classifier SHALL generate a strategy: BUY Kalshi YES + BUY Polymarket NO (equivalent to shorting Polymarket YES)
4. WHEN Kalshi YES is overpriced vs Polymarket YES, THE Opportunity_Classifier SHALL generate a strategy: BUY Polymarket YES + SELL Kalshi YES (Kalshi supports shorting)
5. THE Feasibility_Checker SHALL mark opportunities as "FEASIBLE" only when all required actions are executable on their respective venues

### Requirement 4: Cross-Venue Parity Violation Detection

**User Story:** As a trader, I want to detect when buying YES on one venue and NO on another costs less than $1.00, so that I can lock in guaranteed profit.

#### Acceptance Criteria

1. WHEN a Matched_Pair is provided, THE Cross_Venue_Detector SHALL calculate the cost of buying YES on venue A plus NO on venue B
2. THE Cross_Venue_Detector SHALL detect opportunities where (Kalshi_YES_ask + Polymarket_NO_ask) < 1.0 minus fees
3. THE Cross_Venue_Detector SHALL detect opportunities where (Polymarket_YES_ask + Kalshi_NO_ask) < 1.0 minus fees
4. WHEN a cross-venue parity violation is detected, THE Cross_Venue_Detector SHALL calculate guaranteed profit as (1.0 - total_cost - total_fees)
5. THE Cross_Venue_Detector SHALL generate TradeActions for both legs of the parity trade with appropriate venue assignments

### Requirement 5: Range Market Bucket Arbitrage Detection

**User Story:** As a trader, I want to detect arbitrage between Polymarket range markets and equivalent Kalshi bucket contracts, so that I can exploit structural pricing inefficiencies.

#### Acceptance Criteria

1. WHEN a Polymarket range market maps to multiple Kalshi bucket contracts, THE Range_Bucket_Analyzer SHALL identify the mapping relationship
2. THE Range_Bucket_Analyzer SHALL detect when the sum of Kalshi bucket YES prices differs from the equivalent Polymarket outcome price by more than the threshold
3. WHEN Kalshi buckets are underpriced relative to Polymarket, THE Range_Bucket_Analyzer SHALL generate BUY actions for all relevant Kalshi buckets
4. WHEN Kalshi buckets are overpriced relative to Polymarket, THE Range_Bucket_Analyzer SHALL generate a strategy using Polymarket BUY and Kalshi SELL (respecting short constraints)
5. THE Range_Bucket_Analyzer SHALL calculate net_edge accounting for fees across all legs of the bucket trade

### Requirement 6: Opportunity Output Format

**User Story:** As a downstream consumer, I want arbitrage opportunities in a standardized format, so that the risk manager and broker can process them consistently.

#### Acceptance Criteria

1. THE Cross_Venue_Detector SHALL output opportunities as Opportunity objects with type="CROSS_VENUE_PRICE", "CROSS_VENUE_PARITY", or "RANGE_BUCKET"
2. THE Cross_Venue_Detector SHALL include both market IDs in the market_ids list for all cross-venue opportunities
3. THE Cross_Venue_Detector SHALL populate the actions list with TradeAction objects specifying market_id, outcome_id, side, amount, and limit_price
4. THE Cross_Venue_Detector SHALL include metadata with venue-specific details: kalshi_price, polymarket_price, price_diff, fees_kalshi, fees_polymarket
5. THE Cross_Venue_Detector SHALL set net_edge to the expected profit after all fees and slippage

### Requirement 7: Stale Quote Filtering

**User Story:** As a risk manager, I want to filter out opportunities based on stale quotes, so that we don't trade on outdated prices.

#### Acceptance Criteria

1. WHEN either market in a Matched_Pair has an updated_at timestamp older than the configured staleness threshold (default: 5 minutes), THE Cross_Venue_Detector SHALL flag the opportunity as "STALE"
2. THE Cross_Venue_Detector SHALL include the age of each quote in the opportunity metadata
3. WHILE a market's updated_at is within the staleness threshold, THE Cross_Venue_Detector SHALL treat the quote as valid
4. IF both markets have stale quotes, THEN THE Cross_Venue_Detector SHALL discard the opportunity entirely
5. THE Cross_Venue_Detector SHALL log warnings for opportunities flagged as stale but not discarded

### Requirement 8: Minimum Liquidity Filtering

**User Story:** As a risk manager, I want to filter out opportunities in illiquid markets, so that we can actually execute the proposed trades.

#### Acceptance Criteria

1. WHEN either market in a Matched_Pair has liquidity below the configured minimum (default: $100), THE Cross_Venue_Detector SHALL flag the opportunity as "LOW_LIQUIDITY"
2. THE Cross_Venue_Detector SHALL include liquidity values for both venues in the opportunity metadata
3. THE Cross_Venue_Detector SHALL calculate maximum executable size based on the minimum liquidity of the two venues
4. IF both markets have liquidity below the minimum threshold, THEN THE Cross_Venue_Detector SHALL discard the opportunity
5. THE Cross_Venue_Detector SHALL adjust the recommended trade amount based on available liquidity
