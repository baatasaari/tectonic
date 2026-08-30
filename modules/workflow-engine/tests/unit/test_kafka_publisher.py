"""Ticket #82 (Phase 2 support-agent slice): a failed KafkaEventPublisher
.start() (no reachable broker -- this sandbox's own permanent condition,
see CLAUDE.md) must leave `_producer` as None, not a real-but-never-
actually-started AIOKafkaProducer -- otherwise publish() calling
`send_and_wait` on that half-initialized producer hangs indefinitely
instead of raising immediately, exactly the bug this pins down (found by
standing this module up as a real process for the first time against
main.py's own now-degrading-not-crashing lifespan)."""
from __future__ import annotations

import asyncio

import pytest
from aiokafka.errors import KafkaConnectionError

from workflow_engine.clients.kafka_publisher import KafkaEventPublisher

pytestmark = pytest.mark.asyncio


async def test_failed_start_leaves_producer_none_and_publish_raises_fast():
    # An address nothing listens on; aiokafka's own connect timeout is a few
    # seconds by default, this test still finishes well inside a normal test run.
    publisher = KafkaEventPublisher("localhost:19999")

    with pytest.raises(KafkaConnectionError):
        await publisher.start()

    assert publisher._producer is None

    with pytest.raises(RuntimeError, match="start\\(\\) was not called"):
        # Must raise near-instantly -- this is the exact call that used to hang
        # indefinitely against a half-initialized producer.
        await asyncio.wait_for(publisher.publish("some.topic", {"hello": "world"}), timeout=2.0)
