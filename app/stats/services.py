"""Services for the stats module — aggregate analysis statistics."""

from __future__ import annotations

import uuid
from collections import Counter
from typing import Any

from sqlalchemy import case, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import JSONB

from app.analysis.models import Analysis, AnalysisStatus
from app.stats.schemas import (
    MissingKeywordItem,
    MissingKeywordStats,
    ScoreEvolution,
    ScoreEvolutionPoint,
    StatsSummary,
)


# ── Summary statistics ─────────────────────────────────────────


async def get_summary_stats(
    db: AsyncSession,
    user_id: uuid.UUID,
) -> StatsSummary:
    """Calculate overall analysis statistics for a user.

    Returns total, average compatibility score, and counts by status.
    """
    # Count by status — single query for all statuses
    status_counts_stmt = (
        select(
            Analysis.status,
            func.count().label("count"),
        )
        .where(Analysis.user_id == user_id)
        .group_by(Analysis.status)
    )
    result = await db.execute(status_counts_stmt)
    status_rows = {row.status: row.count for row in result.all()}

    completed = status_rows.get(AnalysisStatus.COMPLETED, 0)
    failed = status_rows.get(AnalysisStatus.FAILED, 0)
    pending = status_rows.get(AnalysisStatus.PENDING, 0) + status_rows.get(
        AnalysisStatus.PROCESSING, 0
    )
    total = completed + failed + pending

    # Average compatibility score (only completed analyses)
    avg_score: float | None = None
    if completed > 0:
        avg_stmt = select(func.avg(Analysis.compatibility_score)).where(
            Analysis.user_id == user_id,
            Analysis.status == AnalysisStatus.COMPLETED,
            Analysis.compatibility_score.isnot(None),
        )
        avg_result = await db.execute(avg_stmt)
        avg_score = avg_result.scalar()
        if avg_score is not None:
            avg_score = round(float(avg_score), 1)

    return StatsSummary(
        total_analyses=total,
        avg_compatibility_score=avg_score,
        completed=completed,
        failed=failed,
        pending=pending,
    )


# ── Score evolution over time ──────────────────────────────────


async def get_score_evolution(
    db: AsyncSession,
    user_id: uuid.UUID,
) -> ScoreEvolution:
    """Return monthly average compatibility score for completed analyses.

    Groups by YYYY-MM using PostgreSQL's date_trunc, ordered chronologically.
    Only includes months where there is at least one completed analysis.
    """
    stmt = (
        select(
            func.to_char(Analysis.created_at, "YYYY-MM").label("month"),
            func.avg(Analysis.compatibility_score).label("avg_score"),
            func.count().label("count"),
        )
        .where(
            Analysis.user_id == user_id,
            Analysis.status == AnalysisStatus.COMPLETED,
            Analysis.compatibility_score.isnot(None),
        )
        .group_by(text("month"))
        .order_by(text("month"))
    )

    result = await db.execute(stmt)
    rows = result.all()

    data_points = [
        ScoreEvolutionPoint(
            month=row.month,
            avg_score=round(float(row.avg_score), 1),
            count=row.count,
        )
        for row in rows
    ]

    return ScoreEvolution(data_points=data_points)


# ── Top missing keywords ───────────────────────────────────────


async def get_missing_keywords(
    db: AsyncSession,
    user_id: uuid.UUID,
) -> MissingKeywordStats:
    """Aggregate missing keywords across all completed analyses for a user.

    The ``analysis_result`` JSONB field contains a ``keywords_missing`` key
    with a list of keyword strings. We fetch all of them, count occurrences,
    and compute the percentage relative to the total number of completed
    analyses.
    """
    # Fetch the total number of completed analyses
    total_completed_stmt = (
        select(func.count())
        .select_from(Analysis)
        .where(
            Analysis.user_id == user_id,
            Analysis.status == AnalysisStatus.COMPLETED,
        )
    )
    total_completed = (await db.execute(total_completed_stmt)).scalar() or 0

    if total_completed == 0:
        return MissingKeywordStats(keywords=[])

    # Fetch all missing_keywords lists from completed analyses
    stmt = select(Analysis.analysis_result["missing_keywords"]).where(
        Analysis.user_id == user_id,
        Analysis.status == AnalysisStatus.COMPLETED,
        Analysis.analysis_result.isnot(None),
        Analysis.analysis_result["missing_keywords"].isnot(None),
    )
    result = await db.execute(stmt)
    rows = result.all()

    # Flatten and count
    counter: Counter[str] = Counter()
    for (keywords_list,) in rows:
        if keywords_list and isinstance(keywords_list, list):
            for kw in keywords_list:
                if isinstance(kw, str) and kw.strip():
                    counter[kw.strip()] += 1

    # Build response, sorted by missing_count descending (TOP 5)
    keyword_items = [
        MissingKeywordItem(
            keyword=keyword,
            missing_count=count,
            percentage=round((count / total_completed) * 100, 1),
        )
        for keyword, count in counter.most_common(5)  # Solo TOP 5
    ]

    return MissingKeywordStats(keywords=keyword_items)
