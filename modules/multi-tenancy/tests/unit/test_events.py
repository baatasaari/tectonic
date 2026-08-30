"""Tests for core/events.py -- the CloudEvents-shaped envelope contract
(independent architecture assessment §3.3 "Add an event backbone"),
this module's rollout of Workflow Engine's own reference implementation.
"""
from __future__ import annotations

from multi_tenancy.core import events

REQUIRED_CORE_ATTRIBUTES = {"specversion", "id", "source", "type", "subject", "time", "datacontenttype", "data"}
REQUIRED_EXTENSION_ATTRIBUTES = {"tenant_id", "environment_id", "correlation_id", "causation_id"}


def test_tenant_registered_carries_every_required_cloudevents_attribute():
    event = events.tenant_registered("acme", "Acme Corp", "enterprise", "org-1")

    assert REQUIRED_CORE_ATTRIBUTES <= event.keys()
    assert REQUIRED_EXTENSION_ATTRIBUTES <= event.keys()
    assert event["specversion"] == "1.0"
    assert event["source"] == "tectonic://multi-tenancy"
    assert event["type"] == "com.tectonic.tenant.registered"
    assert event["subject"] == "acme"
    assert event["tenant_id"] == "acme"
    assert event["causation_id"] is None
    assert event["data"] == {"tenant_id": "acme", "name": "Acme Corp", "tier": "enterprise", "organisation_id": "org-1"}


def test_tenant_status_changed_carries_the_transition():
    event = events.tenant_status_changed("acme", "active", "suspended")

    assert event["type"] == "com.tectonic.tenant.status_changed"
    assert event["subject"] == "acme"
    assert event["data"] == {"tenant_id": "acme", "from_status": "active", "to_status": "suspended"}


def test_every_event_id_is_unique():
    ids = {events.tenant_registered("acme", "n", "t", None)["id"] for _ in range(50)}
    assert len(ids) == 50


def test_all_event_builders_produce_a_well_formed_envelope():
    builders_and_calls = [
        (events.tenant_registered, ("acme", "Acme Corp", "standard", None)),
        (events.tenant_status_changed, ("acme", "active", "deleted")),
    ]
    for builder, args in builders_and_calls:
        event = builder(*args)
        assert REQUIRED_CORE_ATTRIBUTES <= event.keys(), builder.__name__
        assert REQUIRED_EXTENSION_ATTRIBUTES <= event.keys(), builder.__name__
        assert event["type"].startswith("com.tectonic.")
