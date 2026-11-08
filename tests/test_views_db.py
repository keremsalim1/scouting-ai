"""Day 3 acceptance, as tests: position coverage and per-90 correctness.

Marked `db`; the per-90 cross-check also needs the OpenPlay dataset, so it
carries `data` as well. Run with a loaded database:

    make db-up && make migrate && make etl
    uv run pytest -m db
"""

from __future__ import annotations

import psycopg
import pytest

from football_ai.data.db import connect, etl_dsn, readonly_dsn

pytestmark = pytest.mark.db

MIN_MINUTES = 900
TOLERANCE = 0.01
POSITION_GROUPS = {"GK", "CB", "FB", "DM", "CM", "AM", "W", "FW"}
BROAD_GROUPS = {"GK", "DEF", "MID", "ATT"}


@pytest.fixture(scope="module")
def conn():
    try:
        connection = connect(etl_dsn())
    except psycopg.OperationalError as exc:  # pragma: no cover - env dependent
        pytest.skip(f"no database: {exc}")
    yield connection
    connection.close()


def _scalar(conn: psycopg.Connection, sql: str, params: tuple = ()):
    with conn.cursor() as cur:
        cur.execute(sql, params)
        row = cur.fetchone()
        return row[0] if row else None


def _rows(conn: psycopg.Connection, sql: str, params: tuple = ()) -> list[tuple]:
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


# ---------------------------------------------------------------------------
# position_map: "the mapping covers 100%"
# ---------------------------------------------------------------------------


def test_every_player_season_has_exactly_one_position_row(conn) -> None:
    mapped = _scalar(conn, "select count(*) from football.position_map")
    actual = _scalar(
        conn,
        "select count(*) from (select distinct comp, season, player_id "
        "from football.player_match_stats) s",
    )
    assert mapped == actual


def test_no_position_group_is_null(conn) -> None:
    assert (
        _scalar(conn, "select count(*) from football.position_map where position_group is null")
        == 0
    )
    assert (
        _scalar(
            conn, "select count(*) from football.position_map where position_group_broad is null"
        )
        == 0
    )


def test_position_groups_use_the_declared_vocabulary(conn) -> None:
    groups = {
        r[0] for r in _rows(conn, "select distinct position_group from football.position_map")
    }
    broad = {
        r[0] for r in _rows(conn, "select distinct position_group_broad from football.position_map")
    }
    assert groups <= POSITION_GROUPS | {"UNK"}
    assert broad <= BROAD_GROUPS | {"UNK"}


def test_position_source_is_always_declared(conn) -> None:
    sources = {
        r[0] for r in _rows(conn, "select distinct position_source from football.position_map")
    }
    assert sources <= {"starts", "main_position", "unknown"}


def test_unknown_positions_never_reach_the_analysis_threshold(conn) -> None:
    """The fallback gap is real but confined: nobody with 900+ minutes is
    unknown, so no percentile population is affected."""
    leaked = _scalar(
        conn,
        """
        select count(*) from football.player_season
        where minutes_played >= %s and position_group = 'UNK'
        """,
        (MIN_MINUTES,),
    )
    assert leaked == 0


def test_every_900_minute_player_was_voted_from_real_starts(conn) -> None:
    not_from_starts = _scalar(
        conn,
        """
        select count(*) from football.player_season
        where minutes_played >= %s and position_source <> 'starts'
        """,
        (MIN_MINUTES,),
    )
    assert not_from_starts == 0


def test_position_share_is_a_fraction(conn) -> None:
    bad = _scalar(
        conn,
        "select count(*) from football.position_map "
        "where position_share is not null and (position_share <= 0 or position_share > 1)",
    )
    assert bad == 0


def test_the_vote_happens_at_group_level(conn) -> None:
    """The winning group must hold at least as many starting minutes as any
    other group for that player - the property that distinguishes group-level
    voting from voting on raw position codes."""
    violations = _scalar(
        conn,
        """
        with per_group as (
            select comp, season, player_id,
                   football.position_group(position) as grp,
                   sum(minutes_played) as minutes
            from football.player_match_stats
            where position <> 'Sub'
            group by 1, 2, 3, 4
        ), best as (
            select comp, season, player_id, max(minutes) as best_minutes
            from per_group group by 1, 2, 3
        )
        select count(*)
        from football.position_map pm
        join per_group g using (comp, season, player_id)
        join best b using (comp, season, player_id)
        where pm.position_source = 'starts'
          and g.grp = pm.position_group
          and g.minutes < b.best_minutes
        """,
    )
    assert violations == 0


def test_every_fine_group_maps_to_one_broad_group(conn) -> None:
    inconsistent = _scalar(
        conn,
        """
        select count(*) from (
            select position_group from football.position_map
            group by 1 having count(distinct position_group_broad) > 1
        ) s
        """,
    )
    assert inconsistent == 0


# ---------------------------------------------------------------------------
# Season views: no double counting, nothing lost
# ---------------------------------------------------------------------------


def test_player_season_has_one_row_per_player_season(conn) -> None:
    rows = _scalar(conn, "select count(*) from football.player_season")
    distinct = _scalar(
        conn,
        "select count(*) from (select distinct comp, season, player_id "
        "from football.player_match_stats) s",
    )
    assert rows == distinct


def test_club_split_has_a_row_per_player_and_club(conn) -> None:
    rows = _scalar(conn, "select count(*) from football.player_season_club")
    distinct = _scalar(
        conn,
        "select count(*) from (select distinct comp, season, player_id, team_id "
        "from football.player_match_stats) s",
    )
    assert rows == distinct


def test_transfers_produce_more_club_rows_than_season_rows(conn) -> None:
    season = _scalar(conn, "select count(*) from football.player_season")
    club = _scalar(conn, "select count(*) from football.player_season_club")
    switchers = _scalar(conn, "select count(*) from football.player_season where clubs > 1")
    assert switchers > 0
    assert club - season == switchers


@pytest.mark.parametrize(
    "column", ["minutes_played", "goals", "assists", "shots", "passes", "tackles"]
)
def test_totals_survive_both_aggregation_steps(conn, column: str) -> None:
    facts = _scalar(conn, f"select sum({column}) from football.player_match_stats")
    club = _scalar(conn, f"select sum({column}) from football.player_season_club")
    season = _scalar(conn, f"select sum({column}) from football.player_season")
    assert facts == club == season


def test_matches_per_player_match_the_fact_table(conn) -> None:
    mismatched = _scalar(
        conn,
        """
        select count(*) from (
            select comp, season, player_id, count(*) as n
            from football.player_match_stats group by 1, 2, 3
        ) f
        join football.player_season s using (comp, season, player_id)
        where f.n <> s.matches
        """,
    )
    assert mismatched == 0


# ---------------------------------------------------------------------------
# player_per90: the D-004 rules
# ---------------------------------------------------------------------------


def test_ratios_are_null_not_zero_when_nothing_was_attempted(conn) -> None:
    wrong = _scalar(
        conn,
        """
        select count(*) from football.player_per90
        where (passes = 0 and pass_pct is not null)
           or (shots = 0 and shot_accuracy_pct is not null)
        """,
    )
    assert wrong == 0
    # And the case genuinely occurs, so the test is not vacuous.
    assert _scalar(conn, "select count(*) from football.player_per90 where passes = 0") > 0


def test_pass_pct_is_the_ratio_of_sums(conn) -> None:
    """Not the average of per-match percentages (D-004)."""
    worst = _scalar(
        conn,
        """
        select max(abs(pass_pct - 100.0 * passes_completed / passes))
        from football.player_per90 where passes > 0
        """,
    )
    assert worst < 1e-9


def test_per90_is_divided_by_expanded_minutes(conn) -> None:
    worst = _scalar(
        conn,
        """
        select max(abs(npxg_per90 - npxg / minutes_played * 90))
        from football.player_per90 where minutes_played > 0
        """,
    )
    assert worst < 1e-9


def test_npxg_per_shot_excludes_penalties(conn) -> None:
    worst = _scalar(
        conn,
        """
        select max(abs(npxg_per_shot - npxg / (shots - penalties_taken)))
        from football.player_per90 where shots - penalties_taken > 0
        """,
    )
    assert worst < 1e-9


def test_goals_minus_npxg_uses_non_penalty_goals(conn) -> None:
    worst = _scalar(
        conn,
        "select max(abs(goals_minus_npxg - (non_penalty_goals - npxg))) from football.player_per90",
    )
    assert worst < 1e-9


def test_percentile_group_sizes_are_reported_honestly(conn) -> None:
    """Not every league-group is big enough for a percentile. The broad group
    exists as the fallback pool, and must always be larger."""
    rows = _rows(
        conn,
        """
        select comp, position_group, position_group_broad, count(*)
        from football.player_season
        where minutes_played >= %s
        group by 1, 2, 3
        """,
        (MIN_MINUTES,),
    )
    assert rows
    fine = {(c, g): n for c, g, _, n in rows}
    broad: dict[tuple[str, str], int] = {}
    for comp, _, b, n in rows:
        broad[(comp, b)] = broad.get((comp, b), 0) + n
    for (comp, _group), n in fine.items():
        assert n > 0
        assert max(broad[(comp, b)] for (c, b) in broad if c == comp) >= n


# ---------------------------------------------------------------------------
# The headline acceptance check: per-90 against openplay
# ---------------------------------------------------------------------------


@pytest.mark.data
@pytest.mark.parametrize("metric", ["npxg", "xa", "progressive_passes"])
def test_per90_matches_openplay_for_every_qualified_player(conn, metric: str) -> None:
    """Compare against op.player_season_stats(per90=True) at its own grain
    (player AND club) for every player with 900+ minutes - far more than the
    20 the acceptance criterion asks for."""
    import warnings

    import openplay as op
    import pandas as pd

    warnings.simplefilter("ignore", op.CoverageWarning)

    ours = pd.DataFrame(
        _rows(
            conn,
            f"""
            select comp, player_id, team_id,
                   {metric} / minutes_played::double precision * 90
            from football.player_season_club
            where minutes_played >= %s
            """,
            (MIN_MINUTES,),
        ),
        columns=["comp", "player_id", "team_id", "ours"],
    )
    assert len(ours) >= 20

    theirs = pd.concat(
        op.player_season_stats(comp, "2025/26", per90=True).assign(comp=comp)
        for comp in ("eng", "esp", "ita")
    )[["comp", "player_id", "team_id", metric]].rename(columns={metric: "theirs"})

    merged = ours.merge(theirs, on=["comp", "player_id", "team_id"], how="inner")
    assert len(merged) == len(ours), "a qualified player is missing from openplay"

    diff = (merged["ours"] - merged["theirs"]).abs()
    worst = float(diff.max())
    assert worst <= TOLERANCE, (
        f"{metric}: largest difference {worst:.3e} over {len(merged)} players"
    )


# ---------------------------------------------------------------------------
# The read-only role must see the new views too
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "view", ["position_map", "player_season_club", "player_season", "player_per90"]
)
def test_readonly_role_can_read_the_views(view: str) -> None:
    try:
        ro = connect(readonly_dsn(), autocommit=True)
    except psycopg.OperationalError as exc:  # pragma: no cover - env dependent
        pytest.skip(f"no read-only access: {exc}")
    try:
        assert _scalar(ro, f"select count(*) from football.{view}") > 0
    finally:
        ro.close()


def test_readonly_role_still_cannot_write_through_a_view() -> None:
    try:
        ro = connect(readonly_dsn(), autocommit=True)
    except psycopg.OperationalError as exc:  # pragma: no cover - env dependent
        pytest.skip(f"no read-only access: {exc}")
    try:
        with pytest.raises(psycopg.errors.InsufficientPrivilege), ro.cursor() as cur:
            cur.execute("create view football.sneaky as select 1")
    finally:
        ro.close()
