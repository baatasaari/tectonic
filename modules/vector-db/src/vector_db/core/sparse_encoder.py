"""Sparse Encoder (LLD §2 sub-components) — deviation from the LLD's
`fastembed` choice; see the module README's "Design notes vs. the LLD".
Produces a BM25-style sparse vector via the hashing trick: each term
hashes (via `zlib.crc32`, stable across processes — unlike Python's
built-in `hash()` for strings, which is salted per-process) into a fixed-
size index space, with values set to a log-dampened term frequency. This
needs no pretrained vocabulary or model download, so it carries zero
network dependency, at the cost of occasional hash collisions between
unrelated terms — an acceptable trade-off for a keyword-recall signal
that always runs alongside dense vector search in this module's hybrid
queries.
"""
from __future__ import annotations

import math
import re
import zlib
from collections import Counter

from vector_db.core.domain import SparseVectorData

_TOKEN_RE = re.compile(r"[a-z0-9]+")
DEFAULT_VOCAB_SIZE = 2**18


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def _bucket(term: str, vocab_size: int) -> int:
    return zlib.crc32(term.encode("utf-8")) % vocab_size


def encode(text: str, vocab_size: int = DEFAULT_VOCAB_SIZE) -> SparseVectorData:
    tokens = _tokenize(text)
    if not tokens:
        return SparseVectorData(indices=[], values=[])

    counts = Counter(tokens)
    buckets: dict[int, float] = {}
    for term, count in counts.items():
        index = _bucket(term, vocab_size)
        weight = 1.0 + math.log(count)
        # Collisions accumulate weight rather than overwrite — a
        # reasonable approximation when two distinct terms happen to
        # share a bucket.
        buckets[index] = buckets.get(index, 0.0) + weight

    sorted_items = sorted(buckets.items())
    return SparseVectorData(indices=[i for i, _ in sorted_items], values=[v for _, v in sorted_items])
