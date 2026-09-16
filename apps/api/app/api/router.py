"""Versioned API router aggregation."""

from fastapi import APIRouter

from app.api.routes import (
    agents,
    audit,
    auth,
    costs,
    documents,
    evaluations,
    guardrails,
    models,
    monitoring,
    overview,
    prompts,
    rag,
    runs,
    users,
)

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(overview.router)
api_router.include_router(agents.router)
api_router.include_router(runs.router)
api_router.include_router(models.router)
api_router.include_router(prompts.router)
api_router.include_router(documents.router)
api_router.include_router(rag.router)
api_router.include_router(guardrails.router)
api_router.include_router(evaluations.router)
api_router.include_router(monitoring.router)
api_router.include_router(costs.router)
api_router.include_router(audit.router)
