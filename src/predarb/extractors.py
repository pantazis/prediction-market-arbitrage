from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Tuple

from dateutil import parser as dateparser

from predarb.normalize import normalize_text

THRESHOLD_PATTERN = re.compile(
    r"(?P<comp>>=|<=|>|<|over|under|above|at\s+least|below)\s*\$?(?P<num>[0-9,.]+(?:k|m)?)",
    re.IGNORECASE,
)


@dataclass
class ExtractedThreshold:
    """Structured threshold data extracted from market question text."""
    value: float            # numeric value (e.g., 3730.0)
    direction: Optional[str]  # "above", "below", "at_least", "at_most", or None
    unit: Optional[str]     # "usd", "percent", or None
    raw_match: str          # original matched text


class ThresholdExtractor:
    """Enhanced extraction of price/value thresholds from market questions."""
    
    # Patterns for various threshold phrasings
    # Order matters - more specific patterns first
    PATTERNS = [
        # Direction before number: "above $3730", "at least $3730", "below $3730"
        (
            re.compile(
                r"(?P<dir>above|over|at\s+least|higher\s+than)\s*\$(?P<num>[0-9,.]+(?:k|m)?)",
                re.IGNORECASE
            ),
            "above_usd"
        ),
        (
            re.compile(
                r"(?P<dir>below|under|at\s+most|lower\s+than)\s*\$(?P<num>[0-9,.]+(?:k|m)?)",
                re.IGNORECASE
            ),
            "below_usd"
        ),
        # Number then direction: "$3,730 or higher", "$3730 or above"
        (
            re.compile(
                r"\$(?P<num>[0-9,.]+(?:k|m)?)\s+(?P<dir>or\s+higher|or\s+more|or\s+above)",
                re.IGNORECASE
            ),
            "above_usd_suffix"
        ),
        (
            re.compile(
                r"\$(?P<num>[0-9,.]+(?:k|m)?)\s+(?P<dir>or\s+lower|or\s+less|or\s+below)",
                re.IGNORECASE
            ),
            "below_usd_suffix"
        ),
        # Percentage thresholds: "above 5%", "at least 3.5%"
        (
            re.compile(
                r"(?P<dir>above|over|at\s+least|higher\s+than)\s+(?P<num>[0-9,.]+)\s*(?P<unit>%|percent)",
                re.IGNORECASE
            ),
            "above_percent"
        ),
        (
            re.compile(
                r"(?P<dir>below|under|at\s+most|lower\s+than)\s+(?P<num>[0-9,.]+)\s*(?P<unit>%|percent)",
                re.IGNORECASE
            ),
            "below_percent"
        ),
        # Standalone percentage: "5%", "3.5 percent"
        (
            re.compile(
                r"(?P<num>[0-9,.]+)\s*(?P<unit>%|percent)",
                re.IGNORECASE
            ),
            "percent_only"
        ),
        # Standalone dollar amount: "$3,730", "$3730"
        (
            re.compile(
                r"\$(?P<num>[0-9,.]+(?:k|m)?)",
                re.IGNORECASE
            ),
            "usd_only"
        ),
        # Standalone number with k/m suffix: "3.73k", "1.5m"
        (
            re.compile(
                r"(?P<num>[0-9,.]+[kKmM])\b",
                re.IGNORECASE
            ),
            "number_suffix"
        ),
    ]
    
    # Direction mapping for normalization
    DIRECTION_MAP = {
        "above": "above",
        "over": "above",
        "higher than": "above",
        "or higher": "above",
        "or more": "above",
        "or above": "above",
        "at least": "at_least",
        "below": "below",
        "under": "below",
        "lower than": "below",
        "or lower": "below",
        "or less": "below",
        "or below": "below",
        "at most": "at_most",
    }
    
    def extract(self, text: str) -> Optional[ExtractedThreshold]:
        """Extract threshold from market question text.
        
        Args:
            text: Market question or description text
            
        Returns:
            ExtractedThreshold if a threshold pattern is found, None otherwise
        """
        for pattern, pattern_type in self.PATTERNS:
            match = pattern.search(text)
            if match:
                return self._parse_match(match, pattern_type)
        return None
    
    def _parse_match(self, match: re.Match, pattern_type: str) -> ExtractedThreshold:
        """Parse a regex match into an ExtractedThreshold."""
        num_str = match.group("num")
        value = parse_number(num_str)
        
        # Determine direction
        direction = None
        if "dir" in match.groupdict() and match.group("dir"):
            dir_raw = match.group("dir").lower().strip()
            # Normalize multi-word directions
            dir_raw = re.sub(r"\s+", " ", dir_raw)
            direction = self.DIRECTION_MAP.get(dir_raw)
        
        # Determine unit
        unit = None
        if "percent" in pattern_type:
            unit = "percent"
        elif "usd" in pattern_type:
            unit = "usd"
        
        return ExtractedThreshold(
            value=value,
            direction=direction,
            unit=unit,
            raw_match=match.group(0)
        )
    
    def thresholds_match(
        self, 
        t1: ExtractedThreshold, 
        t2: ExtractedThreshold, 
        tolerance: float = 0.001
    ) -> bool:
        """Check if two thresholds match within tolerance.
        
        Args:
            t1: First threshold
            t2: Second threshold
            tolerance: Relative tolerance (default 0.001 = 0.1%)
            
        Returns:
            True if thresholds match within tolerance, False otherwise
        """
        # Check direction match (if both have directions)
        if t1.direction is not None and t2.direction is not None:
            # Normalize "at_least" to "above" and "at_most" to "below" for comparison
            dir1 = "above" if t1.direction in ("above", "at_least") else "below" if t1.direction in ("below", "at_most") else t1.direction
            dir2 = "above" if t2.direction in ("above", "at_least") else "below" if t2.direction in ("below", "at_most") else t2.direction
            if dir1 != dir2:
                return False
        
        # Check unit match (if both have units)
        if t1.unit is not None and t2.unit is not None:
            if t1.unit != t2.unit:
                return False
        
        # Check value within tolerance
        if t1.value == 0 and t2.value == 0:
            return True
        if t1.value == 0 or t2.value == 0:
            return False
        
        # Calculate relative difference
        relative_diff = abs(t1.value - t2.value) / max(abs(t1.value), abs(t2.value))
        return relative_diff <= tolerance


# Module-level instance for convenience
_threshold_extractor = ThresholdExtractor()


def extract_threshold_enhanced(text: str) -> Optional[ExtractedThreshold]:
    """Extract threshold from market question text using enhanced patterns.
    
    This is a convenience function that uses the module-level ThresholdExtractor.
    
    Args:
        text: Market question or description text
        
    Returns:
        ExtractedThreshold if a threshold pattern is found, None otherwise
    """
    return _threshold_extractor.extract(text)


def parse_number(num_str: str) -> Optional[float]:
    num_str = num_str.lower().replace(",", "")
    multiplier = 1.0
    if num_str.endswith("k"):
        multiplier = 1_000
        num_str = num_str[:-1]
    elif num_str.endswith("m"):
        multiplier = 1_000_000
        num_str = num_str[:-1]
    try:
        return float(num_str) * multiplier
    except ValueError:
        return None


def extract_threshold(text: str) -> Tuple[Optional[str], Optional[float]]:
    match = THRESHOLD_PATTERN.search(text)
    if not match:
        return None, None
    comp_raw = match.group("comp").lower()
    comp_map = {">": ">", ">=": ">=", "over": ">", "above": ">", "<": "<", "<=": "<=", "under": "<", "below": "<", "at least": ">="}
    comparator = comp_map.get(comp_raw.replace("  ", " "), None)
    value = parse_number(match.group("num"))
    return comparator, value


def extract_expiry(text: str) -> Optional[datetime]:
    try:
        # Allow multiple date formats
        return dateparser.parse(text, fuzzy=True, default=datetime.utcnow())
    except (ValueError, OverflowError):
        return None


def extract_entity(text: str) -> Optional[str]:
    normalized = normalize_text(text)
    # crude extraction: tickers or capitalized words in original
    ticker_match = re.search(r"\b[A-Z]{2,5}\b", text)
    if ticker_match:
        return ticker_match.group(0).lower()
    # fallback: first significant token
    tokens = [t for t in normalized.split(" ") if t]
    return tokens[0] if tokens else None
