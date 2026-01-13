# Market Filtering Module

The `predarb.filtering` module now performs minimal eligibility checks only:
- Requires at least two outcomes.
- Optionally requires a resolution source (configurable).

Legacy filters (spread/volume/liquidity/expiry) and scoring have been removed.
`rank_markets` remains for compatibility and returns deterministic zero scores.
