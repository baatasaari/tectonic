"""Unit tests for the durable event-outbox relay worker
(core/outbox_worker.py), driven one poll tick at a time via
`poll_once()` rather than a real sleep loop, against the in-memory fake
repository and event publisher. This module's rollout of Workflow
Engine's own `test_outbox_worker.py` (Module 1) to a second module.
"""
from __future__ import annotations

from multi_tenancy.core import events
from multi_tenancy.core.domain import EventOutboxRecord, OutboxEventStatus, TenantRecord, new_id
from multi_tenancy.core.fakes import InMemoryEventPublisher, InMemoryMultiTenancyRepository
from multi_tenancy.core.outbox_worker import OutboxRelayWorker


def _worker(repository, event_publisher=None, **kwargs):
    class _SessionCtx:
        async def __aenter__(self):
            return repository

        async def __aexit__(self, *exc):
            return False

    def repository_factory():
        return _SessionCtx()

    return OutboxRelayWorker(
        repository_factory, event_publisher or InMemoryEventPublisher(), worker_id="worker-test", **kwargs
    )


async def _seed_pending_event(repository) -> dict:
    record = TenantRecord(id=new_id(), name="Acme Corp")
    envelope = events.tenant_registered(record.id, record.name, record.tier, record.organisation_id)
    await repository.create_tenant_and_enqueue_event(record, topic=events.TOPIC_TENANT, envelope=envelope)
    return envelope


async def test_poll_once_claims_and_publishes_the_oldest_pending_event():
    repository = InMemoryMultiTenancyRepository()
    envelope = await _seed_pending_event(repository)
    publisher = InMemoryEventPublisher()
    worker = _worker(repository, publisher)

    did_work = await worker.poll_once()

    assert did_work is True
    outbox_record = repository.outbox[envelope["id"]]
    assert outbox_record.status == OutboxEventStatus.PUBLISHED
    assert outbox_record.worker_id == "worker-test"
    assert outbox_record.attempts == 1
    assert outbox_record.published_at is not None
    assert publisher.published == [(events.TOPIC_TENANT, envelope)]


async def test_poll_once_returns_false_when_the_queue_is_empty():
    worker = _worker(InMemoryMultiTenancyRepository())

    did_work = await worker.poll_once()

    assert did_work is False


async def test_a_publish_failure_requeues_the_event_for_retry():
    repository = InMemoryMultiTenancyRepository()
    envelope = await _seed_pending_event(repository)

    class _RaisingPublisher:
        async def publish(self, topic, event):
            raise RuntimeError("kafka is down")

    worker = _worker(repository, _RaisingPublisher())

    did_work = await worker.poll_once()

    assert did_work is True
    outbox_record = repository.outbox[envelope["id"]]
    assert outbox_record.status == OutboxEventStatus.PENDING
    assert outbox_record.attempts == 1
    assert outbox_record.lease_expires_at is None
    assert "kafka is down" in outbox_record.last_error


async def test_a_requeued_event_is_reclaimable_on_the_next_poll():
    repository = InMemoryMultiTenancyRepository()
    await _seed_pending_event(repository)

    class _FailOnceThenSucceedPublisher:
        def __init__(self):
            self.calls = 0

        async def publish(self, topic, event):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("transient")

    publisher = _FailOnceThenSucceedPublisher()
    worker = _worker(repository, publisher)

    await worker.poll_once()  # fails, requeues
    await worker.poll_once()  # succeeds

    assert publisher.calls == 2
    outbox_record = next(iter(repository.outbox.values()))
    assert outbox_record.status == OutboxEventStatus.PUBLISHED
    assert outbox_record.attempts == 2


async def test_events_exceeding_max_attempts_stop_being_retried():
    repository = InMemoryMultiTenancyRepository()
    envelope = await _seed_pending_event(repository)
    outbox_record = repository.outbox[envelope["id"]]
    outbox_record.attempts = 3  # already at the ceiling

    class _RaisingPublisher:
        async def publish(self, topic, event):
            raise RuntimeError("still down")

    worker = _worker(repository, _RaisingPublisher(), max_attempts=3)

    # The poison-pill sweep at the top of the next poll_once() marks it failed before
    # a claim is ever attempted -- no further publish call, no further attempt.
    did_work = await worker.poll_once()

    assert did_work is False
    assert repository.outbox[envelope["id"]].status == OutboxEventStatus.FAILED
    assert repository.outbox[envelope["id"]].attempts == 3


async def test_recover_stuck_events_force_expires_active_leases():
    """Simulates a worker that claimed an event (a real hour-long lease,
    worker_id, and an attempt already recorded) and then died before
    ever publishing it -- the startup recovery sweep must make that row
    reclaimable again immediately, not wait out the lease."""
    from multi_tenancy.core.domain import now

    repository = InMemoryMultiTenancyRepository()
    await _seed_pending_event(repository)
    claimed = await repository.claim_next_outbox_event("dead-worker", lease_seconds=3600)
    assert claimed is not None
    assert claimed.lease_expires_at > now()

    worker = _worker(repository)
    recovered = await worker.recover_stuck_events()

    assert recovered == 1
    assert repository.outbox[claimed.id].lease_expires_at <= now()

    # Reclaimable again right away by a different worker.
    reclaimed = await repository.claim_next_outbox_event("worker-b", lease_seconds=60)
    assert reclaimed is not None
    assert reclaimed.id == claimed.id
    assert reclaimed.attempts == 2  # claimed once by dead-worker, once by worker-b


def test_event_outbox_record_defaults_to_pending():
    record = EventOutboxRecord(id="e1", topic="tenant.lifecycle", tenant_id="acme", envelope={})
    assert record.status == OutboxEventStatus.PENDING
    assert record.attempts == 0
