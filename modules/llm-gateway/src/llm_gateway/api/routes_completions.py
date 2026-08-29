"""`/v1/llm-gateway/chat/completions` and `/v1/llm-gateway/embeddings`
(LLD §3.3). OpenAI-compatible request/response schema so any existing
OpenAI-SDK-based client can point here with a base URL change.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Response

from llm_gateway.api.deps import build_gateway_service, get_ctx, get_repository
from llm_gateway.app_context import AppContext
from llm_gateway.core.domain import (
    AllProvidersExhaustedError,
    BudgetExceededError,
    ChatMessage,
    CompletionRequest,
    ProviderError,
    QuotaExceededError,
    VirtualKeyInvalidError,
)
from llm_gateway.core.ports import GatewayRepository
from llm_gateway.schemas.completions import (
    ChatCompletionChoice,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatMessageSchema,
    EmbeddingsRequest,
    EmbeddingsResponse,
)

router = APIRouter(prefix="/v1/llm-gateway", tags=["completions"])


@router.post("/chat/completions", response_model=ChatCompletionResponse)
async def chat_completions(
    body: ChatCompletionRequest,
    response: Response,
    x_virtual_key: str = Header(..., alias="X-Virtual-Key"),
    x_tenant_id: str = Header(..., alias="X-Tenant-Id"),
    ctx: AppContext = Depends(get_ctx),
    repository: GatewayRepository = Depends(get_repository),
) -> ChatCompletionResponse:
    service = await build_gateway_service(ctx, repository)
    request = CompletionRequest(
        model=body.model,
        messages=[ChatMessage(role=m.role, content=m.content) for m in body.messages],
        tenant_id=x_tenant_id,
        virtual_key_id=x_virtual_key,
        routing_hints=body.routing_hints,
        task_type=body.routing_hints.get("task_type", "chat"),
    )

    try:
        result = await service.complete(request)
    except VirtualKeyInvalidError as e:
        raise HTTPException(status_code=401, detail=str(e)) from e
    except BudgetExceededError as e:
        raise HTTPException(status_code=429, detail=str(e)) from e
    except QuotaExceededError as e:
        raise HTTPException(status_code=429, detail=str(e)) from e
    except AllProvidersExhaustedError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
    except ProviderError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e

    response.headers["x-provider-used"] = result.provider_used
    response.headers["x-cache-hit"] = str(result.cache_hit).lower()
    response.headers["x-cost"] = str(result.cost)

    return ChatCompletionResponse(
        id=uuid.uuid4().hex,
        model=result.model_used,
        choices=[ChatCompletionChoice(message=ChatMessageSchema(role="assistant", content=result.content))],
        provider_used=result.provider_used,
        cache_hit=result.cache_hit,
        cost=result.cost,
        usage={
            "prompt_tokens": result.input_tokens,
            "completion_tokens": result.output_tokens,
            "total_tokens": result.input_tokens + result.output_tokens,
        },
    )


@router.post("/embeddings", response_model=EmbeddingsResponse)
async def embeddings(
    body: EmbeddingsRequest,
    x_virtual_key: str = Header(..., alias="X-Virtual-Key"),
    x_tenant_id: str = Header(..., alias="X-Tenant-Id"),
    ctx: AppContext = Depends(get_ctx),
    repository: GatewayRepository = Depends(get_repository),
) -> EmbeddingsResponse:
    vk = await repository.get_virtual_key(x_virtual_key)
    if vk is None or vk.status.value != "active" or vk.tenant_id != x_tenant_id:
        raise HTTPException(status_code=401, detail="invalid virtual key")

    providers = await repository.list_provider_configs()
    ctx.provider_client.set_providers({p.provider_name: p for p in providers})

    eligible = [p for p in providers if p.health_status != "down" and (not vk.provider_scope or p.provider_name in vk.provider_scope)]
    if not eligible:
        raise HTTPException(status_code=502, detail="no eligible provider for embeddings")
    provider = min(eligible, key=lambda p: p.priority).provider_name

    try:
        vector = await ctx.provider_client.embed(provider=provider, model=body.model, text=body.input, tenant_id=x_tenant_id)
    except ProviderError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e

    return EmbeddingsResponse(
        model=body.model, data=[{"index": 0, "embedding": vector}], provider_used=provider
    )
