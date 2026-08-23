"""Dependency-stub service for Human Oversight.

Stands in for notification channel webhook endpoints (Slack/Teams/
generic webhook — real HTTP-POST-based adapters call these), the
Workflow Engine approval callback, and Auditability.
"""
from __future__ import annotations

from fastapi import FastAPI

app = FastAPI(title="Human Oversight dependency stub")


@app.post("/v1/notifications/slack")
async def notifications_slack(body: dict) -> dict:
    return {"ok": True}


@app.post("/v1/notifications/teams")
async def notifications_teams(body: dict) -> dict:
    return {"status": "ok"}


@app.post("/v1/notifications/webhook")
async def notifications_webhook(body: dict) -> dict:
    return {"status": "ok"}


@app.post("/v1/workflow-engine/instances/{instance_id}/approvals/{approval_id}/callback")
async def workflow_engine_callback(instance_id: str, approval_id: str, body: dict) -> dict:
    return {"status": "ok"}


@app.post("/v1/auditability/events")
async def auditability_events(body: dict) -> dict:
    return {"status": "ok"}


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}
