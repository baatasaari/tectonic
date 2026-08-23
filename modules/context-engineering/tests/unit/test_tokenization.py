from context_engineering.core.tokenization import SimpleTokenCounter


def test_empty_text_counts_zero():
    assert SimpleTokenCounter().count("") == 0


def test_nonempty_text_counts_positive():
    assert SimpleTokenCounter().count("hello world") > 0


def test_longer_text_counts_more_tokens():
    counter = SimpleTokenCounter()
    short = counter.count("a short sentence")
    long = counter.count("a much longer sentence with quite a few more words in it than the short one")
    assert long > short


def test_truncate_to_zero_returns_empty_string():
    assert SimpleTokenCounter().truncate_to("some text here", 0) == ""


def test_truncate_to_fits_under_budget():
    counter = SimpleTokenCounter()
    text = " ".join(["word"] * 100)
    truncated = counter.truncate_to(text, 10)
    assert counter.count(truncated) <= 10


def test_truncate_noop_when_already_under_budget():
    counter = SimpleTokenCounter()
    text = "short text"
    assert counter.truncate_to(text, 1000) == text
