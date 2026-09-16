"""Evaluation datasets, runs and result export."""

from __future__ import annotations

import csv
import io
import uuid

from fastapi import APIRouter, Depends, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.deps import DbSession, require_permission
from app.core.errors import ConflictError, NotFoundError
from app.core.pagination import Page, PageParams, apply_sort, page_params, paginate
from app.db.models import EvaluationDataset, EvaluationRun, User
from app.schemas import (
    DatasetCreate,
    DatasetOut,
    EvaluationRunDetail,
    EvaluationRunOut,
    EvaluationRunRequest,
)
from app.services import audit
from app.services.evaluation import METRICS, results_as_rows, run_evaluation

router = APIRouter(prefix="/evaluations", tags=["evaluations"])


@router.get("/metrics")
def list_metrics(_: User = Depends(require_permission("evaluations:read"))) -> dict:
    return {
        "metrics": list(METRICS),
        "method": "deterministic lexical proxies",
        "note": (
            "Scores are reproducible proxies computed without a judge model. "
            "Use an LLM judge for production-grade semantic scoring."
        ),
    }


@router.get("/datasets", response_model=list[DatasetOut])
def list_datasets(
    db: DbSession,
    _: User = Depends(require_permission("evaluations:read")),
) -> list[EvaluationDataset]:
    return list(
        db.execute(
            select(EvaluationDataset)
            .where(EvaluationDataset.deleted_at.is_(None))
            .order_by(EvaluationDataset.name.asc())
        )
        .scalars()
        .all()
    )


@router.post("/datasets", response_model=DatasetOut, status_code=status.HTTP_201_CREATED)
def create_dataset(
    payload: DatasetCreate,
    db: DbSession,
    user: User = Depends(require_permission("evaluations:write")),
) -> EvaluationDataset:
    if db.execute(
        select(EvaluationDataset).where(
            EvaluationDataset.name == payload.name, EvaluationDataset.deleted_at.is_(None)
        )
    ).scalar_one_or_none():
        raise ConflictError("A dataset with that name already exists.")
    dataset = EvaluationDataset(**payload.model_dump())
    db.add(dataset)
    audit.record(
        db,
        action="evaluation_dataset.create",
        resource_type="evaluation_dataset",
        resource_id=dataset.id,
        actor=user,
        changes={"name": dataset.name, "items": len(dataset.items or [])},
    )
    db.commit()
    db.refresh(dataset)
    return dataset


@router.get("/runs", response_model=Page[EvaluationRunOut])
def list_runs(
    db: DbSession,
    params: PageParams = Depends(page_params),
    agent_id: uuid.UUID | None = None,
    _: User = Depends(require_permission("evaluations:read")),
) -> Page[EvaluationRunOut]:
    stmt = select(EvaluationRun)
    if agent_id:
        stmt = stmt.where(EvaluationRun.agent_id == agent_id)
    stmt = apply_sort(stmt, EvaluationRun, params, "created_at")
    rows, total = paginate(db, stmt, params)
    return Page.build([EvaluationRunOut.model_validate(row) for row in rows], total, params)


@router.post("/runs", response_model=EvaluationRunDetail, status_code=status.HTTP_201_CREATED)
def create_run(
    payload: EvaluationRunRequest,
    db: DbSession,
    user: User = Depends(require_permission("evaluations:execute")),
) -> EvaluationRunDetail:
    run = run_evaluation(
        db,
        dataset_id=payload.dataset_id,
        agent_id=payload.agent_id,
        threshold=payload.pass_threshold,
        user=user,
    )
    audit.record(
        db,
        action="evaluation.run",
        resource_type="evaluation_run",
        resource_id=run.id,
        actor=user,
        changes={"passed": run.passed, "regression": run.regression_detected},
    )
    db.commit()
    return EvaluationRunDetail.model_validate(_load(db, run.id))


def _load(db, run_id: uuid.UUID) -> EvaluationRun:
    run = db.execute(
        select(EvaluationRun)
        .options(selectinload(EvaluationRun.results))
        .where(EvaluationRun.id == run_id)
    ).scalar_one_or_none()
    if run is None:
        raise NotFoundError("Evaluation run not found.")
    return run


@router.get("/runs/{run_id}", response_model=EvaluationRunDetail)
def get_run(
    run_id: uuid.UUID,
    db: DbSession,
    _: User = Depends(require_permission("evaluations:read")),
) -> EvaluationRunDetail:
    return EvaluationRunDetail.model_validate(_load(db, run_id))


@router.get("/runs/{run_id}/export")
def export_run(
    run_id: uuid.UUID,
    db: DbSession,
    _: User = Depends(require_permission("evaluations:read")),
) -> StreamingResponse:
    run = _load(db, run_id)
    rows = results_as_rows(run)
    buffer = io.StringIO()
    if rows:
        writer = csv.DictWriter(buffer, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    buffer.seek(0)
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="evaluation-{run_id}.csv"'},
    )
