from data_source_plugins.core.domain import DriftClassification
from data_source_plugins.core.schema_drift import detect_drift, should_auto_adapt


def test_identical_schemas_no_drift():
    schema = {"id": "integer", "name": "string"}
    result = detect_drift(schema, dict(schema))
    assert result.drift_detected is False


def test_new_field_is_additive():
    result = detect_drift({"id": "integer"}, {"id": "integer", "email": "string"})
    assert result.drift_detected is True
    assert result.classification == DriftClassification.ADDITIVE


def test_removed_field_is_breaking():
    result = detect_drift({"id": "integer", "email": "string"}, {"id": "integer"})
    assert result.drift_detected is True
    assert result.classification == DriftClassification.BREAKING


def test_safe_type_widening_is_type_widening():
    result = detect_drift({"id": "integer", "amount": "integer"}, {"id": "integer", "amount": "number"})
    assert result.drift_detected is True
    assert result.classification == DriftClassification.TYPE_WIDENING


def test_unsafe_type_change_is_breaking():
    result = detect_drift({"id": "integer", "flag": "boolean"}, {"id": "integer", "flag": "object"})
    assert result.classification == DriftClassification.BREAKING


def test_auto_adapt_additive_always_true_when_enabled():
    assert should_auto_adapt(
        DriftClassification.ADDITIVE, auto_adapt_enabled=True, auto_adapt_scope="additive_only"
    ) is True


def test_auto_adapt_type_widening_requires_wider_scope():
    assert should_auto_adapt(
        DriftClassification.TYPE_WIDENING, auto_adapt_enabled=True, auto_adapt_scope="additive_only"
    ) is False
    assert should_auto_adapt(
        DriftClassification.TYPE_WIDENING, auto_adapt_enabled=True, auto_adapt_scope="additive_and_type_widening"
    ) is True


def test_auto_adapt_breaking_never_auto_adapted():
    assert should_auto_adapt(
        DriftClassification.BREAKING, auto_adapt_enabled=True, auto_adapt_scope="additive_and_type_widening"
    ) is False


def test_auto_adapt_disabled_always_false():
    assert should_auto_adapt(
        DriftClassification.ADDITIVE, auto_adapt_enabled=False, auto_adapt_scope="additive_and_type_widening"
    ) is False
