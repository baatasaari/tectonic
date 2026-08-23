from knowledge_base.core.parser import parse


def test_plain_text_passthrough():
    result = parse(b"hello world", "text/plain")
    assert result.text == "hello world"
    assert result.headings == []


def test_markdown_headings_detected():
    content = b"# Title\n\nIntro text.\n\n## Section One\n\nBody one.\n"
    result = parse(content, "text/markdown")
    assert [h[1] for h in result.headings] == ["Title", "Section One"]


def test_markdown_detected_by_filename():
    content = b"# Heading\nbody"
    result = parse(content, "application/octet-stream", filename="doc.md")
    assert result.headings[0][1] == "Heading"


def test_html_headings_detected_and_tags_stripped():
    content = b"<html><body><h1>Welcome</h1><p>Some text.</p><h2>Details</h2><p>More.</p></body></html>"
    result = parse(content, "text/html")
    assert "Welcome" in result.text
    assert "<h1>" not in result.text
    assert [h[1] for h in result.headings] == ["Welcome", "Details"]


def test_undecodable_bytes_fall_back_gracefully():
    result = parse(b"\xff\xfe\x00\x01hello", "application/octet-stream")
    assert "hello" in result.text or result.text != ""
