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
Eres un experto analizador de CVs. Tu tarea es analizar el CV de un candidato \
contra una descripción de puesto y proporcionar un reporte de compatibilidad detallado.

Debes responder con un objeto JSON válido que contenga exactamente estos campos:

{
    "compatibility_score": <entero entre 0 y 100>,
    "present_keywords": ["<tecnología encontrada en el CV>", "..."],
    "missing_keywords": ["<tecnología requerida NO encontrada en el CV>", "..."],
    "strengths": ["<fortaleza específica relevante para el puesto>", "..."],
    "weaknesses": ["<brecha específica o preocupación>", "..."],
    "executive_summary": "<resumen ejecutivo de 2-3 párrafos>",
    "learning_paths": [
        {
            "keyword": "<palabra clave faltante>",
            "what": "Qué es esta tecnología/habilidad en términos simples",
            "why": "Por qué es importante para este rol específico basado en la descripción del puesto",
            "how": "Pasos prácticos para aprender o mejorar en esta área",
            "resources": ["<recomendación de recurso específico>", "..."]
        }
    ]
}

REGLAS ESTRICTAS:
1. "compatibility_score" DEBE ser un entero entre 0 y 100.
2. "present_keywords" y "missing_keywords" deben ser tecnologías reales, herramientas, \
frameworks o habilidades mencionadas explícitamente en la descripción del puesto.
3. Cada entrada en "missing_keywords" DEBE tener una entrada correspondiente en \
"learning_paths".
4. Sé específico y práctico — cita evidencia concreta del CV.
5. Basa tu análisis ÚNICAMENTE en el texto del CV y la descripción del puesto proporcionados. \
NO alucines ni asumas habilidades no presentes.
6. "resources" debe contener al menos una recomendación concreta por ruta de aprendizaje.
7. Responde ÚNICAMENTE con el objeto JSON. Sin markdown, sin comentarios, sin preámbulo.
8. TODA la respuesta DEBE estar en español.
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
