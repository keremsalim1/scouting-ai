"""Lexical half of hybrid retrieval.

The corpus here is a small fixture inserted in a rolled-back transaction, not
whatever `make ingest-kb` last left in the table. Reason: the db suite is
already order-dependent - tests/test_rag_ingest_db.py truncates kb_chunks and
writes its own fake rows - so a test that reads "the real corpus" either fails
or, worse, passes weakly against two leftover junk rows. Searching the actual
50-chunk corpus is covered by `make kb-search` and the day-10 calibration run,
against real embeddings.
"""

from __future__ import annotations

from collections.abc import Iterator

import psycopg
import pytest

from football_ai.data.db import connect, etl_dsn
from football_ai.rag.search import (
    TextSearchConfigMismatchError,
    assert_text_search_config,
    lexical_search,
)

pytestmark = pytest.mark.db

_ZERO_VECTOR = "[" + ",".join(["0"] * 1024) + "]"

# (doc_id, topic, title, content)
_FIXTURE_CHUNKS = (
    (
        "season-vs-club",
        "season_vs_club",
        "player_season ve player_season_club ayrımı",
        "Takım değiştiren oyuncu player_season_club görünümünde iki satır alır.",
    ),
    (
        "percentile-methodology",
        "percentile_methodology",
        "Yüzdelik metodolojisi",
        "Yüzdelik, berabere duyarlı orta-sıra formülüyle hesaplanır.",
    ),
    (
        "shooting",
        "shooting",
        "Şut metrikleri",
        "npxg_per_shot payda sıfırken null döner, sıfır değil.",
    ),
)


@pytest.fixture
def corpus() -> Iterator[psycopg.Connection]:
    """A known three-chunk corpus, rolled back after the test."""
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
                "values (%s, 0, %s, 'test', %s, %s, %s, %s::vector, now())",
                [
                    (doc_id, topic, title, content, doc_id, _ZERO_VECTOR)
                    for doc_id, topic, title, content in _FIXTURE_CHUNKS
                ],
            )
        yield connection
    finally:
        # never committed: the real corpus survives this test unharmed
        connection.rollback()
        connection.close()


def test_assert_text_search_config_accepts_the_migrated_config(corpus):
    assert_text_search_config(corpus, "simple")


def test_assert_text_search_config_rejects_a_different_config(corpus):
    with pytest.raises(TextSearchConfigMismatchError, match="turkish"):
        assert_text_search_config(corpus, "turkish")


def test_lexical_search_finds_an_exact_technical_term(corpus):
    hits = lexical_search(corpus, "player_season_club", limit=5, text_search_config="simple")
    assert hits
    assert any(h.doc_id == "season-vs-club" for h in hits)
    assert [h.rank for h in hits] == list(range(1, len(hits) + 1))
    assert all(h.source and h.title for h in hits)


def test_lexical_search_ranks_a_title_match_above_a_body_mention(corpus):
    # title is weighted A, body B: a note *about* the term outranks a passing
    # mention of it
    hits = lexical_search(corpus, "yüzdelik", limit=5, text_search_config="simple")
    assert hits[0].doc_id == "percentile-methodology"


def test_lexical_search_is_case_insensitive_for_turkish_text(corpus):
    lower = lexical_search(corpus, "yüzdelik", limit=5, text_search_config="simple")
    upper = lexical_search(corpus, "YÜZDELIK", limit=5, text_search_config="simple")
    assert lower
    assert [h.chunk_id for h in lower] == [h.chunk_id for h in upper]


def test_lexical_search_survives_tsquery_operators(corpus):
    hits = lexical_search(
        corpus, 'yüzdelik & | ! "orta-sıra":', limit=5, text_search_config="simple"
    )
    assert all(h.rank >= 1 for h in hits)


def test_lexical_search_returns_empty_for_a_term_not_in_the_corpus(corpus):
    assert lexical_search(corpus, "zzzqqq", limit=5, text_search_config="simple") == []
