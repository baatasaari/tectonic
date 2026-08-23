import pytest

from conversational_engine.core.emotion import EmotionUrgencyDetector

pytestmark = pytest.mark.asyncio


async def test_calm_message_scores_low():
    detector = EmotionUrgencyDetector()
    score = await detector.score("Hi, could you tell me your opening hours?", "tenant-a")
    assert score < 0.35


async def test_frustrated_message_scores_high():
    detector = EmotionUrgencyDetector()
    score = await detector.score(
        "This is UNACCEPTABLE!! I am furious, this is the worst service, give me a refund now!!!",
        "tenant-a",
    )
    assert score > 0.65


_UNCERTAIN_TEXT = "This is ridiculous, I need this urgent."  # one frustration + one urgency marker -> heuristic ~0.40


async def test_uncertain_band_falls_back_to_heuristic_without_llm_client():
    detector = EmotionUrgencyDetector(llm_gateway=None)
    score = await detector.score(_UNCERTAIN_TEXT, "tenant-a")
    assert 0.35 <= score <= 0.65  # confirms the fixture text lands in the uncertain band


async def test_llm_refinement_used_when_heuristic_uncertain():
    class Refiner:
        async def classify(self, *, text, taxonomy, tenant_id):
            return {"calm": 0.0, "frustrated": 0.9, "urgent": 0.1}

        def stream_complete(self, **kwargs):
            raise NotImplementedError

    detector = EmotionUrgencyDetector(llm_gateway=Refiner())
    # The LLM classification (frustrated=0.9, urgent=0.1) should pull the
    # final score above the plain heuristic value (~0.40).
    score = await detector.score(_UNCERTAIN_TEXT, "tenant-a")
    assert score > 0.5
