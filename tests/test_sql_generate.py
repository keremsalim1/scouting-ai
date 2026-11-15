"""The generation loop, tested without an API key.

A stub client stands in for the provider, so prompt assembly, SQL extraction
and the repair loop are all covered by the default `pytest` run. Only the
provider call itself needs credentials, and that is one thin method.
"""

from __future__ import annotations

import pytest

from football_ai.sql_agent import generate


class StubClient:
    """Returns canned replies in order and records what it was asked."""

    def __init__(self, *replies: str) -> None:
        self.replies = list(replies)
        self.calls: list[tuple[str, str]] = []

    def complete(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        if not self.replies:
            raise AssertionError("StubClient ran out of replies")
        return self.replies.pop(0)


class ExplodingClient:
    def complete(self, system: str, user: str) -> str:
        raise TimeoutError("provider unreachable")


@pytest.fixture(autouse=True)
def _fixed_schema(monkeypatch):
    """Pin the schema text so these tests need no database."""
    monkeypatch.setattr(generate, "schema_text", lambda conn, refresh=False: "SCHEMA HERE\n")


# ---------------------------------------------------------------------------
# Extracting SQL from whatever the model returned
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("select 1", "select 1"),
        ("```sql\nselect 1\n```", "select 1"),
        ("```\nselect 1\n```", "select 1"),
        ("```SQL\nselect 1\n```", "select 1"),
        ("  select 1  ", "select 1"),
        # A trailing semicolon would make the guard count two statements.
        ("select 1;", "select 1"),
        ("```sql\nselect 1;\n```", "select 1"),
        ("", ""),
    ],
)
def test_extract_sql(raw: str, expected: str) -> None:
    assert generate.extract_sql(raw) == expected


def test_extract_sql_keeps_internal_semicolons_out_of_the_way() -> None:
    """Only a trailing semicolon is stripped; a stacked statement must still
    reach the guard so it is refused rather than silently truncated."""
    assert generate.extract_sql("select 1; drop table x") == "select 1; drop table x"


# ---------------------------------------------------------------------------
# The prompt
# ---------------------------------------------------------------------------


def test_user_prompt_carries_schema_question_and_examples() -> None:
    prompt = generate.build_user_prompt("kaç oyuncu var?", "SCHEMA HERE\n")
    assert "SCHEMA HERE" in prompt
    assert "kaç oyuncu var?" in prompt
    for question, sql in generate.FEW_SHOT:
        assert question in prompt
        assert sql.splitlines()[0] in prompt


def test_system_prompt_states_the_rules_the_guard_enforces() -> None:
    """If the prompt and the guard disagree, every query costs a repair."""
    text = generate.SYSTEM_PROMPT.lower()
    for expected in ["select only", "pg_catalog", "'eng'", "900"]:
        assert expected in text


def test_system_prompt_separates_totals_from_rates() -> None:
    """The first version said "filter 900 minutes when comparing players",
    which a literal-minded model applied to `most assists` too - wrong, since
    a total already accounts for playing time."""
    # Whitespace-normalised: the prompt is wrapped for reading, so a phrase
    # can straddle a line break.
    text = " ".join(generate.SYSTEM_PROMPT.lower().split())
    assert "ranking a total" in text
    assert "ranking a rate" in text
    assert "add no minutes filter" in text


def test_few_shot_demonstrates_both_sides_of_the_minutes_rule() -> None:
    """Examples carry more weight than rules, so both cases must be shown."""
    totals = [sql for q, sql in generate.FEW_SHOT if "assists desc" in sql]
    rates = [sql for q, sql in generate.FEW_SHOT if "per90 desc" in sql]
    assert totals, "no worked example of ranking a total"
    assert rates, "no worked example of ranking a rate"
    assert all("minutes_played >=" not in sql for sql in totals)
    assert all("minutes_played >= 900" in sql for sql in rates)


def test_few_shot_always_returns_the_club() -> None:
    """A list of names with no club is hard to act on."""
    for question, sql in generate.FEW_SHOT:
        assert "teams" in sql or "team" in sql, question


def test_repair_prompt_includes_the_refusal_reason() -> None:
    prompt = generate.build_repair_prompt(
        "soru", "SCHEMA HERE\n", "delete from x", "DELETE is not allowed"
    )
    assert "delete from x" in prompt
    assert "DELETE is not allowed" in prompt


# ---------------------------------------------------------------------------
# The loop
# ---------------------------------------------------------------------------


def test_valid_sql_on_the_first_try_uses_one_call() -> None:
    client = StubClient("select player from football.player_season limit 5")
    result = generate.text_to_sql("soru", conn=None, client=client)
    assert result.ok
    assert result.repairs_used == 0
    assert len(client.calls) == 1
    assert "player_season" in result.sql


def test_a_refused_query_is_repaired_once() -> None:
    client = StubClient(
        "delete from football.players",
        "select player from football.player_season limit 5",
    )
    result = generate.text_to_sql("soru", conn=None, client=client)
    assert result.ok
    assert result.repairs_used == 1
    assert len(result.attempts) == 2
    assert "DELETE" in result.attempts[0].refusal


def test_the_repair_call_is_told_why_it_failed() -> None:
    client = StubClient(
        "select * from pg_catalog.pg_user",
        "select player from football.player_season limit 5",
    )
    generate.text_to_sql("soru", conn=None, client=client)
    _, second_prompt = client.calls[1]
    assert "pg_catalog" in second_prompt
    assert "rejected" in second_prompt.lower()


def test_repairs_are_capped() -> None:
    """Two bad answers end the attempt rather than looping on the provider."""
    client = StubClient("delete from football.players", "drop table football.players")
    result = generate.text_to_sql("soru", conn=None, client=client, max_repairs=1)
    assert not result.ok
    assert result.sql is None
    assert len(client.calls) == 2
    assert "DROP" in result.error


def test_max_repairs_zero_means_a_single_call() -> None:
    client = StubClient("delete from football.players")
    result = generate.text_to_sql("soru", conn=None, client=client, max_repairs=0)
    assert not result.ok
    assert len(client.calls) == 1


def test_provider_failure_is_reported_not_raised() -> None:
    """A dead provider must not take the caller down with it."""
    result = generate.text_to_sql("soru", conn=None, client=ExplodingClient())
    assert not result.ok
    assert "TimeoutError" in result.error
    assert result.attempts == []


def test_prose_answer_is_refused_and_explained() -> None:
    client = StubClient("I cannot answer that.", "Still cannot.")
    result = generate.text_to_sql("soru", conn=None, client=client)
    assert not result.ok
    assert "not valid SQL" in result.error


def test_generated_sql_gets_a_limit() -> None:
    client = StubClient("select player from football.player_season")
    result = generate.text_to_sql("soru", conn=None, client=client, max_rows=7)
    assert result.ok
    assert result.sql.upper().rstrip().endswith("LIMIT 7")


def test_attempts_record_the_raw_reply_for_error_analysis() -> None:
    """Day 6 groups failures by cause, which needs the unedited reply."""
    client = StubClient("```sql\ndelete from football.players\n```", "select 1")
    result = generate.text_to_sql("soru", conn=None, client=client)
    assert result.attempts[0].raw.startswith("```")
    assert result.attempts[0].sql == "delete from football.players"
    assert result.ok


# ---------------------------------------------------------------------------
# Client construction (no network)
# ---------------------------------------------------------------------------


def test_client_defaults_to_gemini_and_zero_temperature(monkeypatch) -> None:
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.delenv("LLM_TEMPERATURE", raising=False)
    monkeypatch.setattr(generate, "load_env", lambda: None)
    client = generate.LiteLLMClient()
    assert client.model == generate.DEFAULT_MODEL
    assert client.temperature == 0


def test_model_comes_from_the_environment(monkeypatch) -> None:
    monkeypatch.setenv("LLM_MODEL", "openai/gpt-4o-mini")
    monkeypatch.setattr(generate, "load_env", lambda: None)
    assert generate.LiteLLMClient().model == "openai/gpt-4o-mini"


# ---------------------------------------------------------------------------
# Providers that reject `temperature`
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("gemini does not support parameters: ['temperature'], for model=x", True),
        ("litellm.UnsupportedParamsError: unsupported param temperature", True),
        ("Model does not support temperature", True),
        ("rate limit exceeded", False),
        ("invalid api key", False),
        # A different unsupported parameter must not be mistaken for this one.
        ("does not support parameters: ['top_k']", False),
    ],
)
def test_detects_an_unsupported_temperature(message: str, expected: bool) -> None:
    assert generate._is_unsupported(RuntimeError(message), "temperature") is expected


@pytest.mark.parametrize(
    ("message", "parameter", "expected"),
    [
        ("model does not support reasoning_effort", "reasoning_effort", True),
        ("unsupported param: reasoning_effort", "reasoning_effort", True),
        # A rejection of one parameter must not disable the other.
        ("does not support parameters: ['temperature']", "reasoning_effort", False),
        ("does not support parameters: ['reasoning_effort']", "temperature", False),
    ],
)
def test_detects_which_parameter_was_rejected(message: str, parameter: str, expected: bool) -> None:
    assert generate._is_unsupported(RuntimeError(message), parameter) is expected


def _fake_litellm(monkeypatch, *, reject_temperature: bool):
    """Stand in for the litellm module imported inside complete()."""
    import sys
    import types

    calls: list[dict] = []
    module = types.ModuleType("litellm")

    def completion(**kwargs):
        calls.append(kwargs)
        if reject_temperature and "temperature" in kwargs:
            raise RuntimeError(
                "litellm.UnsupportedParamsError: gemini does not support "
                "parameters: ['temperature'], for model=gemini-3.8-flash"
            )
        message = types.SimpleNamespace(content="select 1")
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=message)])

    module.completion = completion
    monkeypatch.setitem(sys.modules, "litellm", module)
    return calls


def test_temperature_is_sent_when_the_provider_accepts_it(monkeypatch) -> None:
    monkeypatch.setattr(generate, "load_env", lambda: None)
    calls = _fake_litellm(monkeypatch, reject_temperature=False)
    client = generate.LiteLLMClient(model="x", temperature=0, timeout_s=5)
    assert client.complete("sys", "user") == "select 1"
    assert len(calls) == 1
    assert calls[0]["temperature"] == 0
    assert client.temperature_supported is True


def test_temperature_is_dropped_and_recorded_when_rejected(monkeypatch) -> None:
    """Dropping it silently would make day 6's accuracy numbers incomparable
    between runs without anything saying so."""
    monkeypatch.setattr(generate, "load_env", lambda: None)
    calls = _fake_litellm(monkeypatch, reject_temperature=True)
    client = generate.LiteLLMClient(model="x", temperature=0, timeout_s=5)

    assert client.complete("sys", "user") == "select 1"
    assert len(calls) == 2, "expected one rejected call and one retry"
    assert "temperature" in calls[0]
    assert "temperature" not in calls[1]
    assert client.temperature_supported is False


def test_the_retry_happens_only_once_per_client(monkeypatch) -> None:
    """After the first refusal the parameter is not sent again, so a long eval
    run does not pay for a wasted call on every question."""
    monkeypatch.setattr(generate, "load_env", lambda: None)
    calls = _fake_litellm(monkeypatch, reject_temperature=True)
    client = generate.LiteLLMClient(model="x", temperature=0, timeout_s=5)

    client.complete("sys", "one")
    client.complete("sys", "two")
    client.complete("sys", "three")
    assert len(calls) == 4, "one retry on the first call, none afterwards"


def test_reasoning_effort_is_sent_by_default(monkeypatch) -> None:
    monkeypatch.setattr(generate, "load_env", lambda: None)
    monkeypatch.delenv("LLM_REASONING_EFFORT", raising=False)
    calls = _fake_litellm(monkeypatch, reject_temperature=False)
    client = generate.LiteLLMClient(model="x", temperature=0, timeout_s=5)
    client.complete("sys", "user")
    assert calls[0]["reasoning_effort"] == "low"


def test_reasoning_effort_can_be_turned_off_entirely(monkeypatch) -> None:
    """An empty value means send nothing and take the provider default."""
    monkeypatch.setattr(generate, "load_env", lambda: None)
    calls = _fake_litellm(monkeypatch, reject_temperature=False)
    client = generate.LiteLLMClient(model="x", temperature=0, timeout_s=5, reasoning_effort="")
    client.complete("sys", "user")
    assert "reasoning_effort" not in calls[0]
    assert client.reasoning_effort_supported is False


def test_a_rejected_reasoning_effort_is_dropped_without_losing_temperature(
    monkeypatch,
) -> None:
    """Rejecting one optional parameter must not silently disable the other."""
    import sys
    import types

    monkeypatch.setattr(generate, "load_env", lambda: None)
    calls: list[dict] = []
    module = types.ModuleType("litellm")

    def completion(**kwargs):
        calls.append(kwargs)
        if "reasoning_effort" in kwargs:
            raise RuntimeError("model does not support reasoning_effort")
        message = types.SimpleNamespace(content="select 1")
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=message)])

    module.completion = completion
    monkeypatch.setitem(sys.modules, "litellm", module)

    client = generate.LiteLLMClient(model="x", temperature=0, timeout_s=5, reasoning_effort="low")
    assert client.complete("sys", "user") == "select 1"
    assert len(calls) == 2
    assert client.reasoning_effort_supported is False
    assert client.temperature_supported is True
    assert calls[1]["temperature"] == 0


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        # Transient: these clear on their own.
        ("503 This model is currently experiencing high demand", True),
        ("ServiceUnavailableError: UNAVAILABLE", True),
        ("429 RESOURCE_EXHAUSTED", True),
        ("Read timed out", True),
        ("502 Bad Gateway", True),
        # Permanent: retrying only delays the real message.
        ("404 model not found", False),
        ("401 invalid api key", False),
        ("gemini does not support parameters: ['temperature']", False),
        # A 404 that also mentions demand must still count as permanent.
        ("404 not found; this model is in high demand", False),
    ],
)
def test_classifies_transient_failures(message: str, expected: bool) -> None:
    assert generate._is_transient(RuntimeError(message)) is expected


def _flaky_litellm(monkeypatch, failures: int, error: str):
    """Fails `failures` times, then succeeds."""
    import sys
    import types

    state = {"calls": 0}
    module = types.ModuleType("litellm")

    def completion(**kwargs):
        state["calls"] += 1
        if state["calls"] <= failures:
            raise RuntimeError(error)
        message = types.SimpleNamespace(content="select 1")
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=message)])

    module.completion = completion
    monkeypatch.setitem(sys.modules, "litellm", module)
    return state


def test_a_transient_failure_is_retried(monkeypatch) -> None:
    monkeypatch.setattr(generate, "load_env", lambda: None)
    state = _flaky_litellm(monkeypatch, failures=2, error="503 high demand")
    client = generate.LiteLLMClient(model="x", timeout_s=5, max_retries=3)
    monkeypatch.setattr(client, "_sleep", lambda s: None)

    assert client.complete("sys", "user") == "select 1"
    assert state["calls"] == 3
    assert client.retries_used == 2


def test_retries_stop_at_the_limit(monkeypatch) -> None:
    monkeypatch.setattr(generate, "load_env", lambda: None)
    state = _flaky_litellm(monkeypatch, failures=99, error="503 high demand")
    client = generate.LiteLLMClient(model="x", timeout_s=5, max_retries=2)
    monkeypatch.setattr(client, "_sleep", lambda s: None)

    with pytest.raises(RuntimeError, match="503"):
        client.complete("sys", "user")
    assert state["calls"] == 3, "one attempt plus two retries"
    assert client.retries_used == 2


def test_a_permanent_failure_is_not_retried(monkeypatch) -> None:
    """Retrying a bad key or a retired model only delays the real message."""
    monkeypatch.setattr(generate, "load_env", lambda: None)
    state = _flaky_litellm(monkeypatch, failures=99, error="404 model not found")
    client = generate.LiteLLMClient(model="x", timeout_s=5, max_retries=5)
    monkeypatch.setattr(client, "_sleep", lambda s: None)

    with pytest.raises(RuntimeError, match="404"):
        client.complete("sys", "user")
    assert state["calls"] == 1
    assert client.retries_used == 0


def test_hint_reads_the_whole_sequence_not_just_the_last_error() -> None:
    """A run that hit three 503s and then timed out is a saturated model, not
    a timeout to be raised. Reporting only the final error said the latter."""
    import importlib.util
    import pathlib

    spec = importlib.util.spec_from_file_location("ask_mod", pathlib.Path("scripts/ask.py"))
    ask = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ask)

    log = [
        (0.3, "UnsupportedParamsError"),
        (31.2, "ServiceUnavailableError"),
        (3.6, "ServiceUnavailableError"),
        (43.6, "ServiceUnavailableError"),
        (120.0, "Timeout"),
    ]
    hint = ask._hint("litellm.Timeout: Read timed out", log)
    assert "saturated" in hint
    assert "LLM_MODEL" in hint
    assert "LLM_TIMEOUT_S" not in hint

    # A single timeout with no pattern behind it still says what it says.
    lone = ask._hint("litellm.Timeout: Read timed out", [(120.0, "Timeout")])
    assert "LLM_TIMEOUT_S" in lone


def test_each_provider_call_is_timed_and_labelled(monkeypatch) -> None:
    """One total hides whether a slow run was one slow answer or several
    refusals plus retries; those need opposite fixes."""
    monkeypatch.setattr(generate, "load_env", lambda: None)
    _flaky_litellm(monkeypatch, failures=2, error="503 high demand")
    client = generate.LiteLLMClient(model="x", timeout_s=5, max_retries=3)
    monkeypatch.setattr(client, "_sleep", lambda s: None)

    client.complete("sys", "user")
    assert len(client.call_log) == 3
    assert [outcome for _, outcome in client.call_log] == [
        "RuntimeError",
        "RuntimeError",
        "ok",
    ]
    assert all(seconds >= 0 for seconds, _ in client.call_log)


def test_backoff_grows_between_retries(monkeypatch) -> None:
    monkeypatch.setattr(generate, "load_env", lambda: None)
    _flaky_litellm(monkeypatch, failures=3, error="503 high demand")
    client = generate.LiteLLMClient(model="x", timeout_s=5, max_retries=3)
    waits: list[float] = []
    monkeypatch.setattr(client, "_sleep", waits.append)

    client.complete("sys", "user")
    assert waits == [1.0, 2.0, 4.0]


def test_other_provider_errors_still_propagate(monkeypatch) -> None:
    monkeypatch.setattr(generate, "load_env", lambda: None)
    import sys
    import types

    module = types.ModuleType("litellm")

    def completion(**kwargs):
        raise RuntimeError("rate limit exceeded")

    module.completion = completion
    monkeypatch.setitem(sys.modules, "litellm", module)

    client = generate.LiteLLMClient(model="x", temperature=0, timeout_s=5)
    with pytest.raises(RuntimeError, match="rate limit"):
        client.complete("sys", "user")
