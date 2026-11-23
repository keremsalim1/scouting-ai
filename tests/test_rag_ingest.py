"""kb/ document loading and row building: pure, no DB."""

from __future__ import annotations

from pathlib import Path

from football_ai.rag.chunker import ParsedDoc
from football_ai.rag.ingest import build_rows, load_kb_documents


def test_load_kb_documents_maps_filename_stem_to_doc_id(tmp_path: Path):
    (tmp_path / "shooting.md").write_text(
        "---\ntitle: T\ntopic: shooting\nsource: S\n---\n## H\nbody\n",
        encoding="utf-8",
    )
    docs = load_kb_documents(tmp_path)
    assert set(docs) == {"shooting"}
    assert docs["shooting"].topic == "shooting"


def test_build_rows_produces_one_row_per_chunk_with_hash():
    doc = ParsedDoc(title="T", topic="shooting", source="S", body="## H\nbody text\n")
    rows = build_rows("shooting", doc)
    assert len(rows) == 1
    row = rows[0]
    assert row["doc_id"] == "shooting"
    assert row["topic"] == "shooting"
    assert row["source"] == "S"
    assert row["title"] == "T"
    assert "content_hash" in row and len(row["content_hash"]) == 64
