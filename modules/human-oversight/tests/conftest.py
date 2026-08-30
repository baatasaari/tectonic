from __future__ import annotations

import pytest

from human_oversight.core.decision_capture import DecisionCapture
from human_oversight.core.fakes import (
    InMemoryHumanOversightRepository,
    InMemoryNotificationChannel,
    StubAuditabilityClient,
    StubDecisionCallbackDispatcher,
)
from human_oversight.core.notification_dispatcher import NotificationDispatcher
from human_oversight.core.queue_manager import ApprovalQueueManager


class Harness:
    def __init__(self, **kwargs):
        self.repository = InMemoryHumanOversightRepository()
        self.callback_dispatcher = kwargs.get("callback_dispatcher") or StubDecisionCallbackDispatcher()
        self.auditability = kwargs.get("auditability") or StubAuditabilityClient()
        self.channels = kwargs.get("channels") or {"test-channel": InMemoryNotificationChannel()}
        self.default_timeout_seconds = kwargs.get("default_timeout_seconds", 86400)

        self.queue_manager = ApprovalQueueManager(self.repository, self.default_timeout_seconds)
        self.notification_dispatcher = NotificationDispatcher(self.channels)
        self.decision_capture = DecisionCapture(self.repository, self.callback_dispatcher, self.auditability)


@pytest.fixture
def harness_factory():
    return Harness


@pytest.fixture
def harness():
    return Harness()
