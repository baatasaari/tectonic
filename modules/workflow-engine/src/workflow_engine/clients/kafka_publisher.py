"""aiokafka-backed EventPublisher (LLD §2.2 Event Bus Publisher, stack table).

Publishes JSON-encoded lifecycle events to `<topic>` (e.g. `workflow.step`),
async and non-blocking to the caller's execution path. Publish failures are
caught by the scheduler (see core/scheduler.py `_publish`) and surfaced as
the `workflow_event_publish_failures_total` metric plus a WARN log — they do
not fail the workflow step itself, per the LLD's alerting table (§4.4:
"does not block execution, but must be surfaced").
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
