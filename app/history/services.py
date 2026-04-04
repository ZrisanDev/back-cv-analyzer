"""Services for the history module — query and manage user analyses."""

from __future__ import annotations

import math
import uuid

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analysis.models import Analysis, AnalysisStatus
from app.history.schemas import HistoryDetailResponse, HistoryItem


# ── Constants ──────────────────────────────────────────────────

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


def _clamp_per_page(per_page: int | None) -> int:
    """Clamp the per_page value to the allowed range."""
    if per_page is None:
        return DEFAULT_PAGE_SIZE
    return max(1, min(per_page, MAX_PAGE_SIZE))


# ── List user's analyses (paginated) ───────────────────────────


async def get_user_history(
    db: AsyncSession,
    user_id: uuid.UUID,
    page: int = 1,
    per_page: int | None = None,
) -> tuple[list[Analysis], int, int, int]:
    """Return a paginated list of the user's analyses.

    Returns:
        Tuple of (analyses, total_count, page, per_page).

    The caller is responsible for building the paginated response envelope.
    """
    effective_per_page = _clamp_per_page(per_page)
    offset = (page - 1) * effective_per_page

    # Total count
    count_stmt = (
        select(func.count())
        .select_from(Analysis)
        .where(
            Analysis.user_id == user_id,
        )
    )
    total = (await db.execute(count_stmt)).scalar() or 0

    # Paginated items, newest first
    items_stmt = (
        select(Analysis)
        .where(Analysis.user_id == user_id)
        .order_by(Analysis.created_at.desc())
        .offset(offset)
        .limit(effective_per_page)
    )
    result = await db.execute(items_stmt)
    analyses = list(result.scalars().all())

    return analyses, total, page, effective_per_page


# ── Get single analysis detail ─────────────────────────────────


async def get_analysis_detail(
    db: AsyncSession,
    analysis_id: uuid.UUID,
    user_id: uuid.UUID,
) -> Analysis:
    """Fetch a single analysis by ID, scoped to the owning user.

    Raises 404 if the analysis doesn't exist or doesn't belong to the user.
    """
    result = await db.execute(
        select(Analysis).where(
            Analysis.id == analysis_id,
            Analysis.user_id == user_id,
        ),
    )
    analysis = result.scalar_one_or_none()

    if analysis is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Analysis not found or you do not have permission to view it.",
        )

    return analysis


# ── Delete an analysis ─────────────────────────────────────────


async def delete_analysis(
    db: AsyncSession,
    analysis_id: uuid.UUID,
    user_id: uuid.UUID,
) -> Analysis:
    """Delete an analysis owned by the authenticated user.

    Raises 404 if the analysis doesn't exist or doesn't belong to the user.
    Returns the deleted analysis for confirmation.
    """
    analysis = await get_analysis_detail(db, analysis_id, user_id)

    await db.delete(analysis)

    return analysis
