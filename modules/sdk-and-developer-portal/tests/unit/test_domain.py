"""Tests for core/domain.py's pure functions -- spec_hash and the
developer lifecycle's one-way transition."""
from __future__ import annotations

from sdk_and_developer_portal.core.domain import DeveloperStatus, is_legal_transition, spec_hash


def test_spec_hash_is_deterministic():
    spec = {"info": {"title": "X"}, "paths": {"/a": {}}}

    assert spec_hash(spec) == spec_hash(spec)


def test_spec_hash_is_order_independent():
    a = {"b": 2, "a": 1}
    b = {"a": 1, "b": 2}

    assert spec_hash(a) == spec_hash(b)


def test_spec_hash_changes_with_content():
    a = {"paths": {"/a": {}}}
    b = {"paths": {"/a": {}, "/b": {}}}

    assert spec_hash(a) != spec_hash(b)


def test_active_to_revoked_is_legal():
    assert is_legal_transition(DeveloperStatus.ACTIVE, DeveloperStatus.REVOKED) is True


def test_revoked_to_active_is_illegal():
    assert is_legal_transition(DeveloperStatus.REVOKED, DeveloperStatus.ACTIVE) is False
