"""Gün 1: OpenPlay 2025-26 veri doğrulaması (PL, La Liga, Serie A).

Eşikler hedeftir; bir eşik tutmazsa script durmaz, sonucu raporlar
ve etkilenen özelliği "degraded" / "disabled" olarak işaretler.
"""

from __future__ import annotations

import json
import sys
import warnings
from datetime import UTC, datetime
from pathlib import Path

import openplay as op

from football_ai.console import force_utf8

SEASON = "2025/26"
SEASON_CODE = "2526"
LEAGUES = {"eng": "Premier League", "esp": "La Liga", "ita": "Serie A"}
EXPECTED_MATCHES = 380

# Hedef eşikler (DECISIONS.md'de gerekçeli)
TARGETS = {
    "match_coverage_pct": 99.0,
    "shot_xg_filled_pct": 99.0,
    "pass_end_xy_filled_pct": 99.0,
    "coords_out_of_range": 0,
    "score_mismatch_pct": 1.0,
    "unknown_minutes_pct": 1.0,
}
# Eşik başarısız olursa etkilenen özellikler
AFFECTS = {
    "match_coverage_pct": ["tüm sezon toplamları", "per-90"],
    "shot_xg_filled_pct": ["xG analizi", "xG tabanlı scouting metrikleri"],
    "pass_end_xy_filled_pct": ["pas haritaları", "koordinat tabanlı pas metrikleri"],
    "coords_out_of_range": ["tüm koordinat tabanlı görseller"],
    "score_mismatch_pct": ["gol / G−xG analizleri"],
    "unknown_minutes_pct": ["per-90 metrikleri", "minimum dakika filtresi"],
}
# Kritik eşikler: başarısızsa özellik kapatılır; diğerleri "degraded" olur
CRITICAL = {
    "shot_xg_filled_pct": 90.0,
    "pass_end_xy_filled_pct": 90.0,
    "match_coverage_pct": 95.0,
}
LOWER_IS_BETTER = {"coords_out_of_range", "score_mismatch_pct", "unknown_minutes_pct"}


def check(name: str, value: float) -> str:
    target = TARGETS[name]
    lower_is_better = name in LOWER_IS_BETTER
    ok = value <= target if lower_is_better else value >= target
    if ok:
        return "pass"
    if name in CRITICAL and value < CRITICAL[name]:
        return "disabled"
    return "degraded"


def validate(comp: str) -> dict:
    m = op.matches(comp, SEASON)
    s = op.shots(comp, SEASON)
    p = op.player_match_stats(comp, SEASON)
    e = op.events(comp, SEASON, columns=["match_id", "type", "x", "y", "end_x", "end_y"])
    gaps = op.known_gaps(comp, SEASON)
    issues = op.data_issues(comp, SEASON)

    passes = e[e["type"] == "Pass"]
    # xG beklenen şutlar: kendi kalesine gol, penaltı atışları ve kendi
    # yarı sahasından şutlar hariç
    xg_expected = s[~s["is_own_goal"] & ~s["is_shootout"] & (s["x"] >= 50)]
    coords = e[["x", "y"]]
    mismatch = m["score_matches_events"].fillna(True)
    team_minutes = p[p["in_lineup"]].groupby(["match_id", "team_id"])["minutes_played"].sum()
    match_len = m.set_index("match_id")["expanded_max_minute"]

    # float()/int() keep numpy scalars out of the JSON report: np.float64 is a
    # float subclass so it serialises fine, but it leaks into type checks later.
    metrics = {
        "match_coverage_pct": round(len(m) / EXPECTED_MATCHES * 100, 2),
        "shot_xg_filled_pct": round(float(xg_expected["xg"].notna().mean()) * 100, 2),
        "pass_end_xy_filled_pct": round(
            float(passes[["end_x", "end_y"]].notna().all(axis=1).mean()) * 100, 2
        ),
        "coords_out_of_range": int(((coords < 0) | (coords > 100)).any(axis=1).sum()),
        "score_mismatch_pct": round(float((~mismatch).mean()) * 100, 2),
        "unknown_minutes_pct": round(float((~p["in_lineup"]).mean()) * 100, 2),
    }
    status = {k: check(k, v) for k, v in metrics.items()}

    # Bilgi amaçlı ek ölçümler (eşik yok)
    tm = team_minutes.reset_index().merge(
        match_len.rename("len"), left_on="match_id", right_index=True
    )
    tm["ratio"] = tm["minutes_played"] / (11 * tm["len"])
    info = {
        "matches": len(m),
        "events": len(e),
        "passes": len(passes),
        "shots": len(s),
        "players": int(p["player_id"].nunique()),
        "player_match_rows": len(p),
        "known_gaps": len(gaps),
        "data_issues": len(issues),
        "median_match_length_min": float(match_len.median()),
        "team_minutes_ratio_median": round(float(tm["ratio"].median()), 3),
        "team_minutes_ratio_min": round(float(tm["ratio"].min()), 3),
        "sub_position_rows_pct": round(float((p["position"] == "Sub").mean()) * 100, 2),
        "season_goals": int(m["home_score"].sum() + m["away_score"].sum()),
        "season_xg": round(float(s.loc[~s["is_shootout"], "xg"].sum()), 1),
    }
    return {
        "league": LEAGUES[comp],
        "metrics": metrics,
        "status": status,
        "info": info,
        "gaps": gaps.to_dict("records"),
        "issues": issues.to_dict("records"),
    }


def feature_flags(results: dict) -> dict:
    flags: dict[str, str] = {}
    rank = {"pass": 0, "degraded": 1, "disabled": 2}
    for r in results.values():
        for metric, st in r["status"].items():
            for feature in AFFECTS[metric]:
                if rank[st] > rank[flags.get(feature, "pass")]:
                    flags[feature] = st
                flags.setdefault(feature, "pass")
    return dict(sorted(flags.items()))


def to_markdown(results: dict, flags: dict) -> str:
    lines = [
        f"# OpenPlay {SEASON} veri doğrulama raporu",
        "",
        f"Veri sürümü: {op.DATA_TAG} · Ligler: {', '.join(LEAGUES.values())}",
        "",
        "## Hedef eşikler",
        "",
        "| Kontrol | Hedef | " + " | ".join(LEAGUES.values()) + " |",
        "| --- | --- |" + " --- |" * len(LEAGUES),
    ]
    for k, t in TARGETS.items():
        cells = [f"{results[c]['metrics'][k]} ({results[c]['status'][k]})" for c in LEAGUES]
        op_ = "≤" if k in LOWER_IS_BETTER else "≥"
        lines.append(f"| {k} | {op_} {t} | " + " | ".join(cells) + " |")
    lines += [
        "",
        "## Bilgi amaçlı ölçümler",
        "",
        "| Ölçüm | " + " | ".join(LEAGUES.values()) + " |",
        "| --- |" + " --- |" * len(LEAGUES),
    ]
    for k in next(iter(results.values()))["info"]:
        lines.append(f"| {k} | " + " | ".join(str(results[c]["info"][k]) for c in LEAGUES) + " |")
    lines += ["", "## Özellik durumu", "", "| Özellik | Durum |", "| --- | --- |"]
    lines += [f"| {f} | {s} |" for f, s in flags.items()]
    for c in LEAGUES:
        r = results[c]
        lines += ["", f"## {r['league']}: eksik ve sorunlu maçlar", ""]
        if not r["gaps"] and not r["issues"]:
            lines.append("Eksik veya sorunlu maç yok.")
        for g in r["gaps"]:
            lines.append(
                f"- Eksik: {g['date']} {g['home_team']}–{g['away_team']} ({g.get('reason', '')})"
            )
        for i in r["issues"]:
            lines.append(
                f"- Sorun: {i['date']} {i['home_team']}–{i['away_team']}: "
                f"{i['issue']} ({i['detail']})"
            )
    return "\n".join(lines) + "\n"


def main(out_dir: str = "reports") -> int:
    force_utf8()
    warnings.simplefilter("ignore", op.CoverageWarning)
    results = {c: validate(c) for c in LEAGUES}
    flags = feature_flags(results)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        {
            # generated_at is the identity of this report. The ETL uses it as
            # the data_quality primary key, so re-loading the same report is a
            # no-op while a genuinely new run appends a new row. Deriving the
            # key from the data rather than from the loader's wall clock is
            # what makes that load idempotent.
            "generated_at": datetime.now(UTC).isoformat(),
            "data_tag": op.DATA_TAG,
            "season": SEASON_CODE,
            "results": results,
            "feature_flags": flags,
        },
        ensure_ascii=False,
        indent=2,
        default=str,
    )
    # Trailing newline: POSIX text-file convention, and pre-commit's
    # end-of-file-fixer would otherwise rewrite the file on every run.
    (out / "data_validation_2526.json").write_text(f"{payload}\n", encoding="utf-8")
    (out / "data_validation_2526.md").write_text(to_markdown(results, flags), encoding="utf-8")
    for c, r in results.items():
        print(c, r["metrics"], r["status"])
    print("feature_flags:", flags)
    return 0  # eşik başarısızlığı script'i durdurmaz


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
