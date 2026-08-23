"""Context Assembly Service (LLD §3.4): orchestrates the Ontology Filter,
Prioritisation Engine, Token Budget Enforcer and Compression — this
module's central coordinator, same role as the orchestrators in the other
modules. The final assembly step before a prompt goes to LLM Gateway.
"""
from __future__ import annotations

import time

from context_engineering.config import BudgetConfig, PrioritisationConfig
from context_engineering.core.compression import CompressionService
from context_engineering.core.domain import (
    AssembledItem,
    AssemblyResult,
    CandidateItem,
    ContextAssemblyRecord,
    ItemDisposition,
    new_id,
)
from context_engineering.core.ontology_filter import OntologyFilter
from context_engineering.core.ports import ContextRepository
from context_engineering.core.prioritisation_engine import PrioritisationEngine
from context_engineering.core.token_budget_enforcer import TokenBudgetEnforcer
from context_engineering.telemetry.metrics import (
    context_assemblies_total,
    context_assembly_duration_seconds,
    context_summarisation_invocations_total,
    context_token_utilisation_ratio,
    context_truncation_rate,
)


class ContextAssemblyService:
    def __init__(
        self,
        repository: ContextRepository,
        ontology_filter: OntologyFilter,
        prioritisation_engine: PrioritisationEngine,
        budget_enforcer: TokenBudgetEnforcer,
        compression_service: CompressionService,
        prioritisation_config: PrioritisationConfig,
        budget_config: BudgetConfig,
    ) -> None:
        self.repository = repository
        self.ontology_filter = ontology_filter
        self.prioritisation_engine = prioritisation_engine
        self.budget_enforcer = budget_enforcer
        self.compression_service = compression_service
        self.prioritisation_config = prioritisation_config
        self.budget_config = budget_config

    async def assemble(
        self,
        candidate_items: list[CandidateItem],
        token_budget: int,
        task_type: str,
        tenant_id: str,
        request_ref: str,
    ) -> AssemblyResult:
        start = time.perf_counter()

        ontology = await self.repository.get_active_ontology(tenant_id)
        tagged = self.ontology_filter.filter(candidate_items, ontology)

        weights_record = await self.repository.get_weights(tenant_id, task_type)
        weights = (
            weights_record.feature_weights
            if weights_record
            else self.prioritisation_config.default_task_type_weights.get(task_type, {})
        )
        ranked = self.prioritisation_engine.rank(tagged, task_type, weights)

        selection = self.budget_enforcer.select(ranked, token_budget)

        included: list[AssembledItem] = [
            AssembledItem(source=item.tagged.candidate.source, content=item.tagged.candidate.content, tokens=tokens, disposition=ItemDisposition.INCLUDED)
            for item, tokens in selection.fits
        ]
        summarised: list[AssembledItem] = []
        dropped: list[AssembledItem] = []
        tokens_used = selection.tokens_used
        remaining = token_budget - tokens_used

        # Overflow items are already priority-ordered; try summarisation
        # for each in turn while there's still budget left to spend on one.
        for item, _original_tokens in selection.overflow:
            if not self.budget_config.summarisation_enabled or remaining <= 0:
                dropped.append(
                    AssembledItem(source=item.tagged.candidate.source, content=item.tagged.candidate.content, tokens=0, disposition=ItemDisposition.DROPPED)
                )
                continue

            outcome = await self.compression_service.summarise(item, remaining, tenant_id)
            context_summarisation_invocations_total.labels(tenant_id=tenant_id).inc()
            if outcome.summary is not None:
                summarised.append(
                    AssembledItem(source=item.tagged.candidate.source, content=outcome.summary, tokens=outcome.tokens, disposition=ItemDisposition.SUMMARISED)
                )
                tokens_used += outcome.tokens
                remaining -= outcome.tokens
            else:
                dropped.append(
                    AssembledItem(source=item.tagged.candidate.source, content=item.tagged.candidate.content, tokens=0, disposition=ItemDisposition.DROPPED)
                )

        assembled_context = "\n\n".join(i.content for i in included + summarised)

        await self.repository.create_assembly_log(
            ContextAssemblyRecord(
                id=new_id(), request_ref=request_ref, task_type=task_type,
                items_included=included, items_dropped=dropped, items_summarised=summarised,
                total_tokens_used=tokens_used,
            )
        )

        candidate_count = len(candidate_items) or 1
        context_assemblies_total.labels(tenant_id=tenant_id, task_type=task_type).inc()
        context_token_utilisation_ratio.labels(tenant_id=tenant_id, task_type=task_type).observe(
            tokens_used / token_budget if token_budget else 0.0
        )
        context_truncation_rate.labels(tenant_id=tenant_id, task_type=task_type).observe(len(dropped) / candidate_count)
        context_assembly_duration_seconds.labels(tenant_id=tenant_id).observe(time.perf_counter() - start)

        return AssemblyResult(
            assembled_context=assembled_context,
            tokens_used=tokens_used,
            items_included_count=len(included),
            items_dropped_count=len(dropped),
            items_summarised_count=len(summarised),
        )
