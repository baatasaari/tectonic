"""In-memory fakes for unit tests (LLD "Deployability and testability
contract")."""
from __future__ import annotations

from typing import Any

from promptops.core.domain import ABTestRecord, PromptVersionRecord, PromptVersionStatus

_UNSET = object()


class InMemoryPromptOpsRepository:
    def __init__(self) -> None:
        self.prompt_versions: dict[str, PromptVersionRecord] = {}
        self.ab_tests: dict[str, ABTestRecord] = {}

    async def create_prompt_version(self, record: PromptVersionRecord) -> PromptVersionRecord:
        self.prompt_versions[record.id] = record
        return record

    async def get_prompt_version(self, prompt_version_id: str) -> PromptVersionRecord | None:
        return self.prompt_versions.get(prompt_version_id)

    async def update_prompt_version(self, record: PromptVersionRecord) -> PromptVersionRecord:
        self.prompt_versions[record.id] = record
        return record

    async def list_prompt_versions(
        self, *, tenant_id: str | None = None, prompt_name: str | None = None, limit: int = 50, offset: int = 0,
    ) -> tuple[list[PromptVersionRecord], int]:
        results = list(self.prompt_versions.values())
        if tenant_id is not None:
            results = [v for v in results if v.tenant_id == tenant_id]
        if prompt_name is not None:
            results = [v for v in results if v.prompt_name == prompt_name]
        results = sorted(results, key=lambda v: v.created_at)
        return results[offset:offset + limit], len(results)

    async def get_active_prompt_version(self, *, tenant_id: str, prompt_name: str) -> PromptVersionRecord | None:
        for version in self.prompt_versions.values():
            if (
                version.tenant_id == tenant_id and version.prompt_name == prompt_name
                and version.status == PromptVersionStatus.ACTIVE
            ):
                return version
        return None

    async def create_ab_test(self, record: ABTestRecord) -> ABTestRecord:
        self.ab_tests[record.id] = record
        return record

    async def get_ab_test(self, ab_test_id: str) -> ABTestRecord | None:
        return self.ab_tests.get(ab_test_id)

    async def update_ab_test(self, record: ABTestRecord) -> ABTestRecord:
        self.ab_tests[record.id] = record
        return record


class StubEvaluationFrameworkClient:
    def __init__(
        self, *, scores: list[dict[str, Any]] | None = None, scores_by_ref: dict[str, list[dict]] | None = None,
        gate_results_by_ref: dict[str, dict[str, Any] | None] | None = None,
    ) -> None:
        self.calls: list[dict] = []
        self.gate_calls: list[dict] = []
        self._scores = scores if scores is not None else []
        self._scores_by_ref = scores_by_ref or {}
        # Absent from this dict -> None (no eval run yet, matching the real client's
        # own convention) rather than raising KeyError -- most tests never set this up.
        self._gate_results_by_ref = gate_results_by_ref or {}

    async def list_scores(self, *, tenant_id: str, agent_ref: str) -> list[dict[str, Any]]:
        self.calls.append({"tenant_id": tenant_id, "agent_ref": agent_ref})
        if agent_ref in self._scores_by_ref:
            return self._scores_by_ref[agent_ref]
        return self._scores

    async def gate_latest_run(self, *, tenant_id: str, agent_ref: str) -> dict[str, Any] | None:
        self.gate_calls.append({"tenant_id": tenant_id, "agent_ref": agent_ref})
        return self._gate_results_by_ref.get(agent_ref)


class StubLLMGatewayClient:
    def __init__(self, *, response: str | object = _UNSET) -> None:
        self.calls: list[dict] = []
        self._response = "an improved template" if response is _UNSET else response

    async def generate(self, *, tenant_id: str, model: str, prompt: str) -> str:
        self.calls.append({"tenant_id": tenant_id, "model": model, "prompt": prompt})
        return self._response


__all__ = ["InMemoryPromptOpsRepository", "StubEvaluationFrameworkClient", "StubLLMGatewayClient"]
