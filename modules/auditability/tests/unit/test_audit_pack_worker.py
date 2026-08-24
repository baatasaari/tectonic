"""Unit tests for the durable audit-pack worker (core/audit_pack_worker.py),
driven one poll tick at a time via `poll_once()` rather than a real sleep
loop, against the in-memory fake repository. Mirrors Module 17's own
evidence-worker test suite -- same design, same test shape."""
from __future__ import annotations

from datetime import timedelta

from auditability.core.audit_pack_worker import AuditPackWorker
from auditability.core.domain import AuditPackRecord, AuditPackStatus, new_id, now
from auditability.core.fakes import InMemoryAuditabilityRepository


def _worker(repository, **kwargs):
    class _SessionCtx:
        async def __aenter__(self):
            return repository

        async def __aexit__(self, *exc):
            return False

    def session_factory():
        return _SessionCtx()

    return AuditPackWorker(session_factory, "json", worker_id="worker-test", **kwargs)


async def test_poll_once_claims_and_completes_the_oldest_pending_pack():
    repository = InMemoryAuditabilityRepository()
    await repository.append_event(tenant_id="t1", source_module="m1", event_type="a", payload={})
    pack = await repository.create_audit_pack(
        AuditPackRecord(id=new_id(), tenant_id="t1", status=AuditPackStatus.GENERATING)
    )
    worker = _worker(repository)

    did_work = await worker.poll_once()

    assert did_work is True
    result = await repository.get_audit_pack("t1", pack.id)
    assert result.status == AuditPackStatus.COMPLETED
    assert result.worker_id == "worker-test"
    assert result.attempts == 1
    assert result.event_count == 1
    assert result.chain_valid is True


async def test_poll_once_returns_false_when_queue_is_empty():
    repository = InMemoryAuditabilityRepository()
    worker = _worker(repository)

    assert await worker.poll_once() is False


async def test_poll_once_skips_a_pack_whose_lease_is_still_active():
    """A pack another worker is already (within its lease window) processing must not
    be claimed a second time -- the core correctness property FOR UPDATE SKIP LOCKED
    gives for real, that this fake reproduces for single-process unit testing."""
    repository = InMemoryAuditabilityRepository()
    pack = await repository.create_audit_pack(
        AuditPackRecord(id=new_id(), tenant_id="t1", status=AuditPackStatus.GENERATING)
    )
    claimed = await repository.claim_next_audit_pack("other-worker", lease_seconds=120)
    assert claimed.id == pack.id

    worker = _worker(repository)
    did_work = await worker.poll_once()

    assert did_work is False
    still_claimed = await repository.get_audit_pack("t1", pack.id)
    assert still_claimed.worker_id == "other-worker"
    assert still_claimed.attempts == 1


async def test_a_pack_whose_lease_has_expired_is_reclaimed():
    repository = InMemoryAuditabilityRepository()
    pack = AuditPackRecord(
        id=new_id(), tenant_id="t1", status=AuditPackStatus.GENERATING,
        worker_id="dead-worker", lease_expires_at=now() - timedelta(seconds=1), attempts=1,
    )
    await repository.create_audit_pack(pack)

    claimed = await repository.claim_next_audit_pack("new-worker", lease_seconds=120)

    assert claimed is not None
    assert claimed.id == pack.id
    assert claimed.worker_id == "new-worker"
    assert claimed.attempts == 2


async def test_recover_stuck_packs_force_expires_an_active_lease():
    repository = InMemoryAuditabilityRepository()
    await repository.create_audit_pack(
        AuditPackRecord(
            id=new_id(), tenant_id="t1", status=AuditPackStatus.GENERATING,
            worker_id="previous-incarnation", lease_expires_at=now() + timedelta(seconds=100),
        )
    )
    worker = _worker(repository)

    recovered = await worker.recover_stuck_packs()

    assert recovered == 1
    claimed = await repository.claim_next_audit_pack("new-worker", lease_seconds=120)
    assert claimed is not None


async def test_a_transient_generation_failure_is_requeued_while_attempts_remain():
    class BoomOnFirstCallRepository(InMemoryAuditabilityRepository):
        def __init__(self):
            super().__init__()
            self._boomed = False

        async def list_events_for_chain(self, tenant_id):
            if not self._boomed:
                self._boomed = True
                raise RuntimeError("transient db hiccup")
            return await super().list_events_for_chain(tenant_id)

    repository = BoomOnFirstCallRepository()
    await repository.create_audit_pack(
        AuditPackRecord(id=new_id(), tenant_id="t1", status=AuditPackStatus.GENERATING)
    )
    worker = _worker(repository, max_attempts=3)

    await worker.poll_once()
    [pack] = repository.audit_packs.values()
    assert pack.status == AuditPackStatus.GENERATING  # requeued, not permanently failed
    assert pack.lease_expires_at is None  # immediately claimable again
    assert pack.attempts == 1
    assert pack.last_error == "transient db hiccup"

    did_work = await worker.poll_once()
    assert did_work is True
    assert pack.status == AuditPackStatus.COMPLETED
    assert pack.attempts == 2


async def test_a_pack_that_exhausts_max_attempts_is_permanently_failed_not_retried_forever():
    """Every failed attempt is requeued unconditionally (see audit_pack_worker.py's
    poll_once) -- fail_exhausted_audit_packs, run at the top of the *next* poll, is the
    single place that decides a pack has had its last chance, so it takes one poll
    beyond max_attempts failures to converge to the permanent-failed state."""
    class AlwaysBoomRepository(InMemoryAuditabilityRepository):
        async def list_events_for_chain(self, tenant_id):
            raise RuntimeError("permanently broken")

    repository = AlwaysBoomRepository()
    await repository.create_audit_pack(
        AuditPackRecord(id=new_id(), tenant_id="t1", status=AuditPackStatus.GENERATING)
    )
    worker = _worker(repository, max_attempts=2)

    await worker.poll_once()  # attempt 1: fails, requeued
    await worker.poll_once()  # attempt 2: fails, requeued
    [pack] = repository.audit_packs.values()
    assert pack.attempts == 2
    assert pack.status == AuditPackStatus.GENERATING

    # The third poll's fail_exhausted_audit_packs step (attempts >= max_attempts)
    # catches it before any further claim is attempted -- permanently failed, not
    # reclaimed and retried forever.
    did_work = await worker.poll_once()
    assert did_work is False
    assert pack.status == AuditPackStatus.FAILED
    assert pack.last_error == "exceeded max attempts (2)"
