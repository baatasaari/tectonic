import pytest

from intent_detection.config import ClassificationConfig
from intent_detection.core.domain import NoActiveTaxonomyError

pytestmark = pytest.mark.asyncio


async def test_high_confidence_single_intent_skips_fallback(harness):
    await harness.seed_taxonomy()

    result = await harness.service.classify("check my balance please", "tenant-a")

    assert result.fallback_used is False
    assert result.intents[0].name == "check_balance"
    assert harness.llm_gateway.calls == []


async def test_low_confidence_triggers_fallback(harness_factory):
    harness = harness_factory(config=ClassificationConfig(confidence_threshold=0.99))
    await harness.seed_taxonomy()

    # A partial-overlap phrasing, not an exact match to any taxonomy
    # example, scores well below the (deliberately strict) 0.99 threshold.
    result = await harness.service.classify("I would like to know my balance", "tenant-a")

    assert result.fallback_used is True
    assert len(harness.llm_gateway.calls) == 1


async def test_multi_intent_signal_triggers_fallback_even_with_high_confidence(harness):
    await harness.seed_taxonomy()
    harness.llm_gateway.canned_response = [
        {"name": "update_address", "confidence": 0.9},
        {"name": "check_balance", "confidence": 0.85},
    ]

    result = await harness.service.classify("update my mailing address and check my balance", "tenant-a")

    assert result.fallback_used is True
    assert {i.name for i in result.intents} == {"update_address", "check_balance"}


async def test_disabling_multi_intent_detection_skips_compositional_check(harness_factory):
    harness = harness_factory(config=ClassificationConfig(multi_intent_detection_enabled=False, confidence_threshold=0.1))
    await harness.seed_taxonomy()

    result = await harness.service.classify("update my mailing address and check my balance", "tenant-a")

    assert result.fallback_used is False  # would have triggered fallback if the check ran


async def test_no_active_taxonomy_raises(harness):
    with pytest.raises(NoActiveTaxonomyError):
        await harness.service.classify("anything", "tenant-with-no-taxonomy")


async def test_specific_taxonomy_version_used_when_requested(harness):
    await harness.seed_taxonomy(version=1)
    from intent_detection.core.domain import IntentDefinition

    await harness.seed_taxonomy(version=2, intents=[IntentDefinition(name="v2_only", examples=["v2 thing"])])

    result = await harness.service.classify("v2 thing", "tenant-a", taxonomy_version=2)

    assert result.taxonomy_version == 2


async def test_classification_is_logged(harness):
    await harness.seed_taxonomy()

    await harness.service.classify("check my balance", "tenant-a")

    logs = await harness.repository.list_classification_logs("tenant-a")
    assert len(logs) == 1
    assert logs[0].taxonomy_version == 1
