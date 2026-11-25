"""Dense half of hybrid retrieval, over pgvector.

Vectors here are handcrafted unit vectors in a rolled-back fixture corpus
rather than real bge-m3 output, for the same reason test_rag_fts_db.py uses a
fixture corpus, plus one more: with known vectors the expected cosine
similarities are exact numbers, so the test pins the ordering *and* the
arithmetic. Against real embeddings the only honest assertion is "sorted
descending", which would pass even if the sign were flipped.
"""

from __future__ import annotations

from collections.abc import Iterator

import numpy as np
import psycopg
import pytest

from football_ai.data.db import connect, etl_dsn
from football_ai.rag.search import EmptyCorpusError, dense_search

pytestmark = pytest.mark.db

DIM = 1024


def _vector(*leading: float) -> np.ndarray:
    vector = np.zeros(DIM, dtype=np.float32)
    vector[: len(leading)] = leading
    return vector


_HALF_ROOT_TWO = float(np.sqrt(0.5))

# doc_id -> embedding. Query will be _vector(1, 0), so the expected cosine
# similarities are exactly 1.0, 0.7071... and 0.0.
_FIXTURE_VECTORS = {
    "on-axis": _vector(1.0, 0.0),
    "diagonal": _vector(_HALF_ROOT_TWO, _HALF_ROOT_TWO),
    "orthogonal": _vector(0.0, 1.0),
}


def _literal(vector: np.ndarray) -> str:
    return "[" + ",".join(str(float(value)) for value in vector) + "]"


@pytest.fixture
def corpus() -> Iterator[psycopg.Connection]:
    try:
        connection = connect(etl_dsn())
    except psycopg.OperationalError as exc:  # pragma: no cover - env dependent
        pytest.skip(f"no write access: {exc}")
    try:
        with connection.cursor() as cur:
            cur.execute("truncate football.kb_chunks")
            cur.executemany(
                "insert into football.kb_chunks (doc_id, chunk_index, topic, "
                "source, title, content, content_hash, embedding, built_at) "
                "values (%s, 0, 'shooting', 'test', %s, 'body', %s, %s::vector, now())",
                [
                    (doc_id, f"{doc_id} title", doc_id, _literal(vector))
                    for doc_id, vector in _FIXTURE_VECTORS.items()
                ],
            )
        yield connection
    finally:
        connection.rollback()
        connection.close()


@pytest.fixture
def empty_corpus() -> Iterator[psycopg.Connection]:
    try:
        connection = connect(etl_dsn())
    except psycopg.OperationalError as exc:  # pragma: no cover - env dependent
        pytest.skip(f"no write access: {exc}")
    try:
        with connection.cursor() as cur:
            cur.execute("truncate football.kb_chunks")
        yield connection
    finally:
        connection.rollback()
        connection.close()


def test_dense_search_ranks_by_similarity_descending(corpus):
    hits = dense_search(corpus, _vector(1.0, 0.0), limit=10)
    assert [h.doc_id for h in hits] == ["on-axis", "diagonal", "orthogonal"]
    assert [h.rank for h in hits] == [1, 2, 3]
    assert hits[0].score == pytest.approx(1.0, abs=1e-6)
    assert hits[1].score == pytest.approx(_HALF_ROOT_TWO, abs=1e-6)
    assert hits[2].score == pytest.approx(0.0, abs=1e-6)
    assert all(h.source and h.title for h in hits)


def test_dense_search_respects_the_limit(corpus):
    assert len(dense_search(corpus, _vector(1.0, 0.0), limit=2)) == 2


def test_dense_search_raises_on_an_empty_corpus(empty_corpus):
    # zero rows from an empty table is indistinguishable from a correct
    # abstention and would be read as "the corpus doesn't cover this"
    with pytest.raises(EmptyCorpusError, match="ingest-kb"):
        dense_search(empty_corpus, _vector(1.0, 0.0), limit=5)
