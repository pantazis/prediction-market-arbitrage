from __future__ import annotations

import itertools
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict, Iterable, List, Tuple, Optional

from difflib import SequenceMatcher

from predarb.extractors import extract_entity, extract_expiry, extract_threshold
from predarb.models import Market
from predarb.normalize import stable_key, tokenize

# Optional semantic similarity imports
try:
    from sentence_transformers import SentenceTransformer, util
    import numpy as np
    import torch
    SEMANTIC_AVAILABLE = True
except (ImportError, OSError, Exception):
    SEMANTIC_AVAILABLE = False
    SentenceTransformer = None
    util = None
    np = None
    torch = None

# Global caches for semantic model and embeddings
_semantic_model = None
_embedding_cache: Dict[str, any] = {}


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


def semantic_similarity(a: str, b: str, model_name: str = "all-MiniLM-L6-v2") -> float:
    """
    Compute semantic similarity between two strings using sentence embeddings.
    
    Uses sentence-transformers to generate embeddings and computes cosine similarity.
    Results are cached for performance.
    
    Args:
        a: First string
        b: Second string
        model_name: Name of sentence-transformers model to use
        
    Returns:
        Float 0.0-1.0 representing similarity (0=unrelated, 1=identical)
        
    Raises:
        RuntimeError: If sentence-transformers is not available
    """
    global _semantic_model, _embedding_cache
    
    if not SEMANTIC_AVAILABLE:
        raise RuntimeError(
            "sentence-transformers not available. Install with: "
            "pip install sentence-transformers"
        )
    
    # Lazy load model on first use
    if _semantic_model is None:
        _semantic_model = SentenceTransformer(model_name)
    
    # Get or compute embeddings (cached)
    def get_embedding(text: str):
        cache_key = f"{model_name}::{text}"
        if cache_key not in _embedding_cache:
            _embedding_cache[cache_key] = _semantic_model.encode(text, convert_to_numpy=True)
        return _embedding_cache[cache_key]
    
    emb_a = get_embedding(a)
    emb_b = get_embedding(b)
    
    # Cosine similarity
    cos_sim = np.dot(emb_a, emb_b) / (np.linalg.norm(emb_a) * np.linalg.norm(emb_b))
    return float(cos_sim)


def _get_semantic_model(model_name: str) -> SentenceTransformer:
    global _semantic_model
    if not SEMANTIC_AVAILABLE:
        raise RuntimeError(
            "sentence-transformers not available. Install with: "
            "pip install sentence-transformers"
        )
    if _semantic_model is None:
        _semantic_model = SentenceTransformer(model_name)
    return _semantic_model


def _encode_texts(
    texts: List[str],
    model_name: str = "all-MiniLM-L6-v2",
    batch_size: int = 32,
) -> "torch.Tensor":
    if not SEMANTIC_AVAILABLE:
        raise RuntimeError(
            "sentence-transformers not available. Install with: "
            "pip install sentence-transformers"
        )
    if not texts:
        return torch.empty((0, 0))
    model = _get_semantic_model(model_name)
    missing = [text for text in texts if f"{model_name}::{text}" not in _embedding_cache]
    if missing:
        new_emb = model.encode(
            missing,
            convert_to_tensor=True,
            normalize_embeddings=True,
            show_progress_bar=False,
            batch_size=batch_size,
        )
        for text, emb in zip(missing, new_emb):
            _embedding_cache[f"{model_name}::{text}"] = emb
    return torch.stack([_embedding_cache[f"{model_name}::{text}"] for text in texts])


def semantic_topk_matches(
    queries: List[str],
    corpus: List[str],
    model_name: str = "all-MiniLM-L6-v2",
    top_k: int = 5,
    min_score: float = 0.6,
    batch_size: int = 32,
) -> List[List[Tuple[int, float]]]:
    """
    Bi-encoder top-k retrieval for queries against a corpus.

    Returns per-query matches as (corpus_id, score) filtered by min_score.
    """
    if not SEMANTIC_AVAILABLE:
        raise RuntimeError(
            "sentence-transformers not available. Install with: "
            "pip install sentence-transformers"
        )
    if not queries or not corpus:
        return [[] for _ in queries]
    corpus_emb = _encode_texts(corpus, model_name=model_name, batch_size=batch_size)
    top_k = min(top_k, len(corpus))
    matches: List[List[Tuple[int, float]]] = []
    for batch_start in range(0, len(queries), batch_size):
        batch = queries[batch_start: batch_start + batch_size]
        query_emb = _encode_texts(batch, model_name=model_name, batch_size=batch_size)
        hits = util.semantic_search(query_emb, corpus_emb, top_k=top_k)
        for hit_list in hits:
            filtered = [
                (hit["corpus_id"], float(hit["score"]))
                for hit in hit_list
                if hit["score"] >= min_score
            ]
            matches.append(filtered)
    return matches


def cluster_duplicates(
    markets: Iterable[Market], 
    title_threshold: float = 0.8,
    use_semantic: bool = False,
    semantic_model_name: str = "all-MiniLM-L6-v2",
    semantic_top_k: int = 5,
    semantic_batch_size: int = 32,
) -> List[Tuple[Market, Market]]:
    """
    Cluster duplicate or highly similar markets based on title similarity.
    
    Args:
        markets: Iterable of Market objects to cluster
        title_threshold: Minimum similarity score (0.0-1.0) to consider duplicates
        use_semantic: If True, use semantic similarity; if False, use string matching
        semantic_model_name: Sentence-transformers model name for bi-encoder
        semantic_top_k: Top-k candidates to retrieve per market
        semantic_batch_size: Batch size for embedding encoding
        
    Returns:
        List of market pairs that are considered duplicates
    """
    pairs: List[Tuple[Market, Market]] = []
    markets = list(markets)
    fingerprints = [fingerprint(m) for m in markets]

    if use_semantic:
        keys = [fp["key"] for fp in fingerprints]
        hits = semantic_topk_matches(
            keys,
            keys,
            model_name=semantic_model_name,
            top_k=semantic_top_k,
            min_score=title_threshold,
            batch_size=semantic_batch_size,
        )
        for i, hit_list in enumerate(hits):
            fp1 = fingerprints[i]
            for j, _score in hit_list:
                if j <= i:
                    continue
                fp2 = fingerprints[j]
                if fp1["expiry"] and fp2["expiry"]:
                    dt1 = fp1["expiry"]
                    dt2 = fp2["expiry"]
                    if dt1.tzinfo and not dt2.tzinfo:
                        dt2 = dt2.replace(tzinfo=dt1.tzinfo)
                    if dt2.tzinfo and not dt1.tzinfo:
                        dt1 = dt1.replace(tzinfo=dt2.tzinfo)
                    if abs((dt1 - dt2).total_seconds()) > 3600 * 24:
                        continue
                if fp1["entity"] and fp2["entity"] and fp1["entity"] != fp2["entity"]:
                    continue
                pairs.append((markets[i], markets[j]))
        return pairs

    # Default: exact string matching
    for i, j in itertools.combinations(range(len(markets)), 2):
        fp1 = fingerprints[i]
        fp2 = fingerprints[j]
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
        pairs.append((markets[i], markets[j]))
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
