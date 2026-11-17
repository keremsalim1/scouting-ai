"""Turn one or more runs into a JSON record and a Markdown report.

The report is written to be read by someone deciding what to fix next, so the
category table comes before anything else: "ratios 40%, totals 95%" names the
part of the prompt that is missing, while a single overall number names
nothing.

Three things the report must never hide:

* **The denominator.** `unanswerable` questions, provider failures and broken
  reference queries all leave it. A shrinking denominator that is not printed
  turns a bad run into a good-looking one.
* **A broken gold set.** A reference query that stopped working gets its own
  heading naming the gold set, not a line in the model's error list.
* **Dropped parameters.** Gemini 3.x refuses `temperature`; a run where it was
  silently dropped is not comparable with one where it applied.
"""

from __future__ import annotations

import datetime as dt
import json
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

import yaml

from football_ai.data.db import REPO_ROOT
from football_ai.evals.sql.runner import QuestionResult, SuiteResult

# Above this share of infra errors the run is noise, not a measurement.
INFRA_ERROR_WARNING_RATIO = 0.10

PRICING_PATH = REPO_ROOT / "config" / "llm_pricing.yaml"


def _load_pricing() -> dict:
    """Prices are data, not constants: Gemini Flash doubles on 2027-01-01."""
    if not PRICING_PATH.exists():  # pragma: no cover - the file ships with the repo
        return {"as_of": "unknown", "models": {}}
    return yaml.safe_load(PRICING_PATH.read_text(encoding="utf-8"))


PRICING = _load_pricing()


def cost_usd(suite: SuiteResult) -> float | None:
    """What this run actually cost, or None when the model has no listed price.

    The token counts come from the provider's own usage block, so only the
    multiplication is local. An unpriced model reports tokens and no cost
    rather than a guess.
    """
    prices = (PRICING.get("models") or {}).get(suite.model)
    if not prices:
        return None
    return (
        suite.prompt_tokens * float(prices["input"])
        + suite.completion_tokens * float(prices["output"])
    ) / 1_000_000


DIMENSIONS = ("correct", "executes", "required_columns", "no_forbidden")


@dataclass(frozen=True)
class Scores:
    scored: int
    correct: int
    executes: int
    required_columns: int
    no_forbidden: int
    infra_errors: int
    reference_failures: int
    total: int

    @property
    def accuracy(self) -> float | None:
        """`correct / scored`, or None when nothing could be scored."""
        if self.scored == 0:
            return None
        return self.correct / self.scored

    @property
    def infra_error_ratio(self) -> float:
        if self.total == 0:
            return 0.0
        return self.infra_errors / self.total


@dataclass(frozen=True)
class Disagreement:
    id: str
    category: str
    question: str
    verdicts: dict[str, bool | None]
    # The SQL each model wrote, keyed by model name. Named for what it holds:
    # an earlier version called this `relations`, which would have handed a
    # consumer a query where it expected relation names.
    generated_sql: dict[str, str | None]


def score(results: Sequence[QuestionResult]) -> Scores:
    """Count the four dimensions over the questions that can be scored."""
    # A question counts towards accuracy only when it produced a verdict, and
    # `correct is None` is exactly that condition: it covers all three
    # exclusions at once - unanswerable, provider failure, broken reference.
    scorable = [r for r in results if r.correct is not None]
    return Scores(
        scored=len(scorable),
        correct=sum(1 for r in scorable if r.correct),
        executes=sum(1 for r in results if r.executes),
        required_columns=sum(1 for r in results if r.required_columns),
        no_forbidden=sum(1 for r in results if r.no_forbidden),
        infra_errors=sum(1 for r in results if r.infra_error),
        reference_failures=sum(1 for r in results if r.reference_failed),
        total=len(results),
    )


def by_category(suite: SuiteResult) -> dict[str, Scores]:
    """Scores per category, in the order the categories first appear."""
    grouped: dict[str, list[QuestionResult]] = {}
    for result in suite.results:
        grouped.setdefault(result.category, []).append(result)
    return {name: score(items) for name, items in grouped.items()}


def disagreements(a: SuiteResult, b: SuiteResult) -> tuple[Disagreement, ...]:
    """Questions both suites ran where the two models reached different verdicts.

    This is the list day 5 said to look at: where a strong and a weak model
    disagree is where the prompt is ambiguous.
    """
    by_id_b = {r.id: r for r in b.results}
    found: list[Disagreement] = []
    for left in a.results:
        right = by_id_b.get(left.id)
        if right is None or left.correct == right.correct:
            continue
        found.append(
            Disagreement(
                id=left.id,
                category=left.category,
                question=left.question,
                verdicts={a.model: left.correct, b.model: right.correct},
                generated_sql={a.model: left.generated_sql, b.model: right.generated_sql},
            )
        )
    return tuple(found)


# ---------------------------------------------------------------------------
# JSON
# ---------------------------------------------------------------------------


def _jsonable(value: object) -> object:
    """psycopg hands back Decimal, date and datetime; none are JSON types."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (dt.date, dt.datetime, dt.time)):
        return value.isoformat()
    return str(value)


def _result_payload(result: QuestionResult) -> dict:
    return {
        "id": result.id,
        "category": result.category,
        "question": result.question,
        "model": result.model,
        "generated_sql": result.generated_sql,
        "executes": result.executes,
        "correct": result.correct,
        "required_columns": result.required_columns,
        "no_forbidden": result.no_forbidden,
        "infra_error": result.infra_error,
        "reference_failed": result.reference_failed,
        "repairs_used": result.repairs_used,
        "structure_differs": result.structure_differs,
        "reason": result.reason,
        "seconds": round(result.seconds, 3),
        "reference_rows": [[_jsonable(c) for c in row] for row in result.reference_rows],
        "candidate_rows": [[_jsonable(c) for c in row] for row in result.candidate_rows],
    }


def _scores_payload(scores: Scores) -> dict:
    return {
        "scored": scores.scored,
        "total": scores.total,
        "correct": scores.correct,
        "executes": scores.executes,
        "required_columns": scores.required_columns,
        "no_forbidden": scores.no_forbidden,
        "infra_errors": scores.infra_errors,
        "reference_failures": scores.reference_failures,
        "accuracy": scores.accuracy,
    }


def to_json(suites: Sequence[SuiteResult]) -> str:
    payload = {
        "generated_at": dt.datetime.now(dt.UTC).isoformat(),
        "suites": [
            {
                "run_id": suite.run_id,
                "model": suite.model,
                "started_at": suite.started_at.isoformat(),
                "seconds": round(suite.seconds, 3),
                "temperature_supported": suite.temperature_supported,
                "reasoning_effort_supported": suite.reasoning_effort_supported,
                "retries_used": suite.retries_used,
                "quota_exhausted": suite.quota_exhausted,
                "budget_reached": suite.budget_reached,
                "prompt_tokens": suite.prompt_tokens,
                "completion_tokens": suite.completion_tokens,
                "cost_usd": cost_usd(suite),
                "scores": _scores_payload(score(suite.results)),
                "scores_by_category": {
                    name: _scores_payload(s) for name, s in by_category(suite).items()
                },
                "results": [_result_payload(r) for r in suite.results],
            }
            for suite in suites
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _rows(payload: list) -> tuple[tuple, ...]:
    return tuple(tuple(row) for row in payload or ())


def from_json(text: str) -> tuple[SuiteResult, ...]:
    """Rebuild suites from a report file.

    Needed because the free tier allows 20 requests a day: a 40-question run
    has to be split across days, and the partial runs are only useful if they
    can be read back and stitched into one accuracy number.
    """
    payload = json.loads(text)
    suites: list[SuiteResult] = []
    for raw in payload["suites"]:
        results = tuple(
            QuestionResult(
                id=r["id"],
                category=r["category"],
                question=r["question"],
                model=r["model"],
                generated_sql=r["generated_sql"],
                executes=r["executes"],
                correct=r["correct"],
                required_columns=r["required_columns"],
                no_forbidden=r["no_forbidden"],
                infra_error=r["infra_error"],
                reference_failed=r["reference_failed"],
                repairs_used=r["repairs_used"],
                structure_differs=r["structure_differs"],
                reason=r["reason"],
                seconds=r["seconds"],
                reference_rows=_rows(r.get("reference_rows")),
                candidate_rows=_rows(r.get("candidate_rows")),
            )
            for r in raw["results"]
        )
        suites.append(
            SuiteResult(
                model=raw["model"],
                started_at=dt.datetime.fromisoformat(raw["started_at"]),
                results=results,
                temperature_supported=raw["temperature_supported"],
                reasoning_effort_supported=raw["reasoning_effort_supported"],
                retries_used=raw["retries_used"],
                seconds=raw["seconds"],
                prompt_tokens=raw.get("prompt_tokens", 0),
                completion_tokens=raw.get("completion_tokens", 0),
                quota_exhausted=raw.get("quota_exhausted", False),
                budget_reached=raw.get("budget_reached", False),
            )
        )
    return tuple(suites)


def merge(suites: Sequence[SuiteResult]) -> SuiteResult:
    """Stitch partial runs of one model into a single suite.

    Questions are keyed by id and a later suite replaces an earlier answer, so
    re-running one question after a fix does not leave two verdicts in the
    denominator. The run identity comes from the earliest batch; a parameter
    the provider refused in ANY batch is remembered, because one dropped
    `temperature` makes the whole merged measurement non-deterministic.
    """
    if not suites:
        msg = "no suites to merge"
        raise ValueError(msg)
    models = {s.model for s in suites}
    if len(models) > 1:
        msg = f"merge needs the same model in every run, got: {', '.join(sorted(models))}"
        raise ValueError(msg)

    by_id: dict[str, QuestionResult] = {}
    for suite in suites:
        for result in suite.results:
            by_id[result.id] = result

    return SuiteResult(
        model=next(iter(models)),
        started_at=min(s.started_at for s in suites),
        results=tuple(by_id.values()),
        temperature_supported=all(s.temperature_supported for s in suites),
        reasoning_effort_supported=all(s.reasoning_effort_supported for s in suites),
        retries_used=sum(s.retries_used for s in suites),
        seconds=sum(s.seconds for s in suites),
        prompt_tokens=sum(s.prompt_tokens for s in suites),
        completion_tokens=sum(s.completion_tokens for s in suites),
        # A merged result is only 'cut short' if the LAST batch was.
        quota_exhausted=suites[-1].quota_exhausted,
        budget_reached=suites[-1].budget_reached,
    )


# ---------------------------------------------------------------------------
# Markdown
# ---------------------------------------------------------------------------


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"%{value * 100:.1f}"


def _fmt_rows(rows: tuple[tuple, ...]) -> str:
    if not rows:
        return "_(satır yok)_"
    return "\n".join("  - " + " | ".join(str(_jsonable(cell)) for cell in row) for row in rows)


def _suite_section(suite: SuiteResult, threshold: float) -> list[str]:
    scores = score(suite.results)
    lines = [
        f"## {suite.model}",
        "",
        f"- Koşu: `{suite.run_id}` ({suite.seconds:.0f} sn)",
        f"- **Doğruluk: {_pct(scores.accuracy)}** "
        f"({scores.correct}/{scores.scored} puanlanabilir soru, toplam {scores.total})",
    ]

    if scores.accuracy is None:
        lines.append(f"- Eşik {_pct(threshold)}: **değerlendirilemedi** (puanlanabilir soru yok)")
    else:
        met = "geçti" if scores.accuracy >= threshold else "**geçemedi**"
        lines.append(f"- Eşik {_pct(threshold)}: {met}")

    # Each cause needs a different fix - rewrite the gold set, wait for the
    # provider, or nothing at all - so they are counted separately instead of
    # printed as one "excluded" total.
    excluded = scores.total - scores.scored
    unanswerable = excluded - scores.infra_errors - scores.reference_failures
    lines.append(
        f"- Paydadan düşenler: {excluded} "
        f"(cevaplanamaz {unanswerable}, altyapı hatası {scores.infra_errors}, "
        f"bozuk referans {scores.reference_failures})"
    )
    if suite.quota_exhausted:
        lines += [
            "",
            "> **Koşu yarıda kaldı: sağlayıcının günlük istek hakkı bitti.** Yalnızca "
            f"yukarıdaki {len(suite.results)} soru denendi; kalanlar hiç sorulmadı, bu "
            "yüzden hata olarak da sayılmadı. Kota Pasifik gece yarısı sıfırlanıyor; "
            "kaldığı yerden devam edip `make eval-sql-merge` ile birleştir.",
        ]
    if suite.budget_reached:
        lines += [
            "",
            f"> Koşu `--budget` sınırında durdu ({len(suite.results)} soru). Günlük "
            "hakkın tamamını tek koşuda harcamamak için.",
        ]
    if suite.retries_used:
        lines.append(f"- Sağlayıcı yeniden denemesi: {suite.retries_used}")

    if suite.prompt_tokens or suite.completion_tokens:
        tokens = (
            f"- Token: girdi {suite.prompt_tokens:,}, çıktı {suite.completion_tokens:,} "
            "(sağlayıcının kendi sayımı)"
        )
        cost = cost_usd(suite)
        if cost is None:
            tokens += " — fiyat bilinmiyor, `config/llm_pricing.yaml`'da model yok"
        else:
            tokens += f" · **${cost:.4f}** ({PRICING.get('as_of')} fiyatlarıyla)"
        lines.append(tokens)

    if scores.infra_error_ratio > INFRA_ERROR_WARNING_RATIO:
        lines += [
            "",
            f"> **Bu koşu karşılaştırılabilir değil.** Soruların "
            f"%{scores.infra_error_ratio * 100:.0f}'ü altyapı hatası aldı "
            f"(eşik %{INFRA_ERROR_WARNING_RATIO * 100:.0f}). Sağlayıcı doygun; "
            "daha az çekişen bir modelle tekrar koş (`make llm-models`).",
        ]

    dropped = [
        name
        for name, supported in (
            ("temperature", suite.temperature_supported),
            ("reasoning_effort", suite.reasoning_effort_supported),
        )
        if not supported
    ]
    if dropped:
        lines += [
            "",
            f"> Sağlayıcı şu parametreleri reddetti: {', '.join(dropped)}. "
            "Koşular bu yüzden tam deterministik değil; başka bir koşuyla "
            "karşılaştırırken bunu hesaba kat.",
        ]

    lines += [
        "",
        "### Kategoriler",
        "",
        "| Kategori | n | doğru | çalıştı | zorunlu kolon | yasak yapı |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for name, cat in by_category(suite).items():
        lines.append(
            f"| {name} | {cat.total} | {_pct(cat.accuracy)} | "
            f"{cat.executes}/{cat.total} | {cat.required_columns}/{cat.total} | "
            f"{cat.no_forbidden}/{cat.total} |"
        )

    first_try = sum(1 for r in suite.results if r.repairs_used == 0 and r.executes)
    repaired = sum(1 for r in suite.results if r.repairs_used > 0 and r.executes)
    still_refused = sum(1 for r in suite.results if not r.executes and not r.infra_error)
    lines += [
        "",
        "### Onarım döngüsü",
        "",
        f"- İlk denemede geçen: {first_try}",
        f"- Onarımla düzelen: {repaired}",
        f"- Onarımdan sonra da reddedilen: {still_refused}",
    ]

    broken = [r for r in suite.results if r.reference_failed]
    if broken:
        lines += [
            "",
            "### Bozuk referans sorguları (gold set hatası, modelin değil)",
            "",
        ]
        lines += [f"- `{r.id}` — {r.reason}" for r in broken]

    failures = [r for r in suite.results if not r.green and not r.reference_failed]
    if failures:
        lines += ["", "### Soru soru inceleme", ""]
        for result in failures:
            lines += [
                f"#### `{result.id}` ({result.category})",
                "",
                f"Soru: {result.question}",
                "",
                f"Neden: {result.reason or '(sebep kaydedilmedi)'}",
                "",
                "```sql",
                (result.generated_sql or "(SQL üretilmedi)"),
                "```",
            ]
            if result.reference_rows or result.candidate_rows:
                lines += [
                    "",
                    "Beklenen (referans):",
                    _fmt_rows(result.reference_rows),
                    "",
                    "Gelen (model):",
                    _fmt_rows(result.candidate_rows),
                ]
            lines.append("")

    return lines


def to_markdown(suites: Sequence[SuiteResult], *, threshold: float) -> str:
    lines = [
        "# Text-to-SQL değerlendirmesi",
        "",
        f"Üretildi: {dt.datetime.now(dt.UTC).strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        "Hakem sonuç kümesi eşitliğidir: model referanstan farklı SQL yazdıysa ve "
        "satırlar aynıysa cevap doğrudur. Yüzdelik ve grup büyüklüğü gibi zorunlu "
        "kolonlar ile yasak yapılar ayrı boyutlarda puanlanır.",
        "",
    ]
    for suite in suites:
        lines += _suite_section(suite, threshold)

    if len(suites) >= 2:
        found = disagreements(suites[0], suites[1])
        lines += [
            "",
            "## Modeller arası uyuşmazlık",
            "",
            "Gün 5'in bulgusu: iki modelin ayrıldığı yer prompt'un belirsiz olduğu yerdir.",
            "",
        ]
        if not found:
            lines.append("_Uyuşmazlık yok._")
        else:
            lines += [
                f"| Soru | Kategori | {suites[0].model} | {suites[1].model} |",
                "| --- | --- | --- | --- |",
            ]
            for item in found:
                left = item.verdicts[suites[0].model]
                right = item.verdicts[suites[1].model]
                lines.append(
                    f"| `{item.id}` | {item.category} | {_verdict(left)} | {_verdict(right)} |"
                )

    return "\n".join(lines).rstrip() + "\n"


def _verdict(value: bool | None) -> str:
    if value is None:
        return "puanlanmadı"
    return "doğru" if value else "yanlış"
