"""Model Deprecation Watcher (LLD §2.2, differentiator: "model deprecation
early-warning"). In production this is a scheduled job that polls provider
changelogs/APIs; here it compares each ProviderConfig's currently-known
`deprecation_notices` against what was already seen and returns what's new,
so the scheduling/polling mechanism (a cron job, a Routine, whatever the
deployment uses) stays a thin wrapper around this pure comparison.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from llm_gateway.core.ports import GatewayRepository
from llm_gateway.telemetry.metrics import llm_gateway_deprecation_notices_total


@dataclass
class NewDeprecationNotice:
    provider_name: str
    notice: dict[str, Any]


class ModelDeprecationWatcher:
    def __init__(self, repository: GatewayRepository) -> None:
        self.repository = repository
        self._seen: set[tuple[str, str]] = set()  # (provider_name, notice id/model)

    async def check_new_notices(self) -> list[NewDeprecationNotice]:
        providers = await self.repository.list_provider_configs()
        new: list[NewDeprecationNotice] = []
        for provider in providers:
            for notice in provider.deprecation_notices:
                key = (provider.provider_name, notice.get("model", notice.get("id", "")))
                if key not in self._seen:
                    self._seen.add(key)
                    new.append(NewDeprecationNotice(provider_name=provider.provider_name, notice=notice))
                    llm_gateway_deprecation_notices_total.labels(provider=provider.provider_name).inc()
        return new
