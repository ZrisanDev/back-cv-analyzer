"""Ollama AI provider — calls the local Ollama REST API.

Uses ``httpx.AsyncClient`` to POST to ``{ollama_base_url}/api/chat``.
Ollama must be running locally for this provider to work.
"""

from __future__ import annotations

import logging

import httpx

from app.ai.providers.base import AIProvider, ProviderError
from app.ai.schemas import AnalysisResponse
from app.shared.config import settings

logger = logging.getLogger(__name__)

_OLLAMA_TIMEOUT = settings.ai_timeout_seconds


class OllamaProvider(AIProvider):
    """Ollama provider — runs models locally via the Ollama REST API."""

    @property
    def name(self) -> str:
        return "ollama"

    @property
    def is_available(self) -> bool:
        return bool(settings.ollama_base_url)

    async def analyze_cv(self, cv_text: str, job_description: str) -> AnalysisResponse:
        if not self.is_available:
            raise ProviderError(
                self.name,
                "Ollama provider is not available — check OLLAMA_BASE_URL",
            )

        messages = self._build_messages(cv_text, job_description)

        payload = {
            "model": settings.ollama_model,
            "messages": messages,
            "format": "json",
            "stream": False,
            "options": {
                "temperature": 0.3,
                "num_predict": 4096,
            },
        }

        try:
            async with httpx.AsyncClient(timeout=_OLLAMA_TIMEOUT) as client:
                response = await client.post(
                    f"{settings.ollama_base_url}/api/chat",
                    json=payload,
                )
                response.raise_for_status()

            body = response.json()
            raw_content = body.get("message", {}).get("content", "")
            if not raw_content:
                raise ProviderError(
                    self.name,
                    "Ollama returned empty response content",
                )

            logger.debug("Ollama raw response length: %d", len(raw_content))
            return self._parse_response(raw_content)

        except ProviderError:
            raise  # already wrapped
        except httpx.HTTPStatusError as exc:
            logger.error(
                "Ollama HTTP error %s: %s", exc.response.status_code, exc.response.text
            )
            raise ProviderError(
                self.name,
                f"Ollama returned HTTP {exc.response.status_code}",
                original_error=exc,
            ) from exc
        except httpx.RequestError as exc:
            logger.error("Ollama connection error: %s", exc)
            raise ProviderError(
                self.name,
                f"Cannot connect to Ollama at {settings.ollama_base_url}: {exc}",
                original_error=exc,
            ) from exc
        except Exception as exc:
            logger.exception("Ollama provider call failed")
            raise ProviderError(
                self.name,
                f"Ollama API call failed: {exc}",
                original_error=exc,
            ) from exc
