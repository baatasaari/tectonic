"""Dependency-stub service.

Stands in for LLM Gateway, Tool Orchestration, Guardrails and Human
Oversight — the four external module dependencies Workflow Engine talks to
at runtime — so this module can be deployed and integration-tested fully on
its own, per the LLD's Deployability and Testability Contract (§Level 1):
"this module runs and tests fully with LLM Gateway, Tool Orchestration,
Guardrails, Observability, Auditability, Human Oversight and Long-Term
Memory stubbed via a docker-compose profile."

Not a mock of any one module's real API surface — just enough of a fixed
contract for Workflow Engine's HTTP clients (clients/http_clients.py) to
drive against. Swap in the real modules by pointing config at them instead.
"""
from __future__ import annotations

import uuid

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="Workflow Engine dependency stub")


class CompletionRequest(BaseModel):
    agent_ref: str
    context: dict
    tenant_id: str


@app.post("/v1/completions")
async def complete(body: CompletionRequest) -> dict:
    return {
        "response": {"content": f"stub completion for agent '{body.agent_ref}'", "tool_arguments": {}},
        "confidence_score": 0.97,
    }


class ToolInvokeRequest(BaseModel):
    tool_ref: str
    arguments: dict
    tenant_id: str


@app.post("/v1/tools/invoke")
async def invoke_tool(body: ToolInvokeRequest) -> dict:
    return {"tool_ref": body.tool_ref, "result": "stub-ok", "arguments": body.arguments}


class GuardrailsCheckRequest(BaseModel):
    content: dict
    policy_profile: str
    tenant_id: str


@app.post("/v1/guardrails/check")
async def guardrails_check(body: GuardrailsCheckRequest) -> dict:
    return {"allowed": True, "detail": {"policy_profile": body.policy_profile, "violations": []}}


class OversightRequest(BaseModel):
    approval_request_id: str
    step_execution_id: str
    context: dict
    tenant_id: str


@app.post("/v1/oversight/requests")
async def oversight_request(body: OversightRequest) -> dict:
    return {"human_oversight_ref_id": f"stub-ho-{uuid.uuid4().hex[:8]}"}


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}
