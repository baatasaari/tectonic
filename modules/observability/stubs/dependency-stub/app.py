"""Dependency-stub service for Observability.

Stands in for LLM Gateway's narrative-generation call — the LLD's
Deployability and Testability Contract: "LLM Gateway stubbed for
reasoning narrative generation."
"""
from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="Observability dependency stub")


class NarrateRequest(BaseModel):
    trace_summary: list[dict]


@app.post("/v1/narrate")
async def narrate(body: NarrateRequest) -> dict:
    steps = " -> ".join(s.get("name", "unknown") for s in body.trace_summary)
    return {"narrative": f"[stub narrative] steps observed: {steps}"}


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}
