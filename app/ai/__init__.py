"""AI module: CV analysis powered by multiple AI providers with fallback."""

from app.ai.schemas import AnalysisResponse, LearningPath
from app.ai.service import AIAnalyzerService

__all__ = [
    "AIAnalyzerService",
    "AnalysisResponse",
    "LearningPath",
]
