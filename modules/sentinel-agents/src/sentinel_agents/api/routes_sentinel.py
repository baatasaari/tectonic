"""`/v1/sentinel-agents/*` routes (LLD §3).

**`POST /events`** is an addition beyond the LLD's documented API table:
the LLD ingests via a Kafka consumer, replaced here with a synchronous
HTTP ingestion endpoint (see the module README's "Design notes vs. the
LLD"). Everything else matches the LLD's documented admin/query surface.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from sentinel_agents.api.deps import build_event_processor, get_ctx, get_repository
from sentinel_agents.app_context import AppContext
from sentinel_agents.core.domain import AgentActionEvent, now
from sentinel_agents.core.ports import SentinelRepository
from sentinel_agents.schemas.sentinel import (
    AlertListResponse,
    AlertSchema,
    BaselineSchema,
    ConfigureRequest,
    ConfigureResponse,
    IngestEventRequest,
    IngestEventResponse,
)

router = APIRouter(prefix="/v1/sentinel-agents", tags=["sentinel-agents"])


def _alert_schema(a) -> AlertSchema:
    return AlertSchema(
        id=a.id, alert_type=a.alert_type.value, agent_refs=a.agent_refs, severity=a.severity.value,
        description=a.description, status=a.status.value, detected_at=a.detected_at,
    )


def _baseline_schema(b) -> BaselineSchema:
    return BaselineSchema(
        agent_ref=b.agent_ref, action_type=b.action_type, mean=b.mean, variance=b.variance,
        sample_count=b.sample_count, last_updated_at=b.last_updated_at,
    )


@router.post("/events", response_model=IngestEventResponse)
async def ingest_event(
    body: IngestEventRequest,
    ctx: AppContext = Depends(get_ctx),
    repository: SentinelRepository = Depends(get_repository),
) -> IngestEventResponse:
    processor = build_event_processor(ctx, repository)
    event = AgentActionEvent(
        tenant_id=body.tenant_id, agent_ref=body.agent_ref, action_type=body.action_type, value=body.value,
        instance_id=body.instance_id, timestamp=body.timestamp or now(),
    )
    alert = await processor.process(event)
    if alert is None:
        return IngestEventResponse(alert_id=None, alert_type=None, severity=None)
    return IngestEventResponse(alert_id=alert.id, alert_type=alert.alert_type.value, severity=alert.severity.value)


@router.get("/alerts", response_model=AlertListResponse)
async def list_alerts(
    tenant_id: str = Query(...),
    severity: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    repository: SentinelRepository = Depends(get_repository),
) -> AlertListResponse:
    alerts, total = await repository.list_alerts(tenant_id, severity, limit=limit, offset=offset)
    return AlertListResponse(items=[_alert_schema(a) for a in alerts], total=total, limit=limit, offset=offset)


@router.get("/alerts/{alert_id}", response_model=AlertSchema)
async def get_alert(
    alert_id: str,
    tenant_id: str = Query(...),
    repository: SentinelRepository = Depends(get_repository),
) -> AlertSchema:
    alert = await repository.get_alert(tenant_id, alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="alert not found")
    return _alert_schema(alert)


@router.get("/baselines/{agent_ref}", response_model=list[BaselineSchema])
async def get_baselines(
    agent_ref: str,
    request: Request,
    ctx: AppContext = Depends(get_ctx),
    repository: SentinelRepository = Depends(get_repository),
) -> list[BaselineSchema]:
    # Deliberately NOT limit/offset paginated (see core/ports.py's list_baselines_for_agent
    # docstring and the README): one AgentBaseline row per (agent, action_type), upserted in
    # place by SentinelEventProcessor, never appended to — bounded by an agent's small,
    # fixed set of distinct action types, not an unbounded growing history like /alerts.
    tenant_id = request.headers.get("X-Tenant-Id", ctx.settings.tenant_id)
    baselines = await repository.list_baselines_for_agent(tenant_id, agent_ref)
    return [_baseline_schema(b) for b in baselines]


@router.post("/config", response_model=ConfigureResponse)
async def configure(body: ConfigureRequest) -> ConfigureResponse:
    # Runtime per-tenant override storage isn't implemented in this build
    # — configuration is sourced from this module's own YAML/env, with
    # `baselining.sensitivity` marked hot-reloadable there. Accepted here
    # so the documented endpoint exists, but it doesn't mutate live
    # behaviour yet.
    return ConfigureResponse(status="acknowledged")
