"""Structural checks over generated SQL.

These catch the failures result-set equality cannot see: the right numbers
returned in a shape nobody can use (a percentile with no comparison group
size), and the right numbers reached by the wrong route (a 900-minute filter
on a question about season totals, which hides the player who produced a lot
in few minutes - exactly the player a scout wants).
"""

from __future__ import annotations

import pytest

from football_ai.evals.sql import structure


def test_output_columns_prefers_alias():
    cols = structure.output_columns("select player, value as npxg from t limit 1")
    assert cols == ("player", "npxg")


def test_output_columns_of_star():
    assert structure.output_columns("select * from t limit 1") == ("*",)


def test_output_columns_strips_the_table_qualifier():
    assert structure.output_columns("select ps.player from t ps limit 1") == ("player",)


def test_output_columns_reads_the_outermost_select():
    sql = "select name from (select player as name from t) s limit 1"
    assert structure.output_columns(sql) == ("name",)


def test_output_columns_of_a_union_reads_the_left_side():
    sql = "select player from a union all select player from b limit 1"
    assert structure.output_columns(sql) == ("player",)


def test_output_columns_of_an_unparsable_query_is_empty():
    assert structure.output_columns("not sql at all ((") == ()


def test_relations_used_excludes_cte_names():
    sql = "with top as (select player from football.player_season) select player from top limit 1"
    assert structure.relations_used(sql) == frozenset({"player_season"})


def test_relations_used_lowercases_and_drops_the_schema():
    sql = "select 1 from FOOTBALL.Player_Season limit 1"
    assert structure.relations_used(sql) == frozenset({"player_season"})


def test_relations_used_sees_a_relation_in_a_subquery():
    sql = "select 1 from (select player from football.shots) s limit 1"
    assert structure.relations_used(sql) == frozenset({"shots"})


@pytest.mark.parametrize(
    "sql,expected",
    [
        ("select 1 from t where minutes_played >= 900 limit 1", True),
        ("select 1 from t where minutes_played > 899 limit 1", True),
        ("select 1 from t having sum(minutes_played) >= 900 limit 1", True),
        ("select 1 from t where minutes_played between 900 and 3000 limit 1", True),
        ("select 1 from t where 900 <= minutes_played limit 1", True),
        ("select 1 from t where comp = 'eng' limit 1", False),
        ("select minutes_played from t limit 1", False),
        ("select 1 from t order by minutes_played desc limit 1", False),
    ],
)
def test_has_minutes_filter(sql, expected):
    assert structure.has_minutes_filter(sql) is expected


def test_has_minutes_filter_sees_a_filter_inside_a_subquery():
    sql = "select 1 from (select player from t where minutes_played >= 900) s limit 1"
    assert structure.has_minutes_filter(sql) is True


def test_missing_required_is_empty_for_star():
    assert structure.missing_required("select * from t limit 1", ("player", "teams")) == ()


def test_missing_required_lists_absent_columns():
    sql = "select player, value from football.player_metrics limit 1"
    assert structure.missing_required(sql, ("player", "percentile")) == ("percentile",)


def test_missing_required_matches_case_insensitively():
    sql = "select Player as PLAYER from t limit 1"
    assert structure.missing_required(sql, ("player",)) == ()


def test_missing_required_is_empty_when_nothing_is_required():
    assert structure.missing_required("select 1 from t limit 1", ()) == ()


def test_violated_forbidden_minutes_filter():
    sql = "select player from football.player_season where minutes_played >= 900 limit 1"
    assert structure.violated_forbidden(sql, ("minutes_filter",)) == ("minutes_filter",)


def test_violated_forbidden_relation():
    sql = "select player from football.player_season_club limit 1"
    assert structure.violated_forbidden(sql, ("player_season_club",)) == ("player_season_club",)


def test_violated_forbidden_empty_when_clean():
    sql = "select player from football.player_season limit 1"
    assert structure.violated_forbidden(sql, ("minutes_filter", "player_season_club")) == ()


def test_violated_forbidden_reports_several_in_order():
    sql = "select player from football.player_season_club where minutes_played >= 900 limit 1"
    assert structure.violated_forbidden(sql, ("minutes_filter", "player_season_club")) == (
        "minutes_filter",
        "player_season_club",
    )


def test_violated_forbidden_rejects_an_unknown_check():
    """A typo in questions.yaml must fail loudly, not pass silently."""
    with pytest.raises(ValueError, match="hand_of_god"):
        structure.violated_forbidden("select 1 from t limit 1", ("hand_of_god",))
