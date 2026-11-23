"""Content normalization, hashing, and duplicate-row detection for kb/ chunks.

Normalization only collapses whitespace: two chunks that differ by a
rephrased word or changed punctuation must hash differently, so this is
accidental-duplicate detection, not fuzzy matching.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Hashable


def normalize_for_hash(text: str) -> str:
    return " ".join(text.split())


def content_hash(text: str) -> str:
    return hashlib.sha256(normalize_for_hash(text).encode("utf-8")).hexdigest()


def dedupe_rows(rows: list[dict], *, key: Callable[[dict], Hashable]) -> tuple[list[dict], int]:
    seen: set[Hashable] = set()
    deduped: list[dict] = []
    duplicate_count = 0
    for row in rows:
        row_key = key(row)
        if row_key in seen:
            duplicate_count += 1
            continue
        seen.add(row_key)
        deduped.append(row)
    return deduped, duplicate_count
