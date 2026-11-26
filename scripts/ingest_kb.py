"""Ingest kb/*.md into football.kb_chunks.

    uv run python scripts/ingest_kb.py

Full rebuild in one transaction (TRUNCATE then insert), same idempotency
posture as scripts/etl.py and scripts/build_vectors.py.
"""

from __future__ import annotations

from football_ai.console import force_utf8
from football_ai.data.db import REPO_ROOT, connect, etl_dsn
from football_ai.rag.embeddings import Embedder
from football_ai.rag.ingest import ingest

KB_DIR = REPO_ROOT / "kb"


def main() -> None:
    force_utf8()
    conn = connect(etl_dsn())
    embedder = Embedder()
    result = ingest(conn, KB_DIR, embedder.embed)
    # ingest() deliberately does not commit: the transaction boundary belongs
    # here, so the test suite can roll back and leave the real corpus intact.
    conn.commit()
    print(
        f"documents={result.documents} total_chunks={result.total_chunks} "
        f"duplicates_skipped={result.duplicate_chunks_skipped}"
    )


if __name__ == "__main__":
    main()
