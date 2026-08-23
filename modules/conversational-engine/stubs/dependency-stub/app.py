"""Dependency-stub service for Conversational Engine.

Stands in for LLM Gateway, Guardrails, Long-Term Memory, Human Oversight,
Observability and Auditability so this module can be deployed and
integration-tested fully on its own (LLD's Deployability and Testability
Contract). Same pattern as Module 1's stubs/dependency-stub.
"""
from __future__ import annotations

import json
import uuid

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

app = FastAPI(title="Conversational Engine dependency stub")


class StreamRequest(BaseModel):
    context: dict
    tenant_id: str


@app.post("/v1/completions/stream")
async def completions_stream(body: StreamRequest) -> StreamingResponse:
    async def gen():
        for chunk in ["Sure, ", "here's ", "a stubbed ", "streamed ", "answer."]:
            yield f"data: {json.dumps({'text': chunk})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


class ClassifyRequest(BaseModel):
    text: str
    taxonomy: list[str]
    tenant_id: str


@app.post("/v1/classify")
async def classify(body: ClassifyRequest) -> dict:
    scores = {label: (1.0 if label == "calm" else 0.0) for label in body.taxonomy}
    return {"scores": scores}


class GuardrailsCheckRequest(BaseModel):
    content: dict
    policy_profile: str
    tenant_id: str


@app.post("/v1/guardrails/check")
async def guardrails_check(body: GuardrailsCheckRequest) -> dict:
    return {"allowed": True, "detail": {"policy_profile": body.policy_profile, "violations": []}}


@app.get("/v1/memory/identity")
async def recall_identity(user_ref: str, tenant_id: str) -> dict:
    return {"user_ref": user_ref, "known": False}


class HandoffRequest(BaseModel):
    session_id: str
    trigger_reason: str
    context: dict
    tenant_id: str


@app.post("/v1/oversight/handoff-request")
async def handoff_request(body: HandoffRequest) -> dict:
    return {"human_oversight_ref_id": f"stub-ho-{uuid.uuid4().hex[:8]}"}


@app.post("/v1/observability/events")
async def observability_event(event: dict) -> dict:
    return {"status": "accepted"}


@app.post("/v1/auditability/events")
async def auditability_event(event: dict) -> dict:
    return {"status": "accepted"}


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}
