"""Service health and Azure resource monitoring.

Two collectors implement the same interface:

  * `LocalMetricCollector` derives metrics from what the platform can actually
    observe locally (database, blob store, vector store, recent usage records).
    Everything it returns is tagged `data_source="mock"` for Azure-only signals
    it cannot observe, and `"local"` for real local measurements.
  * `AzureMonitorCollector` queries Azure Monitor. It requires credentials.

Nothing here ever fabricates a "healthy Azure" reading when Azure is not
configured — unconfigured resources report status `not_configured`.
"""

from __future__ import annotations

import platform
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import get_logger
from app.db.models import AzureResource, UsageRecord
from app.providers.registry import get_blob_store, get_vector_store, provider_summary

logger = get_logger(__name__)

STARTED_AT = time.time()


@dataclass(slots=True)
class ComponentHealth:
    component: str
    status: str  # healthy | degraded | unhealthy | not_configured
    latency_ms: int = 0
    detail: str = ""
    data_source: str = "local"

    def as_dict(self) -> dict[str, Any]:
        return {
            "component": self.component,
            "status": self.status,
            "latency_ms": self.latency_ms,
            "detail": self.detail,
            "data_source": self.data_source,
        }


class MetricCollector(Protocol):
    name: str

    def collect(self, db: Session) -> list[dict[str, Any]]: ...


def check_database(db: Session) -> ComponentHealth:
    started = time.perf_counter()
    try:
        db.execute(text("SELECT 1"))
        return ComponentHealth(
            component="database",
            status="healthy",
            latency_ms=int((time.perf_counter() - started) * 1000),
            detail=db.bind.dialect.name if db.bind else "unknown",
        )
    except Exception as exc:
        return ComponentHealth("database", "unhealthy", detail=str(exc)[:200])


def check_vector_store(db: Session) -> ComponentHealth:
    started = time.perf_counter()
    try:
        info = get_vector_store(db).health()
        return ComponentHealth(
            component="vector_store",
            status=info.get("status", "unknown"),
            latency_ms=int((time.perf_counter() - started) * 1000),
            detail=f"{info.get('provider')}: {info.get('detail', '')}".strip(": "),
        )
    except Exception as exc:
        return ComponentHealth("vector_store", "unhealthy", detail=str(exc)[:200])


def check_blob_store() -> ComponentHealth:
    started = time.perf_counter()
    try:
        info = get_blob_store().health()
        return ComponentHealth(
            component="blob_storage",
            status=info.get("status", "unknown"),
            latency_ms=int((time.perf_counter() - started) * 1000),
            detail=str(info.get("root") or info.get("container") or ""),
            data_source="local" if settings.blob_provider == "local" else "live",
        )
    except Exception as exc:
        return ComponentHealth("blob_storage", "unhealthy", detail=str(exc)[:200])


def check_azure_openai() -> ComponentHealth:
    if settings.llm_provider != "azure":
        return ComponentHealth(
            component="azure_openai",
            status="not_configured",
            detail="LLM_PROVIDER=local — no Azure OpenAI connection is attempted.",
            data_source="none",
        )
    if not settings.azure_openai_endpoint:
        return ComponentHealth(
            "azure_openai", "unhealthy", detail="AZURE_OPENAI_ENDPOINT missing.", data_source="none"
        )
    return ComponentHealth(
        component="azure_openai",
        status="configured",
        detail=f"Endpoint set ({settings.azure_openai_endpoint.split('//')[-1][:40]}). "
        "Liveness is confirmed on first call.",
        data_source="live",
    )


def system_health(db: Session) -> dict[str, Any]:
    components = [
        check_database(db),
        check_vector_store(db),
        check_blob_store(),
        check_azure_openai(),
    ]
    statuses = {c.status for c in components}
    if "unhealthy" in statuses:
        overall = "unhealthy"
    elif "degraded" in statuses:
        overall = "degraded"
    else:
        overall = "healthy"

    since = datetime.now(timezone.utc) - timedelta(hours=24)
    requests_24h = db.scalar(
        select(func.count(UsageRecord.id)).where(UsageRecord.occurred_at >= since)
    ) or 0
    errors_24h = db.scalar(
        select(func.count(UsageRecord.id)).where(
            UsageRecord.occurred_at >= since, UsageRecord.succeeded.is_(False)
        )
    ) or 0

    return {
        "status": overall,
        "environment": settings.environment,
        "demo_mode": settings.demo_mode,
        "uptime_seconds": int(time.time() - STARTED_AT),
        "python": platform.python_version(),
        "providers": provider_summary(),
        "components": [c.as_dict() for c in components],
        "requests_24h": int(requests_24h),
        "error_rate_24h_pct": round((errors_24h / requests_24h * 100) if requests_24h else 0.0, 2),
        "configuration_warnings": settings.validate_production(),
    }


class LocalMetricCollector:
    """Derives Azure-resource rows from locally observable signals only."""

    name = "local"

    def collect(self, db: Session) -> list[dict[str, Any]]:
        now = datetime.now(timezone.utc)
        since = now - timedelta(hours=1)
        rows = db.execute(
            select(UsageRecord.latency_ms, UsageRecord.succeeded).where(
                UsageRecord.occurred_at >= since
            )
        ).all()
        latencies = sorted(int(r[0] or 0) for r in rows)
        failures = sum(1 for r in rows if not r[1])
        p95 = latencies[int(len(latencies) * 0.95)] if latencies else 0
        error_rate = round((failures / len(rows) * 100) if rows else 0.0, 2)
        throughput = round(len(rows) / 60.0, 2)

        updated: list[dict[str, Any]] = []
        for resource in db.execute(select(AzureResource)).scalars():
            observable = resource.resource_type in {
                "Microsoft.DBforPostgreSQL",
                "Microsoft.Storage",
                "Microsoft.Cache",
            }
            if resource.resource_type == "Microsoft.CognitiveServices":
                resource.latency_p95_ms = p95
                resource.error_rate_pct = error_rate
                resource.throughput_rpm = throughput
                resource.availability_pct = 100.0 - error_rate
                resource.data_source = "local"
                resource.status = "healthy" if error_rate < 5 else "degraded"
                resource.details = {
                    "note": "Derived from local usage records, not Azure Monitor.",
                    "samples": len(rows),
                }
            elif observable and settings.environment == "local":
                resource.data_source = "local"
                resource.status = "healthy"
                resource.details = {"note": "Local container or filesystem equivalent."}
            else:
                resource.data_source = "none"
                resource.status = "not_configured"
                resource.details = {
                    "note": "Requires Azure credentials. No metrics are synthesised."
                }
            resource.last_checked_at = now
            updated.append({"id": str(resource.id), "status": resource.status})
        db.flush()
        return updated


class AzureMonitorCollector:
    """Queries Azure Monitor. Requires credentials and the `azure` extra."""

    name = "azure"

    def collect(self, db: Session) -> list[dict[str, Any]]:
        try:
            from azure.identity import DefaultAzureCredential
            from azure.monitor.query import MetricsQueryClient
        except ImportError as exc:  # pragma: no cover - optional extra
            raise RuntimeError(
                "azure-monitor-query and azure-identity are required for live collection."
            ) from exc

        client = MetricsQueryClient(DefaultAzureCredential())
        now = datetime.now(timezone.utc)
        updated: list[dict[str, Any]] = []
        for resource in db.execute(select(AzureResource)).scalars():
            resource_id = (resource.details or {}).get("resource_id")
            if not resource_id:
                resource.status = "not_configured"
                resource.data_source = "none"
                continue
            response = client.query_resource(
                resource_id,
                metric_names=["Latency", "Availability"],
                timespan=timedelta(hours=1),
            )
            values = {m.name: m for m in response.metrics}
            latency = values.get("Latency")
            availability = values.get("Availability")
            resource.latency_p95_ms = int(_latest(latency) or 0)
            resource.availability_pct = float(_latest(availability) or 0.0)
            resource.data_source = "live"
            resource.status = "healthy" if resource.availability_pct >= 99 else "degraded"
            resource.last_checked_at = now
            updated.append({"id": str(resource.id), "status": resource.status})
        db.flush()
        return updated


def _latest(metric) -> float | None:  # pragma: no cover - live Azure only
    if metric is None or not metric.timeseries:
        return None
    points = metric.timeseries[0].data
    for point in reversed(points):
        value = point.average if point.average is not None else point.total
        if value is not None:
            return float(value)
    return None


def get_collector() -> MetricCollector:
    if settings.environment != "local" and settings.applicationinsights_connection_string:
        return AzureMonitorCollector()
    return LocalMetricCollector()
