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
        # A genuine module-level gap ticket #82 surfaced running this module
        # for real without a Kafka broker (main.py's own lifespan degrades on
        # a failed start instead of crashing -- see its own comment): this
        # assigned `self._producer` *before* actually confirming `.start()`
        # succeeded, so a failed start still left `_producer` pointing at a
        # real-but-never-actually-started `AIOKafkaProducer` -- not `None`.
        # `publish()`'s own `if self._producer is None` guard (its one
        # documented degraded-mode signal, also relied on by main.py's own
        # /healthz check) never fired, and calling `send_and_wait` on that
        # half-initialized producer hung indefinitely instead of raising
        # immediately -- invisible before because every prior test/run
        # either had a real Kafka broker or never actually called
        # `publish()` afterward. Only assign `self._producer` once `.start()`
        # has actually succeeded.
        producer = AIOKafkaProducer(
            bootstrap_servers=self._bootstrap_servers,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        )
        await producer.start()
        self._producer = producer

    async def stop(self) -> None:
        if self._producer is not None:
            await self._producer.stop()

    async def publish(self, topic: str, event: dict[str, Any]) -> None:
        if self._producer is None:
            raise RuntimeError("KafkaEventPublisher.start() was not called")
        await self._producer.send_and_wait(topic, event)
