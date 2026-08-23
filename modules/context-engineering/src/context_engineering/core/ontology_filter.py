"""Ontology Filter (LLD §2.2, differentiator: "ontology-constrained
context"). Tags each candidate against the tenant's domain ontology
(roles, entity types, policy tags) so the model receives structured,
bounded context rather than an undifferentiated pile of text.

An item whose metadata declares a `policy_tags` entry the ontology doesn't
recognise is excluded outright — ungoverned content shouldn't silently
reach the prompt just because nothing was configured to catch it. An item
with no `policy_tags` metadata at all is untagged-but-passable, so this
stays backward compatible with sources that don't yet carry ontology
metadata.
"""
from __future__ import annotations

from context_engineering.core.domain import CandidateItem, OntologyConfigRecord, TaggedItem

_EMPTY_ONTOLOGY = OntologyConfigRecord(id="none", tenant_id="*", version=0)


class OntologyFilter:
    def filter(self, candidates: list[CandidateItem], ontology: OntologyConfigRecord | None) -> list[TaggedItem]:
        ontology = ontology or _EMPTY_ONTOLOGY
        result = []
        for candidate in candidates:
            item_policy_tags = candidate.metadata.get("policy_tags", [])
            if item_policy_tags and ontology.policy_tags:
                unrecognised = [t for t in item_policy_tags if t not in ontology.policy_tags]
                if unrecognised:
                    continue  # excluded: governance tag the ontology doesn't recognise

            role = candidate.metadata.get("role")
            entity_type = candidate.metadata.get("entity_type")
            result.append(
                TaggedItem(
                    candidate=candidate,
                    role_match=bool(role) and role in ontology.roles,
                    entity_type_match=bool(entity_type) and entity_type in ontology.entity_types,
                    matched_policy_tags=[t for t in item_policy_tags if t in ontology.policy_tags],
                )
            )
        return result
