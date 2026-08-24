"""Regression test for the connection-pool sizing fix: `make_engine` must
actually apply the configured pool_size/max_overflow/timeout/recycle to the
resulting engine, not just accept them as unused Settings fields. Defaults
are asserted explicitly so a future accidental revert back to SQLAlchemy's
un-tuned defaults (pool_size=5, max_overflow=10 regardless of this module's
own replica count) is caught here, not discovered in production.
"""
from __future__ import annotations

from workflow_engine.config import WorkflowEngineSettings
from workflow_engine.db.session import make_engine


def test_make_engine_applies_configured_pool_settings():
    settings = WorkflowEngineSettings(database_url="postgresql+asyncpg://u:p@localhost:5432/db")

    engine = make_engine(settings)

    assert engine.pool.size() == 10
    assert engine.pool._max_overflow == 5
    assert engine.pool._timeout == 30
    assert engine.pool._recycle == 1800


def test_pool_settings_are_overridable_via_settings():
    settings = WorkflowEngineSettings(
        database_url="postgresql+asyncpg://u:p@localhost:5432/db",
        db_pool_size=7, db_max_overflow=3, db_pool_timeout_seconds=15, db_pool_recycle_seconds=600,
    )

    engine = make_engine(settings)

    assert engine.pool.size() == 7
    assert engine.pool._max_overflow == 3
    assert engine.pool._timeout == 15
    assert engine.pool._recycle == 600
