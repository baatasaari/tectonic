from __future__ import annotations

import pytest

from graph_db.core.fakes import InMemoryAuditabilityClient, InMemoryGraphRepository
from graph_db.core.graph_engine import GraphEngine


class Harness:
    def __init__(self, **kwargs):
        self.repository = InMemoryGraphRepository()
        self.auditability = kwargs.get("auditability") or InMemoryAuditabilityClient()
        self.max_depth = kwargs.get("max_depth", 3)

        self.engine = GraphEngine(self.repository, self.auditability, self.max_depth)


@pytest.fixture
def harness_factory():
    return Harness


@pytest.fixture
def harness():
    return Harness()
