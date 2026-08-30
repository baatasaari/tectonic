"""Tests for core/nl_query_translator.py -- the LLM Gateway's output is
always treated as an untrusted candidate, validated against this module's
own filter schema before it ever reaches a repository call."""
from __future__ import annotations

import pytest

from auditability.core.domain import InvalidNLQueryFilterError
from auditability.core.fakes import StubLLMGatewayClient
from auditability.core.nl_query_translator import NLQueryTranslator


async def test_translate_maps_a_valid_proposal_to_an_event_filter():
    llm_gateway = StubLLMGatewayClient(proposal={"event_type": "handoff", "source_module": "conversational-engine"})
    translator = NLQueryTranslator(llm_gateway)

    event_filter = await translator.translate("show me handoffs from the conversational engine", "t1")

    assert event_filter.tenant_id == "t1"
    assert event_filter.event_type == "handoff"
    assert event_filter.source_module == "conversational-engine"


async def test_translate_parses_iso_date_fields():
    llm_gateway = StubLLMGatewayClient(proposal={"occurred_after": "2026-03-01T00:00:00+00:00"})
    translator = NLQueryTranslator(llm_gateway)

    event_filter = await translator.translate("events since march", "t1")

    assert event_filter.occurred_after.year == 2026
    assert event_filter.occurred_after.month == 3


async def test_translate_rejects_a_hallucinated_field_name():
    llm_gateway = StubLLMGatewayClient(proposal={"made_up_field": "x"})
    translator = NLQueryTranslator(llm_gateway)

    with pytest.raises(InvalidNLQueryFilterError, match="made_up_field"):
        await translator.translate("something odd", "t1")


async def test_translate_rejects_an_unparseable_date():
    llm_gateway = StubLLMGatewayClient(proposal={"occurred_after": "not-a-date"})
    translator = NLQueryTranslator(llm_gateway)

    with pytest.raises(InvalidNLQueryFilterError):
        await translator.translate("since whenever", "t1")


async def test_translate_rejects_a_non_string_non_date_value():
    llm_gateway = StubLLMGatewayClient(proposal={"event_type": 123})
    translator = NLQueryTranslator(llm_gateway)

    with pytest.raises(InvalidNLQueryFilterError):
        await translator.translate("weird type", "t1")


async def test_translate_ignores_null_valued_fields_in_the_proposal():
    llm_gateway = StubLLMGatewayClient(proposal={"event_type": None})
    translator = NLQueryTranslator(llm_gateway)

    event_filter = await translator.translate("anything", "t1")

    assert event_filter.event_type is None


async def test_translate_passes_the_question_and_instruction_to_the_llm_gateway():
    llm_gateway = StubLLMGatewayClient(proposal={})
    translator = NLQueryTranslator(llm_gateway)

    await translator.translate("who overrode decision X", "t1")

    assert len(llm_gateway.calls) == 1
    assert llm_gateway.calls[0]["prompt_context"]["question"] == "who overrode decision X"
    assert llm_gateway.calls[0]["tenant_id"] == "t1"
