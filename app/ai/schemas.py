"""Pydantic schemas for AI analysis response."""

from __future__ import annotations

from pydantic import BaseModel, Field


class LearningPath(BaseModel):
    """Structured learning path for a missing skill or technology."""

    keyword: str = Field(..., description="The missing keyword or technology")
    what: str = Field(..., description="What this technology/skill is")
    why: str = Field(..., description="Why it is important for this specific role")
    how: str = Field(..., description="Recommended steps to learn or practice it")
    resources: list[str] = Field(
        default_factory=list,
        description="Recommended resources to learn this skill",
    )


class AnalysisResponse(BaseModel):
    """Standardized response from CV analysis across all AI providers."""

    compatibility_score: int = Field(
        ..., ge=0, le=100, description="Compatibility score from 0 to 100"
    )
    present_keywords: list[str] = Field(
        default_factory=list,
        description="Keywords from the job description found in the CV",
    )
    missing_keywords: list[str] = Field(
        default_factory=list,
        description="Important keywords from the job description NOT found in the CV",
    )
    strengths: list[str] = Field(
        default_factory=list,
        description="Candidate's notable strengths relevant to the role",
    )
    weaknesses: list[str] = Field(
        default_factory=list,
        description="Gaps or weaknesses that could hinder performance",
    )
    executive_summary: str = Field(
        ..., description="Executive summary of the analysis (2-3 paragraphs)"
    )
    learning_paths: list[LearningPath] = Field(
        default_factory=list,
        description="Learning path for each missing keyword",
    )
