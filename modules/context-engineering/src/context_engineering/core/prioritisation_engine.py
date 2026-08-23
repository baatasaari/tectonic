"""Prioritisation Engine (LLD §2.2, differentiator: "task-aware context
shaping"). Ranks filtered context items by feature-weighted scoring —
explainable and tunable rather than an opaque black box, per the LLD's
stated rationale for not using a full ML pipeline. Weights are per
tenant/task_type, updated from Evaluation Framework feedback about which
context elements actually influenced correct answers historically.
"""
from __future__ import annotations

from context_engineering.core.domain import RankedItem, TaggedItem

# A feature with no explicit weight (no learned weight yet, and not in the
# tenant's default_task_type_weights) still counts at face value rather
# than zero — "unweighted" isn't "irrelevant."
_DEFAULT_FEATURE_WEIGHT = 1.0
_LEARNING_RATE = 0.1


def item_features(item: TaggedItem) -> dict[str, float]:
    return {
        "role_match": 1.0 if item.role_match else 0.0,
        "entity_type_match": 1.0 if item.entity_type_match else 0.0,
        "policy_tag_match_count": float(len(item.matched_policy_tags)),
        f"source:{item.candidate.source}": 1.0,
    }


class PrioritisationEngine:
    def rank(self, tagged_items: list[TaggedItem], task_type: str, weights: dict[str, float]) -> list[RankedItem]:
        scored = [
            RankedItem(
                tagged=item,
                priority_score=sum(
                    weights.get(name, _DEFAULT_FEATURE_WEIGHT) * value for name, value in item_features(item).items()
                ),
            )
            for item in tagged_items
        ]
        scored.sort(key=lambda r: r.priority_score, reverse=True)
        return scored

    def update_from_feedback(self, current_weights: dict[str, float], feedback: dict[str, float]) -> dict[str, float]:
        """Nudges each fed-back feature's weight toward the Evaluation
        Framework's signal — a small, bounded step rather than overwriting
        the learned weight outright, so one batch of feedback can't swing
        prioritisation wildly."""
        updated = dict(current_weights)
        for feature, delta in feedback.items():
            updated[feature] = updated.get(feature, _DEFAULT_FEATURE_WEIGHT) + _LEARNING_RATE * delta
        return updated
