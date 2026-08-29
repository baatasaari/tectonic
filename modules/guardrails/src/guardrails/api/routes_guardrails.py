"""`/v1/guardrails/*` routes (LLD §3)."""
from __future__ import annotations

import time

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from guardrails.api.deps import build_policy_engine, build_red_team_runner, get_ctx, get_repository
from guardrails.app_context import AppContext
from guardrails.core.domain import CheckStage, InterventionLogRecord, PolicyProfileRecord, new_id
from guardrails.core.ports import GuardrailsRepository
from guardrails.schemas.checks import (
    BypassIncidentSchema,
    CheckRequest,
    CheckResponse,
    CreatePolicyProfileRequest,
    PolicyProfileSchema,
    RedTeamRunListResponse,
    RedTeamRunSchema,
    TriggerRedTeamRunResponse,
)

router = APIRouter(prefix="/v1/guardrails", tags=["guardrails"])


def _tenant_id(request: Request, ctx: AppContext) -> str:
    return request.headers.get("X-Tenant-Id", ctx.settings.tenant_id)


def _default_profile(tenant_id: str, ctx: AppContext) -> PolicyProfileRecord:
    """A real tenant with no policy profile of its own yet (ticket #82
    surfaced this against a freshly-seeded tenant, never exercised by any
    prior stubbed test): an in-memory, never-persisted stand-in, not a
    real row `get_policy_profile` could ever look up again by this id --
    that's fine for `engine.evaluate()`, which only reads its fields, but
    `id` still has to be a real UUID, not the literal string "default",
    because `create_intervention_log` below writes `profile.id` into a
    genuine UUID column: the literal string doesn't round-trip through
    asyncpg's own UUID codec and 500s the whole check, exactly the class
    of gap this ticket keeps finding once a module runs for real. A fresh
    id per call is fine -- nothing needs to look this profile up again by
    it, unlike a real, persisted profile's id.
    """
    enabled = []
    if ctx.settings.checks.pii_detection_enabled:
        enabled.append("pii_detection")
    if ctx.settings.checks.jailbreak_detection_enabled:
        enabled.append("jailbreak_detection")
    if ctx.settings.checks.groundedness_check_enabled:
        enabled.append("groundedness_check")
    return PolicyProfileRecord(
        id=new_id(), tenant_id=tenant_id, name="default", enabled_checks=enabled,
        pii_entity_types=ctx.settings.pii.entity_types, denied_topics=ctx.settings.checks.denied_topics,
        groundedness_threshold=ctx.settings.groundedness.threshold,
    )


def _profile_schema(p: PolicyProfileRecord) -> PolicyProfileSchema:
    return PolicyProfileSchema(
        id=p.id, tenant_id=p.tenant_id, name=p.name, enabled_checks=p.enabled_checks,
        pii_entity_types=p.pii_entity_types, denied_topics=p.denied_topics,
        groundedness_threshold=p.groundedness_threshold, status=p.status, created_at=p.created_at,
    )


@router.post("/check", response_model=CheckResponse)
async def check(
    body: CheckRequest,
    request: Request,
    ctx: AppContext = Depends(get_ctx),
    repository: GuardrailsRepository = Depends(get_repository),
) -> CheckResponse:
    tenant_id = _tenant_id(request, ctx)

    if body.policy_profile_id:
        profile = await repository.get_policy_profile(tenant_id, body.policy_profile_id)
        if profile is None:
            raise HTTPException(status_code=404, detail="policy profile not found")
    else:
        profile = await repository.get_default_policy_profile(tenant_id) or _default_profile(tenant_id, ctx)

    engine = build_policy_engine(ctx)
    started = time.perf_counter()
    result = await engine.evaluate(body.text, CheckStage(body.stage), profile, tenant_id, context=body.context)
    latency_ms = (time.perf_counter() - started) * 1000

    await repository.create_intervention_log(
        InterventionLogRecord(
            id=new_id(), tenant_id=tenant_id, policy_profile_id=profile.id, stage=CheckStage(body.stage),
            check_type=",".join(result.checks_run), decision=result.decision,
            violation_category=result.violation_category, latency_ms=latency_ms,
        )
    )

    return CheckResponse(
        decision=result.decision.value, violation_category=result.violation_category,
        redacted_text=result.redacted_text, checks_run=result.checks_run,
    )


@router.post("/policy-profiles", response_model=PolicyProfileSchema, status_code=201)
async def create_policy_profile(
    body: CreatePolicyProfileRequest,
    repository: GuardrailsRepository = Depends(get_repository),
) -> PolicyProfileSchema:
    record = PolicyProfileRecord(
        id=new_id(), tenant_id=body.tenant_id, name=body.name, enabled_checks=body.enabled_checks,
        pii_entity_types=body.entity_types, denied_topics=body.denied_topics,
        groundedness_threshold=body.groundedness_threshold,
    )
    record = await repository.create_policy_profile(record)
    return _profile_schema(record)


@router.get("/red-team-runs", response_model=RedTeamRunListResponse)
async def list_red_team_runs(
    tenant_id: str = Query(...),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    repository: GuardrailsRepository = Depends(get_repository),
) -> RedTeamRunListResponse:
    runs, total = await repository.list_red_team_runs(tenant_id, limit=limit, offset=offset)
    schemas = []
    for run in runs:
        incidents = await repository.list_bypass_incidents(run.id)
        schemas.append(
            RedTeamRunSchema(
                id=run.id, attempts_generated=run.attempts_generated, successful_bypasses=run.successful_bypasses,
                run_at=run.run_at,
                bypass_incidents=[
                    BypassIncidentSchema(
                        id=i.id, attack_pattern=i.attack_pattern, target_check=i.target_check,
                        severity=i.severity, resolved=i.resolved,
                    )
                    for i in incidents
                ],
            )
        )
    return RedTeamRunListResponse(items=schemas, total=total, limit=limit, offset=offset)


@router.post("/red-team-runs/trigger", response_model=TriggerRedTeamRunResponse, status_code=201)
async def trigger_red_team_run(
    request: Request,
    ctx: AppContext = Depends(get_ctx),
    repository: GuardrailsRepository = Depends(get_repository),
) -> TriggerRedTeamRunResponse:
    tenant_id = _tenant_id(request, ctx)
    shadow_profile = await repository.get_default_policy_profile(tenant_id) or _default_profile(tenant_id, ctx)
    runner = build_red_team_runner(ctx, repository)
    run = await runner.run(tenant_id, shadow_profile)
    return TriggerRedTeamRunResponse(run_id=run.id)
