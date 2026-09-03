"""Abstract ports this module depends on: persistence, and the two real
platform-peer clients the A/B testing, drift detection and reflection
services read from / call.
"""
from __future__ import annotations

from typing import Any, Protocol

from promptops.core.domain import ABTestRecord, PromptVersionRecord


class PromptOpsRepository(Protocol):
    async def create_prompt_version(self, record: PromptVersionRecord) -> PromptVersionRecord: ...

    async def get_prompt_version(self, prompt_version_id: str) -> PromptVersionRecord | None: ...

    async def update_prompt_version(self, record: PromptVersionRecord) -> PromptVersionRecord: ...

    async def list_prompt_versions(
        self, *, tenant_id: str | None = None, prompt_name: str | None = None, limit: int = 50, offset: int = 0,
    ) -> tuple[list[PromptVersionRecord], int]: ...

    async def get_active_prompt_version(self, *, tenant_id: str, prompt_name: str) -> PromptVersionRecord | None:
        """The current `active`-status version for this (tenant, prompt_name), or
        None if nothing is active there yet."""
        ...

    async def create_ab_test(self, record: ABTestRecord) -> ABTestRecord: ...

    async def get_ab_test(self, ab_test_id: str) -> ABTestRecord | None: ...

    async def update_ab_test(self, record: ABTestRecord) -> ABTestRecord: ...


class EvaluationFrameworkClient(Protocol):
    async def list_scores(self, *, tenant_id: str, agent_ref: str) -> list[dict[str, Any]]:
        """Each item at least `{"score": float, "threshold": float,
        "metric_name": str, "passed": bool}`, per Evaluation Framework's
        own MetricScoreSchema. Empty list, not an error, when the
        version has no evaluation history yet."""
        ...

    async def gate_latest_run(self, *, tenant_id: str, agent_ref: str) -> dict[str, Any] | None:
        """Resolves the most recent eval run for `agent_ref` (via
        Evaluation Framework's `GET /eval-runs`) and gates it (`POST
        /gate`), returning that endpoint's own verdict:
        `{"overall_passed": bool, "blocking_failures": list[str]}`.
        `None`, not an error, when no eval run exists yet for this
        agent_ref -- the same "no history yet is not a failure"
        convention `list_scores` already establishes, since a version
        that has never been evaluated has nothing for this gate to
        block on."""
        ...


class LLMGatewayClient(Protocol):
    async def generate(self, *, tenant_id: str, model: str, prompt: str) -> str:
        """Calls LLM Gateway's real `POST /v1/llm-gateway/chat/completions`
        and returns the first choice's message content."""
        ...
