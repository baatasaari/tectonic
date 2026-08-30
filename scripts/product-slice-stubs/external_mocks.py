"""Mock external-systems service for the Phase 2 support-agent product
slice (ticket #82, docs/phase2-product-slice-01-support-agent.md).

Mirrors this platform's own `stubs/dependency-stub` shape and conventions
(see e.g. modules/tool-orchestration/stubs/dependency-stub/app.py), but
stands in for systems genuinely outside this platform's own 34 modules --
never for a platform module's own logic, which always runs for real in
this slice:

1. **A real external LLM provider** (OpenAI/Anthropic/etc.). LLM Gateway
   (Module 3) is real and calls this exactly the way it would call any
   real provider's OpenAI-compatible `/chat/completions`/`/embeddings`
   endpoint (see llm_gateway/clients/http_provider_client.py). Responses
   are deterministic and keyed purely on structure (the `model` field
   naming which of this slice's own workflow steps is calling, and the
   JSON-encoded prompt_context each step sends -- see Workflow Engine's
   own HTTPLLMGatewayClient.complete() docstring for why the prompt is
   JSON, not prose) rather than natural-language parsing, so the 3
   scripted conversations are exactly reproducible.
2. **A real merchant's own order-status backend.** Tool Orchestration
   (Module 4) calls this exactly the way it would call any real external
   MCP tool server (JSON-RPC 2.0 `tools/call`, matching every other
   dependency-stub's own `/mcp` handler shape).
3. **Secrets and Credential Management** (deliberately out of this
   slice's critical path per the design doc's own module table) --
   LLM Gateway still needs *some* answer for a provider API key; this
   is the same "dependency-stub substitutes an out-of-scope peer"
   pattern every module's own docker-compose.yml already uses, not new
   scope for this slice.

Zero third-party dependencies beyond fastapi/uvicorn (already a
transitive dependency of every module in this slice).
"""
from __future__ import annotations

import re
import uuid
from typing import Any

from fastapi import FastAPI

app = FastAPI(title="Support-agent slice: external-systems mock")

# ---------------------------------------------------------------------------
# 1. Mock LLM provider -- OpenAI-compatible, called by LLM Gateway's real
#    HTTPProviderClient.
# ---------------------------------------------------------------------------

_ORDER_ID_RE = re.compile(r"#([A-Za-z]\d+)")
_DOLLAR_AMOUNT_RE = re.compile(r"\$\s*([\d,]+(?:\.\d+)?)")


def _find_key(payload: Any, key: str) -> Any:
    """Depth-first search for `key` anywhere in a nested dict/list -- the
    mock composing agent doesn't need to know which exact prior step id
    produced a piece of context, only that it's present somewhere in the
    JSON-serialized prompt_context Workflow Engine sent (see its own
    HTTPLLMGatewayClient.complete() docstring)."""
    if isinstance(payload, dict):
        if key in payload:
            return payload[key]
        for value in payload.values():
            found = _find_key(value, key)
            if found is not None:
                return found
    elif isinstance(payload, list):
        for item in payload:
            found = _find_key(item, key)
            if found is not None:
                return found
    return None


def _compose_content(model: str, prompt_context: dict) -> dict[str, Any]:
    """Deterministic per-agent behavior, keyed on `model` (this slice's own
    workflow definition passes its `agent_ref` straight through as the
    ChatCompletionRequest.model field)."""
    message = prompt_context.get("message", "") if isinstance(prompt_context, dict) else ""

    if model == "order-lookup-agent":
        match = _ORDER_ID_RE.search(message)
        order_id = match.group(1) if match else "UNKNOWN"
        return {"content": "", "tool_arguments": {"order_id": order_id}}

    if model == "refund-extractor-agent":
        match = _DOLLAR_AMOUNT_RE.search(message)
        amount = float(match.group(1).replace(",", "")) if match else 0.0
        return {"content": "", "refund_amount": amount}

    if model == "rag-groundedness-critic":
        # Deterministic and comfortably above Agentic RAG's own default
        # threshold (0.85) -- this slice's own single indexed document is
        # always relevant enough that a real critic call would say so too;
        # a fixed high score here just means the retrieval loop never needs
        # a second hop, not that critique itself is faked away.
        return {"content": "", "score": 0.92, "gaps": ""}

    if model == "rag-query-reformulator":
        # Unreachable in this slice's own scripted conversations (the
        # groundedness score above always clears the threshold on hop 1),
        # kept real and deterministic anyway rather than left broken, per
        # this repo's own "fix the whole gap class once found" discipline.
        query = prompt_context.get("query", "") if isinstance(prompt_context, dict) else ""
        return {"content": "", "revised_query": query}

    if model == "compose-response-agent":
        tool_result = _find_key(prompt_context, "tool_results")
        if tool_result:
            order_status = _find_key(tool_result, "result") or tool_result
            status = _find_key(order_status, "status", ) if isinstance(order_status, dict) else None
            eta = _find_key(order_status, "eta") if isinstance(order_status, dict) else None
            order_id = _find_key(prompt_context, "order_id") or "your order"
            if status:
                return {"content": f"Your order #{order_id} {status}, arriving {eta}." if eta else f"Your order #{order_id} is {status}."}
            return {"content": "I looked up your order but couldn't read the result -- please try again shortly."}

        synthesized_context = _find_key(prompt_context, "synthesized_context")
        if synthesized_context:
            return {"content": f"Here's what our policy says: {synthesized_context}"}

        refund_amount = _find_key(prompt_context, "refund_amount")
        decision = _find_key(prompt_context, "decision")
        if refund_amount is not None:
            if decision == "escalate":
                return {"content": "Thanks for the details -- a specialist has reviewed and resolved your refund request."}
            return {"content": f"Your refund of ${refund_amount:.2f} has been processed."}

        return {"content": "I'm not sure how to help with that yet."}

    # Any other model (e.g. Intent Detection's own LLM-fallback classifier,
    # or a future agent_ref this slice doesn't name): a generic, harmless
    # completion rather than a hard failure.
    return {"content": f"[mock completion for model={model}]"}


@app.post("/chat/completions")
async def chat_completions(body: dict) -> dict:
    model = body.get("model", "")
    messages = body.get("messages", [])
    prompt_context: Any = {}
    if messages:
        import json as _json

        try:
            prompt_context = _json.loads(messages[-1].get("content", "{}"))
        except (ValueError, TypeError):
            prompt_context = {"message": messages[-1].get("content", "")}

    result = _compose_content(model, prompt_context)
    content = result.pop("content")
    return {
        "id": f"mock-{uuid.uuid4().hex[:8]}",
        "model": model,
        "choices": [{"index": 0, "message": {"role": "assistant", "content": _json_dump(content, result)}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 10, "cost": 0.0002},
    }


def _json_dump(content: str, extra: dict) -> str:
    """The mock's own "content" is itself a small JSON envelope (not prose)
    -- see Workflow Engine's HTTPLLMGatewayClient.complete(), which wraps
    whatever LLM Gateway returns as {"content": <this string>} and hands it
    straight to the next step's context unchanged. Steps that need to act
    on structured fields (tool_arguments, refund_amount) get them back
    losslessly this way; the final "respond" step's own content is read by
    Conversational Engine as plain text (session_manager.py's
    _extract_workflow_response_content), so this only matters for the
    non-final steps -- see how it's parsed back out in Workflow Engine's
    NeuralStepExecutor, which treats a JSON-object "content" transparently
    since `response = {"content": ...}` regardless."""
    import json as _json

    if not extra:
        return content
    return _json.dumps({"content": content, **extra})


@app.post("/embeddings")
async def embeddings(body: dict) -> dict:
    text = body.get("input", "")
    # A deterministic, real-shaped (but not semantically trained) embedding:
    # stable per input string, non-degenerate (Vector DB's own contract
    # tests already reject all-zero vectors), cheap to compute.
    seed = sum(ord(c) for c in text) or 1
    vector = [((seed * (i + 1)) % 997) / 997.0 for i in range(16)]
    return {"data": [{"embedding": vector}]}


# ---------------------------------------------------------------------------
# 2. Mock merchant order-status backend, called by Tool Orchestration's
#    real HTTPMCPClientAdapter (JSON-RPC 2.0 tools/call).
# ---------------------------------------------------------------------------

_ORDERS: dict[str, dict[str, Any]] = {
    "A1029": {"order_id": "A1029", "status": "shipped", "eta": "2026-09-02"},
    "A1030": {"order_id": "A1030", "status": "processing", "eta": None},
}


@app.post("/mcp")
async def mcp_jsonrpc(payload: dict) -> dict:
    params = payload.get("params", {})
    name = params.get("name")
    arguments = params.get("arguments", {})

    if name == "get_order_status":
        order_id = arguments.get("order_id", "")
        record = _ORDERS.get(order_id)
        if record is None:
            return {
                "jsonrpc": "2.0", "id": payload.get("id"),
                "error": {"code": -32001, "message": f"no such order '{order_id}'"},
            }
        return {"jsonrpc": "2.0", "id": payload.get("id"), "result": record}

    return {"jsonrpc": "2.0", "id": payload.get("id"), "error": {"code": -32601, "message": f"unknown tool '{name}'"}}


# ---------------------------------------------------------------------------
# 3. Secrets and Credential Management stub -- LLM Gateway's own
#    HTTPSecretsClient.get_provider_api_key(); deliberately out of this
#    slice's critical path per the design doc's own module table.
# ---------------------------------------------------------------------------


@app.get("/v1/secrets/provider-key")
async def provider_key(provider: str, tenant_id: str) -> dict:
    return {"api_key": f"mock-key-for-{provider}"}


# ---------------------------------------------------------------------------
# 4. Graph DB stub -- deliberately out of this slice's critical path per the
#    design doc's own module table; Knowledge Base's real ingestion pipeline
#    still calls it unconditionally, so it needs *some* answer, exactly the
#    same "dependency-stub substitutes an out-of-scope peer" pattern every
#    module's own docker-compose.yml already uses.
# ---------------------------------------------------------------------------


@app.post("/v1/extract-entities")
async def extract_entities(body: dict) -> dict:
    return {"entities": [], "relationships": []}


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}
