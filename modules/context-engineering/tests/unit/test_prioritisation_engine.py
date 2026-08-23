from context_engineering.core.domain import CandidateItem, TaggedItem
from context_engineering.core.prioritisation_engine import PrioritisationEngine


def _tagged(source: str, role_match: bool = False, entity_type_match: bool = False, policy_tags: list[str] | None = None) -> TaggedItem:
    return TaggedItem(
        candidate=CandidateItem(source=source, content="x"),
        role_match=role_match, entity_type_match=entity_type_match, matched_policy_tags=policy_tags or [],
    )


def test_higher_matching_item_ranks_first_with_default_weights():
    strong = _tagged("rag", role_match=True, entity_type_match=True)
    weak = _tagged("rag")
    ranked = PrioritisationEngine().rank([weak, strong], "task", weights={})
    assert ranked[0].tagged is strong


def test_learned_weights_override_default_ranking():
    role_focused = _tagged("rag", role_match=True)
    source_focused = _tagged("short_term_memory")

    # A weight config that values the short_term_memory source far above a
    # role match should flip the default ranking.
    weights = {"role_match": 0.1, "source:short_term_memory": 10.0}
    ranked = PrioritisationEngine().rank([role_focused, source_focused], "task", weights)

    assert ranked[0].tagged is source_focused


def test_update_from_feedback_nudges_weight_toward_signal():
    engine = PrioritisationEngine()
    updated = engine.update_from_feedback({"role_match": 1.0}, feedback={"role_match": 1.0})
    assert updated["role_match"] > 1.0


def test_update_from_feedback_adds_new_feature_from_default():
    engine = PrioritisationEngine()
    updated = engine.update_from_feedback({}, feedback={"entity_type_match": 1.0})
    assert "entity_type_match" in updated
    assert updated["entity_type_match"] > 1.0  # started from the default weight, nudged upward
