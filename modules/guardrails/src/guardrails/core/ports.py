"""Abstract ports this module depends on: persistence, LLM Gateway (the
ambiguous-jailbreak-case fallback and red-team attack generation), and
Sentinel Agents (bypass alerting)."""
from __future__ import annotations

from typing import Any, Protocol

from guardrails.core.domain import (
    BypassIncidentRecord,
    InterventionLogRecord,
    PolicyProfileRecord,
    RedTeamRunRecord,
)


class GuardrailsRepository(Protocol):
    async def create_policy_profile(self, record: PolicyProfileRecord) -> PolicyProfileRecord: ...

    async def get_policy_profile(self, tenant_id: str, profile_id: str) -> PolicyProfileRecord | None: ...

    async def get_default_policy_profile(self, tenant_id: str) -> PolicyProfileRecord | None: ...

    async def create_intervention_log(self, record: InterventionLogRecord) -> InterventionLogRecord: ...

    async def create_red_team_run(self, record: RedTeamRunRecord) -> RedTeamRunRecord: ...

    async def list_red_team_runs(self, tenant_id: str) -> list[RedTeamRunRecord]: ...

    async def create_bypass_incident(self, record: BypassIncidentRecord) -> BypassIncidentRecord: ...

    async def list_bypass_incidents(self, red_team_run_id: str) -> list[BypassIncidentRecord]: ...


class LLMGatewayClient(Protocol):
    async def classify_intent(self, text: str, tenant_id: str) -> str:
        """Returns a classification label, e.g. 'jailbreak_attempt' or 'benign'."""
        ...

    async def generate_adversarial_prompts(self, count: int, tenant_id: str) -> list[str]: ...


class SentinelAgentsClient(Protocol):
    async def alert(self, event: dict[str, Any]) -> None: ...
