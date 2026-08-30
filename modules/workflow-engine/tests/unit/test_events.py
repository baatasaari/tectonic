"""Tests for core/events.py -- the CloudEvents-shaped envelope contract
(independent architecture assessment §3.3 "Add an event backbone").
"""
from __future__ import annotations

from workflow_engine.core import events

REQUIRED_CORE_ATTRIBUTES = {"specversion", "id", "source", "type", "subject", "time", "datacontenttype", "data"}
REQUIRED_EXTENSION_ATTRIBUTES = {"tenant_id", "environment_id", "correlation_id", "causation_id"}


def test_workflow_started_carries_every_required_cloudevents_attribute():
    event = events.workflow_started("acme", "trace-1", "instance-1", "def-1")

    assert REQUIRED_CORE_ATTRIBUTES <= event.keys()
    assert REQUIRED_EXTENSION_ATTRIBUTES <= event.keys()
    assert event["specversion"] == "1.0"
    assert event["source"] == "tectonic://workflow-engine"
    assert event["type"] == "com.tectonic.workflow.started"
    assert event["subject"] == "instance-1"
    assert event["tenant_id"] == "acme"
    assert event["correlation_id"] == "trace-1"
    assert event["causation_id"] is None
    assert event["data"] == {"instance_id": "instance-1", "definition_id": "def-1"}


def test_every_event_id_is_unique():
    ids = {events.workflow_started("acme", "t", "i", "d")["id"] for _ in range(50)}
    assert len(ids) == 50


def test_step_completed_uses_the_step_as_subject_not_the_instance():
    event = events.step_completed("acme", "trace-1", "instance-1", "step-1", "neural", 0.92)

    assert event["subject"] == "step-1"
    assert event["data"]["instance_id"] == "instance-1"
    assert event["data"]["confidence_score"] == 0.92


def test_approval_requested_uses_the_approval_request_as_subject():
    event = events.approval_requested("acme", "trace-1", "instance-1", "step-1", "approval-1", 3600)

    assert event["subject"] == "approval-1"
    assert event["type"] == "com.tectonic.approval.requested"


def test_all_event_builders_produce_a_well_formed_envelope():
    builders_and_calls = [
        (events.workflow_completed, ("acme", "t", "i")),
        (events.workflow_failed, ("acme", "t", "i", "reason")),
        (events.workflow_paused_for_approval, ("acme", "t", "i", "s")),
        (events.step_started, ("acme", "t", "i", "s", "neural")),
        (events.step_failed, ("acme", "t", "i", "s", 1, "boom")),
        (events.approval_resolved, ("acme", "t", "i", "s", "a", "approved")),
        (events.replan_triggered, ("acme", "t", "i", "s", "reason", "outcome")),
    ]
    for builder, args in builders_and_calls:
        event = builder(*args)
        assert REQUIRED_CORE_ATTRIBUTES <= event.keys(), builder.__name__
        assert REQUIRED_EXTENSION_ATTRIBUTES <= event.keys(), builder.__name__
        assert event["type"].startswith("com.tectonic.")
