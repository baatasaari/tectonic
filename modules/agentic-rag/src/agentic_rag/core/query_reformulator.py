"""Query Reformulator (LLD §2.2): generates a revised query when
groundedness is insufficient, informed by what was missing in the prior
attempt.
"""
from __future__ import annotations

from agentic_rag.core.ports import LLMGatewayClient


class QueryReformulator:
    def __init__(self, llm_gateway: LLMGatewayClient) -> None:
        self.llm_gateway = llm_gateway

    async def reformulate(self, query: str, gaps: str, tenant_id: str) -> str:
        return await self.llm_gateway.reformulate(query=query, gaps=gaps, tenant_id=tenant_id)
