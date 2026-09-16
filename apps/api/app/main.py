"""FastAPI application factory."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api.router import api_router
from app.core.config import settings
from app.core.db import engine
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging, get_logger
from app.core.middleware import (
    MaxBodySizeMiddleware,
    RateLimitMiddleware,
    RequestContextMiddleware,
)
from app.providers.registry import provider_summary

logger = get_logger(__name__)

DESCRIPTION = """
Enterprise control plane for AI agents, RAG pipelines, models, prompts,
evaluations, guardrails, cost and Azure service health.

**Authentication** — `POST /api/v1/auth/login` returns a bearer token. CI and
automation can use a long-lived key in the `X-API-Key` header instead.

**Provider modes** — every external dependency is behind a provider interface.
`local` runs deterministic in-process implementations with no Azure account;
`azure` uses the real services. The active mode is reported by `/api/v1/overview`
and `/health/ready`.
"""


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging("DEBUG" if settings.debug else "INFO")
    problems = settings.validate_production()
    if problems:
        for problem in problems:
            logger.error("configuration_error", extra={"problem": problem})
        if settings.environment == "production":
            raise RuntimeError(
                "Refusing to start in production with an invalid configuration: "
                + "; ".join(problems)
            )
    logger.info(
        "startup",
        extra={
            "environment": settings.environment,
            "demo_mode": settings.demo_mode,
            "providers": provider_summary(),
        },
    )
    yield
    logger.info("shutdown")


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        description=DESCRIPTION,
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    # Order matters: the outermost middleware runs first.
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(MaxBodySizeMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-API-Key", "X-Correlation-ID"],
        expose_headers=["X-Request-ID", "X-Correlation-ID"],
        max_age=600,
    )

    register_exception_handlers(app)
    app.include_router(api_router, prefix=settings.api_v1_prefix)

    @app.get("/health/live", tags=["health"], summary="Liveness probe")
    def live() -> dict:
        return {"status": "alive"}

    @app.get("/health/ready", tags=["health"], summary="Readiness probe")
    def ready() -> dict:
        """Readiness requires a working database connection."""
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            database_ok = True
        except Exception as exc:
            logger.error("readiness_failed", extra={"reason": str(exc)[:200]})
            database_ok = False
        return {
            "status": "ready" if database_ok else "not_ready",
            "database": "up" if database_ok else "down",
            "environment": settings.environment,
            "demo_mode": settings.demo_mode,
            "providers": provider_summary(),
        }

    @app.get("/", include_in_schema=False)
    def root() -> dict:
        return {
            "name": settings.app_name,
            "version": "0.1.0",
            "docs": "/docs",
            "api": settings.api_v1_prefix,
        }

    return app


app = create_app()
