import re
from typing import List, Set

STOPWORDS: Set[str] = {
    "the",
    "a",
    "an",
    "of",
    "on",
    "in",
    "will",
    "be",
    "by",
    "to",
    "for",
    "vs",
    "at",
    "and",
    "or",
    "with",
}


def normalize_text(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s><=]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def tokenize(text: str) -> List[str]:
    cleaned = normalize_text(text)
    tokens = [t for t in cleaned.split(" ") if t and t not in STOPWORDS]
    return tokens


def stable_key(text: str) -> str:
    tokens = tokenize(text)
    return " ".join(sorted(tokens))
