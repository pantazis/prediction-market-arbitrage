"""
Market data injection layer for DRY-RUN stress testing.

Provides a clean interface for Engine to receive markets from:
- Real Polymarket client (production)
- Scenario generators (stress tests)
- Fixture files (deterministic tests)
- Inline JSON (quick tests)

All injection sources are network-free and deterministic (when seeded).
"""
import json
from pathlib import Path
from typing import List, Protocol, Optional
from src.predarb.models import Market


class MarketProvider(Protocol):
    """Protocol for market data providers (real or injected)."""
    
    def get_active_markets(self) -> List[Market]:
        """Fetch active markets (real API or injected data)."""
        ...


class InjectionSource:
    """Factory for creating market providers from injection specifications."""
    
    @staticmethod
    def from_spec(spec: str, seed: Optional[int] = None) -> MarketProvider:
        """
        Create a market provider from an injection spec.
        
        Args:
            spec: Injection specification in format:
                  - "scenario:<name>" - use built-in scenario generator
                  - "file:<path>" - load markets from JSON file
                  - "inline:<json>" - parse inline JSON array
            seed: Random seed for reproducible scenario generation
            
        Returns:
            MarketProvider instance
            
        Raises:
            ValueError: If spec format is invalid or file not found
        """
        if spec.startswith("scenario:"):
            scenario_name = spec[9:]
            from src.predarb.stress_scenarios import get_scenario
            return get_scenario(scenario_name, seed=seed)
        
        elif spec.startswith("file:"):
            file_path = spec[5:]
            return FileMarketProvider(file_path)
        
        elif spec.startswith("inline:"):
            json_str = spec[7:]
            return InlineMarketProvider(json_str)
        
        else:
            raise ValueError(
                f"Invalid injection spec: {spec}\n"
                f"Expected format: scenario:<name> | file:<path> | inline:<json>"
            )


class FileMarketProvider:
    """Load markets from a JSON fixture file."""
    
    def __init__(self, file_path: str):
        self.file_path = Path(file_path)
        if not self.file_path.exists():
            raise FileNotFoundError(f"Market fixture file not found: {file_path}")
    
    def get_active_markets(self) -> List[Market]:
        """Load markets from JSON file."""
        with open(self.file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Handle both array of markets and dict with 'markets' key
        if isinstance(data, dict) and 'markets' in data:
            markets_data = data['markets']
        elif isinstance(data, list):
            markets_data = data
        else:
            raise ValueError(
                f"Invalid fixture format. Expected list of markets or "
                f"dict with 'markets' key, got: {type(data)}"
            )
        
        return [Market(**m) for m in markets_data]


class InlineMarketProvider:
    """Parse markets from inline JSON string."""
    
    def __init__(self, json_str: str):
        self.json_str = json_str
    
    def get_active_markets(self) -> List[Market]:
        """Parse markets from JSON string."""
        data = json.loads(self.json_str)
        
        if isinstance(data, dict) and 'markets' in data:
            markets_data = data['markets']
        elif isinstance(data, list):
            markets_data = data
        else:
            raise ValueError(
                f"Invalid inline JSON format. Expected list of markets or "
                f"dict with 'markets' key"
            )
        
        return [Market(**m) for m in markets_data]
