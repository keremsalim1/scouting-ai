"""football.kb_chunks migration: schema and topic check constraint."""

from __future__ import annotations

import psycopg
import pytest

from football_ai.data.db import connect, readonly_dsn

pytestmark = pytest.mark.db


@pytest.fixture(scope="module")
def ro_conn():
    try:
        connection = connect(readonly_dsn(), autocommit=True)
    except psycopg.OperationalError as exc:  # pragma: no cover - env dependent
        pytest.skip(f"no read-only access: {exc}")
    yield connection
    connection.close()


def test_kb_chunks_has_expected_columns(ro_conn):
    with ro_conn.cursor() as cur:
        cur.execute(
            "select column_name from information_schema.columns "
            "where table_schema = 'football' and table_name = 'kb_chunks'"
        )
        columns = {row[0] for row in cur.fetchall()}
    assert {
        "doc_id",
        "chunk_index",
        "topic",
        "source",
        "title",
        "content",
        "content_hash",
        "embedding",
        "built_at",
    } <= columns


@pytest.fixture
def etl_conn():
    from football_ai.data.db import etl_dsn

    try:
        connection = connect(etl_dsn())
    except psycopg.OperationalError as exc:  # pragma: no cover - env dependent
        pytest.skip(f"no write access: {exc}")
    yield connection
    connection.close()


def test_kb_chunks_rejects_unknown_topic(etl_conn):
    # football_ro only has SELECT (see 008_kb.sql's grant), so an insert
    # attempt through it fails on InsufficientPrivilege before ever reaching
    # the check constraint. The constraint itself needs the writer role.
    with pytest.raises(psycopg.errors.CheckViolation), etl_conn.cursor() as cur:
        cur.execute(
            "insert into football.kb_chunks "
            "(doc_id, chunk_index, topic, source, title, content, "
            "content_hash, embedding, built_at) "
            "values ('x', 0, 'not_a_real_topic', 's', 't', 'c', 'h', "
            "array_fill(0.0, array[1024])::vector, now())"
        )
    etl_conn.rollback()
