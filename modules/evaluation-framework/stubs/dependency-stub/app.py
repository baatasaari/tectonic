"""Dependency-stub service for Evaluation Framework.

Stands in for LLM Gateway's LLM-as-judge fallback — the LLD's
Deployability and Testability Contract: "Runs and tests fully with LLM
Gateway stubbed."
"""
from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="Evaluation Framework dependency stub")


class JudgeRequest(BaseModel):
    agent_output: str
    metric_name: str
    reference_data: dict


@app.post("/v1/judge")
async def judge(body: JudgeRequest) -> dict:
    return {"score": 0.8}


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}
