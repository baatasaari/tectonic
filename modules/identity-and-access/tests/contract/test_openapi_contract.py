"""Real OpenAPI contract testing (P0 Phase 1A closure item: rollout of
Billing and Metering's own reference implementation, ticket #73/#80, to
Identity and Access) -- `schemathesis` was already a listed dev
dependency of every module in this platform, but never actually invoked
here before now.

Property-based, schema-driven fuzzing: for every operation this
module's real, generated OpenAPI document declares, Hypothesis
generates schema-conformant-but-otherwise-arbitrary request bodies/
parameters and sends them at the real running app (middleware stack
included). A 5xx response is a genuine contract violation -- proof
this module's own input validation doesn't actually reject malformed-
but-schema-valid input the way its own documented `422` response
claims it does. Directly exercises this session's own IAM v2 foundation
work (tenant-scoped roles, role bindings) against real, arbitrary
schema-valid input for the first time.

Driven directly with Hypothesis's own `@given`/`@settings`, not
schemathesis's `@schema.parametrize()`/`LazySchema` pytest integration
-- see Billing and Metering's own `test_openapi_contract.py` for why
(that combination was verified NOT to deliver an injected
`Authorization` header to the actual outgoing request in this
schemathesis version).
"""
from __future__ import annotations

from hypothesis import HealthCheck, given, settings


def _make_check(operation, auth_headers, failures: list[str]):
    @given(case=operation.as_strategy())
    @settings(max_examples=15, deadline=None, suppress_health_check=list(HealthCheck))
    def run(case) -> None:
        response = case.call(headers=auth_headers)
        if response.status_code >= 500:
            failures.append(
                f"{operation.label} -> HTTP {response.status_code} for "
                f"{case.path_parameters!r} / {case.query!r} / {case.body!r}: {response.text[:300]}"
            )

    return run


def test_no_operation_returns_a_server_error_on_schema_valid_input(api_schema, auth_headers):
    failures: list[str] = []

    for result in api_schema.get_all_operations():
        operation = result.ok()
        _make_check(operation, auth_headers, failures)()

    assert not failures, "Contract violations (schema-valid input caused a server error):\n" + "\n".join(
        f"- {f}" for f in failures
    )
