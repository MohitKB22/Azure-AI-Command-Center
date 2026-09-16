"""RAG pipeline configuration and the retrieval/answer playground."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy import select

from app.core.db import utcnow
from app.core.deps import DbSession, require_permission
from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.db.models import Agent, RagPipeline, User
from app.schemas import (
    PipelineCreate,
    PipelineOut,
    PipelineUpdate,
    RagQueryRequest,
    RagQueryResponse,
    RetrievedChunkOut,
)
from app.services import audit
from app.services.rag import resolve_pipeline, retrieve
from app.services.runner import execute_agent

router = APIRouter(prefix="/rag", tags=["rag"])

PIPELINE_STAGES = [
    {"id": "document", "label": "Document", "description": "Uploaded file in blob storage"},
    {"id": "extraction", "label": "Extraction", "description": "PDF/DOCX/CSV/JSON to text"},
    {"id": "cleaning", "label": "Cleaning", "description": "Unicode + whitespace normalisation"},
    {"id": "chunking", "label": "Chunking", "description": "Sentence-aware sliding window"},
    {"id": "embedding", "label": "Embedding", "description": "Local hash or Azure OpenAI"},
    {"id": "index", "label": "Vector index", "description": "SQL exact search or Qdrant"},
    {"id": "retrieval", "label": "Retrieval", "description": "Cosine top-K"},
    {"id": "reranking", "label": "Reranking", "description": "Vector 0.65 + lexical 0.35"},
    {"id": "context", "label": "Context assembly", "description": "Numbered, budget-capped"},
    {"id": "llm", "label": "LLM", "description": "Grounded generation"},
    {"id": "evaluation", "label": "Evaluation", "description": "Groundedness and relevance"},
]


@router.get("/stages")
def stages(_: User = Depends(require_permission("documents:read"))) -> list[dict]:
    return PIPELINE_STAGES


@router.get("/pipelines", response_model=list[PipelineOut])
def list_pipelines(
    db: DbSession,
    _: User = Depends(require_permission("documents:read")),
) -> list[RagPipeline]:
    return list(
        db.execute(
            select(RagPipeline)
            .where(RagPipeline.deleted_at.is_(None))
            .order_by(RagPipeline.is_default.desc(), RagPipeline.name.asc())
        )
        .scalars()
        .all()
    )


@router.post("/pipelines", response_model=PipelineOut, status_code=status.HTTP_201_CREATED)
def create_pipeline(
    payload: PipelineCreate,
    db: DbSession,
    user: User = Depends(require_permission("documents:write")),
) -> RagPipeline:
    if db.execute(
        select(RagPipeline).where(
            RagPipeline.name == payload.name, RagPipeline.deleted_at.is_(None)
        )
    ).scalar_one_or_none():
        raise ConflictError("A pipeline with that name already exists.")

    pipeline = RagPipeline(**payload.model_dump())
    if pipeline.is_default:
        _clear_defaults(db)
    db.add(pipeline)
    audit.record(
        db,
        action="rag_pipeline.create",
        resource_type="rag_pipeline",
        resource_id=pipeline.id,
        actor=user,
        changes={"name": pipeline.name},
    )
    db.commit()
    db.refresh(pipeline)
    return pipeline


def _clear_defaults(db) -> None:
    for existing in db.execute(
        select(RagPipeline).where(RagPipeline.is_default.is_(True))
    ).scalars():
        existing.is_default = False


@router.patch("/pipelines/{pipeline_id}", response_model=PipelineOut)
def update_pipeline(
    pipeline_id: uuid.UUID,
    payload: PipelineUpdate,
    db: DbSession,
    user: User = Depends(require_permission("documents:write")),
) -> RagPipeline:
    pipeline = db.get(RagPipeline, pipeline_id)
    if pipeline is None or pipeline.deleted_at is not None:
        raise NotFoundError("Pipeline not found.")

    data = payload.model_dump(exclude_unset=True)
    chunk_size = data.get("chunk_size", pipeline.chunk_size)
    chunk_overlap = data.get("chunk_overlap", pipeline.chunk_overlap)
    if chunk_overlap >= chunk_size:
        raise ValidationError("chunk_overlap must be smaller than chunk_size.")
    if data.get("is_default"):
        _clear_defaults(db)
    for field, value in data.items():
        setattr(pipeline, field, value)

    audit.record(
        db,
        action="rag_pipeline.update",
        resource_type="rag_pipeline",
        resource_id=pipeline.id,
        actor=user,
        changes=data,
    )
    db.commit()
    db.refresh(pipeline)
    return pipeline


@router.delete("/pipelines/{pipeline_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_pipeline(
    pipeline_id: uuid.UUID,
    db: DbSession,
    user: User = Depends(require_permission("documents:delete")),
) -> None:
    pipeline = db.get(RagPipeline, pipeline_id)
    if pipeline is None or pipeline.deleted_at is not None:
        raise NotFoundError("Pipeline not found.")
    if pipeline.is_default:
        raise ValidationError("Set another pipeline as default before deleting this one.")
    pipeline.deleted_at = utcnow()
    audit.record(
        db,
        action="rag_pipeline.delete",
        resource_type="rag_pipeline",
        resource_id=pipeline.id,
        actor=user,
    )
    db.commit()


@router.post("/query", response_model=RagQueryResponse)
def rag_query(
    payload: RagQueryRequest,
    db: DbSession,
    user: User = Depends(require_permission("documents:read")),
) -> RagQueryResponse:
    pipeline = resolve_pipeline(db, payload.pipeline_id)
    filters = (
        {"document_ids": [str(doc_id) for doc_id in payload.document_ids]}
        if payload.document_ids
        else None
    )
    result = retrieve(
        db,
        payload.query,
        pipeline=pipeline,
        top_k=payload.top_k,
        similarity_threshold=payload.similarity_threshold,
        filters=filters,
        use_reranking=payload.use_reranking,
    )

    answer = None
    run_id = None
    if payload.generate_answer:
        agent = None
        if payload.agent_id:
            agent = db.get(Agent, payload.agent_id)
            if agent is None or agent.deleted_at is not None:
                raise NotFoundError("Agent not found.")
        else:
            agent = db.execute(
                select(Agent)
                .where(
                    Agent.deleted_at.is_(None),
                    Agent.enabled.is_(True),
                    Agent.rag_enabled.is_(True),
                )
                .order_by(Agent.created_at.asc())
                .limit(1)
            ).scalar_one_or_none()
        if agent is not None:
            run = execute_agent(db, agent, payload.query, user=user)
            answer = run.output_text
            run_id = run.id
            db.commit()
        else:
            answer = (
                "No enabled RAG agent is available to generate an answer. "
                "Retrieved context is shown below."
            )

    return RagQueryResponse(
        query=result.query,
        answer=answer,
        citations=result.citations,
        chunks=[
            RetrievedChunkOut(
                chunk_id=chunk.chunk_id,
                document_id=chunk.document_id,
                document_name=chunk.document_name,
                ordinal=chunk.ordinal,
                page=chunk.page,
                content=chunk.content,
                score=round(chunk.score, 4),
                rerank_score=chunk.rerank_score,
            )
            for chunk in result.chunks
        ],
        candidates_considered=result.candidates_considered,
        latency_ms=result.latency_ms,
        pipeline=result.pipeline,
        stages=result.stages,
        run_id=run_id,
    )
