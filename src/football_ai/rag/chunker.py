"""Frontmatter parsing and heading-based chunking for kb/*.md.

Splits on markdown `## ` headings rather than a fixed-size sliding window:
a fixed cut can land mid-sentence, while a heading is already the boundary
the note's author chose. Oversized sections split further at a paragraph
boundary for the same reason - never mid-sentence.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import yaml

REQUIRED_FRONTMATTER_FIELDS = ("title", "topic", "source")

_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.DOTALL)
_HEADING_SPLIT_RE = re.compile(r"(?=^## )", re.MULTILINE)


class FrontmatterError(Exception):
    """Raised when a kb/ markdown file has no or incomplete frontmatter."""


@dataclass(frozen=True)
class ParsedDoc:
    title: str
    topic: str
    source: str
    body: str


@dataclass(frozen=True)
class Chunk:
    chunk_index: int
    content: str


def parse_frontmatter(markdown_text: str) -> ParsedDoc:
    match = _FRONTMATTER_RE.match(markdown_text)
    if not match:
        msg = "no --- frontmatter block found"
        raise FrontmatterError(msg)
    raw_meta, body = match.group(1), match.group(2)
    meta = yaml.safe_load(raw_meta) or {}
    missing = [field for field in REQUIRED_FRONTMATTER_FIELDS if field not in meta]
    if missing:
        msg = f"missing frontmatter fields: {missing}"
        raise FrontmatterError(msg)
    return ParsedDoc(title=meta["title"], topic=meta["topic"], source=meta["source"], body=body)


def chunk_markdown(body: str, max_words: int = 500) -> list[Chunk]:
    sections = _HEADING_SPLIT_RE.split(body)
    pieces: list[str] = []
    for section in sections:
        pieces.extend(_split_oversized(section, max_words))
    pieces = [piece for piece in pieces if not _is_empty_section(piece)]
    return [Chunk(chunk_index=i, content=piece) for i, piece in enumerate(pieces)]


def _is_empty_section(section: str) -> bool:
    """A section with only a heading and no body text is empty."""
    first_line, _, rest = section.partition("\n")
    body_text = rest if first_line.strip().startswith("## ") else section
    return not body_text.strip()


def _split_oversized(section: str, max_words: int) -> list[str]:
    words = section.split()
    if len(words) <= max_words:
        return [section]
    paragraphs = section.split("\n\n")
    if len(paragraphs) < 2:
        return [section]

    half_words = len(words) / 2
    first: list[str] = []
    second: list[str] = []
    running = 0
    for paragraph in paragraphs:
        if not first or running < half_words:
            first.append(paragraph)
            running += len(paragraph.split())
        else:
            second.append(paragraph)
    if not second:
        second = [first.pop()]

    first_text = "\n\n".join(first)
    second_text = "\n\n".join(second)
    return _split_oversized(first_text, max_words) + _split_oversized(second_text, max_words)
