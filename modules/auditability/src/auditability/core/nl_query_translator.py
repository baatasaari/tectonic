"""NL Query Translator (LLD §2 sub-components, §Level 3 "Sequence:
natural-language query"): turns a free-text question into this module's
own `AuditEventFilter` -- never raw SQL, and never trusted un-validated.
The LLM Gateway call's output is a candidate; this module's own filter
schema is the only thing that ever reaches the repository, so a
hallucinated field name is rejected outright rather than silently ignored
or, worse, broadening the query beyond what was asked.
"""
from __future__ import annotations

import dataclasses
from datetime import datetime

from auditability.core.domain import AuditEventFilter, InvalidNLQueryFilterError
from auditability.core.ports import LLMGatewayClient

_ALLOWED_FIELDS = frozenset(
    f.name for f in dataclasses.fields(AuditEventFilter) if f.name not in ("tenant_id", "limit", "offset")
)
_DATE_FIELDS = frozenset({"occurred_after", "occurred_before"})

_INSTRUCTION = (
    "Translate the user's question about an audit log into a JSON filter object. "
    f"Allowed keys: {sorted(_ALLOWED_FIELDS)}. Only include a key if the question actually "
    "constrains it. Date fields must be ISO-8601 strings. Respond with only the JSON object."
)


class NLQueryTranslator:
    def __init__(self, llm_gateway: LLMGatewayClient) -> None:
        self._llm_gateway = llm_gateway

    async def translate(self, question: str, tenant_id: str) -> AuditEventFilter:
        proposal = await self._llm_gateway.complete(
            prompt_context={"instruction": _INSTRUCTION, "question": question}, tenant_id=tenant_id,
        )
        return self._validate(proposal, tenant_id)

    def _validate(self, proposal: dict, tenant_id: str) -> AuditEventFilter:
        unknown = set(proposal) - _ALLOWED_FIELDS
        if unknown:
            raise InvalidNLQueryFilterError(f"translated filter used unrecognized field(s): {sorted(unknown)}")

        kwargs: dict = {"tenant_id": tenant_id}
        for key, value in proposal.items():
            if value is None:
                continue
            if key in _DATE_FIELDS:
                try:
                    kwargs[key] = datetime.fromisoformat(str(value))
                except ValueError as exc:
                    raise InvalidNLQueryFilterError(f"field {key!r} was not a valid ISO-8601 date: {value!r}") from exc
            elif isinstance(value, str):
                kwargs[key] = value
            else:
                raise InvalidNLQueryFilterError(f"field {key!r} had an unexpected type: {type(value).__name__}")

        return AuditEventFilter(**kwargs)
