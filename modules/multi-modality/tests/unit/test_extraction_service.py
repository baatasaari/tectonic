"""Tests for core/extraction_service.py -- runs the right extractor per
modality and the groundedness gate, degrading gracefully when Guardrails
is unavailable."""
from __future__ import annotations

from multi_modality.core.domain import GroundednessDecision, Modality
from multi_modality.core.fakes import StubGuardrailsClient


async def test_extract_without_grounding_context_is_not_checked(harness):
    extraction = await harness.extraction_service.extract(
        tenant_id="acme", modality=Modality.TEXT, raw_content="  hello  ",
    )

    assert extraction.extracted_content == "hello"
    assert extraction.groundedness_decision == GroundednessDecision.NOT_CHECKED
    assert harness.guardrails.calls == []


async def test_extract_with_grounding_context_calls_guardrails(harness_factory):
    guardrails = StubGuardrailsClient(decision="allow")
    h = harness_factory(guardrails=guardrails)

    extraction = await h.extraction_service.extract(
        tenant_id="acme", modality=Modality.DOCUMENT, raw_content="claim summary text",
        grounding_context="original claim description",
    )

    assert extraction.groundedness_decision == GroundednessDecision.ALLOW
    assert len(guardrails.calls) == 1
    assert guardrails.calls[0]["tenant_id"] == "acme"
    assert guardrails.calls[0]["context"] == "original claim description"


async def test_extract_records_a_block_decision_and_violation_category(harness_factory):
    guardrails = StubGuardrailsClient(decision="block", violation_category="ungrounded")
    h = harness_factory(guardrails=guardrails)

    extraction = await h.extraction_service.extract(
        tenant_id="acme", modality=Modality.IMAGE, raw_content="a description of a damaged bumper",
        grounding_context="claim: windshield crack only",
    )

    assert extraction.groundedness_decision == GroundednessDecision.BLOCK
    assert extraction.groundedness_violation_category == "ungrounded"


async def test_extract_degrades_to_unavailable_when_guardrails_is_down(harness_factory):
    guardrails = StubGuardrailsClient(raise_error=True)
    h = harness_factory(guardrails=guardrails)

    extraction = await h.extraction_service.extract(
        tenant_id="acme", modality=Modality.VOICE, raw_content="hello there",
        grounding_context="some reference",
    )

    # The extraction still succeeds and is returned -- only the verdict degrades.
    assert extraction.extracted_content == "hello there"
    assert extraction.groundedness_decision == GroundednessDecision.UNAVAILABLE


async def test_extract_runs_the_right_extractor_per_modality(harness):
    voice = await harness.extraction_service.extract(
        tenant_id="acme", modality=Modality.VOICE, raw_content="hi [noise] there",
    )
    assert voice.extracted_content == "hi there"

    document = await harness.extraction_service.extract(
        tenant_id="acme", modality=Modality.DOCUMENT, raw_content="a  b",
    )
    assert document.extracted_content == "a b"


async def test_extract_persists_the_record(harness):
    extraction = await harness.extraction_service.extract(
        tenant_id="acme", modality=Modality.TEXT, raw_content="hello",
    )

    fetched = await harness.repository.get_extraction(extraction.id)
    assert fetched is not None
    assert fetched.id == extraction.id
