"""FastAPI application factory.

Centralises app creation so that tests, CLI scripts, and the production
entry-point all share the exact same configuration, middleware stack,
and lifespan behaviour.
"""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Callable

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.ai.providers.cerebras import CerebrasProvider
from app.ai.providers.gemini import GeminiProvider
from app.ai.providers.groq import GroqProvider
from app.ai.providers.ollama import OllamaProvider
from app.analysis.routes import router as analysis_router
from app.auth.routes import router as auth_router
from app.history.routes import router as history_router
from app.payments.routes import router as payments_router
from app.shared.config import settings
from app.shared.database import engine
from app.stats.routes import router as stats_router

logger = logging.getLogger(__name__)


# ── Lifespan ────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Startup / shutdown hook.

    Startup:
        - Log relevant config (non-sensitive).
        - Verify the database connection.

    Shutdown:
        - Dispose the async SQLAlchemy engine.
    """
    # ── Startup ───────────────────────────────────────────
    logger.info("CV Analyzer starting up (version %s)", settings.app_version)
    logger.info(
        "CORS origins: %s",
        [o.strip() for o in settings.cors_origins.split(",")],
    )

    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        logger.info("Database connection verified — OK")
    except Exception:
        logger.exception("Database connection FAILED — check DATABASE_URL")

    yield

    # ── Shutdown ──────────────────────────────────────────
    logger.info("CV Analyzer shutting down")
    await engine.dispose()
    logger.info("Database engine disposed")


# ── Request-logging middleware ─────────────────────────────────────────


async def _request_logging_middleware(
    request: Request, call_next: Callable
) -> Response:
    """Log every HTTP request with method, path, status code and duration."""
    start = time.perf_counter()
    response: Response = await call_next(request)
    duration_ms = (time.perf_counter() - start) * 1000

    logger.info(
        "%s %s → %d (%.1f ms)",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
    )
    return response


# ── Factory ────────────────────────────────────────────────────────────


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    application = FastAPI(
        title="CV Analyzer",
        description="Backend for CV analysis with AI-powered feedback",
        version=settings.app_version,
        lifespan=lifespan,
    )

    # ── Middleware (order matters — last added runs first) ──
    # 1. Request logging (added first → inner layer)
    application.middleware("http")(_request_logging_middleware)

    # 2. CORS (added last → outermost — handles OPTIONS preflight first)
    origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
    application.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Routers ───────────────────────────────────────────
    application.include_router(auth_router, prefix="/api")
    application.include_router(analysis_router, prefix="/api")
    application.include_router(payments_router, prefix="/api")
    application.include_router(history_router, prefix="/api")
    application.include_router(stats_router, prefix="/api")

    # ── Health check ──────────────────────────────────────
    @application.get("/api/health", tags=["Health"])
    async def health_check() -> dict:
        """Return service health including DB connectivity and AI providers."""
        # Check database
        db_status = "disconnected"
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            db_status = "connected"
        except Exception:
            logger.exception("Health check: database connection failed")

        # Check AI provider availability
        ai_providers: list[str] = []
        all_providers = [
            GeminiProvider(),
            CerebrasProvider(),
            GroqProvider(),
            OllamaProvider(),
        ]
        for provider in all_providers:
            if provider.is_available:
                ai_providers.append(provider.name)

        return {
            "status": "ok",
            "database": db_status,
            "ai_providers": ai_providers,
            "version": settings.app_version,
        }

    return application
