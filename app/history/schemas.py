"""Pydantic schemas for the history module."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


# ── Pagination wrapper ─────────────────────────────────────────


class PaginatedResponse(BaseModel, Generic[T]):
    """Generic paginated response envelope."""

    items: list[T]
    total: int
    page: int
    per_page: int
    pages: int


# ── History item (list view) ───────────────────────────────────


class HistoryItem(BaseModel):
    """Lightweight representation for list views — excludes large text fields."""

    id: uuid.UUID
    status: str
    compatibility_score: int | None = None
    job_url: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── History detail (single item) ───────────────────────────────


class HistoryDetailResponse(BaseModel):
    """Full analysis detail — includes all fields."""

    id: uuid.UUID
    cv_text: str
    job_description: str
    job_url: str | None = None
    status: str
    compatibility_score: int | None = None
    analysis_result: dict[str, Any] | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── Delete confirmation ────────────────────────────────────────


class HistoryDeleteResponse(BaseModel):
    """Confirmation returned after a successful deletion."""

    id: uuid.UUID
    message: str = "Analysis deleted successfully."
