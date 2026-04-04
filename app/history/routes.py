"""History routes: list, detail, and delete user analyses."""

from __future__ import annotations

import math
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.analysis.models import Analysis
from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.history.schemas import (
    HistoryDeleteResponse,
    HistoryDetailResponse,
    HistoryItem,
    PaginatedResponse,
)
from app.history.services import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    delete_analysis,
    get_analysis_detail,
    get_user_history,
)
from app.shared.database import get_db

router = APIRouter(prefix="/history", tags=["History"])


# ── List user's analyses (paginated) ───────────────────────────


@router.get(
    "",
    response_model=PaginatedResponse[HistoryItem],
    summary="List user's analyses with pagination",
)
async def list_history(
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    per_page: int = Query(
        DEFAULT_PAGE_SIZE,
        ge=1,
        le=MAX_PAGE_SIZE,
        description=f"Items per page (1–{MAX_PAGE_SIZE})",
    ),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PaginatedResponse[HistoryItem]:
    """Return a paginated list of the authenticated user's analyses.

    Results are sorted by ``created_at`` descending (newest first).
    Large text fields (``cv_text``, ``job_description``, ``analysis_result``)
    are excluded for performance.
    """
    analyses, total, effective_page, effective_per_page = await get_user_history(
        db,
        user_id=current_user.id,
        page=page,
        per_page=per_page,
    )

    items = [HistoryItem.model_validate(a, from_attributes=True) for a in analyses]
    total_pages = math.ceil(total / effective_per_page) if effective_per_page > 0 else 0

    return PaginatedResponse(
        items=items,
        total=total,
        page=effective_page,
        per_page=effective_per_page,
        pages=total_pages,
    )


# ── Get single analysis detail ─────────────────────────────────


@router.get(
    "/{analysis_id}",
    response_model=HistoryDetailResponse,
    summary="Get full detail of a specific analysis",
)
async def get_history_detail(
    analysis_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> HistoryDetailResponse:
    """Return the complete analysis record including CV text, job description,
    and full AI result.

    Only analyses owned by the authenticated user are accessible.
    """
    analysis = await get_analysis_detail(
        db,
        analysis_id=analysis_id,
        user_id=current_user.id,
    )

    return HistoryDetailResponse.model_validate(analysis, from_attributes=True)


# ── Delete an analysis ─────────────────────────────────────────


@router.delete(
    "/{analysis_id}",
    response_model=HistoryDeleteResponse,
    status_code=status.HTTP_200_OK,
    summary="Delete a specific analysis",
)
async def delete_history_item(
    analysis_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> HistoryDeleteResponse:
    """Permanently delete an analysis owned by the authenticated user.

    This action cannot be undone.
    """
    deleted = await delete_analysis(
        db,
        analysis_id=analysis_id,
        user_id=current_user.id,
    )

    return HistoryDeleteResponse(id=deleted.id)
