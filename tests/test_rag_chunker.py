"""Frontmatter parsing and heading-based chunking: pure, no DB."""

from __future__ import annotations

import pytest

from football_ai.rag.chunker import (
    FrontmatterError,
    ParsedDoc,
    chunk_markdown,
    parse_frontmatter,
)


def test_parse_frontmatter_extracts_title_topic_source():
    text = (
        "---\ntitle: Şut üretimi\ntopic: shooting\nsource: proje notu\n---\n"
        "## Giriş\nİçerik burada.\n"
    )
    doc = parse_frontmatter(text)
    assert doc == ParsedDoc(
        title="Şut üretimi",
        topic="shooting",
        source="proje notu",
        body="## Giriş\nİçerik burada.\n",
    )


def test_parse_frontmatter_missing_field_raises():
    text = "---\ntitle: X\ntopic: shooting\n---\nbody\n"
    with pytest.raises(FrontmatterError):
        parse_frontmatter(text)


def test_chunk_markdown_splits_on_headings():
    body = "## Bir\npara one.\n\n## İki\npara two.\n"
    chunks = chunk_markdown(body)
    assert [c.content.strip() for c in chunks] == ["## Bir\npara one.", "## İki\npara two."]
    assert [c.chunk_index for c in chunks] == [0, 1]


def test_chunk_markdown_drops_empty_section():
    body = "## Bir\n\n## İki\ncontent.\n"
    chunks = chunk_markdown(body)
    assert len(chunks) == 1
    assert "İki" in chunks[0].content


def test_chunk_markdown_splits_oversized_section_at_paragraph_boundary():
    long_para_a = " ".join(["kelime"] * 300)
    long_para_b = " ".join(["farklı"] * 300)
    body = f"## Büyük\n{long_para_a}\n\n{long_para_b}\n"
    chunks = chunk_markdown(body, max_words=400)
    assert len(chunks) == 2
    assert "kelime" in chunks[0].content
    assert "farklı" in chunks[1].content
