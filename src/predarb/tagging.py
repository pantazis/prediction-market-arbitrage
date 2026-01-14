from __future__ import annotations

import re
from datetime import datetime
from typing import Iterable, List, Set

from predarb.extractors import extract_entity
from predarb.normalize import STOPWORDS, normalize_text
from predarb.models import Market

_TOPIC_KEYWORDS = {
    "politics": [
        "election", "president", "prime minister", "congress", "parliament",
        "senate", "governor", "mayor", "vote", "ballot", "poll",
    ],
    "macro": [
        "fed", "fomc", "interest rate", "rate cut", "rate hike", "inflation",
        "cpi", "ppi", "gdp", "unemployment", "recession", "treasury", "yield",
    ],
    "crypto": [
        "bitcoin", "btc", "ethereum", "eth", "solana", "crypto", "blockchain",
    ],
    "sports": [
        "nba", "nfl", "mlb", "nhl", "soccer", "fifa", "uefa", "tennis",
        "golf", "super bowl", "world cup",
    ],
    "war": [
        "war", "invasion", "conflict", "missile", "ukraine", "russia",
        "israel", "gaza", "iran", "china", "taiwan",
    ],
    "tech": [
        "ai", "artificial intelligence", "openai", "google", "apple",
        "microsoft", "meta", "nvidia", "earnings", "ipo",
    ],
    "weather": [
        "hurricane", "storm", "earthquake", "climate", "temperature",
        "rainfall", "wildfire",
    ],
}

_TYPE_KEYWORDS = {
    "winner": ["winner", "win", "champion", "title"],
    "shutdown": ["shutdown"],
    "rate": ["rate cut", "rate hike", "interest rate", "fomc", "fed"],
    "resign": ["resign", "step down", "quit", "resignation"],
    "announce": ["announce", "announcement", "declare", "launch", "release"],
    "approval": ["approval", "approve", "regulator", "sec", "fta"],
}

_FAST_ENTITY_KEYWORDS = {
    "trump": "trump",
    "biden": "biden",
    "fed": "fed",
    "fomc": "fomc",
    "btc": "btc",
    "bitcoin": "btc",
    "eth": "eth",
    "ethereum": "eth",
    "venezuela": "venezuela",
}

_FAST_TOPIC_KEYWORDS = {
    "election": ["election", "vote", "ballot", "poll", "president", "primary"],
    "rates": ["rate", "rates", "fomc", "fed", "interest"],
    "war": ["war", "invasion", "conflict", "missile", "ukraine", "russia", "israel", "gaza"],
    "crypto": ["crypto", "bitcoin", "btc", "ethereum", "eth", "solana"],
    "macro": ["inflation", "cpi", "ppi", "gdp", "unemployment", "recession", "treasury", "yield"],
}

_FAST_COUNTRY_KEYWORDS = {
    "us": ["u.s.", "us ", "united states", "america", "american"],
    "china": ["china", "chinese", "beijing"],
    "russia": ["russia", "russian", "moscow"],
    "ukraine": ["ukraine", "ukrainian", "kyiv"],
    "israel": ["israel", "israeli"],
    "venezuela": ["venezuela", "venezuelan"],
}

_NAME_STOPWORDS = {
    "will",
    "the",
    "a",
    "an",
    "us",
    "u.s",
    "united",
    "states",
    "president",
    "republican",
    "democratic",
    "nomination",
    "party",
}

_NAME_PATTERN = re.compile(
    r"\b(?:[A-Z][a-z]+|[A-Z]\.)(?:\s+(?:[A-Z][a-z]+|[A-Z]\.)){1,3}\b"
)


def normalize_tag(tag: str) -> str:
    if not tag:
        return ""
    tag = tag.strip().lower()
    tag = re.sub(r"\s+", "_", tag)
    tag = re.sub(r"[^a-z0-9:_\-]", "", tag)
    return tag


def _add_tag(tags: List[str], seen: Set[str], raw: str) -> None:
    normalized = normalize_tag(raw)
    if not normalized or normalized in seen:
        return
    tags.append(normalized)
    seen.add(normalized)


def _extract_topics(text: str, tags: List[str], seen: Set[str]) -> None:
    for topic, keywords in _TOPIC_KEYWORDS.items():
        if any(k in text for k in keywords):
            _add_tag(tags, seen, f"topic:{topic}")


def _extract_types(text: str, tags: List[str], seen: Set[str]) -> None:
    for tag, keywords in _TYPE_KEYWORDS.items():
        if any(k in text for k in keywords):
            _add_tag(tags, seen, f"type:{tag}")


def _extract_time_tags(end_date: datetime, tags: List[str], seen: Set[str]) -> None:
    year = end_date.strftime("%Y")
    month = end_date.strftime("%Y-%m")
    _add_tag(tags, seen, f"time:{year}")
    _add_tag(tags, seen, f"time:{month}")


def _extract_name_tags(raw_text: str, tags: List[str], seen: Set[str]) -> None:
    for match in _NAME_PATTERN.finditer(raw_text or ""):
        value = match.group(0).strip()
        parts = [p.strip(".").lower() for p in value.split() if p]
        if not parts:
            continue
        if all(p in _NAME_STOPWORDS for p in parts):
            continue
        _add_tag(tags, seen, f"name:{'_'.join(parts)}")


def build_tags(market: Market) -> List[str]:
    tags: List[str] = []
    seen: Set[str] = set()

    text_parts = [market.question or ""]
    if market.description:
        text_parts.append(str(market.description))
    text = normalize_text(" ".join(text_parts))

    _extract_topics(text, tags, seen)
    _extract_types(text, tags, seen)
    _extract_name_tags(" ".join(text_parts), tags, seen)

    if market.end_date:
        _extract_time_tags(market.end_date, tags, seen)

    entity = extract_entity(market.question or "")
    if entity and entity not in STOPWORDS and len(entity) > 2:
        _add_tag(tags, seen, f"entity:{entity}")

    if market.outcomes:
        if len(market.outcomes) == 2:
            _add_tag(tags, seen, "type:binary")
        else:
            _add_tag(tags, seen, "type:multi")

    if market.comparator or market.threshold is not None:
        _add_tag(tags, seen, "type:threshold")

    return tags


def ensure_market_tags(market: Market) -> None:
    if market.tags is None:
        market.tags = []
    existing = {normalize_tag(t) for t in market.tags if t}
    for tag in build_tags(market):
        if tag in existing:
            continue
        market.tags.append(tag)
        existing.add(tag)


def normalized_tag_set(tags: Iterable[str]) -> Set[str]:
    return {normalize_tag(t) for t in tags if t}


def _expiry_bucket(end_date: datetime) -> str:
    now = datetime.utcnow().replace(tzinfo=end_date.tzinfo) if end_date.tzinfo else datetime.utcnow()
    delta_hours = (end_date - now).total_seconds() / 3600.0
    if delta_hours <= 24:
        return "day"
    if delta_hours <= 24 * 7:
        return "week"
    if delta_hours <= 24 * 31:
        return "month"
    return "year"


def fast_tag_market(market: Market) -> List[str]:
    """
    Fast O(N) tagging for strict A+B pipeline using regex/keywords only.
    """
    tags: List[str] = []
    seen: Set[str] = set()

    raw_text = " ".join(
        [str(market.question or ""), str(market.description or "")]
    )
    text = normalize_text(raw_text)

    for topic, keywords in _FAST_TOPIC_KEYWORDS.items():
        if any(k in text for k in keywords):
            _add_tag(tags, seen, f"topic:{topic}")

    for country, keywords in _FAST_COUNTRY_KEYWORDS.items():
        if any(k in text for k in keywords):
            _add_tag(tags, seen, f"country:{country}")

    for keyword, entity in _FAST_ENTITY_KEYWORDS.items():
        if keyword in text:
            _add_tag(tags, seen, f"entity:{entity}")

    # Asset/country hints from extractors (regex only)
    entity = extract_entity(market.question or "")
    if entity and entity not in STOPWORDS and len(entity) > 2:
        _add_tag(tags, seen, f"asset:{entity}")

    if market.end_date:
        bucket = _expiry_bucket(market.end_date)
        _add_tag(tags, seen, f"expiry:{bucket}")

    return tags
