from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Request

from human_oversight.app_context import AppContext
from human_oversight.core.decision_capture import DecisionCapture
from human_oversight.core.notification_dispatcher import NotificationDispatcher
from human_oversight.core.ports import HumanOversightRepository
from human_oversight.core.queue_manager import ApprovalQueueManager
from human_oversight.db.repository import SQLAlchemyHumanOversightRepository


def get_ctx(request: Request) -> AppContext:
    return request.app.state.ctx


async def get_repository(request: Request) -> AsyncIterator[HumanOversightRepository]:
    ctx: AppContext = request.app.state.ctx
    async with ctx.session_factory() as session:
        yield SQLAlchemyHumanOversightRepository(session)


def build_queue_manager(ctx: AppContext, repository: HumanOversightRepository) -> ApprovalQueueManager:
    return ApprovalQueueManager(repository, ctx.settings.queue.default_timeout_seconds)


def build_notification_dispatcher(ctx: AppContext) -> NotificationDispatcher:
    return NotificationDispatcher(ctx.notification_channels)


def build_decision_capture(ctx: AppContext, repository: HumanOversightRepository) -> DecisionCapture:
    return DecisionCapture(repository, ctx.callback_dispatcher, ctx.auditability)
