# Requirements Document

## Introduction

This feature improves the cross-venue market matching system for arbitrage detection between Kalshi and Polymarket. The current implementation suffers from high false positive rates due to insufficient threshold extraction, weak category filtering (Polymarket often has empty tags), and over-reliance on semantic similarity alone. The improved system will extract structured data from market questions (thresholds, assets, dates) and use multi-stage filtering to produce high-confidence matches suitable for arbitrage trading.

## Glossary

- **Market_Matcher**: The system responsible for finding equivalent markets across Kalshi and Polymarket venues
- **Threshold_Extractor**: Component that parses numeric price/value thresholds from market questions (e.g., "$3730" from "ETH above $3730")
- **Asset_Normalizer**: Component that identifies and normalizes asset names across different phrasings (e.g., "ETH", "Ethereum", "Ether" → "ethereum")
- **Ticker_Parser**: Component that extracts structured data from Kalshi tickers (e.g., "KXETH-26JAN2310-B3730" → asset=ETH, date=Jan 26 2023, threshold=3730, direction=above)
- **Match_Candidate**: A potential pair of markets from different venues that may represent the same underlying event
- **Verified_Match**: A Match_Candidate that has passed all validation stages and is confirmed to represent the same event
- **Semantic_Score**: Cosine similarity score (0.0-1.0) between market question embeddings
- **Structural_Match**: A match based on extracted structured data (asset, threshold, date, direction) rather than semantic similarity alone

## Requirements

### Requirement 1: Kalshi Ticker Parsing

**User Story:** As an arbitrage trader, I want the system to extract structured data from Kalshi tickers, so that I can match markets based on exact threshold values rather than fuzzy text similarity.

#### Acceptance Criteria

1. WHEN a Kalshi market with a structured ticker is processed, THE Ticker_Parser SHALL extract the asset symbol, expiry date, threshold value, and direction (above/below)
2. WHEN the ticker format is "KXETH-26JAN2310-B3730", THE Ticker_Parser SHALL extract asset="ETH", date="2023-01-26 10:00", threshold=3730, direction="above"
3. WHEN the ticker format is "KXBTC-31DEC2412-T95000", THE Ticker_Parser SHALL extract asset="BTC", date="2024-12-31 12:00", threshold=95000, direction="above"
4. IF a ticker does not match known patterns, THEN THE Ticker_Parser SHALL return None for structured fields and fall back to text extraction
5. FOR ALL valid Kalshi tickers, parsing then formatting back to ticker format SHALL produce an equivalent ticker (round-trip property)

### Requirement 2: Enhanced Threshold Extraction from Text

**User Story:** As an arbitrage trader, I want the system to reliably extract price thresholds from varied market question phrasings, so that markets with different wording but identical thresholds can be matched.

#### Acceptance Criteria

1. WHEN a market question contains a price threshold, THE Threshold_Extractor SHALL extract the numeric value and comparison direction
2. THE Threshold_Extractor SHALL recognize patterns including: "$3,730", "$3730", "3730 dollars", "3.73k", "$3,730 or higher", "above $3730", "at least $3730", "below $3730", "under $3730"
3. WHEN extracting from "Will ETH be above $3730?", THE Threshold_Extractor SHALL return threshold=3730, direction="above"
4. WHEN extracting from "Ethereum price $3,730 or higher?", THE Threshold_Extractor SHALL return threshold=3730, direction="above"
5. IF no threshold pattern is found, THEN THE Threshold_Extractor SHALL return None without raising an error
6. THE Threshold_Extractor SHALL handle percentage thresholds (e.g., "above 5%", "at least 3.5%") returning the numeric value and unit

### Requirement 3: Asset Name Normalization

**User Story:** As an arbitrage trader, I want the system to recognize that "ETH", "Ethereum", and "Ether" refer to the same asset, so that markets using different naming conventions can be matched.

#### Acceptance Criteria

1. THE Asset_Normalizer SHALL maintain a mapping of common asset aliases to canonical names
2. WHEN normalizing "ETH", "Ethereum", "Ether", or "ethereum", THE Asset_Normalizer SHALL return "ethereum"
3. WHEN normalizing "BTC", "Bitcoin", or "bitcoin", THE Asset_Normalizer SHALL return "bitcoin"
4. WHEN normalizing "S&P 500", "SPX", "SP500", or "S&P500", THE Asset_Normalizer SHALL return "sp500"
5. IF an asset name is not in the alias mapping, THEN THE Asset_Normalizer SHALL return the lowercase, whitespace-trimmed input
6. THE Asset_Normalizer SHALL be case-insensitive for all lookups

### Requirement 4: Structural Match Filtering

**User Story:** As an arbitrage trader, I want the system to require matching thresholds and assets before considering semantic similarity, so that false positives like "ETH above $3000" matching "ETH above $3500" are eliminated.

#### Acceptance Criteria

1. WHEN both markets have extracted thresholds, THE Market_Matcher SHALL only consider them a Match_Candidate if thresholds are within 0.1% of each other
2. WHEN both markets have extracted assets, THE Market_Matcher SHALL only consider them a Match_Candidate if normalized assets are identical
3. WHEN both markets have extracted directions (above/below), THE Market_Matcher SHALL only consider them a Match_Candidate if directions match
4. IF structural data is available for both markets, THEN THE Market_Matcher SHALL prioritize structural matching over semantic similarity
5. WHILE structural data is missing from one or both markets, THE Market_Matcher SHALL fall back to semantic-only matching with a higher similarity threshold (0.85 instead of 0.65)

### Requirement 5: Date Resolution Matching

**User Story:** As an arbitrage trader, I want the system to verify that matched markets resolve on the same date and time, so that I don't match a "Jan 26 10:00 AM" market with a "Jan 26 12:00 PM" market.

#### Acceptance Criteria

1. WHEN both markets have expiry dates, THE Market_Matcher SHALL only consider them a Match_Candidate if dates are within 2 hours of each other
2. THE Market_Matcher SHALL extract resolution times from Kalshi tickers (e.g., "26JAN2310" = Jan 26, 2023 at 10:00 UTC)
3. WHEN a Polymarket market has an end_date field, THE Market_Matcher SHALL use it for date comparison
4. IF date information is missing from either market, THEN THE Market_Matcher SHALL log a warning and exclude the pair from matching
5. THE Market_Matcher SHALL handle timezone differences by normalizing all dates to UTC before comparison

### Requirement 6: Fallback Category Matching for Empty Tags

**User Story:** As an arbitrage trader, I want the system to infer categories from market questions when Polymarket tags are empty, so that category-based filtering still works.

#### Acceptance Criteria

1. WHEN a Polymarket market has empty tags and null category, THE Market_Matcher SHALL infer category from the market question text
2. THE Market_Matcher SHALL recognize crypto-related keywords ("bitcoin", "ethereum", "btc", "eth", "crypto", "token") and assign category "CRYPTO"
3. THE Market_Matcher SHALL recognize politics-related keywords ("president", "election", "congress", "senate", "vote", "trump", "biden") and assign category "POLITICS"
4. THE Market_Matcher SHALL recognize economics-related keywords ("fed", "inflation", "cpi", "interest rate", "gdp", "unemployment") and assign category "ECONOMICS"
5. IF no category can be inferred, THEN THE Market_Matcher SHALL assign category "OTHER" and the market SHALL be excluded from strict bucket matching

### Requirement 7: Multi-Stage Match Pipeline

**User Story:** As an arbitrage trader, I want the matching system to use a multi-stage pipeline that progressively filters candidates, so that I get high-confidence matches with clear rejection reasons.

#### Acceptance Criteria

1. THE Market_Matcher SHALL implement a pipeline with stages: (1) Category Filter, (2) Asset Filter, (3) Threshold Filter, (4) Date Filter, (5) Semantic Similarity
2. WHEN a candidate is rejected, THE Market_Matcher SHALL log which stage rejected it and why
3. THE Market_Matcher SHALL track rejection counts per stage for debugging and tuning
4. WHEN all structural filters pass, THE Market_Matcher SHALL require semantic similarity >= 0.60 for final acceptance
5. WHEN structural filters cannot be applied (missing data), THE Market_Matcher SHALL require semantic similarity >= 0.85 for acceptance
6. THE Market_Matcher SHALL return Verified_Match objects containing the match score, matched fields, and confidence level

### Requirement 8: Match Confidence Scoring

**User Story:** As an arbitrage trader, I want each match to have a confidence score based on how many fields matched structurally, so that I can prioritize high-confidence matches for trading.

#### Acceptance Criteria

1. THE Market_Matcher SHALL compute a confidence score (0.0-1.0) for each Verified_Match
2. WHEN asset, threshold, direction, and date all match structurally, THE Market_Matcher SHALL assign confidence >= 0.95
3. WHEN only semantic similarity is used (no structural data), THE Market_Matcher SHALL assign confidence = semantic_score * 0.7
4. THE Market_Matcher SHALL include in the Verified_Match which fields matched structurally vs semantically
5. WHEN confidence is below 0.80, THE Market_Matcher SHALL flag the match for LLM verification

### Requirement 9: Duplicate Match Prevention

**User Story:** As an arbitrage trader, I want the system to prevent multiple Kalshi markets from matching the same Polymarket market, so that I don't get conflicting arbitrage signals.

#### Acceptance Criteria

1. THE Market_Matcher SHALL track which Polymarket markets have already been matched
2. WHEN multiple Kalshi markets match the same Polymarket market, THE Market_Matcher SHALL select only the highest-confidence match
3. THE Market_Matcher SHALL log when duplicate matches are detected and which one was selected
4. IF two Kalshi markets have equal confidence for the same Polymarket market, THEN THE Market_Matcher SHALL prefer the one with higher liquidity
5. THE Market_Matcher SHALL return at most one Kalshi market per Polymarket market in the final results

### Requirement 10: Match Result Reporting

**User Story:** As an arbitrage trader, I want detailed match reports showing why pairs were matched or rejected, so that I can debug matching issues and tune parameters.

#### Acceptance Criteria

1. THE Market_Matcher SHALL produce a match report containing: total candidates considered, matches accepted, rejections per stage
2. WHEN a match is accepted, THE Market_Matcher SHALL include: both market IDs, confidence score, matched fields, semantic score
3. WHEN a match is rejected, THE Market_Matcher SHALL include: both market IDs, rejection stage, rejection reason
4. THE Market_Matcher SHALL support outputting the match report as JSON for programmatic analysis
5. THE Market_Matcher SHALL log a summary of match statistics at INFO level after each matching run
