"""Request/response models for the `/v1/workflow-engine/definitions` endpoints
(LLD §3.3)."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from workflow_engine.core.parser import GraphSchema


class CreateDefinitionRequest(BaseModel):
    name: str
    graph_schema: GraphSchema


class DefinitionSummary(BaseModel):
    id: str
    version: int
    status: str


class DefinitionDetail(BaseModel):
    id: str
    name: str
    version: int
    status: str
    graph_schema: dict
    tenant_id: str
    created_by: str
    created_at: datetime
    published_at: datetime | None = None


class PublishDefinitionResponse(BaseModel):
    status: str
    published_at: datetime | None = None
