"""Dependency-stub service for Tool Orchestration.

Stands in for LLM Gateway, Guardrails and Sentinel Agents (the tool-
synthesis dependencies) and doubles as a toy MCP tool server speaking the
JSON-RPC shape `clients/mcp_http_client.py` expects, so this module runs
and tests fully on its own (LLD's Deployability and Testability Contract).
"""
from __future__ import annotations

import uuid

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="Tool Orchestration dependency stub")


class CompletionRequest(BaseModel):
    context: dict
    tenant_id: str


@app.post("/v1/completions")
async def completions(body: CompletionRequest) -> dict:
    return {
        "proposal": {
            "name": "stub_synthesised_tool",
            "mcp_server_ref": "http://dependency-stub:9104/mcp",
            "schema": {"input": {"query": "string"}, "output": {"result": "string"}},
        }
    }


class GuardrailsCheckRequest(BaseModel):
    content: dict
    policy_profile: str
    tenant_id: str


@app.post("/v1/guardrails/check")
async def guardrails_check(body: GuardrailsCheckRequest) -> dict:
    return {"allowed": True, "detail": {"policy_profile": body.policy_profile, "violations": []}}


class SentinelReviewRequest(BaseModel):
    tool_id: str
    proposed_schema: dict
    tenant_id: str


@app.post("/v1/sentinel/reviews")
async def sentinel_review(body: SentinelReviewRequest) -> dict:
    return {"review_id": f"stub-review-{uuid.uuid4().hex[:8]}"}


@app.post("/mcp")
async def mcp_jsonrpc(payload: dict) -> dict:
    """A minimal JSON-RPC `tools/call` responder, so a ToolDefinition can
    point straight at this stub for local dev/integration tests."""
    params = payload.get("params", {})
    return {
        "jsonrpc": "2.0",
        "id": payload.get("id"),
        "result": {"tool": params.get("name"), "arguments": params.get("arguments"), "status": "ok"},
    }


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}
