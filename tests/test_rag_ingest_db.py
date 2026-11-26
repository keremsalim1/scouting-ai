"""ingest() against a real database: idempotency and dedupe."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import psycopg
import pytest
from psycopg.pq import TransactionStatus

from football_ai.data.db import connect, etl_dsn
from football_ai.rag.ingest import ingest

pytestmark = pytest.mark.db


def _fake_embed(texts: list[str]) -> np.ndarray:
    return np.zeros((len(texts), 1024), dtype=np.float32)


@pytest.fixture
def kb_dir(tmp_path: Path) -> Path:
    (tmp_path / "a.md").write_text(
        "---\ntitle: A\ntopic: shooting\nsource: S\n---\n## H1\nbody one\n## H2\nbody two\n",
        encoding="utf-8",
    )
    return tmp_path


@pytest.fixture
def etl_conn():
    """Never commits, so the real kb/ corpus survives the suite.

    `ingest()` used to commit, which meant `make test-db` left kb_chunks
    holding this file's two fake rows. Two rows is not zero rows, so
    `EmptyCorpusError` never fired afterwards and `make kb-search` - a
    documented command - silently searched "body one"/"body two". The
    transaction boundary belongs to the caller for exactly this reason;
    scripts/ingest_kb.py commits, tests roll back.
    """
    try:
        connection = connect(etl_dsn())
    except psycopg.OperationalError as exc:  # pragma: no cover - env dependent
        pytest.skip(f"no write access: {exc}")
    try:
        yield connection
    finally:
        connection.rollback()
        connection.close()


def test_ingest_leaves_committing_to_the_caller(etl_conn, kb_dir):
    """The work must still be inside an open transaction when ingest returns.

    This is the guard on the corpus: if ingest() commits, the suite destroys
    whatever `make ingest-kb` built, and the damage is invisible because a
    2-row corpus still answers queries without raising EmptyCorpusError.

    Asserted via the connection's own transaction status rather than by
    reading from a second connection: TRUNCATE holds ACCESS EXCLUSIVE, so an
    observer SELECT would block until this transaction ends and the test would
    hang instead of failing.
    """
    ingest(etl_conn, kb_dir, _fake_embed)
    assert etl_conn.info.transaction_status == TransactionStatus.INTRANS


def test_ingest_is_idempotent_on_repeat_runs(etl_conn, kb_dir):
    first = ingest(etl_conn, kb_dir, _fake_embed)
    second = ingest(etl_conn, kb_dir, _fake_embed)
    assert first.total_chunks == second.total_chunks == 2
    assert first.duplicate_chunks_skipped == 0
    with etl_conn.cursor() as cur:
        cur.execute("select count(*) from football.kb_chunks")
        assert cur.fetchone()[0] == 2


def test_ingest_keeps_same_body_chunks_from_different_docs(etl_conn, tmp_path):
    (tmp_path / "a.md").write_text(
        "---\ntitle: A\ntopic: shooting\nsource: S\n---\n## H\nsame body\n",
        encoding="utf-8",
    )
    (tmp_path / "b.md").write_text(
        "---\ntitle: B\ntopic: creation\nsource: S\n---\n## H\nsame body\n",
        encoding="utf-8",
    )
    result = ingest(etl_conn, tmp_path, _fake_embed)
    # different doc_id means these are NOT duplicates of each other (unique key
    # is (doc_id, content_hash)) - both rows persist.
    assert result.total_chunks == 2
    assert result.duplicate_chunks_skipped == 0
