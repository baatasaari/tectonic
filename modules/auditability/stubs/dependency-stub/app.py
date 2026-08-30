"""Dependency-stub service for Auditability.

Stands in for LLM Gateway (Module 3) — Auditability's one external
dependency, used only for natural-language query translation. Every
other endpoint this module exposes (ingest, list, verify-chain, audit
packs) is served entirely by this module's own database, no stub needed.
"""
from __future__ import annotations

from fastapi import FastAPI

app = FastAPI(title="Auditability dependency stub")


@app.post("/v1/completions")
async def complete(body: dict) -> dict:
    # Canned, empty filter -- a real LLM Gateway call would return a filter derived
    # from body["context"]["question"]; this stub just proves the wiring, matching
    # this platform's "stub returns canned data, real behavior is exercised by the
    # unit tier's StubLLMGatewayClient with a controllable proposal" convention.
    return {"proposal": {}}


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}
