"""Google Gemini AI provider — uses the free tier for cost-effective analysis."""

from __future__ import annotations

import json
import logging

from google import genai
from google.genai import types

from app.ai.providers.base import AIProvider, ProviderError
from app.ai.schemas import AnalysisResponse
from app.shared.config import settings

logger = logging.getLogger(__name__)


class GeminiProvider(AIProvider):
    """Google Gemini AI provider using the new genai SDK.

    Uses the free tier (gemini-2.0-flash) for cost-effective CV analysis.
    """

    @property
    def name(self) -> str:
        return "gemini"

    @property
    def is_available(self) -> bool:
        return bool(settings.gemini_api_key)

    async def analyze_cv(
        self,
        cv_text: str,
        job_description: str,
    ) -> AnalysisResponse:
        """Analyze a CV against a job description using Gemini."""
        if not self.is_available:
            raise ProviderError(self.name, "API key not configured")

        try:
            client = genai.Client(api_key=settings.gemini_api_key)

            messages = self._build_messages(cv_text, job_description)

            response = await client.aio.models.generate_content(
                model=settings.gemini_model,
                contents="\n\n".join(m["content"] for m in messages),
                config=types.GenerateContentConfig(
                    temperature=0.3,
                    response_mime_type="application/json",
                ),
            )

            if not response.text:
                raise ProviderError(self.name, "Empty response from Gemini")

            return self._parse_response(response.text)

        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError(
                self.name,
                f"Unexpected error: {exc}",
                original_error=exc,
            ) from exc
