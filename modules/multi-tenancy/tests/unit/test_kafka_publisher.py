"""Ticket #82 (Phase 2 support-agent slice): a failed KafkaEventPublisher
.start() (no reachable broker -- this sandbox's own permanent condition,
see CLAUDE.md) must leave `_producer` as None, not a real-but-never-
actually-started AIOKafkaProducer -- otherwise publish() calling
`send_and_wait` on that half-initialized producer hangs indefinitely
instead of raising immediately. See Workflow Engine's own identical fix
and test for the full reasoning (found there first, standing that module
up as a real process for the first time against main.py's own
now-degrading-not-crashing lifespan)."""
from __future__ import annotations

import asyncio

import pytest
from aiokafka.errors import KafkaConnectionError

from multi_tenancy.clients.kafka_publisher import KafkaEventPublisher

pytestmark = pytest.mark.asyncio


async def test_failed_start_leaves_producer_none_and_publish_raises_fast():
    publisher = KafkaEventPublisher("localhost:19999")

    with pytest.raises(KafkaConnectionError):
        await publisher.start()

    assert publisher._producer is None

    with pytest.raises(RuntimeError, match="start\\(\\) was not called"):
        await asyncio.wait_for(publisher.publish("some.topic", {"hello": "world"}), timeout=2.0)
