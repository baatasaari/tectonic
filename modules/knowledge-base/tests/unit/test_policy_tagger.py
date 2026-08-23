from knowledge_base.core.policy_tagger import tag_chunks


def test_all_chunks_inherit_document_tags_by_default():
    tags = tag_chunks(3, ["confidential", "eu-only"])
    assert tags == [["confidential", "eu-only"]] * 3


def test_chunk_override_replaces_inherited_tags():
    tags = tag_chunks(3, ["confidential"], {1: ["public"]})
    assert tags[0] == ["confidential"]
    assert tags[1] == ["public"]
    assert tags[2] == ["confidential"]


def test_zero_chunks_returns_empty_list():
    assert tag_chunks(0, ["x"]) == []
