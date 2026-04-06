"""Services for the analysis module: PDF extraction, web scraping, orchestration."""

from __future__ import annotations

import asyncio
import io
import logging
from typing import Any

from bs4 import BeautifulSoup
from fastapi import HTTPException, status
from playwright.async_api import async_playwright
from pypdf import PdfReader

logger = logging.getLogger(__name__)

# ── Playwright Configuration ────────────────────────────────

PLAYWRIGHT_TIMEOUT = 30000  # 30 seconds
MAX_RETRIES = 3
RETRY_DELAY = 2.0  # seconds

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

    Uses Playwright to execute JavaScript and bypass anti-bot protections:
    - Headless browser (Chromium)
    - Executes JavaScript
    - Handles cookies and sessions
    - Simulates real browser fingerprint

    Args:
        url: The public URL of the job posting.

    Returns:
        Cleaned text extracted from the page body.

    Raises:
        HTTPException 400: If the URL is not supported or scraping fails.
    """
    _validate_job_url(url)

    last_error: Exception | None = None

    # Retry loop with Playwright
    for attempt in range(MAX_RETRIES):
        try:
            logger.info("Scraping attempt %d/%d for %s", attempt + 1, MAX_RETRIES, url)

            async with async_playwright() as p:
                # Launch browser with anti-bot settings
                browser = await p.chromium.launch(
                    headless=True,  # Run in headless mode
                    args=[
                        "--disable-blink-features=AutomationControlled",  # Hide automation
                        "--no-sandbox",
                        "--disable-dev-shm-usage",
                    ],
                )

                # Create browser context with realistic settings
                context = await browser.new_context(
                    viewport={"width": 1920, "height": 1080},
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/131.0.0.0 Safari/537.36"
                    ),
                    locale="en-US",
                    timezone_id="America/New_York",
                    permissions=["geolocation"],
                    # Hide automation signals
                    color_scheme="light",
                )

                # Create page with anti-detection
                page = await context.new_page()

                # Override navigator.webdriver to undefined (anti-bot technique)
                await page.add_init_script("""
                    Object.defineProperty(navigator, 'webdriver', {
                        get: () => undefined,
                    });

                    // Override chrome object
                    window.chrome = {
                        runtime: {},
                    };

                    // Override permissions
                    const originalQuery = window.navigator.permissions.query;
                    window.navigator.permissions.query = (parameters) => (
                        parameters.name === 'notifications' ?
                            Promise.resolve({ state: Notification.permission }) :
                            originalQuery(parameters)
                    );
                """)

                # Navigate to URL with timeout
                await page.goto(
                    url,
                    wait_until="networkidle",  # Wait for network to be idle
                    timeout=PLAYWRIGHT_TIMEOUT,
                )

                # Wait for job description to load (Indeed uses dynamic loading)
                await page.wait_for_timeout(2000)  # 2 seconds for dynamic content

                # Get the HTML content after JavaScript execution
                html_content = await page.content()

                # Close browser
                await browser.close()

                # Parse and extract text
                result = _parse_job_html(html_content, url)

                logger.info("Successfully scraped %s on attempt %d", url, attempt + 1)
                return result

        except Exception as exc:
            last_error = exc
            logger.warning(
                "Scraping attempt %d failed for %s: %s",
                attempt + 1,
                url,
                exc,
            )

            # If not the last attempt, wait before retrying
            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(RETRY_DELAY * (attempt + 1))  # Exponential backoff

    # All attempts failed
    logger.error("All %d scraping attempts failed for %s", MAX_RETRIES, url)
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"Could not fetch the job posting URL after {MAX_RETRIES} attempts. "
        f"Last error: {last_error}",
    ) from last_error


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

    Uses the AIAnalyzerService with fallback chain: Gemini → Cerebras → Groq → Ollama.
    """
    logger.info("🚀 _perform_analysis STARTED for analysis_id=%s", analysis_id)
    from app.analysis.models import Analysis, AnalysisStatus
    from app.ai.service import AIAnalyzerService
    from app.shared.database import async_session_factory as _factory

    factory = db_session_factory or _factory
    async with factory() as db:
        from sqlalchemy import select

        logger.info("📊 Database session created")
        result = await db.execute(
            select(Analysis).where(Analysis.id == analysis_id),
        )
        analysis = result.scalar_one_or_none()
        if analysis is None:
            logger.error("Analysis %s not found in background task", analysis_id)
            return

        logger.info("✅ Analysis found: %s", analysis_id)

        # Mark as processing
        analysis.status = AnalysisStatus.PROCESSING
        await db.flush()
        logger.info("⏳ Status changed to PROCESSING")

        try:
            # Initialize AI service with fallback chain
            logger.info("🔧 Initializing AIAnalyzerService...")
            ai_service = AIAnalyzerService()

            logger.info(
                "Starting analysis %s with providers: %s",
                analysis_id,
                ai_service.provider_names,
            )

            # Run CV analysis with fallback chain
            logger.info("🚀 Calling ai_service.analyze_cv()...")
            ai_result = await ai_service.analyze_cv(
                cv_text=analysis.cv_text,
                job_description=analysis.job_description,
            )
            logger.info("✅ ai_service.analyze_cv() returned successfully!")

            # Convert AnalysisResponse to dict for storage
            result_dict = ai_result.model_dump()

            # Store the full analysis result
            analysis.status = AnalysisStatus.COMPLETED
            analysis.analysis_result = result_dict
            analysis.compatibility_score = ai_result.compatibility_score
            await db.flush()
            await db.commit()

            logger.info(
                "Analysis %s completed with score %d",
                analysis_id,
                ai_result.compatibility_score,
            )

        except Exception as exc:
            logger.exception("Analysis %s failed", analysis_id)
            analysis.status = AnalysisStatus.FAILED
            analysis.error_message = str(exc)[:2000]
            await db.flush()
            await db.commit()
