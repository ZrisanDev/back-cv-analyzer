"""Cerebras AI provider — wraps cerebras-cloud-sdk.

Uses the synchronous ``Cerebras`` client executed via
``asyncio.to_thread`` so we don't block the event loop.
"""

from __future__ import annotations

import asyncio
import logging

from cerebras.cloud.sdk import Cerebras

from app.ai.providers.base import AIProvider, ProviderError
from app.ai.schemas import AnalysisResponse
from app.shared.config import settings

logger = logging.getLogger(__name__)


class CerebrasProvider(AIProvider):
    """Cerebras inference provider (llama models on Cerebras hardware)."""

    def __init__(self) -> None:
        self._client: Cerebras | None = None
        if settings.cerebras_api_key:
            self._client = Cerebras(api_key=settings.cerebras_api_key)

    # ── Provider contract ─────────────────────────────────

    @property
    def name(self) -> str:
        return "cerebras"

    @property
    def is_available(self) -> bool:
        return self._client is not None and bool(settings.cerebras_api_key)

    async def analyze_cv(self, cv_text: str, job_description: str) -> AnalysisResponse:
        if not self.is_available:
            raise ProviderError(
                self.name,
                "Cerebras provider is not available — check CEREBRAS_API_KEY",
            )

        logger.info("Cerebras using model: %s", settings.cerebras_model)
        messages = self._build_messages(cv_text, job_description)

        try:
            response = await asyncio.to_thread(
                self._client.chat.completions.create,  # type: ignore[union-attr]
                model=settings.cerebras_model,
                messages=messages,
                response_format={"type": "json_object"},
                temperature=0.3,
                max_tokens=4096,
            )
            raw_content = response.choices[0].message.content or ""
            logger.debug("Cerebras raw response length: %d", len(raw_content))
            return self._parse_response(raw_content)

        except ProviderError:
            raise  # already wrapped
        except Exception as exc:
            logger.exception("Cerebras provider call failed")
            raise ProviderError(
                self.name,
                f"Cerebras API call failed: {exc}",
                original_error=exc,
            ) from exc
