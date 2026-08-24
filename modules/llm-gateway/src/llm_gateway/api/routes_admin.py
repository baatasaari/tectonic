"""`/v1/llm-gateway/admin/*` routes (LLD §3.3)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from llm_gateway.api.deps import get_repository
from llm_gateway.config import BudgetConfig
from llm_gateway.core.cost_governance import CostGovernanceEngine
from llm_gateway.core.domain import VirtualKeyRecord, new_id
from llm_gateway.core.ports import GatewayRepository
from llm_gateway.schemas.admin import (
    BudgetStatusResponse,
    CreateVirtualKeyRequest,
    ProviderStatusResponse,
    VirtualKeyListResponse,
    VirtualKeyResponse,
)

router = APIRouter(prefix="/v1/llm-gateway/admin", tags=["admin"])


@router.post("/virtual-keys", response_model=VirtualKeyResponse, status_code=201)
async def create_virtual_key(
    body: CreateVirtualKeyRequest,
    repository: GatewayRepository = Depends(get_repository),
) -> VirtualKeyResponse:
    if await repository.get_budget_policy(body.budget_policy_ref) is None:
        raise HTTPException(status_code=422, detail=f"unknown budget_policy_ref '{body.budget_policy_ref}'")

    record = VirtualKeyRecord(
        id=new_id(), tenant_id=body.tenant_id, provider_scope=body.provider_scope, budget_policy_ref=body.budget_policy_ref
    )
    record = await repository.create_virtual_key(record)
    return VirtualKeyResponse(
        id=record.id, tenant_id=record.tenant_id, provider_scope=record.provider_scope,
        budget_policy_ref=record.budget_policy_ref, status=record.status.value,
    )


@router.get("/virtual-keys", response_model=VirtualKeyListResponse)
async def list_virtual_keys(
    tenant_id: str,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    repository: GatewayRepository = Depends(get_repository),
) -> VirtualKeyListResponse:
    records, total = await repository.list_virtual_keys(tenant_id, limit=limit, offset=offset)
    return VirtualKeyListResponse(
        items=[
            VirtualKeyResponse(
                id=r.id, tenant_id=r.tenant_id, provider_scope=r.provider_scope,
                budget_policy_ref=r.budget_policy_ref, status=r.status.value,
            )
            for r in records
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/budgets/{budget_policy_id}", response_model=BudgetStatusResponse)
async def get_budget_status(
    budget_policy_id: str,
    repository: GatewayRepository = Depends(get_repository),
) -> BudgetStatusResponse:
    policy = await repository.get_budget_policy(budget_policy_id)
    if policy is None:
        raise HTTPException(status_code=404, detail="budget policy not found")

    ratio = CostGovernanceEngine(repository, BudgetConfig()).utilisation_ratio(policy)
    return BudgetStatusResponse(
        id=policy.id, tenant_id=policy.tenant_id, period=policy.period.value,
        limit_amount=policy.limit_amount, current_spend=policy.current_spend,
        utilisation_ratio=ratio, alert_threshold_pct=policy.alert_threshold_pct,
        alert=ratio >= policy.alert_threshold_pct,
    )


@router.get("/providers", response_model=list[ProviderStatusResponse])
async def list_providers(
    # Deliberately NOT paginated: unlike /virtual-keys, provider configs
    # are a fixed, admin-configured set of LLM providers this gateway
    # integrates with (one row per provider it knows how to call), not a
    # tenant-scoped dataset that grows with usage. `ProviderConfigRecord`
    # has no tenant_id and list_provider_configs() takes no filters — in
    # practice this is a handful of rows (OpenAI, Anthropic, etc.), so
    # limit/offset would add API surface without a real bound to enforce.
    # Revisit if provider configs ever become tenant-configurable.
    repository: GatewayRepository = Depends(get_repository),
) -> list[ProviderStatusResponse]:
    providers = await repository.list_provider_configs()
    return [
        ProviderStatusResponse(
            provider_name=p.provider_name, priority=p.priority, health_status=p.health_status,
            deprecation_notices=p.deprecation_notices,
        )
        for p in providers
    ]
