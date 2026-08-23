"""Dependency-stub service for Data Source Plugins.

Stands in for both external module dependencies named in the LLD's
Deployability and Testability Contract: Secrets and Credential Management
(returns fake credentials) and the source systems themselves (returns
canned extraction payloads, standing in for real relational
DBs/SaaS APIs/file stores/warehouses behind the generic HTTP connector
runtime — see the module README's "Design notes vs. the LLD").
"""
from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="Data Source Plugins dependency stub")


class ExtractRequest(BaseModel):
    source_type: str
    connection_config: dict[str, Any] = {}
    credentials: dict[str, Any] = {}
    query: dict[str, Any] | None = None


class SecretsResolveRequest(BaseModel):
    secrets_ref: str


@app.post("/v1/extract")
async def extract(body: ExtractRequest) -> dict:
    return {
        "records": [
            {"id": 1, "name": "sample-row-1", "amount": 100},
            {"id": 2, "name": "sample-row-2", "amount": 250},
        ],
        "schema": {"id": "integer", "name": "string", "amount": "integer"},
    }


@app.post("/v1/secrets/resolve")
async def resolve_secrets(body: SecretsResolveRequest) -> dict:
    return {"credentials": {"api_key": "fake-key-for-" + body.secrets_ref}}


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}
