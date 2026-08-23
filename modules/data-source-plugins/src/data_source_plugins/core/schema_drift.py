"""Schema Drift Detector (LLD §2 sub-components, §Level 3 state diagram).

Compares an incoming schema (a flat `{field_name: type_name}` mapping,
the common-denominator shape after Normaliser-level type inference)
against the last-known snapshot for a connector, using `deepdiff` to find
additions, removals and type changes, then classifies the diff so the
sync orchestrator can decide auto-adapt vs. manual review per the
configured `drift.auto_adapt_scope`.
"""
from __future__ import annotations

from typing import Any

from deepdiff import DeepDiff

from data_source_plugins.core.domain import DriftClassification, DriftDetectionResult

# Widening type transitions considered safe to auto-adapt under
# "additive_and_type_widening" scope: a narrower type generalising to a
# broader one without data loss for values already seen.
_WIDENING_TRANSITIONS = {
    ("integer", "number"),
    ("integer", "string"),
    ("number", "string"),
    ("boolean", "string"),
}


def detect_drift(previous_schema: dict[str, Any], current_schema: dict[str, Any]) -> DriftDetectionResult:
    if previous_schema == current_schema:
        return DriftDetectionResult(drift_detected=False, schema_diff={}, classification=DriftClassification.ADDITIVE)

    diff = DeepDiff(previous_schema, current_schema, verbose_level=2)
    schema_diff: dict[str, Any] = diff.to_dict() if diff else {}

    removed = set(diff.get("dictionary_item_removed", []))
    added = set(diff.get("dictionary_item_added", []))
    changed = diff.get("values_changed", {})

    if removed:
        classification = DriftClassification.BREAKING
    elif changed:
        classification = DriftClassification.ADDITIVE
        for change in changed.values():
            old_val, new_val = change.get("old_value"), change.get("new_value")
            if (old_val, new_val) in _WIDENING_TRANSITIONS:
                if classification == DriftClassification.ADDITIVE:
                    classification = DriftClassification.TYPE_WIDENING
            else:
                classification = DriftClassification.BREAKING
                break
    elif added:
        classification = DriftClassification.ADDITIVE
    else:
        classification = DriftClassification.ADDITIVE

    return DriftDetectionResult(drift_detected=True, schema_diff=schema_diff, classification=classification)


def should_auto_adapt(classification: DriftClassification, *, auto_adapt_enabled: bool, auto_adapt_scope: str) -> bool:
    if not auto_adapt_enabled:
        return False
    if classification == DriftClassification.BREAKING:
        return False
    if classification == DriftClassification.ADDITIVE:
        return True
    if classification == DriftClassification.TYPE_WIDENING:
        return auto_adapt_scope == "additive_and_type_widening"
    return False
