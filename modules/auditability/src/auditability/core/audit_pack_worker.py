"""Durable audit-pack generation worker -- the identical design Module 17
(Regulatory and Compliance) already built and proved for its own
evidence-pack generation (its Branch 3 fix: generation running as an
in-process FastAPI `BackgroundTasks` job meant a pod restart between
"202 Accepted" and job completion lost the job forever). Reused here
verbatim rather than reinvented, since the correctness property -- a pack
request surviving a pod restart -- is identical.

Postgres-backed job queue, reusing the `audit_packs` table itself as the
queue (no separate queue table/broker):

- `AuditabilityRepository.claim_next_audit_pack` atomically claims the
  oldest pending pack via `SELECT ... FOR UPDATE SKIP LOCKED` -- the row
  lock is what lets multiple worker processes/pods poll the same table
  concurrently without two of them ever claiming the same row.
- A claimed pack gets a time-bounded lease (`lease_expires_at`); if the
  worker holding it crashes mid-generation, the lease simply expires and
  the next poll from *any* worker reclaims it -- no separate "is this
  worker still alive" liveness check needed.
- `fail_exhausted_audit_packs` is the poison-pill guard: a pack that has
  failed `worker_max_attempts` times in a row stops being retried and is
  marked `failed` for good.
- `force_expire_stale_leases` is the startup recovery sweep: on process
  boot, it force-expires every currently-held lease immediately, so
  anything left mid-flight by a now-dead previous instance is reclaimed
  on the very next poll tick.

Runs as an asyncio task inside this module's own process (see main.py's
lifespan), not a separate deployment -- this platform's modules are built
as single-process services throughout.
"""
from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager

from auditability.core.audit_pack_generator import AuditPackGenerator
from auditability.core.domain import AuditPackStatus
from auditability.core.ports import AuditabilityRepository
from auditability.telemetry.logging import get_logger

logger = get_logger(component="audit_pack_worker")

RepositoryFactory = Callable[[], AbstractAsyncContextManager[AuditabilityRepository]]


def new_worker_id() -> str:
    return f"worker-{uuid.uuid4().hex[:12]}"


class AuditPackWorker:
    def __init__(
        self,
        repository_factory: RepositoryFactory,
        output_format: str,
        *,
        worker_id: str | None = None,
        poll_interval_seconds: float = 5.0,
        lease_seconds: int = 120,
        max_attempts: int = 3,
    ) -> None:
        # A factory over the AuditabilityRepository port, not a raw DB session factory --
        # this class lives in core/ and stays adapter-agnostic, testable against the
        # in-memory fake exactly like everything else here.
        self._repository_factory = repository_factory
        self._output_format = output_format
        self.worker_id = worker_id or new_worker_id()
        self._poll_interval_seconds = poll_interval_seconds
        self._lease_seconds = lease_seconds
        self._max_attempts = max_attempts
        self._stopped = False

    def stop(self) -> None:
        self._stopped = True

    async def recover_stuck_packs(self) -> int:
        async with self._repository_factory() as repository:
            recovered = await repository.force_expire_stale_leases()
            if recovered:
                logger.info("audit_pack_jobs_recovered", worker_id=self.worker_id, count=recovered)
            return recovered

    async def poll_once(self) -> bool:
        """Runs one claim-and-generate cycle. Returns True if it did work,
        False if the queue was empty. Exposed separately from run_forever()
        so unit tests can drive it deterministically, one tick at a time."""
        async with self._repository_factory() as repository:
            failed = await repository.fail_exhausted_audit_packs(self._max_attempts)
            if failed:
                logger.warning("audit_pack_jobs_exhausted", worker_id=self.worker_id, count=failed)

            claimed = await repository.claim_next_audit_pack(self.worker_id, self._lease_seconds)
            if claimed is None:
                return False

            logger.info(
                "audit_pack_job_claimed", worker_id=self.worker_id, pack_id=claimed.id,
                tenant_id=claimed.tenant_id, attempt=claimed.attempts,
            )
            generator = AuditPackGenerator(repository, self._output_format)
            try:
                result = await generator.generate(claimed.id, claimed.tenant_id)
                logger.info(
                    "audit_pack_job_finished", worker_id=self.worker_id, pack_id=claimed.id,
                    status=result.status.value, attempt=claimed.attempts,
                )
                # Always requeue a failed attempt rather than deciding here whether
                # attempts are exhausted -- fail_exhausted_audit_packs, run at the top of
                # the *next* poll, is the single place that decides a pack has had its
                # last chance, matching Module 17's evidence-worker design exactly.
                if result.status == AuditPackStatus.FAILED:
                    await repository.requeue_audit_pack_for_retry(claimed.id)
                    logger.warning(
                        "audit_pack_job_requeued", worker_id=self.worker_id, pack_id=claimed.id,
                        attempt=claimed.attempts, max_attempts=self._max_attempts, error=result.last_error,
                    )
            except Exception:
                logger.exception("audit_pack_job_worker_error", worker_id=self.worker_id, pack_id=claimed.id)
            return True

    async def run_forever(self) -> None:
        logger.info(
            "audit_pack_worker_started", worker_id=self.worker_id,
            poll_interval_seconds=self._poll_interval_seconds, lease_seconds=self._lease_seconds,
            max_attempts=self._max_attempts,
        )
        while not self._stopped:
            try:
                did_work = await self.poll_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("audit_pack_worker_poll_error", worker_id=self.worker_id)
                did_work = False
            if not did_work:
                await asyncio.sleep(self._poll_interval_seconds)
