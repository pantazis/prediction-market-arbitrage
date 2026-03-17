"""
Series-to-Category and Series-to-Asset Mapping for Kalshi Markets.

This module provides dynamic extraction of category and asset information
from Kalshi event_ticker format using regex patterns rather than hardcoded maps.

Event Ticker Format: SERIES-DATE[-STRIKE]
Examples:
- KXBTC-25JAN10 -> series=KXBTC, asset=btc, category=crypto
- KXBTC-25JAN10-B95000 -> series=KXBTC, asset=btc, category=crypto
- KXPRES-24NOV05-DEM -> series=KXPRES, category=politics
- KXFED-25MAR19-CUT -> series=KXFED, category=economics

Design Principles:
- Avoid hardcoded ticker-to-asset maps (future-proof for KXPEPE, KXDOGE, etc.)
- Use regex pattern extraction: series[2:].lower() for crypto assets
- Maintain minimal prefix-to-category map for non-crypto categories
"""

import re
from typing import Optional, Tuple
import logging

logger = logging.getLogger(__name__)


# Category prefixes - minimal map grouping by category type
# Crypto assets are extracted dynamically, not hardcoded here
CATEGORY_PREFIXES = {
    # Politics
    "KXPRES": "politics",
    "KXSENATE": "politics",
    "KXHOUSE": "politics",
    "KXGOV": "politics",
    "KXELEC": "politics",
    
    # Economics
    "KXFED": "economics",
    "KXCPI": "economics",
    "KXGDP": "economics",
    "KXJOBS": "economics",
    "KXRATE": "economics",
    "KXINFL": "economics",
    
    # Weather
    "KXHIGH": "weather",
    "KXLOW": "weather",
    "KXRAIN": "weather",
    "KXTEMP": "weather",
    "KXSNOW": "weather",
    
    # Financial indices (not crypto)
    "INXD": "indices",  # Nasdaq
    "INXU": "indices",  # S&P 500
}

# Known crypto series prefixes (for explicit matching)
# These are used to confirm crypto category, but asset is extracted dynamically
CRYPTO_PREFIXES = {
    "KXBTC", "KXETH", "KXSOL", "KXDOGE", "KXXRP", "KXADA", "KXAVAX",
    "KXLINK", "KXDOT", "KXMATIC", "KXSHIB", "KXLTC", "KXBCH", "KXUNI",
    "KXAAVE", "KXATOM", "KXPEPE", "KXWIF", "KXBONK",  # Meme coins
}

# Asset name normalization (short ticker -> full name)
ASSET_ALIASES = {
    "btc": "bitcoin",
    "eth": "ethereum",
    "sol": "solana",
    "doge": "dogecoin",
    "xrp": "xrp",
    "ada": "cardano",
    "avax": "avalanche",
    "link": "chainlink",
    "dot": "polkadot",
    "matic": "polygon",
    "shib": "shiba",
    "ltc": "litecoin",
    "bch": "bitcoincash",
    "uni": "uniswap",
    "aave": "aave",
    "atom": "cosmos",
    "pepe": "pepe",
    "wif": "dogwifhat",
    "bonk": "bonk",
}


def extract_series_from_ticker(event_ticker: str) -> Optional[str]:
    """
    Extract series prefix from event_ticker using greedy match.
    
    Handles the Kalshi hierarchy: Series -> Event -> Market
    Event ticker can contain strike prices: KXBTC-25JAN10-B95000
    
    Args:
        event_ticker: Kalshi event ticker (e.g., "KXBTC-25JAN10")
    
    Returns:
        Series prefix (e.g., "KXBTC") or None if invalid
    """
    if not event_ticker:
        return None
    
    # Split by dash and take first segment (always the series)
    parts = event_ticker.split('-')
    if not parts:
        return None
    
    series = parts[0].upper()
    
    # Validate it looks like a series (starts with letter, alphanumeric)
    if not series or not series[0].isalpha():
        return None
    
    return series


def infer_category_from_series(series: str) -> Optional[str]:
    """
    Infer category from series prefix.
    
    Uses pattern matching:
    1. Check explicit CATEGORY_PREFIXES map
    2. Check if it's a known crypto prefix
    3. Check if it matches KX + 2-5 letter pattern (likely crypto)
    
    Args:
        series: Series prefix (e.g., "KXBTC")
    
    Returns:
        Category string (e.g., "crypto", "politics") or None
    """
    if not series:
        return None
    
    series = series.upper()
    
    # Check explicit category map first
    if series in CATEGORY_PREFIXES:
        return CATEGORY_PREFIXES[series]
    
    # Check known crypto prefixes
    if series in CRYPTO_PREFIXES:
        return "crypto"
    
    # Pattern match: KX + 2-5 uppercase letters = likely crypto asset
    # This catches new coins like KXPEPE, KXDOGE without hardcoding
    if re.match(r'^KX[A-Z]{2,5}$', series):
        return "crypto"
    
    return None


def extract_asset_from_series(series: str) -> Optional[str]:
    """
    Extract normalized asset name from series prefix.
    
    Uses dynamic extraction: series[2:].lower() for KX-prefixed series.
    Then normalizes via ASSET_ALIASES if available.
    
    Args:
        series: Series prefix (e.g., "KXBTC")
    
    Returns:
        Normalized asset name (e.g., "bitcoin") or None
    """
    if not series:
        return None
    
    series = series.upper()
    
    # Only extract asset from KX-prefixed series (crypto)
    if not series.startswith("KX"):
        return None
    
    # Dynamic extraction: KXBTC -> btc
    raw_asset = series[2:].lower()
    
    if not raw_asset:
        return None
    
    # Normalize via aliases (btc -> bitcoin)
    return ASSET_ALIASES.get(raw_asset, raw_asset)


def parse_kalshi_ticker(event_ticker: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Parse Kalshi event_ticker into (series, category, asset).
    
    This is the main entry point for ticker parsing.
    
    Args:
        event_ticker: Kalshi event ticker (e.g., "KXBTC-25JAN10")
    
    Returns:
        Tuple of (series, category, asset) - any can be None
    
    Examples:
        "KXBTC-25JAN10" -> ("KXBTC", "crypto", "bitcoin")
        "KXPRES-24NOV05" -> ("KXPRES", "politics", None)
        "KXFED-25MAR19" -> ("KXFED", "economics", None)
        "INXD-25JAN10" -> ("INXD", "indices", None)
    """
    series = extract_series_from_ticker(event_ticker)
    if not series:
        return (None, None, None)
    
    category = infer_category_from_series(series)
    asset = extract_asset_from_series(series)
    
    return (series, category, asset)


def get_category_tag(event_ticker: str) -> Optional[str]:
    """
    Get category tag for a Kalshi market.
    
    Convenience function for use in _normalize_market().
    
    Args:
        event_ticker: Kalshi event ticker
    
    Returns:
        Category string or None
    """
    _, category, _ = parse_kalshi_ticker(event_ticker)
    return category


def get_asset_tag(event_ticker: str) -> Optional[str]:
    """
    Get asset tag for a Kalshi market.
    
    Convenience function for use in _get_market_group().
    
    Args:
        event_ticker: Kalshi event ticker
    
    Returns:
        Normalized asset name or None
    """
    _, _, asset = parse_kalshi_ticker(event_ticker)
    return asset
