"""Durable event-outbox relay worker (independent architecture assessment
§3.3 "Add an event backbone"): actually delivers what
`MultiTenancyRepository.create_tenant_and_enqueue_event`/
`.update_tenant_and_enqueue_event` durably queued, to Kafka via the
`EventPublisher` port.

This is the rollout of Workflow Engine's own `OutboxRelayWorker`
(Module 1, `core/outbox_worker.py`) to a second module -- identical
claim/lease/poison-pill shape, copied rather than shared across module
boundaries (this platform's own deployability contract: every module
is independently deployable, so no cross-module import):

- `MultiTenancyRepository.claim_next_outbox_event` atomically claims
  the oldest pending event via `SELECT ... FOR UPDATE SKIP LOCKED` in
  the real SQL implementation -- the row lock is what lets multiple
  worker processes/pods poll the same table concurrently without two
  of them ever claiming the same row.
- A claimed event gets a time-bounded lease; if the worker holding it
  crashes mid-publish, the lease simply expires and the next poll from
  *any* worker reclaims it.
- `fail_exhausted_outbox_events` is the poison-pill guard: an event
  that has failed `max_attempts` times in a row stops being retried
  and is marked `failed` for good (a malformed envelope, or a Kafka
  topic ACL problem, must not block the whole queue forever).
- `force_expire_stale_outbox_leases` is the startup recovery sweep: on
  process boot, force-expires every currently-held lease immediately.

Runs as an asyncio task inside this module's own process (see main.py's
lifespan), the same single-process-poll-loop shape this platform's
modules use throughout.
"""
from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager

from multi_tenancy.core.ports import EventPublisher, MultiTenancyRepository
from multi_tenancy.telemetry.logging import get_logger

logger = get_logger(component="outbox_worker")

RepositoryFactory = Callable[[], AbstractAsyncContextManager[MultiTenancyRepository]]


def new_worker_id() -> str:
    return f"worker-{uuid.uuid4().hex[:12]}"


class OutboxRelayWorker:
    def __init__(
        self,
        repository_factory: RepositoryFactory,
        event_publisher: EventPublisher,
        *,
        worker_id: str | None = None,
        poll_interval_seconds: float = 1.0,
        lease_seconds: int = 60,
        max_attempts: int = 5,
    ) -> None:
        # A factory over the MultiTenancyRepository port, not a raw DB session factory --
        # this class lives in core/ and stays adapter-agnostic like the rest of this
        # module's core logic, testable against the in-memory fake exactly like
        # everything else here, with no import from db/ anywhere in this file.
        self._repository_factory = repository_factory
        self._event_publisher = event_publisher
        self.worker_id = worker_id or new_worker_id()
        self._poll_interval_seconds = poll_interval_seconds
        self._lease_seconds = lease_seconds
        self._max_attempts = max_attempts
        self._stopped = False

    def stop(self) -> None:
        self._stopped = True

    async def recover_stuck_events(self) -> int:
        """Startup recovery sweep -- see module docstring. Call once before
        the poll loop starts, e.g. from the FastAPI lifespan."""
        async with self._repository_factory() as repository:
            recovered = await repository.force_expire_stale_outbox_leases()
            if recovered:
                logger.info("outbox_events_recovered", worker_id=self.worker_id, count=recovered)
            return recovered

    async def poll_once(self) -> bool:
        """Runs one claim-and-publish cycle. Returns True if it did work
        (so a caller can tighten its own poll loop when the queue is
        busy), False if the queue was empty. Exposed separately from
        run_forever() so unit tests can drive it deterministically, one
        tick at a time, without a real sleep loop."""
        async with self._repository_factory() as repository:
            failed = await repository.fail_exhausted_outbox_events(self._max_attempts)
            if failed:
                logger.warning("outbox_events_exhausted", worker_id=self.worker_id, count=failed)

            claimed = await repository.claim_next_outbox_event(self.worker_id, self._lease_seconds)
            if claimed is None:
                return False

            logger.info(
                "outbox_event_claimed", worker_id=self.worker_id, event_id=claimed.id, topic=claimed.topic,
                tenant_id=claimed.tenant_id, attempt=claimed.attempts,
            )
            try:
                await self._event_publisher.publish(claimed.topic, claimed.envelope)
                await repository.mark_outbox_event_published(claimed.id)
                logger.info(
                    "outbox_event_published", worker_id=self.worker_id, event_id=claimed.id,
                    topic=claimed.topic, attempt=claimed.attempts,
                )
            except Exception as exc:
                # A failed attempt is always requeued rather than deciding here whether
                # attempts are exhausted: fail_exhausted_outbox_events, run at the top of
                # the *next* poll, is the single place that decides an event has had its
                # last chance -- one authoritative "gave up" reason instead of two code
                # paths racing to explain a failure.
                await repository.requeue_outbox_event_for_retry(claimed.id, error=str(exc))
                logger.warning(
                    "outbox_event_requeued", worker_id=self.worker_id, event_id=claimed.id,
                    attempt=claimed.attempts, max_attempts=self._max_attempts, error=str(exc),
                )
            return True

    async def run_forever(self) -> None:
        logger.info(
            "outbox_worker_started", worker_id=self.worker_id,
            poll_interval_seconds=self._poll_interval_seconds, lease_seconds=self._lease_seconds,
            max_attempts=self._max_attempts,
        )
        while not self._stopped:
            try:
                did_work = await self.poll_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("outbox_worker_poll_error", worker_id=self.worker_id)
                did_work = False
            if not did_work:
                await asyncio.sleep(self._poll_interval_seconds)
