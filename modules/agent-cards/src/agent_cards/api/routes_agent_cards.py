"""`/v1/agent-cards/*` routes (LLD §3)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from agent_cards.api.deps import (
    build_discovery_service,
    build_registry_service,
    build_trust_score_calculator,
    get_ctx,
    get_repository,
    resolve_tenant_id,
)
from agent_cards.app_context import AppContext
from agent_cards.core.domain import AgentCardNotFoundError, AgentSkill
from agent_cards.core.ports import AgentCardsRepository
from agent_cards.schemas.agent_cards import (
    AgentCardListResponse,
    AgentCardSchema,
    AgentSkillSchema,
    RegisterCardRequest,
    TrustScoreBreakdownSchema,
    UpdateCardRequest,
)

router = APIRouter(prefix="/v1/agent-cards", tags=["agent-cards"])


def _reject_null_byte_query(**params: str | None) -> None:
    """A raw `Query()` string parameter never runs through a Pydantic
    body field's own NUL-byte validator -- a real CI run of a sibling
    module's contract tier (ticket #82) surfaced this exact bug class
    on a raw query parameter, an `UntranslatableCharacterError` at the
    database instead of a clean 422. Applied at the top of every route
    below taking a free-text (non-enum) query parameter."""
    for name, value in params.items():
        if value is not None and "\x00" in value:
            raise HTTPException(status_code=422, detail=f"{name} must not contain a NUL byte")


def _card_schema(card, *, is_stale: bool) -> AgentCardSchema:
    return AgentCardSchema(
        id=card.id, tenant_id=card.tenant_id, agent_ref=card.agent_ref, name=card.name, description=card.description,
        url=card.url, skills=[AgentSkillSchema(id=s.id, name=s.name, description=s.description) for s in card.skills],
        trust_score=card.trust_score, trust_score_computed_at=card.trust_score_computed_at,
        last_verified_at=card.last_verified_at, is_stale=is_stale, created_at=card.created_at, updated_at=card.updated_at,
    )


@router.post("", response_model=AgentCardSchema, status_code=201)
async def register_card(
    body: RegisterCardRequest,
    tenant_id: str = Depends(resolve_tenant_id),
    ctx: AppContext = Depends(get_ctx),
    repository: AgentCardsRepository = Depends(get_repository),
) -> AgentCardSchema:
    service = build_registry_service(repository)
    skills = [AgentSkill(id=s.id, name=s.name, description=s.description) for s in body.skills]
    card = await service.register(
        tenant_id=tenant_id, agent_ref=body.agent_ref, name=body.name, description=body.description,
        url=body.url, skills=skills,
    )
    return _card_schema(card, is_stale=card.is_stale(ttl_seconds=ctx.settings.card_staleness_ttl_seconds))


@router.get("", response_model=AgentCardListResponse)
async def discover_cards(
    tenant_id: str | None = Query(None),
    skill_id: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0, le=1_000_000_000),
    ctx: AppContext = Depends(get_ctx),
    repository: AgentCardsRepository = Depends(get_repository),
) -> AgentCardListResponse:
    _reject_null_byte_query(tenant_id=tenant_id, skill_id=skill_id)
    service = build_discovery_service(repository, ctx)
    results, total = await service.search(tenant_id=tenant_id, skill_id=skill_id, limit=limit, offset=offset)
    items = [_card_schema(card, is_stale=is_stale) for card, is_stale in results]
    return AgentCardListResponse(items=items, total=total, limit=limit, offset=offset)


@router.get("/{card_id}", response_model=AgentCardSchema)
async def get_card(
    card_id: str,
    ctx: AppContext = Depends(get_ctx),
    repository: AgentCardsRepository = Depends(get_repository),
) -> AgentCardSchema:
    service = build_registry_service(repository)
    try:
        card = await service.get(card_id)
    except AgentCardNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _card_schema(card, is_stale=card.is_stale(ttl_seconds=ctx.settings.card_staleness_ttl_seconds))


@router.put("/{card_id}", response_model=AgentCardSchema)
async def update_card(
    card_id: str,
    body: UpdateCardRequest,
    ctx: AppContext = Depends(get_ctx),
    repository: AgentCardsRepository = Depends(get_repository),
) -> AgentCardSchema:
    service = build_registry_service(repository)
    skills = [AgentSkill(id=s.id, name=s.name, description=s.description) for s in body.skills] if body.skills is not None else None
    try:
        card = await service.update(
            card_id, name=body.name, description=body.description, url=body.url, skills=skills,
        )
    except AgentCardNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _card_schema(card, is_stale=card.is_stale(ttl_seconds=ctx.settings.card_staleness_ttl_seconds))


@router.post("/{card_id}/recompute-trust-score", response_model=TrustScoreBreakdownSchema)
async def recompute_trust_score(
    card_id: str,
    ctx: AppContext = Depends(get_ctx),
    repository: AgentCardsRepository = Depends(get_repository),
) -> TrustScoreBreakdownSchema:
    registry = build_registry_service(repository)
    try:
        card = await registry.get(card_id)
    except AgentCardNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    calculator = build_trust_score_calculator(repository, ctx)
    breakdown = await calculator.recompute(card)
    return TrustScoreBreakdownSchema(
        performance_score=breakdown.performance_score, compliance_score=breakdown.compliance_score,
        trust_score=breakdown.trust_score, computed_at=breakdown.computed_at,
    )
