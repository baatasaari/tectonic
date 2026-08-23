from context_engineering.core.domain import CandidateItem, OntologyConfigRecord
from context_engineering.core.ontology_filter import OntologyFilter


def _ontology(**overrides) -> OntologyConfigRecord:
    defaults = {"id": "o1", "tenant_id": "tenant-a", "version": 1, "roles": ["advisor"], "entity_types": ["account"], "policy_tags": ["public", "internal"]}
    defaults.update(overrides)
    return OntologyConfigRecord(**defaults)


def test_item_with_matching_role_and_entity_type_is_tagged():
    item = CandidateItem(source="rag", content="x", metadata={"role": "advisor", "entity_type": "account"})
    tagged = OntologyFilter().filter([item], _ontology())
    assert tagged[0].role_match is True
    assert tagged[0].entity_type_match is True


def test_item_with_no_metadata_passes_untagged():
    item = CandidateItem(source="rag", content="x")
    tagged = OntologyFilter().filter([item], _ontology())
    assert len(tagged) == 1
    assert tagged[0].role_match is False


def test_item_with_unrecognised_policy_tag_is_excluded():
    item = CandidateItem(source="rag", content="secret stuff", metadata={"policy_tags": ["top_secret"]})
    tagged = OntologyFilter().filter([item], _ontology())
    assert tagged == []


def test_item_with_recognised_policy_tag_is_included_and_matched():
    item = CandidateItem(source="rag", content="x", metadata={"policy_tags": ["internal"]})
    tagged = OntologyFilter().filter([item], _ontology())
    assert len(tagged) == 1
    assert tagged[0].matched_policy_tags == ["internal"]


def test_no_ontology_configured_passes_everything_through():
    item = CandidateItem(source="rag", content="x", metadata={"policy_tags": ["anything"]})
    tagged = OntologyFilter().filter([item], None)
    assert len(tagged) == 1
