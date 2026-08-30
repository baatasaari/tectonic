from __future__ import annotations

import pytest

from short_term_memory.config import BufferConfig, SalienceConfig
from short_term_memory.core.buffer_manager import BufferManager
from short_term_memory.core.fakes import InMemoryBufferStore, StubLLMGatewayClient


class Harness:
    def __init__(self, **kwargs):
        self.store = kwargs.get("store") or InMemoryBufferStore()
        self.llm_gateway = kwargs.get("llm_gateway") or StubLLMGatewayClient()
        self.buffer_config = kwargs.get("buffer_config") or BufferConfig()
        self.salience_config = kwargs.get("salience_config") or SalienceConfig()

        self.manager = BufferManager(self.store, self.llm_gateway, self.buffer_config, self.salience_config)


@pytest.fixture
def harness_factory():
    return Harness


@pytest.fixture
def harness():
    return Harness()
