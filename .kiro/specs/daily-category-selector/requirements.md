# Requirements Document

## Introduction

This document specifies requirements for an Intelligent Daily Category Selector that uses a TWO-STAGE LLM approach to maximize arbitrage discovery potential between Polymarket and Kalshi.

**Stage 1 (External LLM):** Uses an LLM with web browsing capabilities (e.g., Gemini with Google Search grounding) to browse polymarket.com and kalshi.com, identifying hot topics and trending markets that exist on both platforms.

**Stage 2 (Internal LLM):** Uses an internal LLM (leveraging existing llm_verifier infrastructure) to intelligently verify that candidate market pairs are truly equivalent and suitable for arbitrage. This stage has deep understanding of arbitrage goals and can reason about whether two market titles represent the same underlying event with compatible resolution criteria.

## Glossary

- **Category_Selector**: The main system component that orchestrates daily category evaluation and selection using a two-stage LLM approach
- **Web_Browsing_LLM**: An LLM with web search/browsing capabilities (e.g., Gemini with Google Search grounding) that can read and analyze live website content from polymarket.com and kalshi.com (Stage 1)
- **Internal_LLM**: An LLM used for intelligent pair verification that understands arbitrage goals and can reason about market equivalence (Stage 2, uses existing llm_verifier infrastructure)
- **Trending_Analyzer**: The LLM capability that identifies which categories are currently trending or featured on each platform
- **Overlap_Detector**: The LLM capability that identifies categories where both platforms have active, similar markets
- **Selection_Output**: The JSON output containing the selected category, confidence score, reasoning, and alternatives
- **Category**: A market classification bucket (e.g., Politics, Crypto, Economics) used to group related prediction markets
- **Cross_Platform_Overlap**: The degree to which both Polymarket and Kalshi list similar or equivalent markets in a category
- **Trending_Category**: A category that is prominently featured, has high activity, or is receiving significant attention on a platform
- **Pair_Verification_Output**: The JSON output from Internal_LLM containing match status, confidence, reasoning, and arbitrage assessment
- **Market_Equivalence**: Two markets that resolve to the same outcome based on the same underlying event with compatible settlement rules

## Requirements

### Requirement 1: Daily Category Selection Execution

**User Story:** As an arbitrage bot operator, I want the system to automatically select the best category to scan each day, so that I can focus resources on the most promising arbitrage opportunities.

#### Acceptance Criteria

1. THE Category_Selector SHALL execute once per day at a configurable time (default: 00:00 UTC)
2. WHEN triggered, THE Category_Selector SHALL invoke the Web_Browsing_LLM to analyze both prediction market websites and produce a Selection_Output
3. THE Category_Selector SHALL persist the Selection_Output to a configurable file path (default: `data/daily_category_selection.json`)
4. WHEN a previous selection exists for the current date, THE Category_Selector SHALL skip execution unless force_refresh is enabled
5. THE Category_Selector SHALL support manual triggering via CLI command `python -m predarb select-category`

### Requirement 2: Web Browsing LLM Configuration

**User Story:** As a bot operator, I want to configure which LLM provider with web browsing capabilities to use, so that I can leverage the best available service for website analysis.

#### Acceptance Criteria

1. THE Category_Selector SHALL support Gemini with Google Search grounding as the primary Web_Browsing_LLM provider
2. THE Category_Selector SHALL read LLM configuration from config.yml under `category_selector.llm` section including provider, model, and api_key_env
3. THE Category_Selector SHALL support configurable timeout for web browsing operations (default: 60 seconds)
4. IF the Web_Browsing_LLM is unavailable, THEN THE Category_Selector SHALL log an error and return a Selection_Output with confidence=0.0
5. THE Category_Selector SHALL support alternative web-browsing LLM providers (e.g., Perplexity, Claude with web search) via configuration

### Requirement 3: Polymarket Website Analysis

**User Story:** As a category evaluator, I want the LLM to browse polymarket.com and identify trending categories, so that I know which markets are currently active and popular.

#### Acceptance Criteria

1. WHEN analyzing Polymarket, THE Web_Browsing_LLM SHALL browse polymarket.com to identify featured and trending markets
2. THE Web_Browsing_LLM SHALL identify which categories have the most visible/promoted markets on the Polymarket homepage and category pages
3. THE Web_Browsing_LLM SHALL note the approximate number of active markets per category observed on the site
4. THE Web_Browsing_LLM SHALL identify any time-sensitive markets (elections, events, deadlines) that are prominently displayed
5. THE Web_Browsing_LLM SHALL extract category names as displayed on Polymarket (e.g., "Politics", "Crypto", "Sports", "Pop Culture")

### Requirement 4: Kalshi Website Analysis

**User Story:** As a category evaluator, I want the LLM to browse kalshi.com and identify trending categories, so that I know which markets are currently active and popular on Kalshi.

#### Acceptance Criteria

1. WHEN analyzing Kalshi, THE Web_Browsing_LLM SHALL browse kalshi.com (or elections.kalshi.com) to identify featured and trending markets
2. THE Web_Browsing_LLM SHALL identify which categories/event types have the most visible/promoted markets on the Kalshi homepage
3. THE Web_Browsing_LLM SHALL note the approximate number of active markets per category observed on the site
4. THE Web_Browsing_LLM SHALL identify any time-sensitive markets (elections, economic events, deadlines) that are prominently displayed
5. THE Web_Browsing_LLM SHALL extract category names as displayed on Kalshi (e.g., "Politics", "Economics", "Climate", "Financials")

### Requirement 5: Cross-Platform Overlap Detection

**User Story:** As a category evaluator, I want the LLM to identify categories where both platforms have similar active markets, so that I can prioritize categories with high arbitrage potential.

#### Acceptance Criteria

1. WHEN both websites have been analyzed, THE Web_Browsing_LLM SHALL identify categories that appear trending on BOTH Polymarket and Kalshi
2. THE Web_Browsing_LLM SHALL identify specific market topics that exist on both platforms (e.g., "2024 Presidential Election" on both)
3. THE Web_Browsing_LLM SHALL rank overlapping categories by the degree of market similarity observed
4. THE Web_Browsing_LLM SHALL note categories that are trending on one platform but absent on the other
5. IF no overlapping trending categories are found, THEN THE Web_Browsing_LLM SHALL recommend the category with the highest potential for future overlap

### Requirement 6: Trending Score Assessment

**User Story:** As a category evaluator, I want the LLM to assess how "hot" each overlapping category is, so that I can prioritize categories with the most trading activity.

#### Acceptance Criteria

1. THE Web_Browsing_LLM SHALL assign a trending score (high/medium/low) to each overlapping category based on observed website prominence
2. THE Web_Browsing_LLM SHALL consider factors such as: homepage placement, "featured" labels, volume indicators if visible, and recency of market creation
3. THE Web_Browsing_LLM SHALL prioritize categories with upcoming resolution dates (within 7 days) as these typically have higher activity
4. THE Web_Browsing_LLM SHALL note any categories with breaking news or current events driving interest
5. THE Web_Browsing_LLM SHALL deprioritize categories that appear stale or have markets with distant resolution dates

### Requirement 7: LLM Category Recommendation

**User Story:** As a category selector, I want the LLM to synthesize its website analysis into a clear category recommendation, so that the arbitrage bot knows which category to focus on.

#### Acceptance Criteria

1. WHEN website analysis is complete, THE Web_Browsing_LLM SHALL generate a structured recommendation including best_category, confidence, and reasoning array
2. THE Web_Browsing_LLM SHALL explain why the selected category has the best arbitrage potential based on observed overlap and trending status
3. THE Web_Browsing_LLM SHALL identify alternative categories with explanations (why_second_best, why_third_best)
4. THE Web_Browsing_LLM SHALL provide specific examples of matching markets observed on both platforms
5. THE Web_Browsing_LLM SHALL include arbitrage_logic explaining why price discrepancies might exist in the selected category

### Requirement 8: Structured Prompt for Web Browsing LLM

**User Story:** As a system developer, I want a well-defined prompt template for the web browsing LLM, so that the analysis is consistent and produces structured output.

#### Acceptance Criteria

1. THE Category_Selector SHALL use a configurable prompt template stored in `data/category_selector_prompt.txt`
2. THE prompt SHALL instruct the LLM to browse both polymarket.com and kalshi.com
3. THE prompt SHALL request the LLM to identify trending categories on each platform
4. THE prompt SHALL request the LLM to find overlapping categories with similar markets
5. THE prompt SHALL specify the exact JSON output format required for Selection_Output

### Requirement 9: Selection Output Format

**User Story:** As a downstream consumer, I want the category selection in a standardized JSON format, so that other system components can use it consistently.

#### Acceptance Criteria

1. THE Selection_Output SHALL include the following fields: date, best_category, confidence, reasoning, alternative_categories, arbitrage_logic, observed_markets
2. THE Selection_Output SHALL format date as ISO 8601 (YYYY-MM-DD)
3. THE Selection_Output SHALL format confidence as a float in [0.0-1.0] range
4. THE Selection_Output SHALL format reasoning as an array of 3-5 short explanation strings based on website observations
5. THE Selection_Output SHALL include alternative_categories as an object with second_best and third_best, each containing category name and explanation
6. THE Selection_Output SHALL include arbitrage_logic as an object with why_this_category_creates_arbitrage and typical_example fields
7. THE Selection_Output SHALL include observed_markets as an object with polymarket_examples and kalshi_examples arrays listing specific market titles seen

### Requirement 10: Configuration Integration

**User Story:** As a bot operator, I want to configure the category selector behavior, so that I can tune it for my specific trading strategy.

#### Acceptance Criteria

1. THE Category_Selector SHALL read configuration from the main config.yml under a `category_selector` section
2. THE Category_Selector SHALL support configurable LLM provider settings (provider, model, api_key_env, timeout)
3. THE Category_Selector SHALL support configurable target URLs for each platform (default: polymarket.com, kalshi.com)
4. THE Category_Selector SHALL support a configurable exclusion list for categories to never recommend
5. WHEN configuration is missing, THE Category_Selector SHALL use sensible defaults as specified in other requirements

### Requirement 11: Exclusion of Unsupported Categories

**User Story:** As a risk manager, I want to automatically exclude categories that cannot be traded cross-venue, so that the selector only recommends actionable categories.

#### Acceptance Criteria

1. THE Category_Selector SHALL instruct the Web_Browsing_LLM to exclude Sports category (Kalshi sports markets not present on Polymarket)
2. THE Category_Selector SHALL instruct the Web_Browsing_LLM to exclude categories only present on one platform
3. THE Category_Selector SHALL support a configurable exclusion list in configuration
4. WHEN a category is excluded, THE Selection_Output reasoning SHALL explain the exclusion
5. IF no valid overlapping categories are found, THEN THE Category_Selector SHALL return a Selection_Output with confidence=0.0 and reasoning explaining why

### Requirement 12: Caching and Rate Limiting

**User Story:** As a system operator, I want to avoid excessive LLM calls and respect rate limits, so that the system operates efficiently and cost-effectively.

#### Acceptance Criteria

1. THE Category_Selector SHALL cache the Selection_Output for the current date to avoid redundant LLM calls
2. WHEN a cached selection exists for today, THE Category_Selector SHALL return the cached result unless force_refresh is specified
3. THE Category_Selector SHALL log the LLM request and response for debugging and audit purposes
4. THE Category_Selector SHALL implement exponential backoff retry (max 3 attempts) if the LLM request fails
5. THE Category_Selector SHALL track LLM usage statistics (calls per day, tokens used) in `data/category_selector_usage.json`

### Requirement 13: Error Handling and Fallback

**User Story:** As a bot operator, I want the system to handle LLM failures gracefully, so that the arbitrage bot can continue operating even when category selection fails.

#### Acceptance Criteria

1. IF the Web_Browsing_LLM fails after all retries, THEN THE Category_Selector SHALL return a fallback Selection_Output with the previous day's category
2. IF no previous selection exists, THEN THE Category_Selector SHALL return a default category from configuration (default: "Politics")
3. WHEN a fallback is used, THE Selection_Output SHALL include is_fallback=true and fallback_reason fields
4. THE Category_Selector SHALL emit a warning log when using fallback selection
5. THE Category_Selector SHALL send a Telegram notification when fallback is triggered (if Telegram is configured)

### Requirement 14: Prompt Template and Response Schema Specification

**User Story:** As a system developer, I want a precise prompt template and response schema, so that the LLM produces output that directly supports the Cross_Venue_Matcher with validated market titles.

#### Acceptance Criteria

1. THE Category_Selector SHALL use the following prompt template structure:

```
You are a prediction market analyst. Browse polymarket.com and kalshi.com to identify HOT TOPICS that exist on BOTH platforms.

INSTRUCTIONS:
1. Browse polymarket.com and note the trending/featured markets
2. Browse kalshi.com (or elections.kalshi.com) and note the trending/featured markets
3. Identify SPECIFIC TOPIC KEYWORDS that appear on BOTH platforms
4. For each topic, record the EXACT market title you observed on each platform

IMPORTANT - Return SPECIFIC TOPIC KEYWORDS, not broad categories:
✅ GOOD examples: "Election 2024", "Trump vs Biden", "Oscars 2026", "Bitcoin $100k", "Fed Rate March", "Super Bowl MVP", "iPhone 16 Sales"
❌ BAD examples: "Politics", "Crypto", "Entertainment", "Sports", "Economics"

EXCLUSIONS:
- Do NOT include Sports topics (Kalshi sports markets not tradeable cross-venue)
- Do NOT include topics that only exist on one platform

PRIORITIZE topics with:
- Upcoming resolution dates (within 30 days)
- High visibility/featured placement on both sites
- Clear, binary outcomes
- Current news relevance

Return your analysis as JSON matching the schema below.
```

2. THE Category_Selector SHALL require the Web_Browsing_LLM response to conform to this JSON schema:

```json
{
  "date": "YYYY-MM-DD",
  "hot_topics": [
    {
      "keyword": "string - specific topic keyword",
      "confidence": 0.0-1.0,
      "polymarket_title": "exact market title observed on Polymarket",
      "kalshi_title": "exact market title observed on Kalshi"
    }
  ],
  "reasoning": ["string", "string", "string"],
  "polymarket_observed": ["list of all topic keywords seen on Polymarket"],
  "kalshi_observed": ["list of all topic keywords seen on Kalshi"]
}
```

3. THE Category_Selector SHALL validate that each hot_topic includes non-empty polymarket_title and kalshi_title fields
4. THE Category_Selector SHALL pass the polymarket_title and kalshi_title to the Cross_Venue_Matcher as seed data for market pair validation
5. IF the Web_Browsing_LLM response does not match the schema, THEN THE Category_Selector SHALL log a validation error and retry with a clarifying prompt
6. THE Category_Selector SHALL limit hot_topics array to maximum 10 entries, sorted by confidence descending
7. THE Category_Selector SHALL require reasoning array to contain 3-5 explanation strings


### Requirement 15: Internal LLM for Intelligent Pair Matching

**User Story:** As an arbitrage bot operator, I want an internal LLM to verify that candidate market pairs are truly equivalent, so that I only trade on pairs that will resolve to the same outcome.

#### Acceptance Criteria

1. WHEN hot_topics are received from Stage 1 (Web_Browsing_LLM), THE Internal_LLM SHALL verify each candidate market pair for true equivalence
2. THE Internal_LLM SHALL receive context about arbitrage goals: price differences between platforms represent profit opportunities
3. THE Internal_LLM SHALL understand that markets must be semantically equivalent (same underlying event, same resolution criteria)
4. THE Internal_LLM SHALL use hot topic keywords from Stage 1 to prioritize which pairs to verify first
5. THE Internal_LLM SHALL leverage the existing llm_verifier infrastructure for LLM calls
6. THE Internal_LLM SHALL provide a confidence score (0.0-1.0) on whether a pair is a true match
7. THE Internal_LLM SHALL explain WHY two markets are or are not equivalent in human-readable reasoning
8. THE Internal_LLM SHALL assess whether settlement/resolution rules are compatible between the two markets
9. WHEN a pair has confidence below 0.7, THE Internal_LLM SHALL mark it as unverified and exclude from arbitrage consideration
10. THE Internal_LLM SHALL process pairs in order of Stage 1 confidence score (highest first)

### Requirement 16: Internal LLM Prompt for Pair Verification

**User Story:** As a system developer, I want a well-defined prompt template for the internal LLM pair verification, so that the verification is consistent and understands arbitrage context.

#### Acceptance Criteria

1. THE Internal_LLM prompt SHALL explain that we are an arbitrage bot looking for price differences between prediction markets
2. THE Internal_LLM prompt SHALL explain that price differences between platforms = profit opportunity (buy low on one, sell high on other)
3. THE Internal_LLM prompt SHALL instruct the LLM to verify that both markets resolve to the same outcome
4. THE Internal_LLM prompt SHALL instruct the LLM to compare settlement/resolution rules for compatibility
5. THE Internal_LLM prompt SHALL include the hot topic context from Stage 1 to provide domain understanding
6. THE Internal_LLM prompt SHALL use the following template structure:

```
You are a prediction market arbitrage analyst. Your job is to verify whether two markets from different platforms are TRULY EQUIVALENT for arbitrage purposes.

ARBITRAGE CONTEXT:
- We profit when the same event has different prices on Polymarket vs Kalshi
- For arbitrage to work, both markets MUST resolve to the same outcome
- Settlement rules must be compatible (same resolution date, same criteria)

HOT TOPIC CONTEXT FROM STAGE 1:
Topic: {keyword}
Polymarket Title: {polymarket_title}
Kalshi Title: {kalshi_title}

VERIFICATION TASK:
1. Are these markets about the SAME underlying event?
2. Will they resolve based on the SAME criteria?
3. Are the settlement dates compatible?
4. Could there be edge cases where one resolves YES and the other NO?

Return your analysis as JSON matching the schema below.
```

7. THE Internal_LLM prompt SHALL be configurable via `data/pair_verification_prompt.txt`
8. THE Internal_LLM prompt SHALL warn about common false-match patterns (e.g., "by end of year" vs "by end of Q4")

### Requirement 17: Internal LLM Response for Pair Verification

**User Story:** As a downstream consumer, I want the pair verification output in a standardized JSON format, so that the arbitrage system can reliably use the verification results.

#### Acceptance Criteria

1. THE Pair_Verification_Output SHALL include the following fields: is_match, confidence, match_reasoning, settlement_comparison, arbitrage_potential
2. THE is_match field SHALL be a boolean indicating whether the markets are equivalent for arbitrage
3. THE confidence field SHALL be a float in [0.0-1.0] range indicating certainty of the match assessment
4. THE match_reasoning field SHALL be a string explaining why these markets are or are not equivalent
5. THE settlement_comparison field SHALL be an object containing:
   - polymarket_resolution: string describing Polymarket's resolution criteria
   - kalshi_resolution: string describing Kalshi's resolution criteria
   - are_compatible: boolean indicating if resolution rules are compatible
   - compatibility_notes: string explaining any differences or concerns
6. THE arbitrage_potential field SHALL be an object containing:
   - price_difference_likely: boolean indicating if price differences are expected
   - why_prices_might_differ: string explaining potential sources of price discrepancy
   - risk_factors: array of strings listing risks that could cause divergent resolution
7. THE Pair_Verification_Output SHALL conform to this JSON schema:

```json
{
  "is_match": true|false,
  "confidence": 0.0-1.0,
  "match_reasoning": "string explaining equivalence assessment",
  "settlement_comparison": {
    "polymarket_resolution": "string",
    "kalshi_resolution": "string",
    "are_compatible": true|false,
    "compatibility_notes": "string"
  },
  "arbitrage_potential": {
    "price_difference_likely": true|false,
    "why_prices_might_differ": "string",
    "risk_factors": ["string", "string"]
  }
}
```

8. IF the Internal_LLM response does not match the schema, THEN THE Category_Selector SHALL log a validation error and retry with a clarifying prompt
9. THE Category_Selector SHALL cache Pair_Verification_Output results to avoid redundant LLM calls for the same market pair
10. THE Category_Selector SHALL aggregate all Pair_Verification_Output results into the final Selection_Output under a verified_pairs field
