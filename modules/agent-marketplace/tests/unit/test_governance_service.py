"""Tests for core/governance_service.py -- submit + the legal/illegal
transition matrix."""
from __future__ import annotations

import pytest

from agent_marketplace.core.domain import (
    AgentCardNotFoundError,
    InvalidTransitionError,
    ListingNotFoundError,
    ListingStatus,
)
from agent_marketplace.core.fakes import StubAgentCardsClient


async def test_submit_creates_a_pending_review_listing_snapshotting_the_card(harness):
    listing = await harness.governance_service.submit(tenant_id="acme", agent_card_id="card-1", submitted_by="alice")

    assert listing.status == ListingStatus.PENDING_REVIEW
    assert listing.name == "Search Agent"
    assert listing.trust_score_snapshot == 0.8


async def test_submit_raises_when_the_agent_card_does_not_exist(harness_factory):
    harness = harness_factory(agent_cards=StubAgentCardsClient(card=None))

    with pytest.raises(AgentCardNotFoundError):
        await harness.governance_service.submit(tenant_id="acme", agent_card_id="does-not-exist", submitted_by="alice")


async def test_approve_transitions_pending_review_to_published(harness):
    listing = await harness.governance_service.submit(tenant_id="acme", agent_card_id="card-1", submitted_by="alice")

    approved = await harness.governance_service.approve(listing.id, reviewed_by="bob")

    assert approved.status == ListingStatus.PUBLISHED
    assert approved.reviewed_by == "bob"
    assert approved.reviewed_at is not None


async def test_reject_transitions_pending_review_to_rejected_with_a_reason(harness):
    listing = await harness.governance_service.submit(tenant_id="acme", agent_card_id="card-1", submitted_by="alice")

    rejected = await harness.governance_service.reject(listing.id, reviewed_by="bob", reason="duplicate of agent X")

    assert rejected.status == ListingStatus.REJECTED
    assert rejected.rejection_reason == "duplicate of agent X"


async def test_deprecate_transitions_published_to_deprecated(harness):
    listing = await harness.governance_service.submit(tenant_id="acme", agent_card_id="card-1", submitted_by="alice")
    await harness.governance_service.approve(listing.id, reviewed_by="bob")

    deprecated = await harness.governance_service.deprecate(listing.id)

    assert deprecated.status == ListingStatus.DEPRECATED


async def test_approving_an_already_published_listing_is_illegal(harness):
    listing = await harness.governance_service.submit(tenant_id="acme", agent_card_id="card-1", submitted_by="alice")
    await harness.governance_service.approve(listing.id, reviewed_by="bob")

    with pytest.raises(InvalidTransitionError):
        await harness.governance_service.approve(listing.id, reviewed_by="bob")


async def test_rejecting_a_published_listing_is_illegal(harness):
    listing = await harness.governance_service.submit(tenant_id="acme", agent_card_id="card-1", submitted_by="alice")
    await harness.governance_service.approve(listing.id, reviewed_by="bob")

    with pytest.raises(InvalidTransitionError):
        await harness.governance_service.reject(listing.id, reviewed_by="bob", reason="too late")


async def test_deprecating_a_pending_review_listing_is_illegal(harness):
    listing = await harness.governance_service.submit(tenant_id="acme", agent_card_id="card-1", submitted_by="alice")

    with pytest.raises(InvalidTransitionError):
        await harness.governance_service.deprecate(listing.id)


async def test_transitioning_an_unknown_listing_raises_not_found(harness):
    with pytest.raises(ListingNotFoundError):
        await harness.governance_service.approve("does-not-exist", reviewed_by="bob")
