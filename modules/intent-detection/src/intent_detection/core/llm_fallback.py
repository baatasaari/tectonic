"""LLM Fallback Handler (LLD §2.2): handles ambiguous or compositional
cases via a structured LLM Gateway call requesting a list of intents.
"""
from __future__ import annotations

from intent_detection.core.domain import DetectedIntent, IntentTaxonomyRecord
from intent_detection.core.ports import LLMGatewayClient


class LLMFallbackHandler:
    def __init__(self, llm_gateway: LLMGatewayClient) -> None:
        self.llm_gateway = llm_gateway

    async def resolve(self, text: str, taxonomy: IntentTaxonomyRecord, tenant_id: str) -> list[DetectedIntent]:
        taxonomy_payload = [
            {"name": i.name, "description": i.description, "examples": i.examples} for i in taxonomy.intents
        ]
        results = await self.llm_gateway.classify_structured(text=text, taxonomy=taxonomy_payload, tenant_id=tenant_id)
        return [DetectedIntent(name=r["name"], confidence=float(r["confidence"])) for r in results]
