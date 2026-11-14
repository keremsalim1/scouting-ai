"""Day 4 acceptance criteria against the live database.

Every expected value below is recomputed from football.player_match_stats, the
fact table. Checking a view against itself proves nothing.

    make db-up && make migrate && make etl
    uv run pytest -m db
"""

from __future__ import annotations

import psycopg
import pytest

from football_ai import metrics as mx
from football_ai.data.db import connect, etl_dsn, readonly_dsn

pytestmark = pytest.mark.db

TOLERANCE = 1e-9


@pytest.fixture(scope="module")
def conn():
    try:
        connection = connect(etl_dsn())
    except psycopg.OperationalError as exc:  # pragma: no cover - env dependent
        pytest.skip(f"no database: {exc}")
    yield connection
    connection.close()


@pytest.fixture(scope="module")
def cfg() -> mx.MetricsConfig:
    return mx.load()


def _scalar(conn, sql: str, params: tuple = ()):
    with conn.cursor() as cur:
        cur.execute(sql, params)
        row = cur.fetchone()
        return row[0] if row else None


# ---------------------------------------------------------------------------
# yaml, table and view must name the same metrics
# ---------------------------------------------------------------------------


def test_metric_definitions_match_the_yaml(conn, cfg) -> None:
    with conn.cursor() as cur:
        cur.execute("select key from football.metric_definitions")
        in_db = {r[0] for r in cur.fetchall()}
    assert in_db == cfg.keys


def test_view_exposes_exactly_the_defined_metrics(conn, cfg) -> None:
    """The lateral VALUES list in the view is hand-maintained; this catches a
    metric added to the yaml but not to the view, and vice versa."""
    with conn.cursor() as cur:
        cur.execute("select distinct metric from football.player_metrics")
        in_view = {r[0] for r in cur.fetchall()}
    assert in_view == cfg.keys


def test_metric_config_matches_the_yaml(conn, cfg) -> None:
    with conn.cursor() as cur:
        cur.execute("select key, value from football.metric_config")
        assert dict(cur.fetchall()) == cfg.config_values


def test_every_source_column_exists_on_player_per90(conn, cfg) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            select column_name from information_schema.columns
            where table_schema = 'football' and table_name = 'player_per90'
            """
        )
        columns = {r[0] for r in cur.fetchall()}
    missing = sorted({m.source_column for m in cfg.metrics} - columns)
    assert not missing


# ---------------------------------------------------------------------------
# Percentile bounds and orientation
# ---------------------------------------------------------------------------


def test_percentiles_are_inside_zero_and_one_hundred(conn) -> None:
    bad = _scalar(
        conn,
        "select count(*) from football.player_metrics "
        "where percentile is not null and (percentile < 0 or percentile > 100)",
    )
    assert bad == 0


def test_percentiles_never_hit_an_absolute_zero_or_hundred(conn) -> None:
    """Midrank, not percent_rank or cume_dist: nobody is ranked as absolutely
    worst or absolutely best in a finite sample."""
    bad = _scalar(
        conn,
        "select count(*) from football.player_metrics "
        "where percentile is not null and (percentile <= 0 or percentile >= 100)",
    )
    assert bad == 0


def test_tied_values_receive_the_same_percentile(conn) -> None:
    bad = _scalar(
        conn,
        """
        select count(*)
        from football.player_metrics a
        join football.player_metrics b
          on a.metric = b.metric
         and a.comparison_scope = b.comparison_scope
         and coalesce(a.comparison_comp, '-') = coalesce(b.comparison_comp, '-')
         and a.position_group = b.position_group
         and a.value = b.value
         and a.player_id < b.player_id
        where a.percentile is distinct from b.percentile
        """,
    )
    assert bad == 0


def test_lower_is_better_metrics_are_inverted(conn, cfg) -> None:
    """For a lower-is-better metric the smallest value must get the highest
    percentile, so that 100 means 'best' for every metric on a radar."""
    lower = sorted(m.key for m in cfg.metrics if not m.higher_is_better)
    assert lower, "expected at least one lower-is-better metric"
    for key in lower:
        with conn.cursor() as cur:
            cur.execute(
                """
                select
                  (select percentile from football.player_metrics
                    where metric = %s and percentile is not null
                    order by value asc limit 1),
                  (select percentile from football.player_metrics
                    where metric = %s and percentile is not null
                    order by value desc limit 1)
                """,
                (key, key),
            )
            best_value_pct, worst_value_pct = cur.fetchone()
        assert best_value_pct > worst_value_pct, key


def test_higher_is_better_metrics_are_not_inverted(conn, cfg) -> None:
    for key in sorted(m.key for m in cfg.metrics if m.higher_is_better):
        with conn.cursor() as cur:
            cur.execute(
                """
                select
                  (select percentile from football.player_metrics
                    where metric = %s and percentile is not null
                    order by value desc limit 1),
                  (select percentile from football.player_metrics
                    where metric = %s and percentile is not null
                    order by value asc limit 1)
                """,
                (key, key),
            )
            top_value_pct, bottom_value_pct = cur.fetchone()
        assert top_value_pct > bottom_value_pct, key


# ---------------------------------------------------------------------------
# Comparison groups
# ---------------------------------------------------------------------------


def test_group_sizes_are_real_partition_sizes(conn, cfg) -> None:
    """Regression guard. An ordered window frame makes count(*) a running
    count, which reported a group size of 1 for the lowest-valued player in
    every group until the counting windows were split out unordered."""
    too_small = _scalar(
        conn,
        "select count(*) from football.player_metrics "
        "where comparison_scope <> 'insufficient' and comparison_group_size < %s",
        (cfg.min_group_size,),
    )
    assert too_small == 0


def test_group_size_equals_the_number_of_peers_actually_ranked(conn) -> None:
    mismatched = _scalar(
        conn,
        """
        with counted as (
            select metric, comparison_scope, comparison_comp, position_group,
                   count(*) as actual, min(comparison_group_size) as claimed
            from football.player_metrics
            where comparison_scope = 'league_position'
            group by 1, 2, 3, 4
        )
        select count(*) from counted where actual <> claimed
        """,
    )
    assert mismatched == 0


def test_insufficient_rows_have_no_percentile_but_keep_the_value(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            select count(*),
                   count(*) filter (where percentile is null),
                   count(*) filter (where value is null)
            from football.player_metrics where comparison_scope = 'insufficient'
            """
        )
        total, no_percentile, no_value = cur.fetchone()
    assert total == no_percentile
    assert no_value == 0


def test_every_row_with_a_percentile_names_its_comparison_group(conn) -> None:
    bad = _scalar(
        conn,
        "select count(*) from football.player_metrics "
        "where percentile is not null and (comparison_comp is null "
        "or comparison_group_size is null)",
    )
    assert bad == 0


def test_only_players_above_the_minute_threshold_appear(conn, cfg) -> None:
    below = _scalar(
        conn,
        "select count(*) from football.player_metrics where minutes_played < %s",
        (cfg.min_minutes,),
    )
    assert below == 0


# ---------------------------------------------------------------------------
# Values recomputed from the fact table
# ---------------------------------------------------------------------------


def test_npxg_per90_matches_a_hand_calculation(conn) -> None:
    worst = _scalar(
        conn,
        """
        with raw as (
            select comp, player_id,
                   sum(npxg::double precision) as npxg,
                   sum(minutes_played) as mins
            from football.player_match_stats group by 1, 2
        )
        select max(abs(r.npxg / r.mins * 90 - pm.value))
        from raw r
        join football.player_metrics pm
          on pm.comp = r.comp and pm.player_id = r.player_id
         and pm.metric = 'npxg_per90'
        """,
    )
    assert worst < TOLERANCE


def test_pass_pct_is_a_ratio_of_sums(conn) -> None:
    worst = _scalar(
        conn,
        """
        with raw as (
            select comp, player_id,
                   sum(passes_completed)::double precision as pc,
                   sum(passes)::double precision as p
            from football.player_match_stats group by 1, 2
        )
        select max(abs(r.pc / r.p * 100 - pm.value))
        from raw r
        join football.player_metrics pm
          on pm.comp = r.comp and pm.player_id = r.player_id and pm.metric = 'pass_pct'
        where r.p > 0
        """,
    )
    assert worst < TOLERANCE


def test_pass_pct_differs_from_the_mean_of_match_percentages(conn) -> None:
    """The wrong formula is not merely different in principle; day 1 measured
    a 6.9-9.7 point gap. This asserts the view did not quietly use it."""
    gap = _scalar(
        conn,
        """
        with raw as (
            select comp, player_id,
                   sum(passes_completed)::double precision / nullif(sum(passes), 0) * 100
                       as ratio_of_sums,
                   avg(pass_pct::double precision) as mean_of_ratios
            from football.player_match_stats where passes > 0 group by 1, 2
        )
        select max(abs(ratio_of_sums - mean_of_ratios)) from raw
        """,
    )
    assert gap > 5.0


def test_npxg_per_shot_excludes_penalties_from_both_sides(conn) -> None:
    worst = _scalar(
        conn,
        """
        with raw as (
            select comp, player_id,
                   sum(npxg::double precision) as npxg,
                   sum(shots) as shots, sum(penalties_taken) as pens
            from football.player_match_stats group by 1, 2
        )
        select max(abs(r.npxg / nullif(r.shots - r.pens, 0) - pm.value))
        from raw r
        join football.player_metrics pm
          on pm.comp = r.comp and pm.player_id = r.player_id
         and pm.metric = 'npxg_per_shot'
        where r.pens > 0
        """,
    )
    assert worst < TOLERANCE


def test_goals_minus_npxg_is_a_season_total(conn) -> None:
    worst = _scalar(
        conn,
        """
        with raw as (
            select comp, player_id,
                   sum(non_penalty_goals) as g, sum(npxg::double precision) as npxg
            from football.player_match_stats group by 1, 2
        )
        select max(abs(r.g - r.npxg - pm.value))
        from raw r
        join football.player_metrics pm
          on pm.comp = r.comp and pm.player_id = r.player_id
         and pm.metric = 'goals_minus_npxg'
        """,
    )
    assert worst < TOLERANCE


def test_npxg_xa_per90_sums_before_dividing(conn) -> None:
    worst = _scalar(
        conn,
        """
        with raw as (
            select comp, player_id,
                   sum(npxg::double precision) + sum(xa::double precision) as total,
                   sum(minutes_played) as mins
            from football.player_match_stats group by 1, 2
        )
        select max(abs(r.total / r.mins * 90 - pm.value))
        from raw r
        join football.player_metrics pm
          on pm.comp = r.comp and pm.player_id = r.player_id
         and pm.metric = 'npxg_xa_per90'
        """,
    )
    assert worst < TOLERANCE


def test_midrank_percentile_matches_a_hand_calculation(conn) -> None:
    """Tie-aware midrank: (players below + half the players tied) / n."""
    worst = _scalar(
        conn,
        """
        with cell as (
            select player_id, value, percentile
            from football.player_metrics
            where metric = 'npxg_xa_per90' and comp = 'eng' and position_group = 'GK'
        )
        select max(abs(
            100.0 * (
                (select count(*) from cell x where x.value < c.value)
                + 0.5 * (select count(*) from cell x where x.value = c.value)
            ) / (select count(*) from cell)
            - c.percentile
        ))
        from cell c
        """,
    )
    assert worst < TOLERANCE


def test_a_mid_ranked_player_sits_at_the_fiftieth_percentile(conn) -> None:
    percentile = _scalar(
        conn,
        """
        with cell as (
            select percentile,
                   row_number() over (order by value) as rn,
                   count(*) over () as n
            from football.player_metrics
            where metric = 'tackles_per90' and comp = 'esp' and position_group = 'FB'
        )
        -- mod(), not the percent operator: psycopg scans the whole query
        -- string, comments included, and reads a bare percent sign as a
        -- parameter placeholder.
        select percentile from cell where rn = (n + 1) / 2 and mod(n, 2) = 1
        """,
    )
    assert percentile == pytest.approx(50.0, abs=1e-9)


# ---------------------------------------------------------------------------
# Read-only role can reach the new objects
# ---------------------------------------------------------------------------


def test_readonly_role_can_read_the_metric_views(conn) -> None:
    try:
        ro = connect(readonly_dsn(), autocommit=True)
    except psycopg.OperationalError as exc:  # pragma: no cover - env dependent
        pytest.skip(f"no read-only access: {exc}")
    try:
        assert _scalar(ro, "select count(*) from football.player_metrics") > 0
        assert _scalar(ro, "select count(*) from football.metric_definitions") > 0
    finally:
        ro.close()
