"""Pydantic schemas for the stats module."""

from __future__ import annotations

from pydantic import BaseModel, Field


# ── Summary statistics ─────────────────────────────────────────


class StatsSummary(BaseModel):
    """Overall analysis statistics for the authenticated user."""

    total_analyses: int = Field(description="Total number of analyses (all statuses)")
    avg_compatibility_score: float | None = Field(
        None,
        description="Average compatibility score across completed analyses",
    )
    completed: int = Field(description="Number of completed analyses")
    failed: int = Field(description="Number of failed analyses")
    pending: int = Field(description="Number of pending + processing analyses")


# ── Score evolution over time ──────────────────────────────────


class ScoreEvolutionPoint(BaseModel):
    """Single data point in the score evolution timeline."""

    month: str = Field(
        description="Month in YYYY-MM format",
        examples=["2024-01"],
    )
    avg_score: float = Field(description="Average compatibility score for that month")
    count: int = Field(description="Number of completed analyses that month")


class ScoreEvolution(BaseModel):
    """Score evolution timeline grouped by month."""

    data_points: list[ScoreEvolutionPoint]


# ── Missing keywords ───────────────────────────────────────────


class MissingKeywordItem(BaseModel):
    """A single missing keyword aggregated across all completed analyses."""

    keyword: str = Field(description="The keyword that was missing")
    missing_count: int = Field(
        description="How many analyses flagged this keyword as missing"
    )
    percentage: float = Field(
        description="Percentage of total completed analyses missing this keyword",
    )


class MissingKeywordStats(BaseModel):
    """Top missing keywords aggregated across completed analyses."""

    keywords: list[MissingKeywordItem]
