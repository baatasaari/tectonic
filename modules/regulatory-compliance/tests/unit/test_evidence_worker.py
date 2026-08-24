"""Unit tests for the durable evidence-pack worker (core/evidence_worker.py),
driven one poll tick at a time via `poll_once()` rather than a real sleep
loop, against the in-memory fake repository."""
from __future__ import annotations

from datetime import timedelta

from regulatory_compliance.core.domain import (
    EvidencePackRecord,
    EvidencePackStatus,
    new_id,
    now,
)
from regulatory_compliance.core.evidence_worker import EvidencePackWorker
from regulatory_compliance.core.fakes import (
    InMemoryRegulatoryComplianceRepository,
    StubAuditabilityClient,
)


def _worker(repository, **kwargs):
    class _SessionCtx:
        async def __aenter__(self):
            return repository

        async def __aexit__(self, *exc):
            return False

    def session_factory():
        return _SessionCtx()

    return EvidencePackWorker(
        session_factory, StubAuditabilityClient(), "json", worker_id="worker-test", **kwargs
    )


async def _seeded_repository() -> InMemoryRegulatoryComplianceRepository:
    from regulatory_compliance.core.crosswalk_engine import CrosswalkEngine
    from regulatory_compliance.core.domain import FrameworkProfileRecord
    from regulatory_compliance.core.regulatory_feed import RegulatoryFeedManager

    repository = InMemoryRegulatoryComplianceRepository()
    await RegulatoryFeedManager(repository).seed_defaults()
    await repository.create_framework_profile(
        FrameworkProfileRecord(id=new_id(), tenant_id="t1", framework_name="eu_ai_act", version="2024")
    )
    await CrosswalkEngine(repository).map_control("t1", "human_oversight", "human_oversight", "ref-1")
    return repository


async def test_poll_once_claims_and_completes_the_oldest_pending_pack():
    repository = await _seeded_repository()
    pack = await repository.create_evidence_pack(
        EvidencePackRecord(id=new_id(), tenant_id="t1", framework_name="eu_ai_act", status=EvidencePackStatus.GENERATING)
    )
    worker = _worker(repository)

    did_work = await worker.poll_once()

    assert did_work is True
    result = await repository.get_evidence_pack("t1", pack.id)
    assert result.status == EvidencePackStatus.COMPLETED
    assert result.worker_id == "worker-test"
    assert result.attempts == 1


async def test_poll_once_returns_false_when_queue_is_empty():
    repository = InMemoryRegulatoryComplianceRepository()
    worker = _worker(repository)

    assert await worker.poll_once() is False


async def test_poll_once_skips_a_pack_whose_lease_is_still_active():
    """A pack another worker is already (within its lease window) processing must not
    be claimed a second time -- the core correctness property FOR UPDATE SKIP LOCKED
    gives for real, that this fake reproduces for single-process unit testing."""
    repository = InMemoryRegulatoryComplianceRepository()
    pack = await repository.create_evidence_pack(
        EvidencePackRecord(id=new_id(), tenant_id="t1", framework_name="eu_ai_act", status=EvidencePackStatus.GENERATING)
    )
    claimed = await repository.claim_next_evidence_pack("other-worker", lease_seconds=120)
    assert claimed.id == pack.id

    worker = _worker(repository)
    did_work = await worker.poll_once()

    assert did_work is False
    still_claimed = await repository.get_evidence_pack("t1", pack.id)
    assert still_claimed.worker_id == "other-worker"
    assert still_claimed.attempts == 1


async def test_a_pack_whose_lease_has_expired_is_reclaimed():
    repository = InMemoryRegulatoryComplianceRepository()
    pack = EvidencePackRecord(
        id=new_id(), tenant_id="t1", framework_name="eu_ai_act", status=EvidencePackStatus.GENERATING,
        worker_id="dead-worker", lease_expires_at=now() - timedelta(seconds=1), attempts=1,
    )
    await repository.create_evidence_pack(pack)

    claimed = await repository.claim_next_evidence_pack("new-worker", lease_seconds=120)

    assert claimed is not None
    assert claimed.id == pack.id
    assert claimed.worker_id == "new-worker"
    assert claimed.attempts == 2


async def test_recover_stuck_packs_force_expires_an_active_lease():
    repository = InMemoryRegulatoryComplianceRepository()
    await repository.create_evidence_pack(
        EvidencePackRecord(
            id=new_id(), tenant_id="t1", framework_name="eu_ai_act", status=EvidencePackStatus.GENERATING,
            worker_id="previous-incarnation", lease_expires_at=now() + timedelta(seconds=100),
        )
    )
    worker = _worker(repository)

    recovered = await worker.recover_stuck_packs()

    assert recovered == 1
    # Immediately claimable now, without waiting out the rest of the original lease.
    claimed = await repository.claim_next_evidence_pack("new-worker", lease_seconds=120)
    assert claimed is not None


async def test_a_transient_generation_failure_is_requeued_while_attempts_remain():
    class BoomOnFirstCallRepository(InMemoryRegulatoryComplianceRepository):
        def __init__(self):
            super().__init__()
            self._boomed = False

        async def list_control_mappings(self, *, control_name=None, framework_name=None):
            if not self._boomed:
                self._boomed = True
                raise RuntimeError("transient db hiccup")
            return await super().list_control_mappings(control_name=control_name, framework_name=framework_name)

    repository = BoomOnFirstCallRepository()
    await repository.create_evidence_pack(
        EvidencePackRecord(id=new_id(), tenant_id="t1", framework_name="eu_ai_act", status=EvidencePackStatus.GENERATING)
    )
    worker = _worker(repository, max_attempts=3)

    await worker.poll_once()
    [pack] = repository.evidence_packs.values()
    assert pack.status == EvidencePackStatus.GENERATING  # requeued, not permanently failed
    assert pack.lease_expires_at is None  # immediately claimable again
    assert pack.attempts == 1
    assert pack.last_error == "transient db hiccup"

    did_work = await worker.poll_once()
    assert did_work is True
    assert pack.status == EvidencePackStatus.COMPLETED
    assert pack.attempts == 2


async def test_a_pack_that_exhausts_max_attempts_is_permanently_failed_not_retried_forever():
    """Every failed attempt is requeued unconditionally (see evidence_worker.py's
    poll_once) -- fail_exhausted_evidence_packs, run at the top of the *next* poll, is
    the single place that decides a pack has had its last chance, so it takes one poll
    beyond max_attempts failures to converge to the permanent-failed state."""
    class AlwaysBoomRepository(InMemoryRegulatoryComplianceRepository):
        async def list_control_mappings(self, *, control_name=None, framework_name=None):
            raise RuntimeError("permanently broken")

    repository = AlwaysBoomRepository()
    await repository.create_evidence_pack(
        EvidencePackRecord(id=new_id(), tenant_id="t1", framework_name="eu_ai_act", status=EvidencePackStatus.GENERATING)
    )
    worker = _worker(repository, max_attempts=2)

    await worker.poll_once()  # attempt 1: fails, requeued
    await worker.poll_once()  # attempt 2: fails, requeued
    [pack] = repository.evidence_packs.values()
    assert pack.attempts == 2
    assert pack.status == EvidencePackStatus.GENERATING

    # The third poll's fail_exhausted_evidence_packs step (attempts >= max_attempts)
    # catches it before any further claim is attempted -- permanently failed, not
    # reclaimed and retried forever.
    did_work = await worker.poll_once()
    assert did_work is False
    assert pack.status == EvidencePackStatus.FAILED
    assert pack.last_error == "exceeded max attempts (2)"
