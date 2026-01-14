from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

from predarb.models import Market
from predarb.llm_verifier import (
    LLMProvider,
    OpenAIChatProvider,
    GeminiProvider,
    OllamaProvider,
)

logger = logging.getLogger(__name__)

PROMPT_VERSION = "strict_ab_v1"


@dataclass
class StrictABLLMResult:
    passed: bool
    confidence: float
    reason: str


class StrictABLLMVerifier:
    def __init__(self, provider: LLMProvider, cache_path: str, daily_limit: int) -> None:
        self.provider = provider
        self.cache_path = Path(cache_path)
        self.daily_limit = daily_limit
        self._cache: Dict[str, StrictABLLMResult] = {}
        self._calls_today = 0
        self._cache_date = self._utc_date()
        self._load_cache()

    @staticmethod
    def _utc_date() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def _load_cache(self) -> None:
        if not self.cache_path.exists():
            return
        try:
            data = json.loads(self.cache_path.read_text())
            meta = data.get("meta", {}) if isinstance(data, dict) else {}
            pairs = data.get("pairs", {}) if isinstance(data, dict) else {}
            self._cache_date = str(meta.get("date", self._utc_date()))
            self._calls_today = int(meta.get("count", 0))
            for key, entry in pairs.items():
                self._cache[key] = StrictABLLMResult(
                    passed=bool(entry.get("pass", False)),
                    confidence=float(entry.get("confidence", 0.0)),
                    reason=str(entry.get("reason", "")),
                )
        except Exception as exc:
            logger.warning("Failed to load strict A+B LLM cache: %s", exc)

    def _save_cache(self) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "meta": {"date": self._cache_date, "count": self._calls_today},
            "pairs": {
                key: {
                    "pass": result.passed,
                    "confidence": result.confidence,
                    "reason": result.reason,
                }
                for key, result in self._cache.items()
            },
        }
        tmp_path = self.cache_path.with_suffix(".tmp")
        tmp_path.write_text(json.dumps(data, indent=2))
        tmp_path.replace(self.cache_path)

    def _rotate_daily_counter(self) -> None:
        today = self._utc_date()
        if today != self._cache_date:
            self._cache_date = today
            self._calls_today = 0

    def _build_prompt(self, market_a: Market, market_b: Market) -> str:
        return (
            "You are verifying whether two prediction markets resolve on the same real-world event "
            "with the same outcome meaning.\n"
            "Respond with strict JSON only: {\"pass\": true|false, \"confidence\": 0.0-1.0, \"reason\": \"short text\"}.\n\n"
            f"Market A: {market_a.question}\n"
            f"Resolution A: {market_a.description or market_a.resolution_source or 'n/a'}\n\n"
            f"Market B: {market_b.question}\n"
            f"Resolution B: {market_b.description or market_b.resolution_source or 'n/a'}\n"
        )

    def _parse_response(self, raw: object) -> StrictABLLMResult:
        if not isinstance(raw, dict):
            raise ValueError("LLM response is not a JSON object")
        passed = bool(raw.get("pass", False))
        confidence = float(raw.get("confidence", 0.0))
        reason = str(raw.get("reason", ""))
        if confidence < 0.0 or confidence > 1.0:
            raise ValueError("confidence out of range")
        return StrictABLLMResult(passed=passed, confidence=confidence, reason=reason)

    def verify_pair(self, pair_key: str, market_a: Market, market_b: Market) -> Optional[StrictABLLMResult]:
        self._rotate_daily_counter()
        if pair_key in self._cache:
            return self._cache[pair_key]
        if self._calls_today >= self.daily_limit:
            return None

        prompt = self._build_prompt(market_a, market_b)
        try:
            raw = self.provider.complete_json(prompt)
            result = self._parse_response(raw)
        except Exception as exc:
            logger.warning("Strict A+B LLM verification failed: %s", exc)
            result = StrictABLLMResult(passed=False, confidence=0.0, reason="llm_error")

        self._calls_today += 1
        self._cache[pair_key] = result
        self._save_cache()
        return result


def build_llm_provider(provider: str, model: str, timeout_s: float) -> LLMProvider:
    name = (provider or "mock").strip().lower()
    if name == "openai":
        return OpenAIChatProvider(model=model, timeout_s=timeout_s)
    if name == "gemini":
        return GeminiProvider(model=model, timeout_s=timeout_s)
    if name == "ollama":
        return OllamaProvider(model=model, timeout_s=timeout_s)
    return StrictABMockProvider(timeout_s=timeout_s)


class StrictABMockProvider(LLMProvider):
    """Mock provider that returns strict A+B schema without network."""

    def __init__(self, timeout_s: float = 0.1) -> None:
        self.timeout_s = timeout_s

    def complete_json(self, prompt: str) -> dict:
        return {"pass": True, "confidence": 0.75, "reason": "mock_pass"}
