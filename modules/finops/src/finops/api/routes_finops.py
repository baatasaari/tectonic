"""`/v1/finops/*` routes (LLD §3)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from finops.api.deps import (
    build_budget_policy_service,
    build_cost_optimisation_agent,
    build_usage_aggregation_service,
    get_ctx,
    get_repository,
    resolve_tenant_id,
)
from finops.app_context import AppContext
from finops.core.domain import BudgetPeriod, BudgetPolicyNotFoundError, UsageEventRecord, new_id
from finops.core.ports import FinOpsRepository
from finops.schemas.finops import (
    BudgetPolicySchema,
    CostReportSchema,
    CreateBudgetPolicyRequest,
    OptimisationActionListResponse,
    OptimisationActionSchema,
    ReportUsageEventRequest,
    UsageEventSchema,
)

router = APIRouter(prefix="/v1/finops", tags=["finops"])


def _policy_schema(policy) -> BudgetPolicySchema:
    return BudgetPolicySchema(
        id=policy.id, tenant_id=policy.tenant_id, period=policy.period.value, limit_amount=policy.limit_amount,
        alert_threshold_pct=policy.alert_threshold_pct, created_at=policy.created_at, updated_at=policy.updated_at,
    )


def _action_schema(action) -> OptimisationActionSchema:
    return OptimisationActionSchema(
        id=action.id, tenant_id=action.tenant_id, budget_policy_id=action.budget_policy_id,
        action_type=action.action_type, previous_value=action.previous_value, new_value=action.new_value,
        reason=action.reason, taken_at=action.taken_at,
    )


@router.post("/usage-events", response_model=UsageEventSchema, status_code=201)
async def report_usage_event(
    body: ReportUsageEventRequest,
    tenant_id: str = Depends(resolve_tenant_id),
    repository: FinOpsRepository = Depends(get_repository),
) -> UsageEventSchema:
    record = UsageEventRecord(
        id=new_id(), tenant_id=tenant_id, source_module=body.source_module, resource_type=body.resource_type,
        quantity=body.quantity, unit_cost=body.unit_cost, cost=body.quantity * body.unit_cost,
    )
    saved = await repository.create_usage_event(record)
    return UsageEventSchema(
        id=saved.id, tenant_id=saved.tenant_id, source_module=saved.source_module, resource_type=saved.resource_type,
        quantity=saved.quantity, unit_cost=saved.unit_cost, cost=saved.cost, occurred_at=saved.occurred_at,
    )


@router.get("/cost-reports/{tenant_id}", response_model=CostReportSchema)
async def get_cost_report(
    tenant_id: str,
    period: str = Query(...),
    budget_policy_id: str | None = Query(None),
    ctx: AppContext = Depends(get_ctx),
    repository: FinOpsRepository = Depends(get_repository),
) -> CostReportSchema:
    budget_policy = await repository.get_budget_policy(budget_policy_id) if budget_policy_id else None
    if budget_policy_id and budget_policy is None:
        raise HTTPException(status_code=404, detail=str(BudgetPolicyNotFoundError(budget_policy_id)))

    service = build_usage_aggregation_service(repository, ctx)
    report = await service.cost_report(tenant_id=tenant_id, period=BudgetPeriod(period), budget_policy=budget_policy)
    return CostReportSchema(
        tenant_id=report.tenant_id, period=report.period.value, llm_gateway_spend=report.llm_gateway_spend,
        other_usage_cost=report.other_usage_cost, total_cost=report.total_cost, forecast_amount=report.forecast_amount,
        budget_policy=_policy_schema(report.budget_policy) if report.budget_policy else None,
        utilisation_ratio=report.utilisation_ratio, alert=report.alert,
    )


@router.post("/budget-policies", response_model=BudgetPolicySchema, status_code=201)
async def create_budget_policy(
    body: CreateBudgetPolicyRequest,
    tenant_id: str = Depends(resolve_tenant_id),
    repository: FinOpsRepository = Depends(get_repository),
) -> BudgetPolicySchema:
    service = build_budget_policy_service(repository)
    policy = await service.create(
        tenant_id=tenant_id, period=BudgetPeriod(body.period), limit_amount=body.limit_amount,
        alert_threshold_pct=body.alert_threshold_pct,
    )
    return _policy_schema(policy)


@router.get("/budget-policies/{budget_policy_id}", response_model=BudgetPolicySchema)
async def get_budget_policy(
    budget_policy_id: str,
    repository: FinOpsRepository = Depends(get_repository),
) -> BudgetPolicySchema:
    service = build_budget_policy_service(repository)
    try:
        policy = await service.get(budget_policy_id)
    except BudgetPolicyNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _policy_schema(policy)


@router.post("/budget-policies/{budget_policy_id}/evaluate", response_model=OptimisationActionSchema | None)
async def evaluate_budget_policy(
    budget_policy_id: str,
    response: Response,
    ctx: AppContext = Depends(get_ctx),
    repository: FinOpsRepository = Depends(get_repository),
) -> OptimisationActionSchema | None:
    policy_service = build_budget_policy_service(repository)
    try:
        policy = await policy_service.get(budget_policy_id)
    except BudgetPolicyNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    agent = build_cost_optimisation_agent(repository, ctx)
    action = await agent.evaluate(policy)
    if action is None:
        response.status_code = 204
        return None
    return _action_schema(action)


@router.get("/budget-policies/{budget_policy_id}/actions", response_model=OptimisationActionListResponse)
async def list_optimisation_actions(
    budget_policy_id: str,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    repository: FinOpsRepository = Depends(get_repository),
) -> OptimisationActionListResponse:
    actions, total = await repository.list_optimisation_actions(budget_policy_id=budget_policy_id, limit=limit, offset=offset)
    return OptimisationActionListResponse(items=[_action_schema(a) for a in actions], total=total, limit=limit, offset=offset)
