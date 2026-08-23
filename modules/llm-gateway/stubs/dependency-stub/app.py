"""Dependency-stub service for LLM Gateway.

Stands in for Secrets and Credential Management (provider API keys) and any
provider itself when pointed at by a ProviderConfig's endpoint in the
docker-compose profile, so the module runs and tests fully on its own
(LLD's Deployability and Testability Contract).
"""
from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="LLM Gateway dependency stub")


@app.get("/v1/secrets/provider-key")
async def provider_key(provider: str, tenant_id: str) -> dict:
    return {"api_key": f"stub-key-{provider}"}


class ChatRequest(BaseModel):
    model: str
    messages: list[dict]


@app.post("/chat/completions")
async def chat_completions(body: ChatRequest) -> dict:
    """A minimal OpenAI-compatible completion endpoint, so a ProviderConfig
    can point straight at this stub for local dev/integration tests."""
    return {
        "model": body.model,
        "choices": [{"message": {"role": "assistant", "content": "stubbed provider response"}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "cost": 0.001},
    }


class EmbeddingsRequest(BaseModel):
    model: str
    input: str


@app.post("/embeddings")
async def embeddings(body: EmbeddingsRequest) -> dict:
    return {"data": [{"embedding": [0.1] * 8}]}


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}
