from __future__ import annotations

import itertools
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict, Iterable, List, Tuple, Optional

from difflib import SequenceMatcher

from predarb.extractors import extract_entity, extract_expiry, extract_threshold
from predarb.models import Market
from predarb.normalize import stable_key, tokenize


def fingerprint(market: Market) -> Dict[str, object]:
    key = stable_key(market.question)
    entity = market.asset or extract_entity(market.question)
    expiry = market.expiry or extract_expiry(market.question)
    comp2, thr2 = extract_threshold(market.question)
    comparator = market.comparator or comp2
    threshold = market.threshold if market.threshold is not None else thr2
    return {
        "key": key,
        "entity": entity,
        "expiry": expiry,
        "comparator": comparator,
        "threshold": threshold,
    }


def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def cluster_duplicates(markets: Iterable[Market], title_threshold: float = 0.8) -> List[Tuple[Market, Market]]:
    pairs: List[Tuple[Market, Market]] = []
    markets = list(markets)
    for m1, m2 in itertools.combinations(markets, 2):
        fp1 = fingerprint(m1)
        fp2 = fingerprint(m2)
        if fp1["expiry"] and fp2["expiry"]:
            dt1 = fp1["expiry"]
            dt2 = fp2["expiry"]
            if dt1.tzinfo and not dt2.tzinfo:
                dt2 = dt2.replace(tzinfo=dt1.tzinfo)
            if dt2.tzinfo and not dt1.tzinfo:
                dt1 = dt1.replace(tzinfo=dt2.tzinfo)
            if abs((dt1 - dt2).total_seconds()) > 3600 * 24:
                continue
        title_sim = similarity(fp1["key"], fp2["key"])
        if title_sim < title_threshold:
            continue
        if fp1["entity"] and fp2["entity"] and fp1["entity"] != fp2["entity"]:
            continue
        pairs.append((m1, m2))
    return pairs


def group_related(markets: Iterable[Market], expiry_window_days: int = 7) -> Dict[str, List[Market]]:
    groups: Dict[str, List[Market]] = defaultdict(list)
    for m in markets:
        fp = fingerprint(m)
        expiry = fp["expiry"]
        entity = fp["entity"] or "unknown"
        bucket_date = expiry.date() if expiry else None
        groups[(entity, bucket_date)].append(m)
    # merge buckets within expiry_window_days
    merged: Dict[str, List[Market]] = defaultdict(list)
    for (entity, date_bucket), items in groups.items():
        merged_key = f"{entity}-{date_bucket}"
        if date_bucket:
            for (entity2, date2), _items2 in groups.items():
                if entity == entity2 and date2 and abs((date_bucket - date2).days) <= expiry_window_days:
                    merged_key = f"{entity}-{min(date_bucket, date2)}"
                    break
        merged[merged_key].extend(items)
    return merged


def verify_semantic_groups(
    groups: Dict[str, List[Market]],
    llm_verifier: Optional[object] = None,
) -> Dict[str, List[List[Market]]]:
    """
    Apply optional LLM verification to semantic market groups.

    After semantic clustering, this function can optionally verify that each group
    truly represents the same event using an LLM. Splits groups into verified subgroups.

    Args:
        groups: Dict from semantic clustering (group_id -> List[Market])
        llm_verifier: Optional LLMVerifier instance. If None or not enabled, returns
                      original groups with no verification.

    Returns:
        Dict mapping group_id -> List[List[Market]] (verified subgroups)
    """
    if llm_verifier is None:
        # No verification; return groups as single subgroups
        return {gid: [markets] for gid, markets in groups.items()}

    if not getattr(llm_verifier.config, "enabled", False):
        # Verification disabled; return groups as single subgroups
        return {gid: [markets] for gid, markets in groups.items()}

    verified_groups: Dict[str, List[List[Market]]] = {}

    for group_id, markets in groups.items():
        if len(markets) < 2:
            # Single market or empty group; no verification needed
            verified_groups[group_id] = [markets]
            continue

        # Verify the group
        verified_result = llm_verifier.verify_group(markets)

        # Extract verified subgroups from union-find result
        verified_groups[group_id] = verified_result.verified_subgroups

    return verified_groups

