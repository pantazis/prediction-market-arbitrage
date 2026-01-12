# Arbitrage Bot Enhancement Roadmap

## Current Status
- ✅ Semantic matching with batching (50 markets/batch)
- ✅ Sports filtering for Kalshi
- ✅ Category-based fetching (Politics/Economics/Crypto)
- ✅ Rich description extraction (rules_primary from Kalshi)
- ✅ Cross-venue price comparison
- ✅ Configurable similarity threshold (currently 0.60)

## Planned Enhancements

### 1. ✅ Expand Ladder Comparisons
**Status:** Planned  
**Description:** Enhance ladder arbitrage detection to check multiple price levels simultaneously
- [ ] Compare full order book depth (not just best bid/ask)
- [ ] Detect multi-level ladder opportunities (3+ outcomes)
- [ ] Calculate optimal execution across ladder rungs
- [ ] Add ladder-specific risk metrics

**Implementation:**
- Extend `LadderDetector` in `src/predarb/detectors/ladder.py`
- Add order book depth fetching from both APIs
- Implement multi-level profit calculation

### 2. ✅ Compare Many Thresholds, Not One
**Status:** Planned  
**Description:** Test multiple similarity thresholds simultaneously to find optimal matching
- [ ] Add multi-threshold testing mode: [0.50, 0.55, 0.60, 0.65, 0.70]
- [ ] Generate match quality reports per threshold
- [ ] Auto-tune threshold based on false positive rate
- [ ] Show confidence scores for each match

**Implementation:**
- Add `threshold_ranges` config parameter
- Modify `CrossVenueMatcher.find_pairs()` to return results for all thresholds
- Create threshold analysis report

### 3. ✅ Check Time-Window Inclusion
**Status:** Planned  
**Description:** Verify markets resolve within same time window (not just expiry proximity)
- [ ] Parse resolution time windows from descriptions
- [ ] Extract date ranges (e.g., "by March 2026" vs "in March 2026")
- [ ] Flag markets with mismatched resolution windows
- [ ] Add temporal logic to semantic matching

**Implementation:**
- Add date/time extraction to `_get_text_blob()`
- Parse temporal phrases: "by", "before", "after", "between"
- Add `resolution_window` field to Market model
- Filter matches with incompatible windows

### 4. ✅ Compare Resolution Sources
**Status:** Planned  
**Description:** Ensure markets resolve from same authoritative source
- [ ] Extract resolution sources from descriptions
- [ ] Standardize source names (e.g., "Federal Reserve" = "FED" = "Fed")
- [ ] Flag markets with different sources
- [ ] Add resolution source similarity scoring

**Implementation:**
- Parse resolution sources from Kalshi `rules_primary` and Polymarket descriptions
- Build source equivalence dictionary
- Add `resolution_source_match` boolean to match results
- Weight similarity scores by source alignment

### 5. ✅ Exploit Venue Mechanics (Shorting vs Buy-Only)
**Status:** Planned  
**Description:** Account for exchange-specific trading mechanics
- [ ] Map Kalshi vs Polymarket trading capabilities
- [ ] Identify short-selling restrictions
- [ ] Calculate directional arbitrage opportunities
- [ ] Factor in transaction costs per venue

**Venue Mechanics:**
- **Kalshi:** Full market (YES/NO both tradeable), maker/taker fees
- **Polymarket:** CLOB with limit orders, different fee structure
- **Key difference:** Shorting mechanics, liquidity depth, order types

**Implementation:**
- Add `VenueMechanics` class with exchange-specific rules
- Adjust profit calculations for unidirectional trades
- Add fee structure to config (maker/taker splits)
- Calculate net profit after fees

### 6. ✅ Run Continuously with Unit Tests
**Status:** Planned  
**Description:** Add continuous operation mode with comprehensive testing
- [ ] Implement daemon mode (24/7 operation)
- [ ] Add health checks and monitoring
- [ ] Create unit tests for all components
- [ ] Add integration tests for end-to-end flows
- [ ] Implement error recovery and retry logic

**Testing Coverage:**
- [ ] Unit tests for semantic matching
- [ ] Mock API responses for deterministic testing
- [ ] Test batch processing edge cases
- [ ] Validate price calculations
- [ ] Test sports filtering logic
- [ ] Test category-based fetching

**Continuous Operation:**
- [ ] Add `--daemon` mode to CLI
- [ ] Implement market data refresh intervals (configurable)
- [ ] Add logging rotation
- [ ] Create monitoring dashboard/alerts
- [ ] Add performance metrics (match rate, latency, accuracy)

**Implementation:**
```python
# Example daemon mode
python3 -c 'from predarb.cli import main; main()' continuous --config config_live_paper.yml --interval 300
```

## Priority Order
1. **High:** Time-window inclusion (critical for accurate matching)
2. **High:** Resolution source comparison (reduces false positives)
3. **Medium:** Multi-threshold testing (improves match quality)
4. **Medium:** Venue mechanics (improves profit calculations)
5. **Medium:** Unit tests (improves reliability)
6. **Low:** Ladder comparisons (advanced feature)
7. **Low:** Continuous operation (requires stable base features)

## Quick Wins
- Add resolution source extraction (2-3 hours)
- Implement multi-threshold testing (1-2 hours)
- Parse temporal windows from descriptions (3-4 hours)

## Dependencies
```bash
# Additional packages needed
pip install dateparser  # For temporal phrase parsing
pip install pytest pytest-cov  # For testing
pip install python-daemon  # For daemon mode
```

## Success Metrics
- **Match accuracy:** >95% true positives at 0.60 threshold
- **False positive rate:** <5%
- **Latency:** <60 seconds for 500x500 market comparison
- **Test coverage:** >80% code coverage
- **Uptime:** >99% in continuous mode
