"""
LLM-based verification layer for Polymarket semantic clustering.

Confirms whether two markets in a semantic cluster truly resolve on the same event
and same resolution criteria using a cheap LLM (e.g., GPT-3.5, Gemini 1.5-flash).

Features:
  - Optional (default OFF)
  - Cacheable with TTL
  - Timeout-safe (fail_open or fail_closed)
  - Network-free testing with MockLLMProvider
  - Strict JSON response parsing
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from abc import ABC, abstractmethod
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Any

from pydantic import BaseModel, Field

from predarb.models import Market

logger = logging.getLogger(__name__)

PROMPT_VERSION = "v1"


class VerificationResult(BaseModel):
    """Result of verifying whether two markets are the same event."""

    same_event: bool
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str
    resolution_source: Optional[str] = None
    resolution_date: Optional[str] = None
    key_fields: Dict[str, Any] = Field(default_factory=dict)


class VerifiedGroup(BaseModel):
    """Result of verifying a group of markets."""

    original_markets: List[Market]
    verified_subgroups: List[List[Market]] = Field(default_factory=list)
    verification_results: List[VerificationResult] = Field(default_factory=list)
    total_verifications: int = 0
    skipped_pairs: int = 0


class LLMVerifierConfig(BaseModel):
    """Configuration for LLM-based market verification."""

    enabled: bool = False
    provider: str = "mock"  # "openai", "gemini", "mock"
    model: str = "gpt-3.5-turbo"  # or "gemini-1.5-flash", etc.
    timeout_s: float = 3.0
    max_pairs_per_group: int = 5
    min_similarity_to_verify: float = 0.90
    cache_path: str = "data/llm_verify_cache.json"
    ttl_hours: int = 168
    fail_mode: str = "fail_open"  # "fail_open" or "fail_closed"

    def __post_init__(self):
        """Validate configuration."""
        if self.fail_mode not in ("fail_open", "fail_closed"):
            raise ValueError(
                f"fail_mode must be 'fail_open' or 'fail_closed', got {self.fail_mode}"
            )
        if not 0.0 <= self.min_similarity_to_verify <= 1.0:
            raise ValueError(
                f"min_similarity_to_verify must be in [0, 1], got {self.min_similarity_to_verify}"
            )


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""

    @abstractmethod
    def complete_json(self, prompt: str) -> dict:
        """
        Send a prompt and parse strict JSON response.

        Args:
            prompt: The prompt text

        Returns:
            Parsed JSON dict or empty dict on failure

        Raises:
            TimeoutError: If request exceeds timeout
        """
        pass


class OpenAIChatProvider(LLMProvider):
    """OpenAI Chat Completions provider (network-enabled)."""

    def __init__(self, api_key: Optional[str] = None, timeout_s: float = 3.0):
        """
        Initialize OpenAI provider.

        Args:
            api_key: OpenAI API key (default: OPENAI_API_KEY env var)
            timeout_s: Request timeout in seconds
        """
        self.api_key = api_key or os.getenv("OPENAI_API_KEY", "")
        self.timeout_s = timeout_s
        if not self.api_key:
            logger.warning("OpenAI API key not set; verify_pair will fail")

    def complete_json(self, prompt: str) -> dict:
        """
        Send prompt to OpenAI and extract JSON from response.

        Returns empty dict on error or timeout.
        """
        if not self.api_key:
            logger.debug("OpenAI API key not configured")
            return {}

        try:
            import openai
        except ImportError:
            logger.error("openai package required for OpenAIChatProvider")
            return {}

        try:
            client = openai.OpenAI(api_key=self.api_key)
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                timeout=self.timeout_s,
            )
            text = response.choices[0].message.content.strip()
            # Extract JSON from response
            return self._parse_json_from_text(text)
        except TimeoutError:
            logger.warning("OpenAI request timed out")
            raise TimeoutError("OpenAI request timeout") from None
        except Exception as e:
            logger.error(f"OpenAI request failed: {e}")
            return {}

    @staticmethod
    def _parse_json_from_text(text: str) -> dict:
        """Extract and parse JSON from response text."""
        # Try direct parse first
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Try extracting JSON block
        start_idx = text.find("{")
        end_idx = text.rfind("}")
        if start_idx >= 0 and end_idx > start_idx:
            try:
                return json.loads(text[start_idx : end_idx + 1])
            except json.JSONDecodeError:
                pass

        logger.warning(f"Failed to parse JSON from response: {text[:100]}")
        return {}


class MockLLMProvider(LLMProvider):
    """Mock LLM provider for deterministic testing (no network)."""

    def __init__(self, timeout_s: float = 0.1):
        """
        Initialize mock provider.

        Args:
            timeout_s: Simulated timeout (for testing timeout behavior)
        """
        self.timeout_s = timeout_s
        self.call_count = 0

    def complete_json(self, prompt: str) -> dict:
        """
        Return deterministic result based on prompt content.

        Simulates real LLM responses for testing without network.
        """
        self.call_count += 1

        # Simulate timeout if requested
        if "TIMEOUT" in prompt:
            raise TimeoutError("Simulated timeout")

        # Deterministic logic: check for key signals
        prompt_lower = prompt.lower()

        # Different events - check FIRST before same-event checks
        has_january = "january" in prompt_lower
        has_march = "march" in prompt_lower
        has_fed = "fed" in prompt_lower
        has_bitcoin = "bitcoin" in prompt_lower
        has_btc = "btc" in prompt_lower
        has_100k = "$100,000" in prompt_lower

        # Reject if comparing different months for same entity
        if has_january and has_march:
            return {
                "same_event": False,
                "confidence": 0.95,
                "reason": "Different resolution months (January vs March)",
                "resolution_source": "Federal Reserve",
                "resolution_date": "Different",
            }

        # Same event: January + Fed (but not other months)
        if has_january and has_fed and not has_march:
            return {
                "same_event": True,
                "confidence": 0.92,
                "reason": "Both markets resolve on Fed decision in January",
                "resolution_source": "Federal Reserve",
                "resolution_date": "2024-01-31",
            }

        # Same event: Bitcoin/BTC at $100k
        if (has_bitcoin or has_btc) and has_100k:
            return {
                "same_event": True,
                "confidence": 0.88,
                "reason": "Both reference Bitcoin price at same level",
                "resolution_source": "CoinGecko",
                "resolution_date": "2024-12-31",
            }

        # Generic match
        if any(word in prompt_lower for word in ["same", "identical", "match"]):
            return {
                "same_event": True,
                "confidence": 0.75,
                "reason": "Markets appear to cover same event",
                "resolution_source": "Unknown",
                "resolution_date": None,
            }

        # Default: different events
        return {
            "same_event": False,
            "confidence": 0.60,
            "reason": "Markets appear to cover different events",
            "resolution_source": None,
            "resolution_date": None,
        }


class LLMVerifier:
    """
    Verifies semantic market clusters using an LLM.

    Caches results, respects timeouts, and handles parse errors gracefully.
    """

    PROMPT_TEMPLATE = """
You are a prediction market expert. Compare these two Polymarket questions and determine if they resolve on the same real-world event using the same criteria.

Market A: {question_a}
  - Resolution Source: {resolution_source_a}
  - Tags: {tags_a}
  - Description: {description_a}

Market B: {question_b}
  - Resolution Source: {resolution_source_b}
  - Tags: {tags_b}
  - Description: {description_b}

Respond with ONLY valid JSON in this exact format:
{{
  "same_event": true/false,
  "confidence": <float 0.0-1.0>,
  "reason": "<brief explanation>",
  "resolution_source": "<common source if same_event, else null>",
  "resolution_date": "<extracted date if available, else null>"
}}
"""

    def __init__(
        self,
        config: LLMVerifierConfig,
        provider: Optional[LLMProvider] = None,
    ):
        """
        Initialize LLM verifier.

        Args:
            config: Verification configuration
            provider: LLM provider (default: based on config.provider)
        """
        self.config = config
        self.provider = provider or self._create_provider()
        self.original_markets: List[Market] = []
        self._cache: Dict[str, tuple[VerificationResult, float]] = {}
        self._load_cache()

    def _create_provider(self) -> LLMProvider:
        """Create LLM provider based on configuration."""
        if self.config.provider == "openai":
            return OpenAIChatProvider(timeout_s=self.config.timeout_s)
        elif self.config.provider == "gemini":
            # Placeholder for Gemini implementation
            logger.warning("Gemini provider not yet implemented; using mock")
            return MockLLMProvider(timeout_s=self.config.timeout_s)
        else:
            return MockLLMProvider(timeout_s=self.config.timeout_s)

    def _cache_key(self, market_a: Market, market_b: Market) -> str:
        """
        Generate stable cache key.

        Order-invariant: pair (a, b) and (b, a) have same key.
        """
        ids = sorted([market_a.id, market_b.id])
        content = f"{ids[0]}|{ids[1]}|{PROMPT_VERSION}|{self.config.model}"
        return hashlib.md5(content.encode()).hexdigest()

    def _load_cache(self) -> None:
        """Load cache from disk if it exists."""
        cache_path = Path(self.config.cache_path)
        if not cache_path.exists():
            return

        try:
            with open(cache_path, "r") as f:
                data = json.load(f)
            for key, entry in data.items():
                result_dict, timestamp = entry["result"], entry["timestamp"]
                self._cache[key] = (
                    VerificationResult(**result_dict),
                    timestamp,
                )
            logger.debug(f"Loaded {len(self._cache)} cached verifications")
        except Exception as e:
            logger.warning(f"Failed to load verification cache: {e}")

    def _save_cache(self) -> None:
        """Save cache to disk (write-then-rename for safety)."""
        cache_path = Path(self.config.cache_path)
        cache_path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            key: {
                "result": result.model_dump(),
                "timestamp": timestamp,
            }
            for key, (result, timestamp) in self._cache.items()
        }

        try:
            # Write to temp file
            temp_path = cache_path.with_suffix(".tmp")
            with open(temp_path, "w") as f:
                json.dump(data, f, indent=2)
            # Atomic rename
            temp_path.replace(cache_path)
            logger.debug(f"Saved {len(self._cache)} cached verifications")
        except Exception as e:
            logger.error(f"Failed to save verification cache: {e}")

    def _is_cache_expired(self, timestamp: float) -> bool:
        """Check if cached result has expired."""
        age_hours = (time.time() - timestamp) / 3600.0
        return age_hours > self.config.ttl_hours

    def verify_pair(self, market_a: Market, market_b: Market) -> VerificationResult:
        """
        Verify if two markets are the same event.

        Args:
            market_a: First market
            market_b: Second market

        Returns:
            VerificationResult with same_event bool and confidence
        """
        if not self.config.enabled:
            # Return neutral result if verification disabled
            return VerificationResult(
                same_event=False,
                confidence=0.0,
                reason="Verification disabled",
            )

        # Check cache
        cache_key = self._cache_key(market_a, market_b)
        if cache_key in self._cache:
            result, timestamp = self._cache[cache_key]
            if not self._is_cache_expired(timestamp):
                logger.debug(f"Cache hit for {cache_key}")
                return result

        # Build prompt
        prompt = self.PROMPT_TEMPLATE.format(
            question_a=market_a.question,
            resolution_source_a=market_a.resolution_source or "Not specified",
            tags_a=", ".join(market_a.tags) if market_a.tags else "None",
            description_a=market_a.description or "None",
            question_b=market_b.question,
            resolution_source_b=market_b.resolution_source or "Not specified",
            tags_b=", ".join(market_b.tags) if market_b.tags else "None",
            description_b=market_b.description or "None",
        )

        # Call provider with timeout
        try:
            response_json = self._call_with_timeout(prompt)
        except TimeoutError:
            logger.warning(f"Verification timeout for markets {market_a.id}, {market_b.id}")
            return self._handle_timeout()

        # Parse response
        try:
            result = self._parse_response(response_json)
        except Exception as e:
            logger.error(f"Failed to parse verification response: {e}")
            return self._handle_parse_error()

        # Cache and return
        self._cache[cache_key] = (result, time.time())
        self._save_cache()
        return result

    def _call_with_timeout(self, prompt: str) -> dict:
        """Call provider with timeout protection."""
        try:
            result = self.provider.complete_json(prompt)
            return result
        except TimeoutError:
            raise

    def _parse_response(self, response_json: dict) -> VerificationResult:
        """
        Parse and validate LLM response JSON.

        Raises ValueError if response is invalid.
        """
        if not isinstance(response_json, dict):
            raise ValueError(f"Expected dict, got {type(response_json)}")

        same_event = response_json.get("same_event", False)
        if not isinstance(same_event, bool):
            raise ValueError(f"same_event must be bool, got {type(same_event)}")

        confidence = float(response_json.get("confidence", 0.0))
        if not 0.0 <= confidence <= 1.0:
            raise ValueError(f"confidence must be in [0, 1], got {confidence}")

        reason = str(response_json.get("reason", "No reason provided"))
        resolution_source = response_json.get("resolution_source")
        resolution_date = response_json.get("resolution_date")

        return VerificationResult(
            same_event=same_event,
            confidence=confidence,
            reason=reason,
            resolution_source=resolution_source,
            resolution_date=resolution_date,
            key_fields={
                "resolution_source": resolution_source,
                "resolution_date": resolution_date,
            },
        )

    def _handle_timeout(self) -> VerificationResult:
        """Handle timeout based on fail_mode config."""
        if self.config.fail_mode == "fail_open":
            # Assume same event
            return VerificationResult(
                same_event=True,
                confidence=0.0,
                reason="Verification timeout (fail_open)",
            )
        else:
            # Assume different events
            return VerificationResult(
                same_event=False,
                confidence=0.0,
                reason="Verification timeout (fail_closed)",
            )

    def _handle_parse_error(self) -> VerificationResult:
        """Handle parse error based on fail_mode config."""
        if self.config.fail_mode == "fail_open":
            return VerificationResult(
                same_event=True,
                confidence=0.0,
                reason="Verification parse error (fail_open)",
            )
        else:
            return VerificationResult(
                same_event=False,
                confidence=0.0,
                reason="Verification parse error (fail_closed)",
            )

    def verify_group(self, group: List[Market]) -> VerifiedGroup:
        """
        Verify all markets in a group.

        Splits group into verified subgroups and tracks results.

        Args:
            group: List of markets to verify

        Returns:
            VerifiedGroup with subgroups and verification metadata
        """
        self.original_markets = group

        if not self.config.enabled or len(group) < 2:
            # Return original group as single subgroup if verification disabled
            return VerifiedGroup(
                original_markets=group,
                verified_subgroups=[group] if group else [],
            )

        # Verify pairs
        results: List[tuple[int, int, VerificationResult]] = []
        verified_count = 0
        max_pairs = self.config.max_pairs_per_group
        pairs = [
            (i, j)
            for i in range(len(group))
            for j in range(i + 1, len(group))
        ]

        for i, j in pairs[:max_pairs]:
            result = self.verify_pair(group[i], group[j])
            results.append((i, j, result))
            if result.same_event:
                verified_count += 1

        # Build subgroups using union-find
        subgroups = self._build_subgroups(len(group), results)

        return VerifiedGroup(
            original_markets=group,
            verified_subgroups=subgroups,
            verification_results=[r[2] for r in results],
            total_verifications=len(results),
            skipped_pairs=len(pairs) - len(results),
        )

    def _build_subgroups(
        self, num_markets: int, results: List[tuple[int, int, VerificationResult]]
    ) -> List[List[Market]]:
        """
        Build subgroups from verification results using union-find.

        Returns list of market lists (not indices).
        """
        parent = list(range(num_markets))

        def find(x: int) -> int:
            if parent[x] != x:
                parent[x] = find(parent[x])
            return parent[x]

        def union(x: int, y: int) -> None:
            px, py = find(x), find(y)
            if px != py:
                parent[px] = py

        # Union markets that are verified as same event
        for i, j, result in results:
            if result.same_event:
                union(i, j)

        # Group by root and return market lists
        groups: Dict[int, List[int]] = defaultdict(list)
        for idx in range(num_markets):
            root = find(idx)
            groups[root].append(idx)

        # Return as market lists
        return [
            [self.original_markets[i] for i in sorted(indices)]
            for indices in groups.values()
        ]
