"""Real OpenAPI contract testing (Phase 1 kernel: CI supply-chain
gates) -- `schemathesis` was already a listed dev dependency of every
module in this platform, but never actually invoked anywhere; this is
the reference implementation that makes it real.

Property-based, schema-driven fuzzing: for every operation this
module's real, generated OpenAPI document declares, Hypothesis
generates schema-conformant-but-otherwise-arbitrary request bodies/
parameters and sends them at the real running app (middleware stack
included). A 5xx response is a genuine contract violation -- proof
this module's own input validation doesn't actually reject malformed-
but-schema-valid input the way its own documented `422` response
claims it does. On its first real runs this exact test caught three:
  1. `GET /pricing-plans?offset=<out-of-64-bit-range integer>` crashed
     with an unhandled `DataError` instead of a clean `422`, because
     `Query(0, ge=0)` (no upper bound) let schemathesis generate an
     arbitrarily large `offset` that overflowed Postgres's `bigint`
     column type deep inside the query -- fixed with an `le=` bound on
     every `offset`/`limit` query parameter this module declares
     (`api/routes_billing_and_metering.py`).
  2. `POST /pricing-plans` with a NUL byte (`\x00`) in `name`/
     `tenant_id`/a `unit_prices` key crashed with an unhandled
     `CharacterNotInRepertoireError` -- schema-valid per OpenAPI
     (`type: string` says nothing about NUL) but not valid UTF-8 text
     as far as Postgres is concerned -- fixed with a `field_validator`
     rejecting the NUL byte on every affected request field
     (`schemas/billing_and_metering.py`), returning a clean `422`.
  3. `GET /pricing-plans/{plan_id}` and `GET /invoices/{invoice_id}`
     with a non-UUID path segment crashed with an unhandled `ValueError`
     from `asyncpg` trying to bind it to the `UUID` column -- fixed by
     guarding both repository lookups with a syntactic UUID check that
     returns `None` (a clean `404`) instead (`db/repository.py`).
  4. `GET /invoices?status=<anything>` crashed with an unhandled
     `ValueError: '...' is not a valid InvoiceStatus` because the route
     hand-converted an untyped `str` query parameter -- fixed by typing
     the parameter itself as `InvoiceStatus | None`, letting FastAPI/
     Pydantic reject a non-member value with a clean `422`
     (`api/routes_billing_and_metering.py`).

Driven directly with Hypothesis's own `@given`/`@settings`, not
schemathesis's `@schema.parametrize()`/`LazySchema` pytest integration:
that combination (a lazily-resolved, fixture-backed schema plus a
`schemathesis.auth()` provider) was verified NOT to deliver the
provider's injected `Authorization` header to the actual outgoing
request in this schemathesis version -- confirmed directly (the
provider's own `set()` ran, but the request that reached the ASGI app
never carried it) -- while `Case.call(headers=...)` called directly,
as this file does, was verified to work correctly. Real headers on
every real request beats a convenience wrapper that silently drops
them.
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
