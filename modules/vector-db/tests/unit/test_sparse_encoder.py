from vector_db.core.sparse_encoder import DEFAULT_VOCAB_SIZE, _bucket, encode


def test_empty_text_produces_empty_vector():
    result = encode("")
    assert result.indices == []
    assert result.values == []


def test_deterministic_for_same_text():
    a = encode("hello world hello")
    b = encode("hello world hello")
    assert a.indices == b.indices
    assert a.values == b.values


def test_indices_sorted_and_within_vocab():
    result = encode("the quick brown fox jumps over the lazy dog", vocab_size=1024)
    assert result.indices == sorted(result.indices)
    assert all(0 <= i < 1024 for i in result.indices)


def test_repeated_term_gets_higher_weight_than_singleton():
    repeated = encode("apple apple apple banana")
    singleton = encode("apple banana")
    # Find apple's bucket in both (same term -> same bucket).
    apple_bucket = _bucket("apple", DEFAULT_VOCAB_SIZE)
    repeated_weight = dict(zip(repeated.indices, repeated.values))[apple_bucket]
    singleton_weight = dict(zip(singleton.indices, singleton.values))[apple_bucket]
    assert repeated_weight > singleton_weight


def test_different_texts_usually_differ():
    a = encode("completely different content about astronomy")
    b = encode("another unrelated passage regarding cooking recipes")
    assert (a.indices, a.values) != (b.indices, b.values)
