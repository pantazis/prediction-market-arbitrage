"""Asset name normalization for cross-venue market matching.

This module provides the AssetNormalizer class that maps various asset name
aliases to canonical forms, enabling matching between markets that use
different naming conventions (e.g., "ETH" vs "Ethereum" vs "Ether").
"""

from typing import Dict, List, Optional


class AssetNormalizer:
    """Normalizes asset names to canonical forms for cross-venue matching.
    
    Maps common asset aliases to a single canonical name, enabling matching
    between markets that use different naming conventions.
    
    Example:
        >>> normalizer = AssetNormalizer()
        >>> normalizer.normalize("ETH")
        'ethereum'
        >>> normalizer.normalize("Ethereum")
        'ethereum'
        >>> normalizer.assets_match("ETH", "Ether")
        True
    """
    
    ALIASES: Dict[str, List[str]] = {
        "ethereum": ["eth", "ethereum", "ether"],
        "bitcoin": ["btc", "bitcoin"],
        "sp500": ["s&p 500", "spx", "sp500", "s&p500", "s&p"],
        "gold": ["gold", "xau", "gld"],
        "oil": ["oil", "wti", "crude", "brent"],
    }
    
    def __init__(self, custom_aliases: Optional[Dict[str, List[str]]] = None):
        """Initialize with optional custom alias mappings.
        
        Args:
            custom_aliases: Optional dictionary mapping canonical names to
                lists of aliases. These are merged with the default ALIASES,
                with custom mappings taking precedence.
        """
        # Build reverse lookup: alias -> canonical name
        self._alias_to_canonical: Dict[str, str] = {}
        
        # Add default aliases
        for canonical, aliases in self.ALIASES.items():
            for alias in aliases:
                self._alias_to_canonical[alias.lower()] = canonical
        
        # Add custom aliases (override defaults if conflicts)
        if custom_aliases:
            for canonical, aliases in custom_aliases.items():
                for alias in aliases:
                    self._alias_to_canonical[alias.lower()] = canonical.lower()
    
    def normalize(self, asset: str) -> str:
        """Normalize asset name to canonical form.
        
        Performs case-insensitive lookup in the alias mapping. If the asset
        is not found, returns the lowercase, whitespace-trimmed input.
        
        Args:
            asset: The asset name to normalize (e.g., "ETH", "Ethereum", "BTC")
        
        Returns:
            The canonical asset name (e.g., "ethereum", "bitcoin") or the
            lowercase, trimmed input if not found in aliases.
        """
        normalized_input = asset.strip().lower()
        return self._alias_to_canonical.get(normalized_input, normalized_input)
    
    def assets_match(self, a1: str, a2: str) -> bool:
        """Check if two asset names refer to the same asset.
        
        Compares the normalized forms of both asset names.
        
        Args:
            a1: First asset name
            a2: Second asset name
        
        Returns:
            True if both names normalize to the same canonical form.
        """
        return self.normalize(a1) == self.normalize(a2)
