"""Groq AI provider — wraps the groq Python SDK.

Uses the native ``AsyncGroq`` client for non-blocking inference.
"""

from __future__ import annotations

import logging

from groq import AsyncGroq

from app.ai.providers.base import AIProvider, ProviderError
from app.ai.schemas import AnalysisResponse
from app.shared.config import settings

logger = logging.getLogger(__name__)


class GroqProvider(AIProvider):
    """Groq inference provider (LPU-accelerated llama models)."""

    def __init__(self) -> None:
        self._client: AsyncGroq | None = None
        if settings.groq_api_key:
            self._client = AsyncGroq(api_key=settings.groq_api_key)

    # ── Provider contract ─────────────────────────────────

    @property
    def name(self) -> str:
        return "groq"

    @property
    def is_available(self) -> bool:
        return self._client is not None and bool(settings.groq_api_key)

    async def analyze_cv(self, cv_text: str, job_description: str) -> AnalysisResponse:
        if not self.is_available:
            raise ProviderError(
                self.name,
                "Groq provider is not available — check GROQ_API_KEY",
            )

        logger.info("Groq using model: %s", settings.groq_model)
        messages = self._build_messages(cv_text, job_description)

        try:
            response = await self._client.chat.completions.create(  # type: ignore[union-attr]
                model=settings.groq_model,
                messages=messages,
                response_format={"type": "json_object"},
                temperature=0.3,
                max_tokens=4096,
            )
            raw_content = response.choices[0].message.content or ""
            logger.debug("Groq raw response length: %d", len(raw_content))
            return self._parse_response(raw_content)

        except ProviderError:
            raise  # already wrapped
        except Exception as exc:
            logger.exception("Groq provider call failed")
            raise ProviderError(
                self.name,
                f"Groq API call failed: {exc}",
                original_error=exc,
            ) from exc
