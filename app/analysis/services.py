"""Services for the analysis module: PDF extraction, web scraping, orchestration."""

from __future__ import annotations

import io
import logging
from typing import Any

import httpx
from bs4 import BeautifulSoup
from fastapi import HTTPException, status
from pypdf import PdfReader

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────

MAX_PDF_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB
ALLOWED_CONTENT_TYPES = {"application/pdf"}


# ── PDF Extraction ────────────────────────────────────────────


def extract_text_from_pdf(file_bytes: bytes) -> str:
    """Extract all textual content from a PDF file.

    Args:
        file_bytes: Raw bytes of the uploaded PDF.

    Returns:
        Concatenated text from every page.

    Raises:
        HTTPException 400: If the file cannot be parsed.
    """
    try:
        reader = PdfReader(io.BytesIO(file_bytes))
    except Exception as exc:
        logger.warning("PDF parse error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The uploaded file is not a valid PDF or is corrupted.",
        ) from exc

    pages: list[str] = []
    for page in reader.pages:
        text = page.extract_text()
        if text:
            pages.append(text)

    if not pages:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not extract any text from the PDF. "
            "Make sure the file contains selectable text (not scanned images).",
        )

    return "\n\n".join(pages)


# ── Web Scraping ──────────────────────────────────────────────


async def scrape_job_description(url: str) -> str:
    """Fetch a job posting URL and extract the meaningful text content.

    Currently targets:
    - Indeed (indeed.com)
    - Bommerang (bommerang.com)

    Args:
        url: The public URL of the job posting.

    Returns:
        Cleaned text extracted from the page body.

    Raises:
        HTTPException 400: If the URL is not supported or scraping fails.
    """
    _validate_job_url(url)

    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=30.0,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/125.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            },
        ) as client:
            response = await client.get(url)
            response.raise_for_status()
    except httpx.HTTPError as exc:
        logger.warning("Scraping HTTP error for %s: %s", url, exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Could not fetch the job posting URL. Error: {exc}",
        ) from exc

    raw_html = response.text
    return _parse_job_html(raw_html, url)


def _validate_job_url(url: str) -> None:
    """Raise 400 if the URL is not one of the supported job boards."""
    supported_domains = {"indeed.com", "bommerang.com"}
    from urllib.parse import urlparse

    parsed = urlparse(url)
    if not parsed.hostname:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid URL format.",
        )
    domain = parsed.hostname.lower()
    if not any(domain == d or domain.endswith("." + d) for d in supported_domains):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Unsupported job board domain: {parsed.hostname}. "
                f"Supported domains: {', '.join(sorted(supported_domains))}."
            ),
        )


def _parse_job_html(html: str, url: str) -> str:
    """Extract job description text from raw HTML.

    Each supported job board has a different DOM structure, so we try
    multiple selectors in priority order.
    """
    soup = BeautifulSoup(html, "html.parser")

    # Remove script/style/noise elements
    for tag in soup(["script", "style", "nav", "header", "footer", "noscript"]):
        tag.decompose()

    # ── Indeed ────────────────────────────────────────────────
    if "indeed.com" in url:
        # Indeed wraps the main description in a div with data-testid or id
        candidate = (
            soup.find("div", attrs={"data-testid": "jobsearch-JobDescription"})
            or soup.find("div", class_="jobsearch-jobDescriptionText")
            or soup.find("div", id="jobDescriptionText")
        )
        if candidate:
            return candidate.get_text(separator="\n", strip=True)

    # ── Bommerang ─────────────────────────────────────────────
    if "bommerang.com" in url:
        candidate = (
            soup.find("div", class_="description")
            or soup.find("div", class_="job-description")
            or soup.find("section", class_="job-details")
        )
        if candidate:
            return candidate.get_text(separator="\n", strip=True)

    # ── Fallback: grab the largest <article> or <main> ────────
    candidate = (
        soup.find("article")
        or soup.find("main")
        or soup.find("div", class_="description")
    )
    if candidate:
        text = candidate.get_text(separator="\n", strip=True)
        if len(text) > 200:
            return text

    # Last resort: full body text
    body = soup.find("body")
    if body:
        text = body.get_text(separator="\n", strip=True)
        if len(text) > 200:
            return text

    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail="Could not extract a job description from the provided URL. "
        "The page structure may not be supported.",
    )


# ── Analysis Orchestration ────────────────────────────────────


async def _perform_analysis(analysis_id: str, db_session_factory: Any) -> None:
    """Background worker that runs the actual CV-vs-job analysis.

    This is the function passed to ``FastAPI.BackgroundTasks``.
    It updates the analysis record from ``pending`` → ``processing`` → ``completed``/``failed``.

    NOTE: The actual AI analysis will be wired in a future phase.
    For now this extracts/stores text and marks the analysis as completed
    with a placeholder result.
    """
    from app.analysis.models import Analysis, AnalysisStatus
    from app.shared.database import async_session_factory as _factory

    factory = db_session_factory or _factory
    async with factory() as db:
        from sqlalchemy import select

        result = await db.execute(
            select(Analysis).where(Analysis.id == analysis_id),
        )
        analysis = result.scalar_one_or_none()
        if analysis is None:
            logger.error("Analysis %s not found in background task", analysis_id)
            return

        # Mark as processing
        analysis.status = AnalysisStatus.PROCESSING
        await db.flush()

        try:
            # --- Actual AI analysis will be added in the AI module phase ---
            # For now, store a placeholder so the flow is end-to-end testable.
            placeholder_result = {
                "summary": "Analysis pending AI integration.",
                "compatibility": 0,
                "keywords_present": [],
                "keywords_missing": [],
                "strengths": [],
                "weaknesses": [],
            }

            analysis.status = AnalysisStatus.COMPLETED
            analysis.analysis_result = placeholder_result
            analysis.compatibility_score = 0  # Will be real score from AI
            await db.flush()
            await db.commit()

        except Exception as exc:
            logger.exception("Analysis %s failed", analysis_id)
            analysis.status = AnalysisStatus.FAILED
            analysis.error_message = str(exc)[:2000]
            await db.flush()
            await db.commit()
