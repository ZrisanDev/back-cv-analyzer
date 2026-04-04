"""Stats routes: summary, score evolution, and missing keywords."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.shared.database import get_db
from app.stats.schemas import MissingKeywordStats, ScoreEvolution, StatsSummary
from app.stats.services import (
    get_missing_keywords,
    get_score_evolution,
    get_summary_stats,
)

router = APIRouter(prefix="/stats", tags=["Stats"])


# ── Overall summary ────────────────────────────────────────────


@router.get(
    "/summary",
    response_model=StatsSummary,
    summary="Get overall analysis statistics",
)
async def stats_summary(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StatsSummary:
    """Return overall statistics for the authenticated user:

    - Total number of analyses
    - Average compatibility score (across completed analyses)
    - Breakdown by status (completed, failed, pending/processing)
    """
    return await get_summary_stats(db, user_id=current_user.id)


# ── Score evolution over time ──────────────────────────────────


@router.get(
    "/evolution",
    response_model=ScoreEvolution,
    summary="Get compatibility score evolution over time",
)
async def score_evolution(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ScoreEvolution:
    """Return the user's average compatibility score grouped by month.

    Only includes completed analyses with a non-null score.
    Data points are ordered chronologically (oldest first).
    """
    return await get_score_evolution(db, user_id=current_user.id)


# ── Top missing keywords ───────────────────────────────────────


@router.get(
    "/missing-keywords",
    response_model=MissingKeywordStats,
    summary="Get top missing keywords across analyses",
)
async def missing_keywords(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MissingKeywordStats:
    """Aggregate the most frequently missing keywords across all of the
    user's completed analyses.

    Each keyword includes:
    - ``missing_count``: how many analyses flagged it as missing
    - ``percentage``: percentage of total completed analyses missing it

    Results are sorted by ``missing_count`` descending.
    """
    return await get_missing_keywords(db, user_id=current_user.id)
