"""methodology_search against the real ingested corpus and real models.

These are the only tests that exercise the actual bge-m3 / bge-reranker models
and the real 50-chunk corpus, which is also what makes them fragile in two
ways, both handled by skipping rather than by faking:

  * The models are local downloads (~2.2 GB and ~600 MB). CI never has them,
    so the fixtures skip when sentence-transformers cannot load.
  * tests/test_rag_ingest_db.py *commits* a two-row fake corpus, so running
    the whole `-m db` suite leaves kb_chunks unusable for these tests. They
    skip unless the table still looks like the real corpus, and the fix is to
    re-run `make ingest-kb`.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Iterator
from typing import Any

import psycopg
import pytest

from football_ai.data.db import connect, etl_dsn, readonly_dsn
from football_ai.rag.config import RagConfig
from football_ai.rag.config import load as load_config
from football_ai.rag.retrieval import methodology_search
from football_ai.rag.search import EmptyCorpusError, TextSearchConfigMismatchError

pytestmark = pytest.mark.db

# Day 9's acceptance floor was 25 documents; the real corpus is 50 chunks.
# Anything less means some other test left its fixture rows behind.
_MIN_REAL_CHUNKS = 25


def _cfg(**overrides: Any) -> RagConfig:
    return dataclasses.replace(load_config(), **overrides)


@pytest.fixture(scope="module")
def ro_conn() -> Iterator[psycopg.Connection]:
    try:
        connection = connect(readonly_dsn(), autocommit=True)
    except psycopg.OperationalError as exc:  # pragma: no cover - env dependent
        pytest.skip(f"no read-only access: {exc}")
    with connection.cursor() as cur:
        cur.execute("select count(*) from football.kb_chunks")
        count = cur.fetchone()[0]
    if count < _MIN_REAL_CHUNKS:  # pragma: no cover - env dependent
        connection.close()
        pytest.skip(f"kb_chunks has {count} rows, not the real corpus; run `make ingest-kb`")
    yield connection
    connection.close()


def _load_or_skip(name: str, warm_up):
    """Skip only when the model is genuinely absent, never on a real bug.

    A bare `except Exception -> skip` here would turn a broken reranker into a
    silently green suite, which is the exact failure this project refuses: an
    ImportError or a missing download is an environment fact, anything else is
    a finding.
    """
    try:
        warm_up()
    except (ImportError, OSError) as exc:  # pragma: no cover - env dependent
        pytest.skip(f"{name} unavailable: {exc}")


@pytest.fixture(scope="module")
def embedder() -> Any:
    from football_ai.rag.embeddings import Embedder

    instance = Embedder()
    _load_or_skip("bge-m3", lambda: instance.embed(["ısınma"]))
    return instance


@pytest.fixture(scope="module")
def reranker() -> Any:
    from football_ai.rag.rerank import Reranker

    instance = Reranker()
    _load_or_skip("bge-reranker-v2-m3", lambda: instance.score("ısınma", ["ısınma"]))
    return instance


def test_empty_corpus_raises_rather_than_abstaining(embedder):
    # zero results from an empty table is indistinguishable from a correct
    # abstention and would be read as "the corpus doesn't cover this"
    try:
        conn = connect(etl_dsn())
    except psycopg.OperationalError as exc:  # pragma: no cover - env dependent
        pytest.skip(f"no write access: {exc}")
    try:
        with conn.cursor() as cur:
            cur.execute("truncate football.kb_chunks")
        with pytest.raises(EmptyCorpusError, match="ingest-kb"):
            methodology_search(conn, "yüzdelik", embed_fn=embedder.embed, mode="dense")
    finally:
        conn.rollback()  # the real corpus survives
        conn.close()


def test_stale_text_search_config_is_refused(ro_conn, embedder):
    with pytest.raises(TextSearchConfigMismatchError):
        methodology_search(
            ro_conn,
            "yüzdelik",
            embed_fn=embedder.embed,
            mode="hybrid",
            config=_cfg(text_search_config="turkish"),
        )


def test_in_corpus_question_returns_cited_passages(ro_conn, embedder, reranker):
    result = methodology_search(
        ro_conn,
        "Yüzdelikler nasıl hesaplanıyor?",
        embed_fn=embedder.embed,
        rerank_fn=reranker.score,
    )
    assert not result.abstained, result.abstain_reason
    assert any(p.topic == "percentile_methodology" for p in result.passages)
    assert all(p.source and p.title and p.content for p in result.passages)


def test_out_of_corpus_question_abstains(ro_conn, embedder, reranker):
    result = methodology_search(
        ro_conn,
        "Mbappé'nin maaşı ne kadar?",
        embed_fn=embedder.embed,
        rerank_fn=reranker.score,
    )
    assert result.abstained
    assert result.passages == []
