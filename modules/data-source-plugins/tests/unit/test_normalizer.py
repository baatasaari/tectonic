from data_source_plugins.core.normalizer import infer_schema, infer_type, normalise


def test_infer_type_distinguishes_bool_from_int():
    assert infer_type(True) == "boolean"
    assert infer_type(1) == "integer"
    assert infer_type(1.5) == "number"
    assert infer_type("x") == "string"
    assert infer_type(None) == "null"


def test_infer_schema_scans_all_records():
    records = [{"id": 1, "name": "a"}, {"id": 2, "name": "b", "extra": True}]
    schema = infer_schema(records)
    assert schema == {"id": "integer", "name": "string", "extra": "boolean"}


def test_infer_schema_fills_null_type_from_later_non_null_record():
    records = [{"id": 1, "email": None}, {"id": 2, "email": "a@b.com"}]
    schema = infer_schema(records)
    assert schema["email"] == "string"


def test_normalise_coerces_values_to_schema_types():
    records = [{"id": "1", "amount": "10.5"}]
    schema = {"id": "integer", "amount": "number"}
    result = normalise(records, schema)
    assert result == [{"id": 1, "amount": 10.5}]


def test_normalise_drops_fields_not_in_schema_and_fills_missing_with_none():
    records = [{"id": 1, "unwanted": "x"}]
    schema = {"id": "integer", "email": "string"}
    result = normalise(records, schema)
    assert result == [{"id": 1, "email": None}]
