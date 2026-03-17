# Implementation Plan: Daily Category Selector

## Overview

Two-stage LLM system for discovering hot topics across Polymarket and Kalshi. Stage 1 uses Gemini with web browsing to discover trending topics. Stage 2 uses existing llm_verifier infrastructure to verify market pair equivalence.

## Tasks

- [-] 1. Add configuration models and prompt templates
  - [x] 1.1 Add TopicSelectorConfig, WebBrowsingLLMConfig, and PairVerificationConfig to config.py
    - Add Pydantic models for topic_selector configuration section
    - Include all fields: enabled, execution_time_utc, output_path, llm settings, verification settings
    - _Requirements: 2.1, 2.2, 2.3, 10.1, 10.2, 10.3, 10.4, 10.5_
  
  - [x] 1.2 Create topic_selector_prompt.txt template
    - Create `data/topic_selector_prompt.txt` with Stage 1 prompt
    - Include instructions for browsing both platforms
    - Specify JSON output schema for hot topics
    - Include exclusions (Sports) and prioritization criteria
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 14.1, 14.2_
  
  - [ ] 1.3 Create pair_verification_prompt.txt template
    - Create `data/pair_verification_prompt.txt` with Stage 2 prompt
    - Include arbitrage context explanation
    - Specify JSON output schema for verification
    - Include settlement comparison instructions
    - _Requirements: 16.1, 16.2, 16.3, 16.4, 16.5, 16.6, 16.7, 16.8_

- [ ] 2. Implement data models
  - [ ] 2.1 Create topic_selector.py with data classes
    - Create `src/predarb/topic_selector.py`
    - Implement HotTopic, SelectionOutput, VerifiedPair dataclasses
    - Include JSON serialization/deserialization methods
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7, 14.3_
  
  - [ ]* 2.2 Write property test for SelectionOutput round-trip
    - **Property 1: SelectionOutput Persistence Round-Trip**
    - **Validates: Requirements 1.3**
  
  - [ ]* 2.3 Write property test for SelectionOutput schema validation
    - **Property 3: SelectionOutput Schema Validation**
    - **Validates: Requirements 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7**

- [ ] 3. Checkpoint - Ensure configuration and data models work
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 4. Implement Stage 1: Web Browsing LLM Client
  - [ ] 4.1 Create web_browsing_llm.py with provider abstraction
    - Create `src/predarb/web_browsing_llm.py`
    - Implement WebBrowsingLLMProvider abstract base class
    - Implement GeminiWebBrowsingProvider with Google Search grounding
    - _Requirements: 2.1, 2.3, 2.4, 3.1, 3.2, 3.3, 3.4, 3.5_
  
  - [ ] 4.2 Implement PerplexityProvider as alternative
    - Add PerplexityProvider class for alternative web browsing
    - Support configurable model and timeout
    - _Requirements: 2.5_
  
  - [ ] 4.3 Implement WebBrowsingLLMClient
    - Create WebBrowsingLLMClient class
    - Implement discover_topics() with retry logic
    - Implement response validation and parsing
    - Implement exponential backoff retry (max 3 attempts)
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 12.4_
  
  - [ ]* 4.4 Write property test for retry behavior
    - **Property 8: Retry with Exponential Backoff**
    - **Validates: Requirements 12.4, 17.8**

- [ ] 5. Implement Stage 2: Pair Verifier
  - [ ] 5.1 Create pair_verifier.py
    - Create `src/predarb/pair_verifier.py`
    - Implement PairVerificationOutput dataclass
    - Implement PairVerifier class using existing llm_verifier
    - _Requirements: 15.1, 15.2, 15.3, 15.4, 15.5, 17.1, 17.2, 17.3, 17.4, 17.5, 17.6, 17.7_
  
  - [ ] 5.2 Implement verify_pair() method
    - Build prompt with arbitrage context
    - Call internal LLM via llm_verifier infrastructure
    - Parse and validate response
    - _Requirements: 15.6, 15.7, 15.8_
  
  - [ ] 5.3 Implement verify_all() with ordering and filtering
    - Process pairs in confidence order (highest first)
    - Filter pairs below min_confidence threshold
    - Implement caching for pair verification results
    - _Requirements: 15.9, 15.10, 17.9_
  
  - [ ]* 5.4 Write property test for PairVerificationOutput schema
    - **Property 9: PairVerificationOutput Schema Validation**
    - **Validates: Requirements 15.6, 15.7, 15.8, 17.1-17.7**
  
  - [ ]* 5.5 Write property test for low confidence exclusion
    - **Property 10: Low Confidence Pair Exclusion**
    - **Validates: Requirements 15.9**
  
  - [ ]* 5.6 Write property test for pair processing order
    - **Property 11: Pair Processing Order**
    - **Validates: Requirements 15.10**
  
  - [ ]* 5.7 Write property test for pair verification caching
    - **Property 12: Pair Verification Caching**
    - **Validates: Requirements 17.9**

- [ ] 6. Checkpoint - Ensure Stage 1 and Stage 2 components work
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 7. Implement TopicSelector orchestrator
  - [ ] 7.1 Implement TopicSelector class
    - Add TopicSelector class to topic_selector.py
    - Wire Stage 1 (WebBrowsingLLMClient) and Stage 2 (PairVerifier)
    - Implement select() method with caching logic
    - _Requirements: 1.1, 1.2, 1.4_
  
  - [ ] 7.2 Implement caching and persistence
    - Implement _load_cache(), _save_cache(), _is_cache_valid()
    - Persist SelectionOutput to configurable file path
    - Skip execution if valid cache exists (unless force_refresh)
    - _Requirements: 1.3, 12.1, 12.2_
  
  - [ ] 7.3 Implement fallback behavior
    - Return previous day's selection on LLM failure
    - Return default category if no previous cache
    - Set is_fallback=true and fallback_reason on fallback
    - Send Telegram notification on fallback (if configured)
    - _Requirements: 13.1, 13.2, 13.3, 13.4, 13.5_
  
  - [ ]* 7.4 Write property test for cache idempotency
    - **Property 2: Cache Idempotency**
    - **Validates: Requirements 1.4, 12.1, 12.2**
  
  - [ ]* 7.5 Write property test for hot topics overlap invariant
    - **Property 4: Hot Topics Overlap Invariant**
    - **Validates: Requirements 5.1, 5.2**
  
  - [ ]* 7.6 Write property test for hot topics confidence ordering
    - **Property 5: Hot Topics Confidence Ordering**
    - **Validates: Requirements 5.3**
  
  - [ ]* 7.7 Write property test for category exclusion
    - **Property 6: Category Exclusion Invariant**
    - **Validates: Requirements 11.1, 11.2, 11.3, 11.4**
  
  - [ ]* 7.8 Write property test for fallback behavior
    - **Property 7: Fallback Behavior on Failure**
    - **Validates: Requirements 2.4, 13.1, 13.3**

- [ ] 8. Implement CLI command
  - [ ] 8.1 Add select-category CLI command
    - Add `select-category` command to cli.py
    - Support --config and --force-refresh options
    - Load config and execute TopicSelector.select()
    - Output results to console and persist to file
    - _Requirements: 1.5_
  
  - [ ]* 8.2 Write unit test for CLI command
    - Test CLI command exists and runs with mock providers
    - _Requirements: 1.5_

- [ ] 9. Implement usage tracking and logging
  - [ ] 9.1 Add usage statistics tracking
    - Track LLM calls per day and tokens used
    - Persist to data/category_selector_usage.json
    - Log requests and responses for debugging
    - _Requirements: 12.3, 12.5_
  
  - [ ] 9.2 Add structured error logging
    - Log errors to log/topic_selector.log
    - Include error type, timestamp, request details
    - _Requirements: 13.4_

- [ ] 10. Checkpoint - Ensure full pipeline works
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 11. Integration with CrossVenueMatcher
  - [ ] 11.1 Add get_verified_pairs() integration point
    - Implement get_verified_pairs() method on TopicSelector
    - Return verified pairs for CrossVenueMatcher consumption
    - _Requirements: 14.4_
  
  - [ ]* 11.2 Write integration test for CrossVenueMatcher
    - Test verified pairs integrate correctly with matcher
    - _Requirements: 14.4_

- [ ] 12. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Stage 1 uses Gemini with Google Search grounding for web browsing
- Stage 2 leverages existing llm_verifier infrastructure
- Property tests use hypothesis library for Python
- All configuration goes under `topic_selector` section in config.yml
