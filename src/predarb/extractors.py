from __future__ import annotations

import re
from datetime import datetime
from typing import Optional, Tuple

from dateutil import parser as dateparser

from predarb.normalize import normalize_text

THRESHOLD_PATTERN = re.compile(
    r"(?P<comp>>=|<=|>|<|over|under|above|at\s+least|below)\s*\$?(?P<num>[0-9,.]+(?:k|m)?)",
    re.IGNORECASE,
)


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
