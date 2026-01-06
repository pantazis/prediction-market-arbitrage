"""Fake (mock) Polymarket client for testing and simulation.

Provides deterministic, in-memory market data without HTTP calls.
"""

import logging
from typing import List, Dict, Optional

from predarb.models import Market
from predarb.testing.synthetic_data import generate_synthetic_markets, evolve_markets_minute_by_minute

logger = logging.getLogger(__name__)


class FakePolymarketClient:
    """In-memory Polymarket client that generates synthetic market data.
    
    Produces deterministic 2-day market evolution with various opportunity types:
      - Parity violations
      - Ladder markets
      - Duplicate/clone markets
      - Multi-outcome violations
      - Time-lag divergence
    
    All data is generated in-memory on construction; no HTTP calls are made.
    """

    def __init__(
        self,
        num_markets: int = 30,
        days: int = 2,
        seed: int = 42,
    ):
        """Initialize FakePolymarketClient.
        
        Args:
            num_markets: Number of unique markets to generate (default 30)
            days: Number of days to simulate (default 2)
            seed: Random seed for deterministic generation
        """
        self.num_markets = num_markets
        self.days = days
        self.seed = seed
        
        # Generate synthetic markets once
        self.initial_markets = generate_synthetic_markets(num_markets, days, seed)
        
        # Pre-compute minute-by-minute evolution
        self.market_evolution = evolve_markets_minute_by_minute(
            self.initial_markets,
            days,
            seed,
        )
        
        # Current minute (0..2880)
        self.current_minute = 0
        
        logger.info(
            f"FakePolymarketClient initialized: {len(self.initial_markets)} markets, "
            f"{days} days simulation, seed={seed}"
        )

    def fetch_markets(self) -> List[Market]:
        """Fetch active markets at current minute.
        
        Returns list of markets as they exist at the current simulation minute.
        Subsequent calls will advance the minute counter (simulating polling).
        
        Returns:
            List of Market objects at current minute
        """
        markets = self.market_evolution.get(self.current_minute, self.initial_markets)
        
        # Advance minute for next call
        self.current_minute = min(self.current_minute + 1, len(self.market_evolution) - 1)
        
        logger.debug(f"Fetched {len(markets)} markets at minute {self.current_minute - 1}")
        return markets

    def get_active_markets(self) -> List[Market]:
        """Alias for fetch_markets() to match PolymarketClient interface.
        
        Returns:
            List of Market objects at current minute
        """
        return self.fetch_markets()

    def reset(self, minute: int = 0) -> None:
        """Reset simulation to a specific minute.
        
        Args:
            minute: Minute to reset to (default 0 = start)
        """
        self.current_minute = max(0, min(minute, len(self.market_evolution) - 1))
        logger.info(f"FakePolymarketClient reset to minute {self.current_minute}")

    def advance_minute(self, minutes: int = 1) -> None:
        """Advance simulation by N minutes.
        
        Args:
            minutes: Number of minutes to advance (default 1)
        """
        self.current_minute = min(self.current_minute + minutes, len(self.market_evolution) - 1)
        logger.debug(f"Advanced to minute {self.current_minute}")


__all__ = ["FakePolymarketClient"]
