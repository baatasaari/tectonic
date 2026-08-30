"""Dependency-stub service for A2A.

Plays two roles so this module's own full round trip -- both directions
-- is exercised end to end without either a real third-party agent or a
real Workflow Engine deployed alongside it, per the LLD's Deployability
and Testability Contract:

1. An external A2A peer -- serves its own Agent Card at
   `/.well-known/agent.json` and a canned `message/send` response,
   exercising `DelegationService` (outbound).
2. A stand-in for Workflow Engine's `POST /v1/workflow-engine/instances`,
   exercising `InboundGateway` (inbound).
"""
from __future__ import annotations

from fastapi import FastAPI

app = FastAPI(title="A2A dependency stub")

_CARD = {
    "name": "dependency-stub-peer",
    "description": "Canned external A2A peer used by this module's own docker-compose stack.",
    "url": "http://dependency-stub:9122",
    "skills": [{"id": "summarize", "name": "Summarize", "description": "Canned summarization skill."}],
}


@app.get("/.well-known/agent.json")
async def agent_card() -> dict:
    return _CARD


@app.post("/v1/a2a/rpc")
async def rpc(body: dict) -> dict:
    method = body.get("method")
    request_id = body.get("id")

    if method == "message/send":
        # Canned success -- a real peer would dispatch on params["skill_id"]; this stub
        # just proves the wiring, matching this platform's "stub returns canned data,
        # real behavior is exercised by the unit tier's fakes" convention.
        result = {"status": "completed", "artifacts": [{"summary": "canned summary from the dependency stub"}]}
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32601, "message": "Method not found"}}


@app.post("/v1/workflow-engine/instances")
async def start_instance(body: dict) -> dict:
    return {"id": "stub-instance-1", "status": "running", "trace_id": "stub-trace-1"}


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}

@app.get("/v1/multi-tenancy/tenants/{tenant_id}/gate")
async def gate(tenant_id: str, module: str | None = None) -> dict:
    return {"allowed": True, "reason": "active"}
