"""
Dual-venue market injection layer for stress testing with BOTH Polymarket and Kalshi.

Provides coordinated injection of fake market data into both exchanges simultaneously
to test cross-venue arbitrage detection end-to-end without hitting real APIs.
"""
import json
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple
from src.predarb.models import Market
from src.predarb.market_client_base import MarketClient


class DualInjectionClient(MarketClient):
    """
    Wraps two separate market providers (one for each exchange) and merges their results.
    
    This allows Engine to receive markets from both Polymarket and Kalshi sources
    simultaneously, with each source being independently controlled via injection specs.
    """
    
    def __init__(
        self,
        venue_a_provider: Optional[MarketClient] = None,
        venue_b_provider: Optional[MarketClient] = None,
        exchange_a: str = "polymarket",
        exchange_b: str = "kalshi",
    ):
        """
        Initialize dual injection client.
        
        Args:
            venue_a_provider: Provider for market A (e.g., Polymarket)
            venue_b_provider: Provider for market B (e.g., Kalshi)
            exchange_a: Exchange tag for venue A markets
            exchange_b: Exchange tag for venue B markets
        """
        self.venue_a = venue_a_provider
        self.venue_b = venue_b_provider
        self.exchange_a = exchange_a
        self.exchange_b = exchange_b
    
    def fetch_markets(self) -> List[Market]:
        """Fetch and merge markets from both venues."""
        markets = []
        
        if self.venue_a:
            markets_a = self.venue_a.fetch_markets()
            # Ensure exchange tags
            for m in markets_a:
                if not m.exchange:
                    m.exchange = self.exchange_a
            markets.extend(markets_a)
        
        if self.venue_b:
            markets_b = self.venue_b.fetch_markets()
            # Ensure exchange tags
            for m in markets_b:
                if not m.exchange:
                    m.exchange = self.exchange_b
            markets.extend(markets_b)
        
        return markets
    
    def get_active_markets(self) -> List[Market]:
        """Alias for fetch_markets()."""
        return self.fetch_markets()
    
    def get_metadata(self) -> Dict[str, Any]:
        """Return metadata about both venues."""
        return {
            "exchange": "dual_injection",
            "venues": [self.exchange_a, self.exchange_b],
            "venue_a_enabled": self.venue_a is not None,
            "venue_b_enabled": self.venue_b is not None,
        }
    
    def get_exchange_name(self) -> str:
        """Return exchange name for logging."""
        venues = []
        if self.venue_a:
            venues.append(self.exchange_a)
        if self.venue_b:
            venues.append(self.exchange_b)
        return f"DualInjection({'+'.join(venues)})"


class InjectionFactory:
    """Factory for creating market providers from injection specifications."""
    
    @staticmethod
    def from_spec(spec: str, seed: Optional[int] = None, exchange: str = "polymarket") -> MarketClient:
        """
        Create a market provider from an injection spec.
        
        Args:
            spec: Injection specification:
                  - "scenario:<name>" - use built-in scenario generator
                  - "file:<path>" - load markets from JSON file
                  - "inline:<json>" - parse inline JSON
                  - "none" - no injection (disabled)
            seed: Random seed for reproducible generation
            exchange: Exchange tag to apply to generated markets
            
        Returns:
            MarketClient instance or None if spec is "none"
        """
        if spec == "none":
            return None
        
        if spec.startswith("scenario:"):
            scenario_name = spec[9:]
            from src.predarb.stress_scenarios import get_scenario
            provider = get_scenario(scenario_name, seed=seed)
            
            # Wrap to tag markets with exchange
            class TaggedScenarioProvider:
                def __init__(self, wrapped_provider, exchange_tag):
                    self.wrapped = wrapped_provider
                    self.exchange_tag = exchange_tag
                
                def fetch_markets(self):
                    markets = self.wrapped.get_active_markets()
                    for m in markets:
                        m.exchange = self.exchange_tag
                    return markets
                
                def get_active_markets(self):
                    return self.fetch_markets()
                
                def get_exchange_name(self):
                    return f"Scenario({scenario_name})"
            
            return TaggedScenarioProvider(provider, exchange)
        
        elif spec.startswith("file:"):
            file_path = spec[5:]
            return FileInjectionProvider(file_path, exchange=exchange)
        
        elif spec.startswith("inline:"):
            json_str = spec[7:]
            return InlineInjectionProvider(json_str, exchange=exchange)
        
        else:
            raise ValueError(
                f"Invalid injection spec: {spec}\n"
                f"Expected: scenario:<name> | file:<path> | inline:<json> | none"
            )


class FileInjectionProvider:
    """Load markets from a JSON fixture file with exchange tagging."""
    
    def __init__(self, file_path: str, exchange: str = "polymarket"):
        self.file_path = Path(file_path)
        self.exchange = exchange
        
        if not self.file_path.exists():
            raise FileNotFoundError(f"Fixture file not found: {file_path}")
    
    def fetch_markets(self) -> List[Market]:
        """Load markets from JSON file."""
        with open(self.file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Handle both array and dict with 'markets' key
        if isinstance(data, dict) and 'markets' in data:
            markets_data = data['markets']
        elif isinstance(data, list):
            markets_data = data
        else:
            raise ValueError(
                f"Invalid fixture format. Expected list or dict with 'markets' key"
            )
        
        markets = [Market(**m) for m in markets_data]
        
        # Tag with exchange
        for m in markets:
            if not m.exchange:
                m.exchange = self.exchange
        
        return markets
    
    def get_active_markets(self) -> List[Market]:
        """Alias for fetch_markets()."""
        return self.fetch_markets()
    
    def get_metadata(self) -> Dict[str, Any]:
        """Return metadata."""
        return {"exchange": self.exchange, "source": "file", "path": str(self.file_path)}
    
    def get_exchange_name(self) -> str:
        """Return exchange name."""
        return f"FileInjection({self.exchange})"


class InlineInjectionProvider:
    """Parse markets from inline JSON string with exchange tagging."""
    
    def __init__(self, json_str: str, exchange: str = "polymarket"):
        self.json_str = json_str
        self.exchange = exchange
    
    def fetch_markets(self) -> List[Market]:
        """Parse markets from JSON string."""
        data = json.loads(self.json_str)
        
        # Handle both array and dict
        if isinstance(data, dict) and 'markets' in data:
            markets_data = data['markets']
        elif isinstance(data, list):
            markets_data = data
        else:
            raise ValueError("Invalid inline JSON format")
        
        markets = [Market(**m) for m in markets_data]
        
        # Tag with exchange
        for m in markets:
            if not m.exchange:
                m.exchange = self.exchange
        
        return markets
    
    def get_active_markets(self) -> List[Market]:
        """Alias for fetch_markets()."""
        return self.fetch_markets()
    
    def get_metadata(self) -> Dict[str, Any]:
        """Return metadata."""
        return {"exchange": self.exchange, "source": "inline"}
    
    def get_exchange_name(self) -> str:
        """Return exchange name."""
        return f"InlineInjection({self.exchange})"
