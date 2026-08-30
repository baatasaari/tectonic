"""Request/response models for the `/v1/workflow-engine/definitions` endpoints
(LLD §3.3)."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel

from workflow_engine.core.parser import GraphSchema


class SymbolicRuleSchema(BaseModel):
    id: str
    when: str
    then: dict[str, Any]
    priority: int = 0


class CreateDefinitionRequest(BaseModel):
    name: str
    graph_schema: GraphSchema
    # Ticket #82 (Phase 2 support-agent slice): before this, there was no
    # real way at all -- through this module's own API -- to configure a
    # symbolic_rule_ref a `execution_mode=symbolic` node could actually
    # evaluate; SymbolicRuleExecutor.register_ruleset() was only ever called
    # directly in-process, by unit tests. A definition now carries its own
    # rulesets, registered into this process's shared SymbolicRuleExecutor
    # when the definition is created (see routes_definitions.py) -- a real,
    # documented simplification: a multi-replica deployment would need this
    # broadcast to every replica (or persisted and loaded per-process at
    # startup), the same class of gap this platform already documents
    # elsewhere for per-process state (e.g. Sentinel Agents' own sliding
    # window).
    symbolic_rulesets: dict[str, list[SymbolicRuleSchema]] = {}


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
