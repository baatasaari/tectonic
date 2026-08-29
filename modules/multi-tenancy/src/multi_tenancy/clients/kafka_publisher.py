"""aiokafka-backed EventPublisher (independent architecture assessment
§3.3 "Add an event backbone") -- the rollout of Workflow Engine's own
`KafkaEventPublisher` (Module 1) to a second module.

Publishes JSON-encoded Tenant lifecycle events to `tenant.lifecycle`,
relayed by `OutboxRelayWorker`, never called directly from a request
path. Publish failures are caught by the worker itself (see
`core/outbox_worker.py`'s `poll_once`) and requeued for retry -- they
never block or fail the tenancy control-plane write that produced them.
"""
from __future__ import annotations

import json
from typing import Any

from aiokafka import AIOKafkaProducer


class KafkaEventPublisher:
    def __init__(self, bootstrap_servers: str) -> None:
        self._bootstrap_servers = bootstrap_servers
        self._producer: AIOKafkaProducer | None = None

    async def start(self) -> None:
        self._producer = AIOKafkaProducer(
            bootstrap_servers=self._bootstrap_servers,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        )
        await self._producer.start()

    async def stop(self) -> None:
        if self._producer is not None:
            await self._producer.stop()

    async def publish(self, topic: str, event: dict[str, Any]) -> None:
        if self._producer is None:
            raise RuntimeError("KafkaEventPublisher.start() was not called")
        await self._producer.send_and_wait(topic, event)
