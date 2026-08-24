from __future__ import annotations

import pytest

from a2a_gateway.core.access_policy_engine import AccessPolicyEngine
from a2a_gateway.core.delegation_service import DelegationService
from a2a_gateway.core.fakes import (
    InMemoryA2AGatewayRepository,
    StubA2APeerClient,
    StubWorkflowEngineClient,
)
from a2a_gateway.core.inbound_gateway import InboundGateway
from a2a_gateway.core.rpc_gateway import A2ARpcGateway


class Harness:
    def __init__(self, **kwargs):
        self.repository = InMemoryA2AGatewayRepository()
        self.peer_client = kwargs.get("peer_client") or StubA2APeerClient()
        self.workflow_client = kwargs.get("workflow_client") or StubWorkflowEngineClient()
        self.skill_definition_map = kwargs.get("skill_definition_map") or {"summarize": "def-summarize"}

        self.access_policy_engine = AccessPolicyEngine(self.repository)
        self.delegation_service = DelegationService(self.repository, self.peer_client)
        self.inbound_gateway = InboundGateway(self.repository, self.workflow_client, self.skill_definition_map)
        self.rpc_gateway = A2ARpcGateway(self.repository, self.workflow_client, self.skill_definition_map)


@pytest.fixture
def harness_factory():
    return Harness


@pytest.fixture
def harness():
    return Harness()
