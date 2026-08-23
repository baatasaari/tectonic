"""Normaliser (LLD §2 sub-components): converts source-specific payloads
into the platform's common internal schema — a flat `{field: value}` shape
per record, values coerced to the types declared in the connector's
current schema mapping."""
from __future__ import annotations

from typing import Any

_TYPE_NAMES = {
    bool: "boolean",
    int: "integer",
    float: "number",
    str: "string",
    dict: "object",
    list: "array",
}


def infer_type(value: Any) -> str:
    if value is None:
        return "null"
    for py_type, name in _TYPE_NAMES.items():
        # bool must be checked before int since bool is an int subclass
        if py_type is bool and isinstance(value, bool):
            return name
        if py_type is not bool and py_type is int and isinstance(value, bool):
            continue
        if isinstance(value, py_type):
            return name
    return "string"


def infer_schema(records: list[dict[str, Any]]) -> dict[str, str]:
    """Derives a flat field->type schema by scanning all records — the
    common denominator the Schema Drift Detector compares against."""
    schema: dict[str, str] = {}
    for record in records:
        for field_name, value in record.items():
            inferred = infer_type(value)
            if inferred == "null":
                schema.setdefault(field_name, "null")
                continue
            existing = schema.get(field_name)
            if existing is None or existing == "null":
                schema[field_name] = inferred
    return schema


def _coerce(value: Any, type_name: str) -> Any:
    if value is None:
        return None
    try:
        if type_name == "string":
            return str(value)
        if type_name == "integer":
            return int(value)
        if type_name == "number":
            return float(value)
        if type_name == "boolean":
            return bool(value)
    except (TypeError, ValueError):
        return value
    return value


def normalise(records: list[dict[str, Any]], schema: dict[str, str]) -> list[dict[str, Any]]:
    """Coerces every record's fields to the types declared in `schema`
    (the adapted mapping after any auto-adapt decision), dropping fields
    the schema doesn't know about and filling absent ones with None."""
    normalised: list[dict[str, Any]] = []
    for record in records:
        row = {field_name: _coerce(record.get(field_name), type_name) for field_name, type_name in schema.items()}
        normalised.append(row)
    return normalised
