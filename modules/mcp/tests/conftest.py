from __future__ import annotations

import pytest

from mcp_gateway.core.access_policy_engine import AccessPolicyEngine
from mcp_gateway.core.capability_sync_service import CapabilitySyncService
from mcp_gateway.core.fakes import InMemoryMCPGatewayRepository, StubMCPBackendClient
from mcp_gateway.core.registry_service import RegistryService
from mcp_gateway.core.rpc_gateway import RpcGateway


class Harness:
    def __init__(self, **kwargs):
        self.repository = InMemoryMCPGatewayRepository()
        self.backend = kwargs.get("backend") or StubMCPBackendClient()

        self.registry_service = RegistryService(self.repository)
        self.access_policy_engine = AccessPolicyEngine(self.repository)
        self.rpc_gateway = RpcGateway(self.repository, self.backend)
        self.capability_sync_service = CapabilitySyncService(self.repository, self.backend)


@pytest.fixture
def harness_factory():
    return Harness


@pytest.fixture
def harness():
    return Harness()
