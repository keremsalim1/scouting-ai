"""Turn a football question into validated SQL.

The loop is deliberately small: ask, validate, and on refusal ask once more
with the refusal reason attached. A second repair rarely helps - if the model
could not use the reason the first time, it usually repeats itself - and it
doubles both latency and cost. Day 6 measures whether that holds.

The LLM is behind a protocol rather than called directly so the tests can run
a stub: the prompt shape, the SQL extraction and the repair loop are all
testable without an API key or a network call. Only the provider call itself
needs credentials.
"""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass, field
from typing import Protocol

import psycopg

from football_ai.data.db import load_env
from football_ai.sql_agent import guard, schema

# Model names get retired, and the failure is a 404 at the first real call
# rather than anything a test catches. `gemini-2.5-flash` was already closed to
# new keys by the time this was wired up; the provider's own error named this
# replacement. Run `make llm-models` to see what a given key can actually
# reach rather than trusting this constant.
DEFAULT_MODEL = "gemini/gemini-3.8-flash"

SYSTEM_PROMPT = """\
You write PostgreSQL SELECT queries over a football scouting database.

Rules:
1. Answer with SQL only. No prose, no explanation, no markdown fences.
2. SELECT only. INSERT, UPDATE, DELETE, DDL, SET and multiple statements are
   rejected before they run.
3. Use only the relations described below. Never query pg_catalog,
   information_schema or any other schema.
4. Never invent a column. If the question cannot be answered with these
   columns, write a SELECT that returns the closest available answer.
5. Use the literal values listed for a column. `comp` is 'eng', 'esp' or
   'ita', never 'Premier League'.

Choosing a relation:
- Percentiles and metric comparisons -> player_metrics (one row per player per
  metric; filter `metric = '<key>'`). It already applies the 900-minute
  threshold, and `percentile` is oriented so 100 is best.
- Raw per-90 rates for one player or a handful -> player_per90.
- Season totals, clubs combined -> player_season.
- Season totals split by club (a mid-season transfer) -> player_season_club.
- Match-level detail -> player_match_stats, shots, passes, lineups, matches.

Minimum minutes - this depends on the question, so read it carefully:
- Ranking a RATE (per-90, a percentage, a percentile) outside player_metrics:
  add `minutes_played >= 900`. Without it a 40-minute cameo tops the table.
- Ranking a TOTAL (goals, assists, minutes, appearances): add NO minutes
  filter. The total already accounts for playing time, and filtering would
  hide a player who produced a lot in few minutes, which is exactly the
  player a scout wants to see.
- player_metrics already applies the threshold, so never add it there.

Other conventions:
- Per-90 uses real expanded minutes, so a full match is ~98-101 minutes.
- Ratios are already ratios of sums; do not average them again.

Columns to return:
- Always include enough to identify the row: the player's name, and their
  club (`teams` in player_season and player_per90, `team` in
  player_season_club). A list of names with no club is hard to act on.
- Include the number the question asked about, and the sample it rests on
  (`minutes_played`, `matches`) when ranking players.
- From player_metrics also return `percentile` and `comparison_group_size`:
  a percentile without its group size cannot be interpreted.
"""

FEW_SHOT: tuple[tuple[str, str], ...] = (
    (
        "Premier League'de npxG+xA/90'ı en yüksek 10 kanat oyuncusu kim?",
        "select player, teams, value as npxg_xa_per90, percentile, comparison_group_size\n"
        "from football.player_metrics\n"
        "where metric = 'npxg_xa_per90' and comp = 'eng' and position_group = 'W'\n"
        "order by value desc\n"
        "limit 10",
    ),
    (
        "Serie A stoperleri arasında pas isabeti 90. yüzdeliğin üstünde olanlar",
        "select player, teams, value as pass_pct, percentile\n"
        "from football.player_metrics\n"
        "where metric = 'pass_pct' and comp = 'ita' and position_group = 'CB'\n"
        "  and percentile >= 90\n"
        "order by percentile desc",
    ),
    (
        # A TOTAL, so no minutes filter: a player with 10 assists in 500
        # minutes belongs in this answer, and the club and sample are returned
        # so the row can be read without a second query.
        "Premier League'de en cok asist yapan 5 oyuncu",
        "select player, teams, assists, minutes_played, matches\n"
        "from football.player_season\n"
        "where comp = 'eng'\n"
        "order by assists desc\n"
        "limit 5",
    ),
    (
        # A RATE, so the threshold applies: without it a 40-minute cameo wins.
        "La Liga'da 90 dakikada en cok kilit pas atan orta saha",
        "select player, teams, key_passes_per90, minutes_played\n"
        "from football.player_per90\n"
        "where comp = 'esp' and position_group = 'CM' and minutes_played >= 900\n"
        "order by key_passes_per90 desc\n"
        "limit 10",
    ),
    (
        "Sezon içinde takım değiştiren ve toplam 900+ dakika oynayan oyuncular",
        "select player, teams, clubs, minutes_played\n"
        "from football.player_season\n"
        "where clubs > 1 and minutes_played >= 900\n"
        "order by minutes_played desc",
    ),
    (
        "La Liga'da en çok gol atan takım hangisi?",
        "select team, sum(goals) as goals\n"
        "from football.player_season_club\n"
        "where comp = 'esp'\n"
        "group by team\n"
        "order by goals desc",
    ),
)

# Models often answer with a fenced block despite being told not to.
_FENCE = re.compile(r"```(?:sql)?\s*(.*?)\s*```", re.DOTALL | re.IGNORECASE)


class QuotaExhausted(RuntimeError):
    """The daily request allowance is gone; nothing in this run can succeed.

    Separate from a transient rate limit on purpose. A per-minute 429 clears in
    seconds and retrying is right. A per-DAY 429 says "retry in 13h20m", and
    every retry is another request counted against an allowance that already
    ran out - so retrying both wastes the remaining calls and delays the one
    message the caller needs to read. Day 6's first batched run lost all 16
    questions this way: five burned the 20-request allowance on timeout
    retries, and the remaining eleven hammered a 429 that had already said it
    needed half a day.
    """


_DAILY_QUOTA_MARKERS = (
    "per day limit",
    "perday",
    "requests per day",
    "generaterequestsperday",
)


def _is_daily_quota(exc: Exception) -> bool:
    """Is this a daily allowance error rather than a per-minute one?"""
    text = str(exc).lower()
    if "429" not in text and "ratelimit" not in text and "quota" not in text:
        return False
    if any(marker in text for marker in _DAILY_QUOTA_MARKERS):
        return True
    # "Please retry in 13h20m49s" - an hours-long wait is a daily window by
    # any other name, whatever the provider calls the metric.
    return bool(re.search(r"retry in \d+h", text))


def _is_transient(exc: Exception) -> bool:
    """Is this worth retrying, or is retrying just a slower failure?

    Overload (503), rate limiting (429), gateway errors and timeouts clear on
    their own; the provider says so itself ("spikes in demand are usually
    temporary"). A bad key or a retired model name never clears, and retrying
    those only delays the message the caller needs to read.
    """
    text = str(exc).lower()
    transient_markers = (
        "503",
        "502",
        "504",
        "500",
        "429",
        "unavailable",
        "overloaded",
        "high demand",
        "rate limit",
        "resource_exhausted",
        "timeout",
        "timed out",
        "connection reset",
    )
    permanent_markers = ("401", "403", "404", "not found", "api key", "unsupported")
    if any(marker in text for marker in permanent_markers):
        return False
    return any(marker in text for marker in transient_markers)


def _is_unsupported(exc: Exception, parameter: str) -> bool:
    """Does this exception mean the provider rejected `parameter`?

    Matched on the message rather than the exception class: the class lives in
    litellm's namespace and would have to be imported at module scope, which
    would make the whole package require litellm just to be imported.
    """
    text = str(exc).lower()
    return parameter.lower() in text and (
        "unsupported" in text or "does not support" in text or "not support" in text
    )


class LLMClient(Protocol):
    """Anything that turns a prompt into text. Keeps the provider swappable."""

    def complete(self, system: str, user: str) -> str: ...


class LiteLLMClient:
    """Provider-agnostic client. The model prefix picks the provider, so
    `gemini/gemini-2.5-flash` and `openai/gpt-4o-mini` both work with no code
    change - only the matching API key needs to be in the environment."""

    def __init__(
        self,
        model: str | None = None,
        temperature: float | None = None,
        timeout_s: float | None = None,
        reasoning_effort: str | None = None,
        max_retries: int | None = None,
    ) -> None:
        load_env()
        self.model = model or os.environ.get("LLM_MODEL", DEFAULT_MODEL)
        self.temperature = (
            temperature
            if temperature is not None
            else float(os.environ.get("LLM_TEMPERATURE", "0"))
        )
        self.timeout_s = (
            timeout_s if timeout_s is not None else float(os.environ.get("LLM_TIMEOUT_S", "30"))
        )
        # How much the model may think before answering. Gemini 3.x reasons by
        # default, which cost ~40s per question against ~0.1s for the database
        # query it produces. Text-to-SQL is not a reasoning task here: the
        # schema, the literals and the worked examples are all in the prompt,
        # so there is little left to work out. Day 6 measures accuracy at each
        # setting rather than assuming "more thinking is better".
        # Empty string means "send nothing", i.e. the provider default.
        self.reasoning_effort = (
            reasoning_effort
            if reasoning_effort is not None
            else os.environ.get("LLM_REASONING_EFFORT", "low")
        ).strip()
        self.max_retries = (
            max_retries if max_retries is not None else int(os.environ.get("LLM_MAX_RETRIES", "3"))
        )
        # Each flips to False the first time the provider refuses that
        # parameter. Read them after a run: temperature_supported=False means
        # repeated runs may differ, which day 6 has to report.
        self.temperature_supported = True
        self.reasoning_effort_supported = bool(self.reasoning_effort)
        # Counted so day 6 can separate "the model was wrong" from "the
        # provider was busy" when a benchmark run comes back slow.
        self.retries_used = 0
        # One entry per provider call: (seconds, outcome). A single total
        # cannot distinguish "one slow answer" from "three fast refusals and
        # a retry", and those two call for opposite fixes.
        self.call_log: list[tuple[float, str]] = []
        # Tokens the provider says it billed, accumulated over every call this
        # client makes. Measured rather than estimated from character counts,
        # so a run can price itself and a decision about paying for a higher
        # quota rests on a number instead of a guess.
        self.prompt_tokens = 0
        self.completion_tokens = 0

    def _record_usage(self, response: object) -> None:
        """Add this call's billed tokens, if the provider reported any.

        Written defensively: `usage` is absent on some providers and on
        streamed responses, and a missing field must not turn a working run
        into a crash over bookkeeping.
        """
        usage = getattr(response, "usage", None)
        if usage is None:
            return
        self.prompt_tokens += int(getattr(usage, "prompt_tokens", 0) or 0)
        self.completion_tokens += int(getattr(usage, "completion_tokens", 0) or 0)

    def _optional_params(self) -> dict[str, object]:
        """The parameters this provider has not yet rejected."""
        params: dict[str, object] = {}
        if self.temperature_supported:
            params["temperature"] = self.temperature
        if self.reasoning_effort_supported:
            params["reasoning_effort"] = self.reasoning_effort
        return params

    def _disable(self, name: str) -> None:
        setattr(self, f"{name}_supported", False)

    def _sleep(self, seconds: float) -> None:
        """Separate method so tests can wait for nothing."""
        time.sleep(seconds)

    def complete(self, system: str, user: str) -> str:
        # Imported here so the package stays importable, and the whole test
        # suite stays runnable, on a machine with no LLM dependencies set up.
        import litellm

        # LiteLLM prints a bug-report URL and a debug tip on every provider
        # error. With retries that is several screens of noise around the one
        # line that matters, and it invites filing a bug for a 503 that is not
        # one. The exception still carries the full message.
        litellm.suppress_debug_info = True

        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]

        # Two different retry reasons, deliberately kept apart.
        #
        # Parameter rejection: providers refuse optional parameters rather than
        # ignoring them, and which ones changes model by model. LiteLLM offers
        # drop_params=True to discard them silently; that is the wrong trade
        # here, because day 6 measures accuracy and a run whose temperature was
        # quietly dropped is not comparable with one where it applied. So each
        # rejection is handled once, remembered, and left visible on a flag.
        # These retries are free and immediate.
        #
        # Transient failure: 503 overload, 429 rate limit, timeouts. These
        # clear on their own, so they are retried with a growing pause. A bad
        # key or a retired model never clears and is raised immediately -
        # retrying it would only delay the message the caller needs.
        attempts_left = self.max_retries
        backoff = 1.0
        while True:
            started = time.perf_counter()
            try:
                response = litellm.completion(
                    model=self.model,
                    messages=messages,
                    timeout=self.timeout_s,
                    **self._optional_params(),
                )
            except Exception as exc:
                self.call_log.append((time.perf_counter() - started, type(exc).__name__))
                rejected = next(
                    (
                        name
                        for name in ("temperature", "reasoning_effort")
                        if _is_unsupported(exc, name) and getattr(self, f"{name}_supported")
                    ),
                    None,
                )
                if rejected is not None:
                    self._disable(rejected)
                    continue
                # Checked before the transient branch: a daily 429 matches the
                # transient markers ("429", "rate limit") but retrying it
                # spends calls from an allowance that is already gone.
                if _is_daily_quota(exc):
                    raise QuotaExhausted(str(exc)) from exc
                if attempts_left > 0 and _is_transient(exc):
                    attempts_left -= 1
                    self.retries_used += 1
                    self._sleep(backoff)
                    backoff *= 2
                    continue
                raise
            self.call_log.append((time.perf_counter() - started, "ok"))
            self._record_usage(response)
            return response.choices[0].message.content or ""


@dataclass
class Attempt:
    """One pass through the loop, kept so day 6 can see where failures come from."""

    raw: str
    sql: str | None
    refusal: str | None


@dataclass
class SqlResult:
    ok: bool
    sql: str | None = None
    question: str = ""
    attempts: list[Attempt] = field(default_factory=list)
    error: str | None = None

    @property
    def repairs_used(self) -> int:
        return max(0, len(self.attempts) - 1)

    def __bool__(self) -> bool:
        return self.ok


def extract_sql(text: str) -> str:
    """Pull the statement out of whatever the model actually returned."""
    if not text:
        return ""
    fenced = _FENCE.search(text)
    if fenced:
        text = fenced.group(1)
    # A trailing semicolon is harmless to Postgres but makes the guard count
    # two statements, so it is stripped rather than refused.
    return text.strip().rstrip(";").strip()


def build_user_prompt(question: str, schema_text: str) -> str:
    examples = "\n\n".join(f"Question: {q}\nSQL:\n{sql}" for q, sql in FEW_SHOT)
    return f"{schema_text}\nExamples:\n\n{examples}\n\nQuestion: {question}\nSQL:"


def build_repair_prompt(question: str, schema_text: str, bad_sql: str, reason: str) -> str:
    return (
        f"{build_user_prompt(question, schema_text)}\n{bad_sql}\n\n"
        f"That query was rejected: {reason}\n"
        f"Write a corrected SELECT that answers the same question."
    )


_schema_cache: dict[str, str] = {}


def schema_text(conn: psycopg.Connection, *, refresh: bool = False) -> str:
    """Describe the schema once per process; it does not change under us."""
    if refresh or "text" not in _schema_cache:
        _schema_cache["text"] = schema.describe(conn)
    return _schema_cache["text"]


def text_to_sql(
    question: str,
    *,
    conn: psycopg.Connection,
    client: LLMClient | None = None,
    max_repairs: int | None = None,
    max_rows: int = guard.DEFAULT_LIMIT,
) -> SqlResult:
    """Ask for SQL, validate it, and retry once with the refusal reason."""
    load_env()
    if max_repairs is None:
        max_repairs = int(os.environ.get("LLM_MAX_REPAIRS", "1"))
    client = client or LiteLLMClient()

    described = schema_text(conn)
    result = SqlResult(ok=False, question=question)
    prompt = build_user_prompt(question, described)

    for _ in range(max_repairs + 1):
        try:
            raw = client.complete(SYSTEM_PROMPT, prompt)
        except QuotaExhausted:
            # Deliberately not turned into a result: every later question
            # would fail the same way, so the caller has to be able to stop
            # the whole run rather than record N identical failures.
            raise
        except Exception as exc:
            result.error = f"the model call failed: {type(exc).__name__}: {exc}"
            return result

        candidate = extract_sql(raw)
        checked = guard.validate(candidate, max_rows=max_rows)
        result.attempts.append(Attempt(raw=raw, sql=candidate or None, refusal=checked.reason))
        if checked.ok:
            result.ok = True
            result.sql = checked.sql
            return result
        prompt = build_repair_prompt(question, described, candidate, checked.reason or "")

    result.error = result.attempts[-1].refusal if result.attempts else "no answer produced"
    return result


def run(
    question: str,
    *,
    read_conn: psycopg.Connection,
    describe_conn: psycopg.Connection | None = None,
    client: LLMClient | None = None,
    max_rows: int = guard.DEFAULT_LIMIT,
) -> tuple[SqlResult, list[tuple] | None, list[str] | None]:
    """Generate, validate and execute. Returns (result, rows, column names).

    `read_conn` should be the read-only connection: the guard is the first
    line, the role is the one that holds.
    """
    generated = text_to_sql(
        question,
        conn=describe_conn or read_conn,
        client=client,
        max_rows=max_rows,
    )
    if not generated.ok or not generated.sql:
        return generated, None, None

    with read_conn.cursor() as cur:
        cur.execute(generated.sql)
        rows = cur.fetchall()
        columns = [d.name for d in cur.description] if cur.description else []
    return generated, rows, columns
