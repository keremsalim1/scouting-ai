"""The two retrievers behind hybrid search: lexical and dense.

They are deliberately separate functions returning the same `Hit` shape, so
fusion can combine them by rank without knowing anything about how either
produced its order. See
docs/superpowers/specs/2026-11-26-day10-rag-retrieval-design.md.

Every `Hit.score` points the same way - higher is more relevant - even though
the underlying numbers are not comparable at all (`ts_rank` is unbounded and
length-dependent, cosine similarity is bounded). That is exactly why fusion
reads ranks instead of scores.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import psycopg
from psycopg.rows import dict_row

# Columns every retriever selects. `source` and `title` are not optional:
# citation is the day-10 acceptance criterion, and both are `not null` in
# football.kb_chunks, so a passage without one is impossible by schema.
_HIT_COLUMNS = "id, doc_id, chunk_index, topic, source, title, content"


@dataclass(frozen=True)
class Hit:
    chunk_id: int
    doc_id: str
    chunk_index: int
    topic: str
    source: str
    title: str
    content: str
    score: float
    rank: int


class TextSearchConfigMismatchError(Exception):
    """Raised when config/rag.yaml disagrees with the index in the schema.

    A stored generated column needs an immutable expression, so
    009_kb_fts.sql hardcodes its text search configuration. If the query side
    ever used a different one, the search would silently run against a
    differently-tokenized query - plausible wrong passages rather than an
    error, which is the failure this project refuses to ship.
    """


class EmptyCorpusError(Exception):
    """Raised when football.kb_chunks has no rows.

    Zero results from an empty table is indistinguishable from a correct
    abstention, and a caller would read it as "the corpus does not cover
    this" - so it raises instead.
    """


def assert_text_search_config(conn: psycopg.Connection, expected: str) -> None:
    """Check that `content_tsv` was generated with `expected`'s configuration."""
    with conn.cursor() as cur:
        cur.execute(
            "select pg_get_expr(d.adbin, d.adrelid) "
            "from pg_attrdef d "
            "join pg_attribute a on a.attrelid = d.adrelid and a.attnum = d.adnum "
            "where d.adrelid = 'football.kb_chunks'::regclass "
            "and a.attname = 'content_tsv'"
        )
        row = cur.fetchone()
    if row is None:
        msg = (
            "football.kb_chunks.content_tsv is missing; apply migration "
            "009_kb_fts.sql with `make migrate`"
        )
        raise TextSearchConfigMismatchError(msg)
    expression = row[0]
    if f"'{expected}'::regconfig" not in expression:
        msg = (
            f"config/rag.yaml asks for text search configuration {expected!r}, "
            f"but content_tsv was generated as: {expression}. Changing the "
            "configuration needs a new migration, not a config edit."
        )
        raise TextSearchConfigMismatchError(msg)


def _to_hits(rows: list[dict], score_key: str) -> list[Hit]:
    return [
        Hit(
            chunk_id=row["id"],
            doc_id=row["doc_id"],
            chunk_index=row["chunk_index"],
            topic=row["topic"],
            source=row["source"],
            title=row["title"],
            content=row["content"],
            score=float(row[score_key]),
            rank=rank,
        )
        for rank, row in enumerate(rows, start=1)
    ]


def lexical_search(
    conn: psycopg.Connection,
    query: str,
    *,
    limit: int,
    text_search_config: str,
) -> list[Hit]:
    """Full-text search over `content_tsv`, ranked by `ts_rank`.

    The query is the OR of the question's lexemes, not the AND that
    `websearch_to_tsquery` and `plainto_tsquery` both produce. That choice is
    the difference between a lexical retriever and decoration: ANDing makes
    every word a hard requirement, and under the `simple` configuration there
    is no stopword list to drop question words, so "player_season_club nedir?"
    demanded a chunk containing "nedir" and returned nothing - while
    "player_season_club" alone matched. Hybrid search then silently degraded
    to dense-with-extra-steps, which the design doc names as an anti-goal.

    AND is filter semantics; retrieval wants disjunction plus ranking, and
    `ts_rank` is what separates "matched three rare terms" from "matched one
    common one". Precision is recovered downstream by fusion and the
    cross-encoder, which is what they are for.

    The lexemes come from Postgres's own parser rather than from splitting the
    string here, so tokenization matches the index exactly (`player_season_club`
    becomes three lexemes on both sides) and nothing user-typed reaches the
    tsquery as syntax.
    """
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            # string_agg over zero lexemes is NULL, so a query of pure
            # punctuation yields a NULL tsquery, matches nothing, and returns
            # an empty list rather than raising.
            "with q as ("
            "  select to_tsquery(%s, string_agg(quote_literal(lexeme), ' | ')) as query"
            "  from unnest(to_tsvector(%s, %s))"
            ") "
            f"select {_HIT_COLUMNS}, "
            "ts_rank(content_tsv, q.query) as ts_rank_score "
            "from football.kb_chunks, q "
            "where content_tsv @@ q.query "
            # id breaks ties so the rank list is deterministic; without it
            # equal-ranked chunks arrive in whatever order the scan produced.
            "order by ts_rank_score desc, id "
            "limit %s",
            (text_search_config, text_search_config, query, limit),
        )
        rows = cur.fetchall()
    return _to_hits(rows, "ts_rank_score")


def dense_search(conn: psycopg.Connection, embedding: np.ndarray, *, limit: int) -> list[Hit]:
    """Nearest neighbours by cosine distance, scored as cosine *similarity*.

    `1 - distance` rather than the raw `<=>` distance so that every Hit.score
    in this module means "higher is more relevant", the same direction as
    `ts_rank` and the reranker. A consumer that has to remember which of three
    scores is inverted will eventually forget.
    """
    vector = "[" + ",".join(str(float(value)) for value in embedding) + "]"
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            f"select {_HIT_COLUMNS}, "
            "1 - (embedding <=> %s::vector) as similarity "
            "from football.kb_chunks "
            # id breaks ties, as in lexical_search: equidistant chunks must not
            # change places between calls.
            "order by embedding <=> %s::vector, id "
            "limit %s",
            (vector, vector, limit),
        )
        rows = cur.fetchall()
    if not rows:
        msg = (
            "football.kb_chunks is empty; run `make ingest-kb` before searching. "
            "Returning zero passages here would look like a correct abstention."
        )
        raise EmptyCorpusError(msg)
    return _to_hits(rows, "similarity")
