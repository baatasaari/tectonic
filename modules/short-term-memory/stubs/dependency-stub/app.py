"""Dependency-stub service for Short-Term Memory.

Stands in for LLM Gateway's summarisation endpoint (LLD's Deployability
and Testability Contract: "Runs and tests fully with LLM Gateway stubbed
for the summarisation path").
"""
from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="Short-Term Memory dependency stub")


class SummariseRequest(BaseModel):
    text: str
    tenant_id: str


@app.post("/v1/summarise")
async def summarise(body: SummariseRequest) -> dict:
    line_count = len(body.text.splitlines())
    return {"summary": f"Summary of {line_count} message(s)."}


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}
