"""Content normalization, hashing, and duplicate-row detection: pure."""

from __future__ import annotations

from football_ai.rag.hashing import content_hash, dedupe_rows, normalize_for_hash


def test_normalize_collapses_internal_whitespace_and_strips_edges():
    assert normalize_for_hash("  a   b\n\nc  ") == "a b c"


def test_content_hash_same_after_whitespace_only_change():
    assert content_hash("a   b") == content_hash("a\nb")


def test_content_hash_differs_on_real_change():
    assert content_hash("a b") != content_hash("a c")


def test_dedupe_rows_keeps_first_and_counts_duplicates():
    rows = [
        {"doc_id": "x", "content_hash": "h1", "n": 1},
        {"doc_id": "x", "content_hash": "h1", "n": 2},
        {"doc_id": "x", "content_hash": "h2", "n": 3},
    ]
    deduped, dup_count = dedupe_rows(rows, key=lambda r: (r["doc_id"], r["content_hash"]))
    assert deduped == [rows[0], rows[2]]
    assert dup_count == 1
