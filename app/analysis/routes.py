"""Analysis routes: submit CV analysis, poll status."""

from __future__ import annotations

import uuid

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.analysis.models import Analysis, AnalysisStatus
from app.analysis.schemas import AnalysisSubmitResponse, AnalysisStatusResponse
from app.analysis.services import (
    MAX_PDF_SIZE_BYTES,
    ALLOWED_CONTENT_TYPES,
    _perform_analysis,
    extract_text_from_pdf,
    scrape_job_description,
)
from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.payments.services import (
    consume_credit,
    has_credits_available,
)
from app.shared.database import async_session_factory, get_db

router = APIRouter(prefix="/analysis", tags=["Analysis"])


# ── Submit analysis ───────────────────────────────────────────


@router.post(
    "/submit",
    response_model=AnalysisSubmitResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Submit a CV for analysis against a job posting",
)
async def submit_analysis(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="PDF file containing the CV"),
    job_text: str | None = Form(None, description="Pasted job description text"),
    job_url: str | None = Form(None, description="URL to scrape the job posting from"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AnalysisSubmitResponse:
    """Accept a PDF CV and either a pasted job description or a job URL.

    The analysis runs asynchronously — the response includes the analysis ID
    so the client can poll ``GET /analysis/{id}/status`` for results.

    Validation:
    - User must have available credits (free or paid).
    - ``file`` must be a PDF ≤ 10 MB.
    - Exactly one of ``job_text`` / ``job_url`` must be provided.
    """
    # ── Check user credits ─────────────────────────────────
    can_analyze, reason = await has_credits_available(db, current_user.id)
    if not can_analyze:
        if reason == "no_credits":
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail="No tienes suficientes análisis disponibles. Compra un paquete de créditos.",
                headers={"X-Needs-Payment": "true"},
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No se puede realizar el análisis.",
            )

    # ── Validate mutual exclusivity ─────────────────────────
    has_text = job_text is not None and job_text.strip() != ""
    has_url = job_url is not None and job_url.strip() != ""

    if not has_text and not has_url:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Either 'job_text' or 'job_url' must be provided.",
        )
    if has_text and has_url:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Provide 'job_text' OR 'job_url', not both.",
        )

    # ── Validate PDF upload ─────────────────────────────────
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid file type '{file.content_type}'. Only PDF files are accepted.",
        )

    file_bytes = await file.read()
    if len(file_bytes) > MAX_PDF_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File too large ({len(file_bytes) / 1024 / 1024:.1f} MB). Maximum size is 10 MB.",
        )
    if len(file_bytes) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty.",
        )

    # ── Extract CV text from PDF ────────────────────────────
    cv_text = extract_text_from_pdf(file_bytes)

    # ── Resolve job description ─────────────────────────────
    if has_url:
        job_description = await scrape_job_description(job_url.strip())
        effective_url = job_url.strip()
    else:
        job_description = job_text.strip()
        effective_url = None

    # ── Persist analysis record (pending) ───────────────────
    analysis = Analysis(
        user_id=current_user.id,
        cv_text=cv_text,
        job_description=job_description,
        job_url=effective_url,
        status=AnalysisStatus.PENDING,
    )
    db.add(analysis)
    await db.flush()
    await db.refresh(analysis)

    analysis_id_str = str(analysis.id)

    # ── Consume user credit ─────────────────────────────────
    await consume_credit(db, current_user.id)

    # ── Kick off background processing ──────────────────────
    background_tasks.add_task(_perform_analysis, analysis_id_str, async_session_factory)

    return AnalysisSubmitResponse(
        id=analysis.id,
        status="pending",
        message="Analysis submitted successfully. Poll /analysis/{id}/status for updates.",
    )


# ── Poll analysis status ──────────────────────────────────────


@router.get(
    "/{analysis_id}/status",
    response_model=AnalysisStatusResponse,
    summary="Poll the status and result of an analysis",
)
async def get_analysis_status(
    analysis_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Analysis:
    """Return the current status of an analysis owned by the authenticated user.

    Once ``status`` is ``completed`` the ``analysis_result`` field will contain
    the full AI response and ``compatibility_score`` will be populated.
    """
    from sqlalchemy import select

    result = await db.execute(
        select(Analysis).where(
            Analysis.id == analysis_id,
            Analysis.user_id == current_user.id,
        ),
    )
    analysis = result.scalar_one_or_none()

    if analysis is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Analysis not found or you do not have permission to view it.",
        )

    return analysis
