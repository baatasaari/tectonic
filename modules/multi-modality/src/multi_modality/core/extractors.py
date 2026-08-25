"""Per-modality extractors (LLD §2 sub-components "Modality
Extractors"): deterministic, synchronous stand-ins for a real cloud
ASR/vision/OCR provider. Each normalizes `raw_content` into the common
`extracted_content` shape this module returns regardless of modality.

These are intentionally simple, not a claimed ML pipeline: this
module's own real, tested contribution is the unified interface behind
them and the groundedness gate applied after them
(`extraction_service.py`), not audio/image model inference. Swapping
one of these for an adapter that actually calls a cloud provider is
real future work, the same pluggable-port shape this platform already
uses for its Tectonic-peer clients.
"""
from __future__ import annotations

import re

from multi_modality.core.domain import Modality


class TextExtractor:
    """Text is already text -- extraction is normalization only."""

    def extract(self, raw_content: str) -> str:
        return raw_content.strip()


class VoiceExtractor:
    """Stands in for a real ASR provider's output. `raw_content` is
    treated as an already-transcribed string (a real deployment's own
    ASR call happens upstream of this stand-in); this extractor's job is
    the post-ASR cleanup real transcription pipelines also do: strip
    bracketed non-speech artifacts (`[noise]`, `[silence]`, `[music]`)
    and collapse whitespace.
    """

    _ARTIFACT_PATTERN = re.compile(r"\[[^\]]*\]")

    def extract(self, raw_content: str) -> str:
        without_artifacts = self._ARTIFACT_PATTERN.sub("", raw_content)
        return re.sub(r"\s+", " ", without_artifacts).strip()


class ImageExtractor:
    """Stands in for a real vision-model provider's generated caption or
    description. `raw_content` is treated as that provider's own output
    already; this extractor's job is normalization only, identical to
    `TextExtractor` -- kept as its own class so a real vision-model
    adapter has an obvious, dedicated seam to swap in.
    """

    def extract(self, raw_content: str) -> str:
        return raw_content.strip()


class DocumentExtractor:
    """Stands in for a real document-parser/OCR provider's extracted
    text. Collapses excessive whitespace and common page-break/form-feed
    artifacts a real parser's raw output often carries.
    """

    def extract(self, raw_content: str) -> str:
        without_page_breaks = raw_content.replace("\f", "\n")
        collapsed = re.sub(r"[ \t]+", " ", without_page_breaks)
        collapsed = re.sub(r"\n{3,}", "\n\n", collapsed)
        return collapsed.strip()


def default_extractors() -> dict[Modality, object]:
    return {
        Modality.TEXT: TextExtractor(),
        Modality.VOICE: VoiceExtractor(),
        Modality.IMAGE: ImageExtractor(),
        Modality.DOCUMENT: DocumentExtractor(),
    }
