"""Document Parser (LLD §2 sub-components) — deviation from the LLD's
`unstructured`/`pypdf` choice; see the module README's "Design notes vs.
the LLD". Handles the text-native formats directly (plain text, Markdown,
HTML) and falls back to best-effort UTF-8 decoding for anything else, so
the module has zero binary-parsing dependencies for its unit-test tier.
"""
from __future__ import annotations

import re

from knowledge_base.core.ports import ParsedContent

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_HTML_HEADING_RE = re.compile(r"<h([1-6])[^>]*>(.*?)</h\1>", re.IGNORECASE | re.DOTALL)
_MD_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)


def _decode(raw: bytes) -> str:
    for encoding in ("utf-8", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="ignore")


def _parse_html(text: str) -> ParsedContent:
    headings: list[tuple[int, str]] = []
    plain = _HTML_TAG_RE.sub(lambda m: "", text)
    # Re-scan to locate headings by their text within the tag-stripped body.
    for match in _HTML_HEADING_RE.finditer(text):
        heading_text = _HTML_TAG_RE.sub("", match.group(2)).strip()
        offset = plain.find(heading_text)
        if heading_text and offset != -1:
            headings.append((offset, heading_text))
    plain = re.sub(r"\n{3,}", "\n\n", plain).strip()
    return ParsedContent(text=plain, headings=headings)


def _parse_markdown(text: str) -> ParsedContent:
    headings = [(m.start(), m.group(2).strip()) for m in _MD_HEADING_RE.finditer(text)]
    return ParsedContent(text=text.strip(), headings=headings)


def parse(raw: bytes, content_type: str = "text/plain", filename: str = "") -> ParsedContent:
    text = _decode(raw)
    lowered_type = (content_type or "").lower()
    is_markdown = "markdown" in lowered_type or filename.lower().endswith((".md", ".markdown"))
    is_html = "html" in lowered_type or filename.lower().endswith((".html", ".htm"))

    if is_html:
        return _parse_html(text)
    if is_markdown:
        return _parse_markdown(text)
    return ParsedContent(text=text.strip(), headings=[])
