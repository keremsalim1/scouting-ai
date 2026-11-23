"""Load kb/*.md, chunk, embed, and write football.kb_chunks.

Full rebuild in one transaction (TRUNCATE then insert), the same idempotency
posture as scripts/etl.py and scripts/build_vectors.py: running it twice on
an unchanged kb/ produces identical rows.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import psycopg

from football_ai.rag.chunker import ParsedDoc, chunk_markdown, parse_frontmatter
from football_ai.rag.hashing import content_hash, dedupe_rows


def load_kb_documents(kb_dir: Path) -> dict[str, ParsedDoc]:
    return {
        path.stem: parse_frontmatter(path.read_text(encoding="utf-8"))
        for path in sorted(kb_dir.glob("*.md"))
    }


def build_rows(doc_id: str, doc: ParsedDoc) -> list[dict]:
    return [
        {
            "doc_id": doc_id,
            "chunk_index": chunk.chunk_index,
            "topic": doc.topic,
            "source": doc.source,
            "title": doc.title,
            "content": chunk.content,
            "content_hash": content_hash(chunk.content),
        }
        for chunk in chunk_markdown(doc.body)
    ]


@dataclass(frozen=True)
class IngestResult:
    total_chunks: int
    duplicate_chunks_skipped: int
    documents: int


def ingest(
    conn: psycopg.Connection,
    kb_dir: Path,
    embed_fn: Callable[[list[str]], np.ndarray],
) -> IngestResult:
    docs = load_kb_documents(kb_dir)
    all_rows: list[dict] = []
    for doc_id, doc in docs.items():
        all_rows.extend(build_rows(doc_id, doc))

    deduped, duplicate_count = dedupe_rows(
        all_rows, key=lambda row: (row["doc_id"], row["content_hash"])
    )

    embeddings = embed_fn([row["content"] for row in deduped])
    built_at = datetime.now(UTC)
    records = [
        (
            row["doc_id"],
            row["chunk_index"],
            row["topic"],
            row["source"],
            row["title"],
            row["content"],
            row["content_hash"],
            str(embedding.tolist()),
            built_at,
        )
        for row, embedding in zip(deduped, embeddings, strict=True)
    ]

    with conn.cursor() as cur:
        cur.execute("truncate football.kb_chunks")
        cur.executemany(
            "insert into football.kb_chunks (doc_id, chunk_index, topic, source, "
            "title, content, content_hash, embedding, built_at) "
            "values (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
            records,
        )
    conn.commit()

    return IngestResult(
        total_chunks=len(deduped),
        duplicate_chunks_skipped=duplicate_count,
        documents=len(docs),
    )
