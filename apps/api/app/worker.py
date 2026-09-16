"""Background worker.

Runs the periodic jobs the control plane needs: metric collection, alert
evaluation and retention. It is a plain loop rather than Celery because the
current job set is small, periodic and idempotent — adding a broker would be
complexity without benefit. Swap `run_once` into a Celery beat schedule when
the workload grows.
"""

from __future__ import annotations

import os
import signal
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from app.core.db import session_scope
from app.core.logging import configure_logging, get_logger
from app.db.models import Alert, Document, UsageRecord
from app.services.monitoring import get_collector
from app.services.rag import ingest_document

logger = get_logger("worker")

INTERVAL_SECONDS = int(os.getenv("COLLECT_INTERVAL_SECONDS", "60"))
LATENCY_ALERT_MS = int(os.getenv("LATENCY_ALERT_MS", "5000"))

_running = True


def _stop(signum, _frame) -> None:  # pragma: no cover - signal handler
    global _running
    logger.info("worker_stopping", extra={"signal": signum})
    _running = False


def collect_metrics() -> int:
    with session_scope() as db:
        collector = get_collector()
        updated = collector.collect(db)
        return len(updated)


def evaluate_alerts() -> int:
    """Raise alerts from observable conditions. Never invents Azure signals."""
    raised = 0
    since = datetime.now(timezone.utc) - timedelta(minutes=15)
    with session_scope() as db:
        p95_sample = db.execute(
            select(func.avg(UsageRecord.latency_ms)).where(UsageRecord.occurred_at >= since)
        ).scalar()
        if p95_sample and p95_sample > LATENCY_ALERT_MS:
            existing = db.execute(
                select(Alert).where(
                    Alert.title.like("Elevated model latency%"), Alert.status == "active"
                )
            ).first()
            if not existing:
                db.add(
                    Alert(
                        title="Elevated model latency detected",
                        description=(
                            f"Average latency over the last 15 minutes was "
                            f"{int(p95_sample)} ms, above the {LATENCY_ALERT_MS} ms threshold."
                        ),
                        severity="warning",
                        source="worker",
                        context={"avg_latency_ms": int(p95_sample)},
                    )
                )
                raised += 1

        stuck = db.execute(
            select(Document).where(
                Document.status == "processing",
                Document.updated_at < datetime.now(timezone.utc) - timedelta(minutes=30),
            )
        ).scalars().all()
        for document in stuck:
            document.status = "failed"
            document.error_message = "Ingestion did not complete within 30 minutes."
            raised += 1
    return raised


def retry_failed_ingestion(limit: int = 5) -> int:
    """Retry documents whose ingestion failed transiently."""
    retried = 0
    from app.providers.registry import get_blob_store

    with session_scope() as db:
        pending = db.execute(
            select(Document)
            .where(Document.status == "pending", Document.deleted_at.is_(None))
            .limit(limit)
        ).scalars().all()
        store = get_blob_store()
        for document in pending:
            try:
                data = store.get(f"documents/{document.id}/{document.filename}")
                ingest_document(db, document, data)
                retried += 1
            except Exception as exc:
                logger.warning(
                    "ingest_retry_failed",
                    extra={"document_id": str(document.id), "reason": str(exc)[:200]},
                )
    return retried


def run_once() -> dict[str, int]:
    return {
        "resources_collected": collect_metrics(),
        "alerts_raised": evaluate_alerts(),
        "documents_retried": retry_failed_ingestion(),
    }


def main() -> None:  # pragma: no cover - long-running loop
    configure_logging()
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    logger.info("worker_started", extra={"interval_seconds": INTERVAL_SECONDS})
    while _running:
        try:
            logger.info("worker_cycle", extra=run_once())
        except Exception:
            logger.exception("worker_cycle_failed")
        for _ in range(INTERVAL_SECONDS):
            if not _running:
                break
            time.sleep(1)
    logger.info("worker_stopped")


if __name__ == "__main__":  # pragma: no cover
    main()
