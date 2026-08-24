"""Ingestion Service (LLD §Level 3 "Sequence: event ingestion and
chaining"): the one entry point every inbound `POST /events` call goes
through. `source_module` is resolved by the API layer from the verified
inbound JWT's `iss` claim -- never accepted as a payload field, so a
caller cannot misattribute an event to a different source (see the module
README's "Design notes vs. the LLD").
"""
from __future__ import annotations

from typing import Any

from auditability.core.domain import AuditEventRecord
from auditability.core.hash_chain import extract_event_type
from auditability.core.ports import AuditabilityRepository


class IngestionService:
    def __init__(self, repository: AuditabilityRepository) -> None:
        self._repository = repository

    async def ingest(self, *, tenant_id: str, source_module: str, payload: dict[str, Any]) -> AuditEventRecord:
        event_type = extract_event_type(payload)
        return await self._repository.append_event(
            tenant_id=tenant_id, source_module=source_module, event_type=event_type, payload=payload,
        )
