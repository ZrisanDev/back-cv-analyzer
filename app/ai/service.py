"""AI Analyzer Service — orchestrates providers with fallback and retry logic.

Fallback chain:  Gemini → Groq → Cerebras → Ollama
- Each provider gets up to ``ai_max_retries`` attempts with exponential backoff.
- Provider health is tracked (successes / failures) for observability.
- When all providers are exhausted, a ``RuntimeError`` is raised.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

from app.ai.providers.base import AIProvider, ProviderError
from app.ai.providers.cerebras import CerebrasProvider
from app.ai.providers.gemini import GeminiProvider
from app.ai.providers.groq import GroqProvider
from app.ai.providers.ollama import OllamaProvider
from app.ai.schemas import AnalysisResponse
from app.shared.config import settings

logger = logging.getLogger(__name__)

# ── Health tracking ────────────────────────────────────────────────────


@dataclass
class ProviderHealth:
    """Tracks success/failure counts for a single provider."""

    name: str
    successes: int = 0
    failures: int = 0

    @property
    def total_requests(self) -> int:
        return self.successes + self.failures

    @property
    def success_rate(self) -> float:
        return self.successes / self.total_requests if self.total_requests > 0 else 0.0


# ── Retry configuration ────────────────────────────────────────────────


@dataclass
class RetryConfig:
    """Controls retry behaviour when a provider call fails."""

    max_retries: int = 2
    base_delay_seconds: float = 1.0
    max_delay_seconds: float = 10.0
    backoff_factor: float = 2.0


# ── Service ────────────────────────────────────────────────────────────


class AIAnalyzerService:
    """Facade that routes CV analysis requests through providers with fallback.

    Usage::

        service = AIAnalyzerService()
        result = await service.analyze_cv(cv_text, job_description)
        print(result.compatibility_score)
    """

    def __init__(
        self,
        providers: list[AIProvider] | None = None,
        retry_config: RetryConfig | None = None,
    ) -> None:
        # Ordered by model quality: Gemini (if quota) → Groq (70b) → Cerebras (8b) → Ollama (local)
        # NOTE: If you see 'cerebras' being tried before 'groq', code is up to date
        self._providers = providers or [
            GeminiProvider(),
            GroqProvider(),
            CerebrasProvider(),
            OllamaProvider(),
        ]
        self._retry = retry_config or RetryConfig(
            max_retries=settings.ai_max_retries,
        )
        self._health: dict[str, ProviderHealth] = {
            p.name: ProviderHealth(name=p.name) for p in self._providers
        }

    # ── Public API ────────────────────────────────────────

    @property
    def provider_names(self) -> list[str]:
        """Ordered list of registered provider names."""
        return [p.name for p in self._providers]

    @property
    def health(self) -> dict[str, ProviderHealth]:
        """Snapshot of current provider health metrics."""
        return dict(self._health)

    async def analyze_cv(self, cv_text: str, job_description: str) -> AnalysisResponse:
        """Run CV analysis with fallback chain and retry logic.

        Tries each provider in order.  On failure the provider is retried
        up to ``max_retries`` times with exponential backoff before falling
        through to the next provider.

        Raises:
            RuntimeError: When every provider has been exhausted.
        """
        logger.info("Starting CV analysis with fallback chain: %s", self.provider_names)
        logger.info("CV text length: %d chars", len(cv_text))
        logger.info("Job description length: %d chars", len(job_description))
        last_error: Exception | None = None

        for idx, provider in enumerate(self._providers):
            if not provider.is_available:
                logger.info(
                    "⏭️  Skipping %s (%d/%d) — provider is not configured / available",
                    provider.name,
                    idx + 1,
                    len(self._providers),
                )
                continue

            logger.info(
                "🔄 Trying %s (%d/%d in fallback chain)",
                provider.name,
                idx + 1,
                len(self._providers),
            )
            result = await self._try_provider(provider, cv_text, job_description)
            if result is not None:
                logger.info(
                    "✅ %s succeeded! Analysis completed with score %d",
                    provider.name,
                    result.compatibility_score,
                )
                return result
            # _try_provider updates health; grab last error for final message
            last_error = ProviderError(
                provider.name,
                f"All retries exhausted for {provider.name}",
            )
            logger.warning(
                "⚠️  %s failed after all retries, falling back to next provider",
                provider.name,
            )

        # All providers exhausted
        available_providers = [p.name for p in self._providers if p.is_available]
        logger.error("All providers exhausted. Available: %s", available_providers)
        raise RuntimeError(
            f"❌ All AI providers failed. "
            f"Tried: {available_providers}. "
            f"Last error: {last_error}"
        )

    # ── Internal ──────────────────────────────────────────

    async def _try_provider(
        self,
        provider: AIProvider,
        cv_text: str,
        job_description: str,
    ) -> AnalysisResponse | None:
        """Attempt the provider with retries.  Returns None if exhausted."""
        for attempt in range(self._retry.max_retries + 1):
            try:
                logger.info(
                    "Trying provider=%s attempt=%d/%d",
                    provider.name,
                    attempt + 1,
                    self._retry.max_retries + 1,
                )
                result = await provider.analyze_cv(cv_text, job_description)
                self._health[provider.name].successes += 1
                logger.info(
                    "Provider %s succeeded on attempt %d", provider.name, attempt + 1
                )
                return result

            except ProviderError as exc:
                self._health[provider.name].failures += 1
                logger.warning(
                    "Provider %s failed on attempt %d: %s",
                    provider.name,
                    attempt + 1,
                    exc,
                )

                if attempt < self._retry.max_retries:
                    delay = min(
                        self._retry.base_delay_seconds
                        * (self._retry.backoff_factor**attempt),
                        self._retry.max_delay_seconds,
                    )
                    logger.info("Retrying %s in %.1fs …", provider.name, delay)
                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        "Provider %s exhausted all %d retries — moving to next provider",
                        provider.name,
                        self._retry.max_retries + 1,
                    )
                    return None

        return None  # should not reach here, but keep mypy happy
