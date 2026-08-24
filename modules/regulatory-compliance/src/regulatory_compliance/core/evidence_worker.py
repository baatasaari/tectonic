"""Durable evidence-pack generation worker (fixes a real gap: generation used
to run as an in-process FastAPI `BackgroundTasks` job, so a pod restart
between "202 Accepted" and job completion left the pack stuck at
`status=generating` forever, with no other process ever picking it back up).

This replaces that with a Postgres-backed job queue, reusing the
`evidence_packs` table itself as the queue (no separate queue table/broker):

- `RegulatoryComplianceRepository.claim_next_evidence_pack` atomically claims
  the oldest pending pack via `SELECT ... FOR UPDATE SKIP LOCKED` — the row
  lock is what lets multiple worker processes/pods poll the same table
  concurrently without two of them ever claiming the same row.
- A claimed pack gets a time-bounded lease (`lease_expires_at`); if the
  worker holding it crashes mid-generation, the lease simply expires and the
  next poll from *any* worker reclaims it — no separate "is this worker still
  alive" liveness check needed.
- `fail_exhausted_evidence_packs` is the poison-pill guard: a pack that has
  failed `worker_max_attempts` times in a row stops being retried and is
  marked `failed` for good, rather than being silently reclaimed forever.
- `force_expire_stale_leases` is the startup recovery sweep: on process boot,
  it force-expires every currently-held lease immediately, so anything left
  mid-flight by a now-dead previous instance is reclaimed on the very next
  poll tick instead of waiting out the remainder of its lease window.

Runs as an asyncio task inside this module's own process (see main.py's
lifespan), not a separate deployment — this platform's modules are built as
single-process services throughout, so a poll loop is the natural fit here;
swapping in a dedicated worker deployment later is a matter of running this
same class's `run_forever()` as its own entrypoint against the same table.
"""
from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager

from regulatory_compliance.core.domain import EvidencePackStatus
from regulatory_compliance.core.evidence_generator import EvidencePackGenerator
from regulatory_compliance.core.ports import AuditabilityClient, RegulatoryComplianceRepository
from regulatory_compliance.telemetry.logging import get_logger

logger = get_logger(component="evidence_worker")

RepositoryFactory = Callable[[], AbstractAsyncContextManager[RegulatoryComplianceRepository]]


def new_worker_id() -> str:
    return f"worker-{uuid.uuid4().hex[:12]}"


class EvidencePackWorker:
    def __init__(
        self,
        repository_factory: RepositoryFactory,
        auditability: AuditabilityClient,
        output_format: str,
        *,
        worker_id: str | None = None,
        poll_interval_seconds: float = 2.0,
        lease_seconds: int = 120,
        max_attempts: int = 3,
    ) -> None:
        # A factory over the RegulatoryComplianceRepository port, not a raw DB session
        # factory — this class lives in core/ and stays adapter-agnostic like the rest
        # of this module's core logic, testable against the in-memory fake exactly like
        # everything else here, with no import from db/ anywhere in this file.
        self._repository_factory = repository_factory
        self._auditability = auditability
        self._output_format = output_format
        self.worker_id = worker_id or new_worker_id()
        self._poll_interval_seconds = poll_interval_seconds
        self._lease_seconds = lease_seconds
        self._max_attempts = max_attempts
        self._stopped = False

    def stop(self) -> None:
        self._stopped = True

    async def recover_stuck_packs(self) -> int:
        """Startup recovery sweep — see module docstring. Call once before the poll
        loop starts, e.g. from the FastAPI lifespan."""
        async with self._repository_factory() as repository:
            recovered = await repository.force_expire_stale_leases()
            if recovered:
                logger.info("evidence_pack_jobs_recovered", worker_id=self.worker_id, count=recovered)
            return recovered

    async def poll_once(self) -> bool:
        """Runs one claim-and-generate cycle. Returns True if it did work (so a caller
        can tighten its own poll loop when the queue is busy), False if the queue was
        empty. Exposed separately from run_forever() so unit tests can drive it
        deterministically, one tick at a time, without a real sleep loop."""
        async with self._repository_factory() as repository:
            failed = await repository.fail_exhausted_evidence_packs(self._max_attempts)
            if failed:
                logger.warning("evidence_pack_jobs_exhausted", worker_id=self.worker_id, count=failed)

            claimed = await repository.claim_next_evidence_pack(self.worker_id, self._lease_seconds)
            if claimed is None:
                return False

            logger.info(
                "evidence_pack_job_claimed", worker_id=self.worker_id, pack_id=claimed.id,
                tenant_id=claimed.tenant_id, attempt=claimed.attempts,
            )
            generator = EvidencePackGenerator(repository, self._auditability, self._output_format)
            try:
                result = await generator.generate(claimed.id, claimed.tenant_id, claimed.framework_name)
                logger.info(
                    "evidence_pack_job_finished", worker_id=self.worker_id, pack_id=claimed.id,
                    status=result.status.value, attempt=claimed.attempts,
                )
                # generate() itself always resolves to completed/failed in one attempt and
                # never raises (see its own docstring/tests) -- retry policy belongs here,
                # not inside the generator. Always requeue a failed attempt rather than
                # deciding here whether attempts are exhausted: fail_exhausted_evidence_packs,
                # run at the top of the *next* poll, is the single place that decides a pack
                # has had its last chance, so there's one authoritative "gave up" reason
                # (its own last_error) instead of two code paths racing to explain a failure.
                if result.status == EvidencePackStatus.FAILED:
                    await repository.requeue_evidence_pack_for_retry(claimed.id)
                    logger.warning(
                        "evidence_pack_job_requeued", worker_id=self.worker_id, pack_id=claimed.id,
                        attempt=claimed.attempts, max_attempts=self._max_attempts, error=result.last_error,
                    )
            except Exception:
                # Something went wrong outside generate()'s own self-contained try/except
                # (e.g. the claim's own session breaking) -- guard so one bad job can
                # never take the whole poll loop down. The pack stays claimed with its
                # lease still running; it becomes reclaimable once that lease expires.
                logger.exception("evidence_pack_job_worker_error", worker_id=self.worker_id, pack_id=claimed.id)
            return True

    async def run_forever(self) -> None:
        logger.info(
            "evidence_worker_started", worker_id=self.worker_id,
            poll_interval_seconds=self._poll_interval_seconds, lease_seconds=self._lease_seconds,
            max_attempts=self._max_attempts,
        )
        while not self._stopped:
            try:
                did_work = await self.poll_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("evidence_worker_poll_error", worker_id=self.worker_id)
                did_work = False
            if not did_work:
                await asyncio.sleep(self._poll_interval_seconds)
