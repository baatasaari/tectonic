"""`/v1/agentic-rag/*` routes (LLD §3.3)."""
from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, Request

from agentic_rag.api.deps import build_rag_service, get_ctx, get_repository
from agentic_rag.app_context import AppContext
from agentic_rag.core.ports import RAGRepository
from agentic_rag.schemas.rag import HopSummary, RequestDetail, RetrieveRequest, RetrieveResponse

router = APIRouter(prefix="/v1/agentic-rag", tags=["agentic-rag"])


def _tenant_id(request: Request, ctx: AppContext) -> str:
    return request.headers.get("X-Tenant-Id", ctx.settings.tenant_id)


@router.post("/retrieve", response_model=RetrieveResponse)
async def retrieve(
    body: RetrieveRequest,
    request: Request,
    ctx: AppContext = Depends(get_ctx),
    repository: RAGRepository = Depends(get_repository),
) -> RetrieveResponse:
    tenant_id = _tenant_id(request, ctx)
    service = build_rag_service(ctx, repository)

    result = await service.retrieve(
        query=body.query,
        scope=body.scope,
        tenant_id=tenant_id,
        max_hops=body.max_hops or ctx.settings.retrieval.max_hops,
        groundedness_threshold=body.groundedness_threshold or ctx.settings.retrieval.groundedness_threshold,
    )
    return RetrieveResponse(
        synthesized_context=result.final_context,
        groundedness_score=result.final_groundedness_score,
        hop_count=result.total_hops,
        outcome=result.outcome.value,
        provenance_chain=[asdict(p) for p in result.provenance_chain],
    )


@router.get("/requests/{request_id}", response_model=RequestDetail)
async def get_request(
    request_id: str,
    repository: RAGRepository = Depends(get_repository),
) -> RequestDetail:
    req = await repository.get_request(request_id)
    if req is None:
        raise HTTPException(status_code=404, detail="retrieval request not found")
    hops = await repository.list_hops(request_id)
    result = await repository.get_result(request_id)

    return RequestDetail(
        id=req.id, tenant_id=req.tenant_id, query=req.query, scope=req.scope, max_hops=req.max_hops,
        groundedness_threshold=req.groundedness_threshold, created_at=req.created_at,
        hops=[
            HopSummary(
                hop_number=h.hop_number, reformulated_query=h.reformulated_query,
                groundedness_score=h.groundedness_score, item_count=len(h.retrieved_items),
            )
            for h in hops
        ],
        result=RetrieveResponse(
            synthesized_context=result.final_context, groundedness_score=result.final_groundedness_score,
            hop_count=result.total_hops, outcome=result.outcome.value,
            provenance_chain=[asdict(p) for p in result.provenance_chain],
        ) if result else None,
    )
