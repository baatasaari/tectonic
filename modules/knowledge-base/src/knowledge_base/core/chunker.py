"""Chunking Engine (LLD §2 sub-components, §Level 4 config
`chunking.default_strategy`): fixed_size, structural (heading-aware) and
semantic (embedding-similarity-based in the LLD) chunkers.

**Semantic chunker deviation.** The LLD calls for "semantic (embedding-
similarity-based)" chunking. Rather than a real embedding model this
module reuses the platform's established lightweight fallback — term-
frequency cosine similarity (`core/similarity.py`, the same approach used
by Modules 3/5/6) — as the coherence signal for where to break between
sentences: sentences merge into the running chunk while they stay
similar to it (approximating topical coherence) and the chunk stays
within budget. Swapping in real sentence embeddings means implementing
the same `chunk_semantic` interface with a real similarity function.
"""
from __future__ import annotations

import re

from knowledge_base.core.similarity import cosine_similarity, tokenize
from knowledge_base.core.tokenization import TokenCounter

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
_TOKENS_PER_WORD = 1.3


def _split_sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_SPLIT_RE.split(text.strip()) if s.strip()]


def chunk_fixed_size(text: str, chunk_size_tokens: int, overlap_tokens: int, counter: TokenCounter) -> list[str]:
    words = text.split()
    if not words:
        return []
    word_budget = max(1, int(chunk_size_tokens / _TOKENS_PER_WORD))
    overlap_words = max(0, min(word_budget - 1, int(overlap_tokens / _TOKENS_PER_WORD)))

    chunks: list[str] = []
    start = 0
    while start < len(words):
        end = min(len(words), start + word_budget)
        chunks.append(" ".join(words[start:end]))
        if end >= len(words):
            break
        start = end - overlap_words if overlap_words else end
    return chunks


def chunk_structural(
    text: str, headings: list[tuple[int, str]], chunk_size_tokens: int, overlap_tokens: int, counter: TokenCounter,
) -> list[str]:
    if not headings:
        return chunk_fixed_size(text, chunk_size_tokens, overlap_tokens, counter)

    sorted_headings = sorted(headings, key=lambda h: h[0])
    boundaries = [h[0] for h in sorted_headings] + [len(text)]

    sections: list[str] = []
    if sorted_headings[0][0] > 0:
        preamble = text[: sorted_headings[0][0]].strip()
        if preamble:
            sections.append(preamble)
    for i in range(len(sorted_headings)):
        section_text = text[boundaries[i] : boundaries[i + 1]].strip()
        if section_text:
            sections.append(section_text)

    chunks: list[str] = []
    for section in sections:
        if counter.count(section) <= chunk_size_tokens:
            chunks.append(section)
        else:
            chunks.extend(chunk_fixed_size(section, chunk_size_tokens, overlap_tokens, counter))
    return chunks


def chunk_semantic(
    text: str, chunk_size_tokens: int, counter: TokenCounter, *, similarity_threshold: float = 0.08,
) -> list[str]:
    sentences = _split_sentences(text)
    if not sentences:
        return []

    chunks: list[str] = []
    current = sentences[0]
    min_grow_tokens = max(1, int(chunk_size_tokens * 0.3))

    for sentence in sentences[1:]:
        candidate = f"{current} {sentence}"
        if counter.count(candidate) > chunk_size_tokens:
            chunks.append(current)
            current = sentence
            continue
        similarity = cosine_similarity(tokenize(current), tokenize(sentence))
        still_small = counter.count(current) < min_grow_tokens
        if similarity >= similarity_threshold or still_small:
            current = candidate
        else:
            chunks.append(current)
            current = sentence

    if current:
        chunks.append(current)
    return chunks


_STRATEGIES = {
    "fixed_size": lambda text, headings, size, overlap, counter: chunk_fixed_size(text, size, overlap, counter),
    "structural": lambda text, headings, size, overlap, counter: chunk_structural(text, headings, size, overlap, counter),
    "semantic": lambda text, headings, size, overlap, counter: chunk_semantic(text, size, counter),
}


def chunk(
    text: str, strategy: str, headings: list[tuple[int, str]], chunk_size_tokens: int, overlap_tokens: int,
    counter: TokenCounter,
) -> list[str]:
    fn = _STRATEGIES.get(strategy, _STRATEGIES["fixed_size"])
    return fn(text, headings, chunk_size_tokens, overlap_tokens, counter)
