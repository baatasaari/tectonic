from __future__ import annotations

import pytest

from agentic_rag.core.fakes import (
    FakeGraphDBClient,
    FakeKnowledgeBaseClient,
    FakeVectorDBClient,
    InMemoryRAGRepository,
    StubLLMGatewayClient,
)
from agentic_rag.core.groundedness_critic import GroundednessCritic, LLMGroundednessCritic
from agentic_rag.core.hybrid_retriever import HybridRetriever
from agentic_rag.core.query_reformulator import QueryReformulator
from agentic_rag.core.rag_service import RAGService
from agentic_rag.core.retrieval_loop import RetrievalLoop


class Harness:
    def __init__(self, **kwargs):
        self.repository = InMemoryRAGRepository()
        self.vector_db = kwargs.get("vector_db") or FakeVectorDBClient()
        self.graph_db = kwargs.get("graph_db") or FakeGraphDBClient()
        self.knowledge_base = kwargs.get("knowledge_base") or FakeKnowledgeBaseClient()
        self.llm_gateway = kwargs.get("llm_gateway") or StubLLMGatewayClient()

        self.retriever = HybridRetriever(
            self.vector_db, self.graph_db, self.knowledge_base, kwargs.get("hybrid_enabled", True)
        )
        self.critic: GroundednessCritic = kwargs.get("critic") or LLMGroundednessCritic(self.llm_gateway)
        self.reformulator = QueryReformulator(self.llm_gateway)
        self.loop = RetrievalLoop(self.retriever, self.critic, self.reformulator)
        self.service = RAGService(self.repository, self.loop)


@pytest.fixture
def harness_factory():
    return Harness


@pytest.fixture
def harness():
    return Harness()
