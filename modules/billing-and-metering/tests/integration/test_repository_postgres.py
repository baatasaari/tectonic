"""Integration tier: proves things SQLite's unit-tier fakes can't
reliably prove -- real Postgres round-tripping for the pricing plan's
JSON `unit_prices` column, the global-default-plan lookup (`tenant_id
IS NULL`), invoice status transitions, and invoice-line ordering.
See `conftest.py` for how the Postgres instance is obtained.
"""
from __future__ import annotations

import os

import pytest
from alembic.config import Config as AlembicConfig
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from alembic import command
from billing_and_metering.core.domain import (
    InvoiceLineRecord,
    InvoiceRecord,
    InvoiceStatus,
    MeteredUsageRecord,
    PricingPlanRecord,
    new_id,
)
from billing_and_metering.db.repository import SQLAlchemyBillingRepository

pytestmark = pytest.mark.asyncio


@pytest.fixture(scope="module")
def migrated_url(postgres_url):
    alembic_cfg = AlembicConfig("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", postgres_url)
    os.environ["BILLING_DATABASE_URL"] = postgres_url
    command.upgrade(alembic_cfg, "head")
    return postgres_url


async def test_pricing_plan_unit_prices_json_round_trips(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyBillingRepository(session)
            created = await repo.create_pricing_plan(PricingPlanRecord(
                id=new_id(), tenant_id="acme", name="Standard",
                unit_prices={"llm.cost_usd": 1.5, "identity-and-access": 0.02},
            ))

            fetched = await repo.get_pricing_plan(created.id)
            assert fetched.unit_prices == {"llm.cost_usd": 1.5, "identity-and-access": 0.02}
    finally:
        await engine.dispose()


async def test_get_pricing_plan_and_get_invoice_return_none_for_a_malformed_id(migrated_url):
    """`id` is a Postgres `UUID` column; a path-param string that isn't a
    syntactically valid UUID names no row and must resolve to `None` (a
    clean 404 at the route), not an unhandled `asyncpg` `ValueError` from
    trying to bind it as one. Real regression coverage for the bug the
    contract-test tier (`tests/contract/`) caught on a real running app."""
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyBillingRepository(session)
            assert await repo.get_pricing_plan("not-a-uuid") is None
            assert await repo.get_invoice("not-a-uuid") is None
    finally:
        await engine.dispose()


async def test_default_plan_lookup_finds_the_null_tenant_plan(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyBillingRepository(session)
            default_plan = await repo.create_pricing_plan(PricingPlanRecord(
                id=new_id(), tenant_id=None, name="Global Default", unit_prices={"llm.cost_usd": 1.0},
            ))

            fetched = await repo.get_default_pricing_plan()
            assert fetched is not None
            assert fetched.id == default_plan.id

            no_tenant_plan = await repo.get_pricing_plan_for_tenant(f"no-such-tenant-{new_id()[:8]}")
            assert no_tenant_plan is None
    finally:
        await engine.dispose()


async def test_invoice_status_transition_round_trips(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyBillingRepository(session)
            invoice = await repo.create_invoice(InvoiceRecord(
                id=new_id(), tenant_id="acme", period="monthly", total_amount=42.0, complete=True,
            ))

            invoice.status = InvoiceStatus.FINALIZED
            updated = await repo.update_invoice(invoice)

            fetched = await repo.get_invoice(invoice.id)
            assert fetched.status == InvoiceStatus.FINALIZED
            assert updated.status == InvoiceStatus.FINALIZED
    finally:
        await engine.dispose()


async def test_invoice_lines_list_for_an_invoice(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyBillingRepository(session)
            invoice = await repo.create_invoice(InvoiceRecord(id=new_id(), tenant_id="acme", period="monthly"))
            await repo.create_invoice_line(InvoiceLineRecord(
                id=new_id(), invoice_id=invoice.id, resource="llm.cost_usd", quantity=10.0, unit_price=1.0, amount=10.0,
            ))
            await repo.create_invoice_line(InvoiceLineRecord(
                id=new_id(), invoice_id=invoice.id, resource="identity-and-access", quantity=5, unit_price=0.02, amount=0.1,
            ))

            lines = await repo.list_invoice_lines(invoice_id=invoice.id)
            assert len(lines) == 2
            assert {ln.resource for ln in lines} == {"llm.cost_usd", "identity-and-access"}
    finally:
        await engine.dispose()


async def test_list_usage_records_filters_by_tenant_and_period(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyBillingRepository(session)
            tenant = f"filter-tenant-{new_id()[:8]}"
            await repo.create_usage_record(MeteredUsageRecord(
                id=new_id(), tenant_id=tenant, period="monthly", resource="llm.cost_usd", quantity=10.0, source="finops",
            ))
            await repo.create_usage_record(MeteredUsageRecord(
                id=new_id(), tenant_id=tenant, period="daily", resource="llm.cost_usd", quantity=1.0, source="finops",
            ))
            await repo.create_usage_record(MeteredUsageRecord(
                id=new_id(), tenant_id="other-tenant", period="monthly", resource="llm.cost_usd", quantity=99.0,
                source="finops",
            ))

            results, total = await repo.list_usage_records(tenant_id=tenant, period="monthly")
            assert total == 1
            assert results[0].quantity == 10.0
    finally:
        await engine.dispose()
