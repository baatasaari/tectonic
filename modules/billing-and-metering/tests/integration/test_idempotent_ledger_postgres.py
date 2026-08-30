"""Integration tier for the idempotent metering ledger (Phase 1 kernel):
proves the real `ON CONFLICT` upsert and the real unique constraints
SQLite's unit-tier fakes can't exercise -- concurrent-safe convergence
under real Postgres, not just single-threaded dict logic.
"""
from __future__ import annotations

import asyncio
import os

import pytest
from alembic.config import Config as AlembicConfig
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from alembic import command
from billing_and_metering.core.domain import (
    InvoiceLineRecord,
    InvoiceRecord,
    MeteredUsageRecord,
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


async def test_upsert_usage_record_converges_to_one_row_per_key(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyBillingRepository(session)
            tenant = f"tenant-{new_id()[:8]}"

            first = await repo.upsert_usage_record(MeteredUsageRecord(
                id=new_id(), tenant_id=tenant, period="monthly", resource="llm.cost_usd", quantity=10.0,
                source="finops",
            ))
            second = await repo.upsert_usage_record(MeteredUsageRecord(
                id=new_id(), tenant_id=tenant, period="monthly", resource="llm.cost_usd", quantity=25.0,
                source="finops",
            ))

            assert second.id == first.id  # same row, updated in place, not a second one
            assert second.quantity == 25.0

            results, total = await repo.list_usage_records(tenant_id=tenant, period="monthly")
            assert total == 1
            assert results[0].quantity == 25.0
    finally:
        await engine.dispose()


async def test_concurrent_upserts_for_the_same_key_never_duplicate(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        tenant = f"tenant-{new_id()[:8]}"

        async def upsert_once(quantity: float) -> None:
            async with engine.connect() as conn, AsyncSession(conn) as session:
                repo = SQLAlchemyBillingRepository(session)
                await repo.upsert_usage_record(MeteredUsageRecord(
                    id=new_id(), tenant_id=tenant, period="monthly", resource="identity-and-access",
                    quantity=quantity, source="auditability",
                ))

        await asyncio.gather(*(upsert_once(float(i)) for i in range(10)))

        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyBillingRepository(session)
            results, total = await repo.list_usage_records(tenant_id=tenant, period="monthly")
            assert total == 1  # ten concurrent callers, one converged row -- never ten
            assert results[0].quantity in {float(i) for i in range(10)}  # whichever committed last
    finally:
        await engine.dispose()


async def test_create_invoice_is_idempotent_under_a_concurrent_race(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        tenant = f"tenant-{new_id()[:8]}"

        async def create_once() -> str:
            async with engine.connect() as conn, AsyncSession(conn) as session:
                repo = SQLAlchemyBillingRepository(session)
                invoice = await repo.create_invoice(InvoiceRecord(
                    id=new_id(), tenant_id=tenant, period="monthly", total_amount=10.0,
                ))
                return invoice.id

        results = await asyncio.gather(*(create_once() for _ in range(5)))

        assert len(set(results)) == 1  # every concurrent caller converged to the same row
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyBillingRepository(session)
            _invoices, total = await repo.list_invoices(tenant_id=tenant)
            assert total == 1
    finally:
        await engine.dispose()


async def test_replace_invoice_lines_removes_stale_lines(migrated_url):
    engine = create_async_engine(migrated_url)
    try:
        async with engine.connect() as conn, AsyncSession(conn) as session:
            repo = SQLAlchemyBillingRepository(session)
            tenant = f"tenant-{new_id()[:8]}"
            invoice = await repo.create_invoice(InvoiceRecord(id=new_id(), tenant_id=tenant, period="monthly"))
            await repo.create_invoice_line(InvoiceLineRecord(
                id=new_id(), invoice_id=invoice.id, resource="stale-resource", quantity=1, unit_price=1.0, amount=1.0,
            ))

            replaced = await repo.replace_invoice_lines(invoice_id=invoice.id, records=[
                InvoiceLineRecord(
                    id=new_id(), invoice_id=invoice.id, resource="llm.cost_usd", quantity=10, unit_price=1.0,
                    amount=10.0,
                ),
            ])

            assert [line.resource for line in replaced] == ["llm.cost_usd"]
            lines = await repo.list_invoice_lines(invoice_id=invoice.id)
            assert [line.resource for line in lines] == ["llm.cost_usd"]
    finally:
        await engine.dispose()
