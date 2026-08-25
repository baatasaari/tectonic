"""Tests for core/extractors.py -- per-modality normalization."""
from __future__ import annotations

from multi_modality.core.extractors import (
    DocumentExtractor,
    ImageExtractor,
    TextExtractor,
    VoiceExtractor,
)


def test_text_extractor_trims_whitespace():
    assert TextExtractor().extract("  hello world  ") == "hello world"


def test_voice_extractor_strips_non_speech_artifacts():
    result = VoiceExtractor().extract("hello [noise] there [silence]  friend")
    assert result == "hello there friend"


def test_voice_extractor_collapses_whitespace():
    result = VoiceExtractor().extract("hello    there\n\nfriend")
    assert result == "hello there friend"


def test_image_extractor_trims_whitespace():
    assert ImageExtractor().extract("  a red car in a driveway  ") == "a red car in a driveway"


def test_document_extractor_collapses_page_breaks_and_excess_blank_lines():
    raw = "Page one text.\f\n\n\n\nPage two text."
    result = DocumentExtractor().extract(raw)
    assert "\f" not in result
    assert "\n\n\n" not in result


def test_document_extractor_collapses_repeated_spaces():
    result = DocumentExtractor().extract("Hello    world")
    assert result == "Hello world"
