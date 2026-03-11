"""
Kalshi Ticker Parser for extracting structured data from ticker formats.

Parses tickers like:
- KXETH-26JAN2310-B3730 → asset=ETH, date=2023-01-26 10:00, threshold=3730, direction="below"
- KXBTC-31DEC2412-T95000 → asset=BTC, date=2024-12-31 12:00, threshold=95000, direction="above"

Direction codes:
- B = Below threshold for YES outcome (YES if price is BELOW threshold)
- T = Above threshold for YES outcome (YES if price is ABOVE threshold)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional


@dataclass
class ParsedTicker:
    """Structured representation of a parsed Kalshi ticker."""
    
    asset: str              # e.g., "eth", "btc" (lowercase)
    expiry: datetime        # e.g., 2023-01-26 10:00 UTC
    threshold: float        # e.g., 3730.0
    direction: str          # "above" or "below"
    raw_ticker: str         # original ticker string


class TickerParser:
    """
    Parser for Kalshi ticker formats.
    
    Extracts structured data (asset, expiry, threshold, direction) from
    Kalshi tickers for use in market matching.
    """
    
    # Month abbreviation to number mapping
    MONTHS = {
        "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4,
        "MAY": 5, "JUN": 6, "JUL": 7, "AUG": 8,
        "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
    }
    
    # Known ticker patterns
    # Pattern: KX{ASSET}-{DD}{MON}{YY}{HH}-{DIR}{THRESHOLD}
    # Example: KXETH-26JAN2310-B3730
    CRYPTO_PRICE_PATTERN = re.compile(
        r"^KX(?P<asset>[A-Z]+)-"
        r"(?P<day>\d{2})(?P<month>[A-Z]{3})(?P<year>\d{2})(?P<hour>\d{2})-"
        r"(?P<dir>[BT])(?P<threshold>\d+)$",
        re.IGNORECASE
    )
    
    def parse(self, ticker: str) -> Optional[ParsedTicker]:
        """
        Parse a Kalshi ticker into structured components.
        
        Args:
            ticker: The raw ticker string (e.g., "KXETH-26JAN2310-B3730")
            
        Returns:
            ParsedTicker if the ticker matches a known pattern, None otherwise.
        """
        if not ticker:
            return None
            
        match = self.CRYPTO_PRICE_PATTERN.match(ticker.strip())
        if not match:
            return None
            
        try:
            asset = match.group("asset").lower()
            day = int(match.group("day"))
            month_str = match.group("month").upper()
            year_short = int(match.group("year"))
            hour = int(match.group("hour"))
            dir_code = match.group("dir").upper()
            threshold = float(match.group("threshold"))
            
            # Validate month
            if month_str not in self.MONTHS:
                return None
            month = self.MONTHS[month_str]
            
            # Convert 2-digit year to 4-digit (assume 2000s)
            year = 2000 + year_short
            
            # Validate date components
            if not (1 <= day <= 31):
                return None
            if not (0 <= hour <= 23):
                return None
            
            # Create datetime in UTC
            try:
                expiry = datetime(year, month, day, hour, 0, 0, tzinfo=timezone.utc)
            except ValueError:
                # Invalid date (e.g., Feb 30)
                return None
            
            # Direction: B = Below threshold for YES, T = Above threshold for YES
            direction = "below" if dir_code == "B" else "above"
            
            return ParsedTicker(
                asset=asset,
                expiry=expiry,
                threshold=threshold,
                direction=direction,
                raw_ticker=ticker.strip(),
            )
            
        except (ValueError, AttributeError):
            return None
    
    def format_ticker(self, parsed: ParsedTicker) -> str:
        """
        Format a ParsedTicker back to a ticker string.
        
        This enables round-trip testing: parse(format(parse(ticker))) == parse(ticker)
        
        Args:
            parsed: The ParsedTicker to format
            
        Returns:
            A ticker string in the format "KX{ASSET}-{DD}{MON}{YY}{HH}-{DIR}{THRESHOLD}"
        """
        # Get month abbreviation
        month_abbrevs = {v: k for k, v in self.MONTHS.items()}
        month_str = month_abbrevs[parsed.expiry.month]
        
        # Get 2-digit year
        year_short = parsed.expiry.year % 100
        
        # Direction code: "below" -> B, "above" -> T
        dir_code = "B" if parsed.direction == "below" else "T"
        
        # Format threshold as integer (no decimal)
        threshold_int = int(parsed.threshold)
        
        return (
            f"KX{parsed.asset.upper()}-"
            f"{parsed.expiry.day:02d}{month_str}{year_short:02d}{parsed.expiry.hour:02d}-"
            f"{dir_code}{threshold_int}"
        )
