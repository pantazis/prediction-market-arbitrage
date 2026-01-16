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

import requests

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


class ArbitrageCaseResult(BaseModel):
    """Structured arbitrage validation result for a matched market pair."""

    case_name: str
    kalshi_action: str
    polymarket_action: str
    prices_used: Dict[str, Any] = Field(default_factory=dict)
    edge_gross: float
    edge_net: float
    max_size: float
    guaranteed: bool
    reason: str


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
    provider: str = "mock"  # "openai", "gemini", "ollama", "mock"
    model: str = "gpt-3.5-turbo"  # or "gemini-1.5-flash", etc.
    timeout_s: float = 3.0
    max_pairs_per_group: int = 5
    min_similarity_to_verify: float = 0.90
    cache_path: str = "data/llm_verify_cache.json"
    ttl_hours: int = 168
    fail_mode: str = "fail_closed"  # "fail_open" or "fail_closed"


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

        # Try extracting JSON block (support markdown fences)
        start_idx = text.find("{")
        end_idx = text.rfind("}")
        if start_idx >= 0 and end_idx > start_idx:
            block = text[start_idx : end_idx + 1]
            try:
                return json.loads(block)
            except json.JSONDecodeError:
                # Fallback: Try ast.literal_eval for single-quoted Python dicts
                # LLMs often output Python dicts instead of strict JSON
                try:
                    import ast
                    return ast.literal_eval(block)
                except (ValueError, SyntaxError):
                    pass

        logger.warning(f"Failed to parse JSON from response. Raw output: {text}")
        return {}


class GeminiProvider(LLMProvider):
    """Gemini provider (network-enabled)."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "gemini-1.5-flash",
        timeout_s: float = 3.0,
    ):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY", "")
        self.model = model
        self.timeout_s = timeout_s
        if not self.api_key:
            logger.warning("Gemini API key not set; verify_pair will fail")

    def complete_json(self, prompt: str) -> dict:
        if not self.api_key:
            logger.debug("Gemini API key not configured")
            return {}

        url = (
            f"https://generativelanguage.googleapis.com/v1/models/"
            f"{self.model}:generateContent?key={self.api_key}"
        )
        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": prompt}],
                }
            ]
        }

        try:
            resp = requests.post(url, json=payload, timeout=self.timeout_s)
            resp.raise_for_status()
            data = resp.json()
        except requests.exceptions.Timeout:
            logger.warning("Gemini request timed out")
            raise TimeoutError("Gemini request timeout") from None
        except requests.exceptions.HTTPError as e:
            status = getattr(e.response, "status_code", "unknown")
            body = getattr(e.response, "text", "") or ""
            body = body[:2000]
            logger.error("Gemini request failed: HTTP %s | %s", status, body)
            return {}
        except Exception as e:
            logger.error(f"Gemini request failed: {e}")
            return {}

        try:
            candidates = data.get("candidates") or []
            if not candidates:
                logger.warning("Gemini returned no candidates")
                return {}
            parts = candidates[0].get("content", {}).get("parts", [])
            if not parts:
                logger.warning("Gemini returned empty parts")
                return {}
            text = str(parts[0].get("text", "")).strip()
        except Exception as e:
            logger.error(f"Gemini response parse failed: {e}")
            return {}

        if not text:
            logger.warning("Gemini returned empty response text")
            return {}

        return OpenAIChatProvider._parse_json_from_text(text)


class OllamaProvider(LLMProvider):
    """Ollama provider for local models (no API cost)."""

    def __init__(
        self,
        model: str,
        host: Optional[str] = None,
        timeout_s: float = 3.0,
    ):
        self.model = model
        self.host = (host or os.getenv("OLLAMA_HOST", "http://localhost:11434")).rstrip("/")
        self.timeout_s = timeout_s

    def complete_json(self, prompt: str) -> dict:
        if not self.model:
            logger.warning("Ollama model not set; verify_pair will fail")
            return {}

        url = f"{self.host}/api/generate"
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "format": "json",
        }

        try:
            resp = requests.post(url, json=payload, timeout=self.timeout_s)
            resp.raise_for_status()
            data = resp.json()
        except TimeoutError:
            logger.warning("Ollama request timed out")
            raise TimeoutError("Ollama request timeout") from None
        except Exception as e:
            logger.error(f"Ollama request failed: {e}")
            return {}

        text = str(data.get("response", "")).strip()
        if not text:
            logger.warning("Ollama returned empty response")
            return {}

        return OpenAIChatProvider._parse_json_from_text(text)


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

    @staticmethod
    def _normalize_label(label: str) -> str:
        return str(label or "").strip().lower()

    def _extract_prices(self, market: Market) -> Dict[str, Optional[float]]:
        """Extract best bid/ask (or fallback to mid) for YES/NO outcomes."""
        best_bid = getattr(market, "best_bid", {}) or {}
        best_ask = getattr(market, "best_ask", {}) or {}
        prices: Dict[str, Optional[float]] = {
            "yes_bid": None,
            "yes_ask": None,
            "no_bid": None,
            "no_ask": None,
            "yes_mid": None,
            "no_mid": None,
            "yes_liquidity": None,
            "no_liquidity": None,
        }

        for outcome in market.outcomes or []:
            label = self._normalize_label(outcome.label)
            if label not in ("yes", "no"):
                continue
            bid = best_bid.get(label)
            ask = best_ask.get(label)
            mid = float(outcome.price) if outcome.price is not None else None
            prices[f"{label}_bid"] = bid if bid is not None else mid
            prices[f"{label}_ask"] = ask if ask is not None else mid
            prices[f"{label}_mid"] = mid
            prices[f"{label}_liquidity"] = float(outcome.liquidity or 0.0)

        if prices["yes_liquidity"] in (None, 0.0) or prices["no_liquidity"] in (None, 0.0):
            per_outcome = float(getattr(market, "liquidity", 0.0) or 0.0)
            if per_outcome:
                per_outcome = per_outcome / max(len(market.outcomes), 1)
            if not prices["yes_liquidity"]:
                prices["yes_liquidity"] = per_outcome
            if not prices["no_liquidity"]:
                prices["no_liquidity"] = per_outcome

        return prices

    @staticmethod
    def _max_size_for_leg(price: Optional[float], liquidity: Optional[float], depth_fraction: float) -> Optional[float]:
        if price is None or price <= 0:
            return None
        if liquidity is None or liquidity <= 0:
            return None
        return (liquidity * depth_fraction) / price

    @staticmethod
    def _strictness_score(text: Optional[str]) -> int:
        if not text:
            return 0
        lowered = text.lower()
        tokens = [
            "official",
            "certified",
            "final",
            "must",
            "only",
            "excluding",
            "no later than",
            "as reported by",
            "according to",
            "government",
            "federal",
            "sec",
            "court",
            "kalshi official",
        ]
        return sum(1 for token in tokens if token in lowered)

    def _create_provider(self) -> LLMProvider:
        """Create LLM provider based on configuration."""
        if self.config.provider == "openai":
            return OpenAIChatProvider(timeout_s=self.config.timeout_s)
        elif self.config.provider == "gemini":
            return GeminiProvider(
                model=self.config.model,
                timeout_s=self.config.timeout_s,
            )
        elif self.config.provider == "ollama":
            return OllamaProvider(
                model=self.config.model,
                timeout_s=self.config.timeout_s,
            )
        else:
            return MockLLMProvider(timeout_s=self.config.timeout_s)

    def _cache_key(self, market_a: Market, market_b: Market) -> str:
        """
        Generate stable cache key.

        Order-invariant: pair (a, b) and (b, a) have same key.
        """
        def _sig(market: Market) -> str:
            return "|".join(
                [
                    str(market.id),
                    str(market.question or ""),
                    str(market.resolution_source or ""),
                    str(market.description or ""),
                ]
            )

        pair = sorted([_sig(market_a), _sig(market_b)])
        content = f"{pair[0]}|{pair[1]}|{PROMPT_VERSION}|{self.config.model}"
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

    def classify_market(self, market: Market) -> str:
        """
        Classify a market into a high-level category using the LLM.
        
        Categories: Politics, Economics, Crypto, Sports, Science, Other.
        """
        if not self.config.enabled:
            return "Uncategorized"

        # Simple cache for classification (in-memory for now, could be persisted)
        if not hasattr(self, "_category_cache"):
            self._category_cache = {}
        
        if market.id in self._category_cache:
            return self._category_cache[market.id]

        prompt = (
            f"Classify this prediction market question into exactly one of these categories: "
            f"Politics, Economics, Crypto, Sports, Science, Other.\n\n"
            f"Question: {market.question}\n"
            f"Description: {market.description or ''}\n\n"
            f"Return ONLY the category name (e.g., 'Politics'). Do not add any other text."
        )

        try:
            # Use the provider directly to get raw text, not JSON
            # We temporarily bypass complete_json to just get the category string
            # But our providers are designed for JSON. Let's ask for JSON to be safe/consistent.
            json_prompt = (
                f"{prompt}\n\n"
                f"Respond with JSON: {{ \"category\": \"<CategoryName>\" }}"
            )
            response = self.provider.complete_json(json_prompt)
            category = response.get("category", "Uncategorized")
            
            # Normalize
            valid = {"Politics", "Economics", "Crypto", "Sports", "Science", "Other"}
            if category not in valid:
                # Fuzzy match or fallback
                for v in valid:
                    if v.lower() in category.lower():
                        category = v
                        break
                else:
                    category = "Other"
            
            self._category_cache[market.id] = category
            return category
            
        except Exception as e:
            logger.warning(f"Classification failed for {market.id}: {e}")
            return "Uncategorized"

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

        if not response_json:
            logger.warning(f"Empty verification response for markets {market_a.id}, {market_b.id}")
            return VerificationResult(
                same_event=True if self.config.fail_mode == "fail_open" else False,
                confidence=0.0,
                reason="Verification failed: API Error or Empty Response",
            )

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

    def evaluate_arbitrage_cases(
        self,
        kalshi_market: Market,
        poly_market: Market,
        cost_bps: float,
        depth_fraction: float,
    ) -> List[ArbitrageCaseResult]:
        """
        Evaluate locked/quasi-locked arbitrage cases for a matched market pair.

        Uses best bid/ask (or mid fallback) and applies per-leg costs.
        """
        k_prices = self._extract_prices(kalshi_market)
        p_prices = self._extract_prices(poly_market)
        fee_rate = max(cost_bps, 0.0) / 10_000.0

        results: List[ArbitrageCaseResult] = []

        def add_case(
            case_name: str,
            kalshi_action: str,
            polymarket_action: str,
            prices_used: Dict[str, Any],
            edge_gross: float,
            edge_net: float,
            max_size: Optional[float],
            guaranteed: bool,
            reason: str,
        ) -> None:
            if edge_net <= 0 or edge_gross <= 0:
                return
            if max_size is None or max_size <= 0:
                return
            results.append(
                ArbitrageCaseResult(
                    case_name=case_name,
                    kalshi_action=kalshi_action,
                    polymarket_action=polymarket_action,
                    prices_used=prices_used,
                    edge_gross=edge_gross,
                    edge_net=edge_net,
                    max_size=max_size,
                    guaranteed=guaranteed,
                    reason=reason,
                )
            )

        # Case 1: YES overpriced on Kalshi
        k_yes_bid = k_prices.get("yes_bid")
        p_yes_ask = p_prices.get("yes_ask")
        if k_yes_bid is not None and p_yes_ask is not None:
            gross_edge = k_yes_bid - p_yes_ask
            net_edge = k_yes_bid * (1 - fee_rate) - p_yes_ask * (1 + fee_rate)
            max_size = min(
                filter(
                    None,
                    [
                        self._max_size_for_leg(
                            k_yes_bid, k_prices.get("yes_liquidity"), depth_fraction
                        ),
                        self._max_size_for_leg(
                            p_yes_ask, p_prices.get("yes_liquidity"), depth_fraction
                        ),
                    ],
                ),
                default=None,
            )
            add_case(
                "YES overpriced on Kalshi",
                "SHORT YES",
                "BUY YES",
                {
                    "kalshi_yes_bid": k_yes_bid,
                    "polymarket_yes_ask": p_yes_ask,
                    "cost_bps": cost_bps,
                },
                gross_edge,
                net_edge,
                max_size,
                True,
                "Kalshi YES bid exceeds Polymarket YES ask after costs.",
            )

        # Case 2: NO overpriced on Kalshi
        k_no_bid = k_prices.get("no_bid")
        p_no_ask = p_prices.get("no_ask")
        if k_no_bid is not None and p_no_ask is not None:
            gross_edge = k_no_bid - p_no_ask
            net_edge = k_no_bid * (1 - fee_rate) - p_no_ask * (1 + fee_rate)
            max_size = min(
                filter(
                    None,
                    [
                        self._max_size_for_leg(
                            k_no_bid, k_prices.get("no_liquidity"), depth_fraction
                        ),
                        self._max_size_for_leg(
                            p_no_ask, p_prices.get("no_liquidity"), depth_fraction
                        ),
                    ],
                ),
                default=None,
            )
            add_case(
                "NO overpriced on Kalshi",
                "SHORT NO",
                "BUY NO",
                {
                    "kalshi_no_bid": k_no_bid,
                    "polymarket_no_ask": p_no_ask,
                    "cost_bps": cost_bps,
                },
                gross_edge,
                net_edge,
                max_size,
                True,
                "Kalshi NO bid exceeds Polymarket NO ask after costs.",
            )

        # Case 3: Cross complement (YES + NO < 1)
        k_yes_ask = k_prices.get("yes_ask")
        p_no_ask = p_prices.get("no_ask")
        if k_yes_ask is not None and p_no_ask is not None:
            gross_cost = k_yes_ask + p_no_ask
            gross_edge = 1.0 - gross_cost
            net_cost = k_yes_ask * (1 + fee_rate) + p_no_ask * (1 + fee_rate)
            net_edge = 1.0 - net_cost
            max_size = min(
                filter(
                    None,
                    [
                        self._max_size_for_leg(
                            k_yes_ask, k_prices.get("yes_liquidity"), depth_fraction
                        ),
                        self._max_size_for_leg(
                            p_no_ask, p_prices.get("no_liquidity"), depth_fraction
                        ),
                    ],
                ),
                default=None,
            )
            add_case(
                "Cross complement (YES + NO < 1)",
                "BUY YES",
                "BUY NO",
                {
                    "kalshi_yes_ask": k_yes_ask,
                    "polymarket_no_ask": p_no_ask,
                    "cost_bps": cost_bps,
                },
                gross_edge,
                net_edge,
                max_size,
                True,
                "YES on Kalshi plus NO on Polymarket costs less than 1 after fees.",
            )

        # Case 4: Synthetic YES (equivalent complement)
        k_no_ask = k_prices.get("no_ask")
        p_yes_ask = p_prices.get("yes_ask")
        if k_no_ask is not None and p_yes_ask is not None:
            gross_cost = k_no_ask + p_yes_ask
            gross_edge = 1.0 - gross_cost
            net_cost = k_no_ask * (1 + fee_rate) + p_yes_ask * (1 + fee_rate)
            net_edge = 1.0 - net_cost
            max_size = min(
                filter(
                    None,
                    [
                        self._max_size_for_leg(
                            k_no_ask, k_prices.get("no_liquidity"), depth_fraction
                        ),
                        self._max_size_for_leg(
                            p_yes_ask, p_prices.get("yes_liquidity"), depth_fraction
                        ),
                    ],
                ),
                default=None,
            )
            add_case(
                "Synthetic YES (equivalent complement)",
                "BUY NO",
                "BUY YES",
                {
                    "kalshi_no_ask": k_no_ask,
                    "polymarket_yes_ask": p_yes_ask,
                    "cost_bps": cost_bps,
                },
                gross_edge,
                net_edge,
                max_size,
                True,
                "NO on Kalshi plus YES on Polymarket costs less than 1 after fees.",
            )

        # Case 5: Synthetic NO
        if k_yes_ask is not None and p_no_ask is not None:
            gross_cost = k_yes_ask + p_no_ask
            gross_edge = 1.0 - gross_cost
            net_cost = k_yes_ask * (1 + fee_rate) + p_no_ask * (1 + fee_rate)
            net_edge = 1.0 - net_cost
            max_size = min(
                filter(
                    None,
                    [
                        self._max_size_for_leg(
                            k_yes_ask, k_prices.get("yes_liquidity"), depth_fraction
                        ),
                        self._max_size_for_leg(
                            p_no_ask, p_prices.get("no_liquidity"), depth_fraction
                        ),
                    ],
                ),
                default=None,
            )
            add_case(
                "Synthetic NO",
                "BUY YES",
                "BUY NO",
                {
                    "kalshi_yes_ask": k_yes_ask,
                    "polymarket_no_ask": p_no_ask,
                    "cost_bps": cost_bps,
                },
                gross_edge,
                net_edge,
                max_size,
                True,
                "YES on Kalshi plus NO on Polymarket costs less than 1 after fees.",
            )

        # Case 6: Time-ladder (same event, different deadlines)
        k_end = getattr(kalshi_market, "end_date", None)
        p_end = getattr(poly_market, "end_date", None)
        k_yes_mid = k_prices.get("yes_mid")
        p_yes_mid = p_prices.get("yes_mid")
        if (
            k_end
            and p_end
            and k_end < p_end
            and k_yes_mid is not None
            and p_yes_mid is not None
            and k_yes_mid > p_yes_mid
            and k_yes_bid is not None
            and p_yes_ask is not None
        ):
            gross_edge = k_yes_bid - p_yes_ask
            net_edge = k_yes_bid * (1 - fee_rate) - p_yes_ask * (1 + fee_rate)
            max_size = min(
                filter(
                    None,
                    [
                        self._max_size_for_leg(
                            k_yes_bid, k_prices.get("yes_liquidity"), depth_fraction
                        ),
                        self._max_size_for_leg(
                            p_yes_ask, p_prices.get("yes_liquidity"), depth_fraction
                        ),
                    ],
                ),
                default=None,
            )
            resolution_match = (
                (kalshi_market.resolution_source or "").strip().lower()
                == (poly_market.resolution_source or "").strip().lower()
            )
            description_match = (
                (kalshi_market.description or "").strip().lower()
                == (poly_market.description or "").strip().lower()
            )
            if resolution_match or description_match:
                add_case(
                    "Time-ladder (same event, different deadlines)",
                    "SHORT YES (earlier deadline)",
                    "BUY YES (later deadline)",
                    {
                        "kalshi_yes_bid": k_yes_bid,
                        "polymarket_yes_ask": p_yes_ask,
                        "kalshi_end": k_end.isoformat(),
                        "polymarket_end": p_end.isoformat(),
                        "cost_bps": cost_bps,
                    },
                    gross_edge,
                    net_edge,
                    max_size,
                    True,
                    "Earlier deadline priced above later deadline with matching resolution rules.",
                )

        # Case 7: Resolution mismatch (risky)
        k_strictness = self._strictness_score(kalshi_market.description) + self._strictness_score(
            kalshi_market.resolution_source
        )
        p_strictness = self._strictness_score(poly_market.description) + self._strictness_score(
            poly_market.resolution_source
        )
        if (
            k_strictness > p_strictness
            and k_yes_bid is not None
            and p_yes_ask is not None
        ):
            gross_edge = k_yes_bid - p_yes_ask
            net_edge = k_yes_bid * (1 - fee_rate) - p_yes_ask * (1 + fee_rate)
            max_size = min(
                filter(
                    None,
                    [
                        self._max_size_for_leg(
                            k_yes_bid, k_prices.get("yes_liquidity"), depth_fraction
                        ),
                        self._max_size_for_leg(
                            p_yes_ask, p_prices.get("yes_liquidity"), depth_fraction
                        ),
                    ],
                ),
                default=None,
            )
            add_case(
                "Resolution mismatch",
                "SHORT YES (stricter rules)",
                "BUY YES (looser rules)",
                {
                    "kalshi_yes_bid": k_yes_bid,
                    "polymarket_yes_ask": p_yes_ask,
                    "kalshi_strictness": k_strictness,
                    "polymarket_strictness": p_strictness,
                    "cost_bps": cost_bps,
                },
                gross_edge,
                net_edge,
                max_size,
                False,
                "Kalshi resolution rules appear stricter than Polymarket (risky).",
            )

        return results

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
