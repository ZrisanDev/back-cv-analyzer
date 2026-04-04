"""Abstract base class (protocol) for all AI providers.

Every provider must implement the same interface so the fallback service
can swap them transparently.  This module also contains the shared system
prompt and the common JSON-parsing logic used by all providers.
"""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod

from app.ai.schemas import AnalysisResponse

logger = logging.getLogger(__name__)

# ── Shared system prompt ───────────────────────────────────────────────
SYSTEM_PROMPT = """\
You are an expert CV analyzer. Your task is to analyze a candidate's CV \
against a job description and provide a detailed compatibility report.

You MUST respond with a valid JSON object containing exactly these fields:

{
    "compatibility_score": <integer between 0 and 100>,
    "present_keywords": ["<technology found in CV>", "..."],
    "missing_keywords": ["<required technology NOT found in CV>", "..."],
    "strengths": ["<specific strength relevant to the role>", "..."],
    "weaknesses": ["<specific gap or concern>", "..."],
    "executive_summary": "<2-3 paragraph executive summary>",
    "learning_paths": [
        {
            "keyword": "<missing keyword>",
            "what": "What this technology/skill is in simple terms",
            "why": "Why it is important for this specific role based on the job description",
            "how": "Practical steps to learn or improve in this area",
            "resources": ["<specific resource recommendation>", "..."]
        }
    ]
}

STRICT RULES:
1. "compatibility_score" MUST be an integer between 0 and 100.
2. "present_keywords" and "missing_keywords" must be real technologies, tools, \
frameworks, or skills explicitly mentioned in the job description.
3. Every entry in "missing_keywords" MUST have a corresponding entry in \
"learning_paths".
4. Be specific and practical — cite concrete evidence from the CV.
5. Base your analysis ONLY on the provided CV text and job description. \
Do NOT hallucinate or assume skills not present.
6. "resources" must contain at least one concrete recommendation per learning path.
7. Respond ONLY with the JSON object. No markdown, no commentary, no preamble.
"""


# ── Provider error ─────────────────────────────────────────────────────


class ProviderError(Exception):
    """Raised when an AI provider fails to produce a valid response."""

    def __init__(
        self,
        provider_name: str,
        message: str,
        original_error: Exception | None = None,
    ) -> None:
        self.provider_name = provider_name
        self.original_error = original_error
        super().__init__(f"[{provider_name}] {message}")


# ── Abstract base ──────────────────────────────────────────────────────


class AIProvider(ABC):
    """Contract that every AI provider must satisfy."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable provider identifier (e.g. 'cerebras', 'groq')."""

    @property
    @abstractmethod
    def is_available(self) -> bool:
        """Return True when the provider is properly configured and reachable."""

    @abstractmethod
    async def analyze_cv(self, cv_text: str, job_description: str) -> AnalysisResponse:
        """Analyze a CV against a job description and return structured results.

        Args:
            cv_text: Full extracted text from the candidate's CV.
            job_description: The full text of the job description.

        Returns:
            An AnalysisResponse with score, keywords, strengths, etc.

        Raises:
            ProviderError: If the provider call or response parsing fails.
        """

    # ── Shared helpers ─────────────────────────────────────

    def _build_messages(self, cv_text: str, job_description: str) -> list[dict]:
        """Build the message payload sent to every provider."""
        return [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    "<JOB_DESCRIPTION>\n"
                    f"{job_description}\n"
                    "</JOB_DESCRIPTION>\n\n"
                    "<CANDIDATE_CV>\n"
                    f"{cv_text}\n"
                    "</CANDIDATE_CV>"
                ),
            },
        ]

    def _parse_response(self, raw: str) -> AnalysisResponse:
        """Parse raw LLM output into an AnalysisResponse.

        Handles common quirks:
        - Markdown code fences (```json … ```)
        - Leading/trailing whitespace
        - Non-JSON preamble text
        """
        cleaned = raw.strip()

        # Strip markdown code fences
        if cleaned.startswith("```"):
            lines = cleaned.split("\n", 1)
            cleaned = lines[1] if len(lines) > 1 else cleaned[3:]
            if cleaned.rstrip().endswith("```"):
                cleaned = cleaned.rstrip()[:-3]
            cleaned = cleaned.strip()

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            logger.error("Failed to parse AI response as JSON: %s", cleaned[:500])
            raise ProviderError(
                self.name,
                f"Provider returned invalid JSON: {exc}",
                original_error=exc,
            ) from exc

        try:
            return AnalysisResponse.model_validate(data)
        except Exception as exc:
            logger.error("AI response JSON does not match expected schema: %s", data)
            raise ProviderError(
                self.name,
                f"Provider response does not match expected schema: {exc}",
                original_error=exc,
            ) from exc
