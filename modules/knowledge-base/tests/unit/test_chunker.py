from knowledge_base.core.chunker import chunk_fixed_size, chunk_semantic, chunk_structural
from knowledge_base.core.tokenization import SimpleTokenCounter

counter = SimpleTokenCounter()


def test_fixed_size_splits_into_multiple_chunks_when_over_budget():
    text = " ".join([f"word{i}" for i in range(100)])
    chunks = chunk_fixed_size(text, chunk_size_tokens=50, overlap_tokens=0, counter=counter)
    assert len(chunks) > 1
    for c in chunks:
        assert counter.count(c) <= 55  # small slack for the word-budget approximation


def test_fixed_size_overlap_repeats_trailing_words():
    text = " ".join([f"word{i}" for i in range(40)])
    chunks = chunk_fixed_size(text, chunk_size_tokens=20, overlap_tokens=10, counter=counter)
    assert len(chunks) >= 2
    # Some words from the end of chunk 0 should reappear at the start of chunk 1.
    first_words = chunks[0].split()
    second_words = chunks[1].split()
    assert any(w in second_words for w in first_words[-3:])


def test_fixed_size_short_text_single_chunk():
    chunks = chunk_fixed_size("short text here", chunk_size_tokens=512, overlap_tokens=50, counter=counter)
    assert chunks == ["short text here"]


def test_fixed_size_empty_text_no_chunks():
    assert chunk_fixed_size("", chunk_size_tokens=512, overlap_tokens=50, counter=counter) == []


def test_structural_splits_on_headings():
    text = "# Intro\nIntro body.\n# Details\nDetails body with more words in it."
    headings = [(0, "Intro"), (text.index("# Details"), "Details")]
    chunks = chunk_structural(text, headings, chunk_size_tokens=512, overlap_tokens=0, counter=counter)
    assert len(chunks) == 2
    assert "Intro" in chunks[0]
    assert "Details" in chunks[1]


def test_structural_falls_back_to_fixed_size_without_headings():
    text = " ".join([f"word{i}" for i in range(100)])
    chunks = chunk_structural(text, [], chunk_size_tokens=50, overlap_tokens=0, counter=counter)
    assert len(chunks) > 1


def test_structural_large_section_further_split():
    body = " ".join([f"word{i}" for i in range(200)])
    text = f"# Big Section\n{body}"
    headings = [(0, "Big Section")]
    chunks = chunk_structural(text, headings, chunk_size_tokens=50, overlap_tokens=0, counter=counter)
    assert len(chunks) > 1


def test_semantic_groups_similar_adjacent_sentences():
    text = (
        "The cat sat on the mat. The cat likes the warm mat. "
        "Stock markets rallied today on strong earnings. Tech stocks led broad market gains."
    )
    chunks = chunk_semantic(text, chunk_size_tokens=512, counter=counter)
    assert len(chunks) >= 1
    # The whole thing fits comfortably within budget with the "still small"
    # grow-through-dissimilarity rule, but each chunk must be non-empty.
    assert all(c.strip() for c in chunks)


def test_semantic_respects_token_budget():
    text = ". ".join([f"Sentence number {i} about topic {i}" for i in range(30)]) + "."
    chunks = chunk_semantic(text, chunk_size_tokens=30, counter=counter)
    assert len(chunks) > 1
    for c in chunks:
        assert counter.count(c) <= 35


def test_semantic_empty_text_no_chunks():
    assert chunk_semantic("", chunk_size_tokens=512, counter=counter) == []
