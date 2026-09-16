"""RAG/agent evaluation.

Metrics are computed with deterministic lexical measures so evaluation runs are
reproducible and require no judge model. They are proxies: `groundedness` here
means "the answer's terms are supported by the retrieved context", not a
semantic entailment judgement. Swap in an LLM judge for production scoring.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, ValidationError
from app.db.models import (
    Agent,
    EvaluationDataset,
    EvaluationResult,
    EvaluationRun,
    User,
)
from app.providers.embeddings import tokenize
from app.services.runner import execute_agent

METRICS = (
    "groundedness",
    "relevance",
    "faithfulness",
    "context_precision",
    "context_recall",
    "answer_correctness",
    "safety",
    "token_efficiency",
)


def _f1(predicted: set[str], expected: set[str]) -> float:
    if not predicted or not expected:
        return 0.0
    overlap = len(predicted & expected)
    if overlap == 0:
        return 0.0
    precision = overlap / len(predicted)
    recall = overlap / len(expected)
    return 2 * precision * recall / (precision + recall)


@dataclass(slots=True)
class ItemScore:
    scores: dict[str, float]
    passed: bool


def score_item(
    *,
    question: str,
    answer: str,
    expected: str | None,
    contexts: list[str],
    guardrail_outcome: str,
    total_tokens: int,
    threshold: float,
) -> ItemScore:
    answer_terms = set(tokenize(answer))
    question_terms = set(tokenize(question))
    context_terms = set(tokenize(" ".join(contexts)))
    expected_terms = set(tokenize(expected or ""))

    groundedness = (
        len(answer_terms & context_terms) / len(answer_terms) if answer_terms else 0.0
    )
    relevance = _f1(answer_terms, question_terms) if question_terms else 0.0
    faithfulness = groundedness if contexts else 0.0
    context_precision = (
        len(context_terms & question_terms) / len(context_terms) if context_terms else 0.0
    )
    context_recall = (
        len(question_terms & context_terms) / len(question_terms) if question_terms else 0.0
    )
    correctness = _f1(answer_terms, expected_terms) if expected_terms else groundedness
    safety = 1.0 if guardrail_outcome == "pass" else 0.5 if guardrail_outcome == "flagged" else 0.0
    efficiency = max(0.0, min(1.0, 1.0 - (total_tokens / 8000.0)))

    scores = {
        "groundedness": round(groundedness, 4),
        "relevance": round(relevance, 4),
        "faithfulness": round(faithfulness, 4),
        "context_precision": round(context_precision, 4),
        "context_recall": round(context_recall, 4),
        "answer_correctness": round(correctness, 4),
        "safety": round(safety, 4),
        "token_efficiency": round(efficiency, 4),
    }
    overall = sum(scores[m] for m in ("groundedness", "relevance", "answer_correctness")) / 3
    scores["overall"] = round(overall, 4)
    return ItemScore(scores=scores, passed=overall >= threshold)


def run_evaluation(
    db: Session,
    *,
    dataset_id,
    agent_id,
    threshold: float = 0.5,
    user: User | None = None,
) -> EvaluationRun:
    dataset = db.get(EvaluationDataset, dataset_id)
    if dataset is None or dataset.deleted_at is not None:
        raise NotFoundError("Evaluation dataset not found.")
    agent = db.get(Agent, agent_id)
    if agent is None or agent.deleted_at is not None:
        raise NotFoundError("Agent not found.")
    items = list(dataset.items or [])
    if not items:
        raise ValidationError("Dataset has no items.")

    run = EvaluationRun(
        dataset_id=dataset.id,
        agent_id=agent.id,
        status="running",
        pass_threshold=threshold,
        triggered_by=user.id if user else None,
    )
    db.add(run)
    db.flush()

    started = time.perf_counter()
    totals: dict[str, float] = dict.fromkeys((*METRICS, "overall"), 0.0)
    passed_count = 0

    for index, item in enumerate(items):
        question = str(item.get("question", "")).strip()
        expected = item.get("expected_answer")
        if not question:
            continue
        agent_run = execute_agent(db, agent, question, user=user, correlation_id=str(run.id))
        contexts = [c.get("snippet", "") for c in (agent_run.citations or [])]
        item_score = score_item(
            question=question,
            answer=agent_run.output_text or "",
            expected=expected,
            contexts=contexts,
            guardrail_outcome=agent_run.guardrail_outcome,
            total_tokens=agent_run.total_tokens,
            threshold=threshold,
        )
        agent_run.evaluation_score = item_score.scores["overall"]

        db.add(
            EvaluationResult(
                run_id=run.id,
                item_index=index,
                question=question,
                expected=expected,
                answer=agent_run.output_text or "",
                scores=item_score.scores,
                passed=item_score.passed,
                latency_ms=agent_run.latency_ms,
                total_tokens=agent_run.total_tokens,
            )
        )
        for metric, value in item_score.scores.items():
            totals[metric] = totals.get(metric, 0.0) + value
        passed_count += int(item_score.passed)

    count = max(1, len(items))
    aggregate = {metric: round(value / count, 4) for metric, value in totals.items()}
    aggregate["pass_rate"] = round(passed_count / count, 4)

    previous = db.execute(
        select(EvaluationRun)
        .where(
            EvaluationRun.dataset_id == dataset.id,
            EvaluationRun.agent_id == agent.id,
            EvaluationRun.status == "completed",
            EvaluationRun.id != run.id,
        )
        .order_by(EvaluationRun.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()

    regression = False
    if previous and previous.aggregate_scores:
        prior = float(previous.aggregate_scores.get("overall", 0.0))
        regression = aggregate["overall"] < prior - 0.05

    run.status = "completed"
    run.aggregate_scores = aggregate
    run.passed = aggregate["overall"] >= threshold
    run.regression_detected = regression
    run.duration_ms = int((time.perf_counter() - started) * 1000)
    db.flush()
    return run


def results_as_rows(run: EvaluationRun) -> list[dict[str, Any]]:
    """Flat rows for CSV export."""
    return [
        {
            "item_index": result.item_index,
            "question": result.question,
            "expected": result.expected or "",
            "answer": result.answer,
            "passed": result.passed,
            "latency_ms": result.latency_ms,
            "total_tokens": result.total_tokens,
            **{key: value for key, value in (result.scores or {}).items()},
        }
        for result in sorted(run.results, key=lambda r: r.item_index)
    ]
