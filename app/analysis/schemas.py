"""Pydantic schemas for the analysis module."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


# ── Status enum exposed to the API ───────────────────────────


class Status(str):
    """Mirror of the DB enum so the API layer never imports SQLAlchemy."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


# ── Request schemas ───────────────────────────────────────────


class AnalysisCreate(BaseModel):
    """Body payload when submitting via JSON (file upload uses multipart instead).

    Validation rules enforced at the route level:
    - ``job_text`` and ``job_url`` are mutually exclusive.
    - At least one of them must be provided.
    """

    job_text: str | None = Field(None, description="Pasted job description text")
    job_url: str | None = Field(
        None,
        description="URL to scrape the job posting from (Indeed / Bommerang)",
    )


# ── Response schemas ──────────────────────────────────────────


class AnalysisSubmitResponse(BaseModel):
    """Returned immediately after a successful submission."""

    id: uuid.UUID
    status: str = "pending"
    message: str = (
        "Analysis submitted successfully. Poll /analysis/{id}/status for updates."
    )


class AnalysisStatusResponse(BaseModel):
    """Returned when polling for analysis status/completion."""

    id: uuid.UUID
    status: str
    compatibility_score: int | None = None
    analysis_result: dict[str, Any] | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
