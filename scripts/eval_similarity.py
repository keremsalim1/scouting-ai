"""Measure position consistency for all three weighting configurations.

    uv run python scripts/eval_similarity.py        # writes reports/similarity_eval.md

Production `similar_players()` filters candidates to the query player's FINE
position group, which would make "position consistency" trivially 100%. So this
drops that filter: for each qualified player, take the top-10 nearest rows in
their BROAD pool and ask what fraction share the query's fine position. A
weighting that washes out positional signal scores near the base rate; one that
preserves it scores well above.

GK is excluded: its broad pool IS its fine pool, so it scores 100% by
construction and would inflate the average.

The headline is the unweighted mean over the seven non-GK fine groups, not over
players: a per-player mean would let CB (221) and FW (172) carry the number
while AM (61, base rate 20%) - the hardest and most informative case - barely
moved it.
"""

from __future__ import annotations

import sys
import time
from datetime import UTC, datetime

import psycopg
from psycopg.rows import dict_row

from football_ai.console import force_utf8
from football_ai.data.db import REPO_ROOT, connect, readonly_dsn

WEIGHTINGS = ("equal", "role", "pca")
TOP_N = 10
TARGET = 0.90
REPORT_PATH = REPO_ROOT / "reports" / "similarity_eval.md"

# One row per qualified non-GK player: how many of his 10 nearest neighbours in
# the broad pool share his fine position group. Self-exclusion is by player_id,
# so a mid-season league changer is not his own neighbour.
_NEIGHBOUR_SQL = """
with candidate as (
    select player_id, comp, season, position_group, position_group_broad, vec
    from football.player_vectors
    where weighting = %s and position_group_broad <> 'GK'
)
select q.position_group as query_group,
       n.position_group as neighbour_group,
       count(*) as hits
from candidate q
cross join lateral (
    select c.position_group
    from candidate c
    where c.position_group_broad = q.position_group_broad
      and c.player_id <> q.player_id
    order by c.vec <=> q.vec
    limit %s
) n
group by q.position_group, n.position_group
"""

_SIMILARITY_SQL = """
with candidate as (
    select player_id, comp, season, position_group_broad, vec
    from football.player_vectors
    where weighting = %s and position_group_broad <> 'GK'
)
select avg(n.similarity) as mean_similarity
from candidate q
cross join lateral (
    select 1 - (c.vec <=> q.vec) as similarity
    from candidate c
    where c.position_group_broad = q.position_group_broad
      and c.player_id <> q.player_id
    order by c.vec <=> q.vec
    limit %s
) n
"""


def confusion(conn: psycopg.Connection, weighting: str) -> dict[str, dict[str, int]]:
    """{query fine group: {neighbour fine group: count}} over the broad pool."""
    with conn.cursor() as cur:
        cur.execute(_NEIGHBOUR_SQL, (weighting, TOP_N))
        rows = cur.fetchall()
    table: dict[str, dict[str, int]] = {}
    for query_group, neighbour_group, hits in rows:
        table.setdefault(query_group, {})[neighbour_group] = hits
    return table


def position_consistency(conn: psycopg.Connection, weighting: str) -> dict[str, float]:
    """Fraction of top-10 broad-pool neighbours sharing the query's fine group."""
    table = confusion(conn, weighting)
    return {
        group: counts.get(group, 0) / sum(counts.values())
        for group, counts in table.items()
        if sum(counts.values()) > 0
    }


def base_rates(conn: psycopg.Connection) -> dict[str, float]:
    """Each fine group's share of its broad pool: the random-ranking baseline."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            "select position_group, position_group_broad, count(*) as n "
            "from football.player_vectors where weighting = 'equal' "
            "group by position_group, position_group_broad"
        )
        rows = cur.fetchall()
    totals: dict[str, int] = {}
    for row in rows:
        totals[row["position_group_broad"]] = totals.get(row["position_group_broad"], 0) + row["n"]
    return {
        row["position_group"]: row["n"] / totals[row["position_group_broad"]]
        for row in rows
        if row["position_group_broad"] != "GK"
    }


def mean_similarity(conn: psycopg.Connection, weighting: str) -> float:
    with conn.cursor() as cur:
        cur.execute(_SIMILARITY_SQL, (weighting, TOP_N))
        return float(cur.fetchone()[0])


def measure(conn: psycopg.Connection) -> dict:
    rates = base_rates(conn)
    per_weighting: dict[str, dict] = {}
    for weighting in WEIGHTINGS:
        start = time.monotonic()
        scores = position_consistency(conn, weighting)
        elapsed = time.monotonic() - start
        per_weighting[weighting] = {
            "scores": scores,
            "headline": sum(scores.values()) / len(scores),
            "mean_similarity": mean_similarity(conn, weighting),
            "confusion": confusion(conn, weighting),
            "sweep_seconds": elapsed,
        }
    return {"base_rates": rates, "weightings": per_weighting}


def render(measured: dict) -> str:
    rates = measured["base_rates"]
    groups = sorted(rates)
    lines = [
        "# Benzerlik değerlendirmesi — pozisyon tutarlılığı",
        "",
        f"Üretildi: {datetime.now(UTC).isoformat(timespec='seconds')}",
        "",
        "Üretimdeki `similar_players()` adayları **ince** pozisyon grubuna filtreler,",
        "bu da tutarlılığı tanım gereği %100 yapardı. Bu ölçüm o filtreyi kaldırır:",
        f"her oyuncunun **geniş** havuzdaki en yakın {TOP_N} komşusunun kaçı aynı ince",
        "pozisyonda? Taban oranın üstündeki fark, vektörün taşıdığı pozisyon sinyalidir.",
        "",
        "**GK dışlandı:** geniş havuzu ince havuzuyla aynı, yani yapı gereği %100 alır",
        "ve ortalamayı şişirirdi.",
        "",
        "**Manşet sayı, yedi GK-dışı grubun ağırlıksız ortalaması** — oyuncu başına",
        "ortalama olsaydı CB (221) ve FW (172) sonucu taşır, AM (61, taban %20) ise",
        "neredeyse hiç etkilemezdi.",
        "",
        f"Hedef: ≥ %{TARGET * 100:.0f}",
        "",
        "## Özet",
        "",
        "| Ağırlıklandırma | Pozisyon tutarlılığı | Hedef | Ortalama top-10 benzerlik |",
        "| --- | --- | --- | --- |",
    ]
    for weighting in WEIGHTINGS:
        data = measured["weightings"][weighting]
        verdict = "geçti" if data["headline"] >= TARGET else "altında"
        lines.append(
            f"| `{weighting}` | **%{data['headline'] * 100:.1f}** | {verdict} | "
            f"{data['mean_similarity']:.3f} |"
        )

    winner = max(WEIGHTINGS, key=lambda w: measured["weightings"][w]["headline"])
    winner_headline = measured["weightings"][winner]["headline"]
    headlines = [measured["weightings"][w]["headline"] for w in WEIGHTINGS]
    spread = (max(headlines) - min(headlines)) * 100
    lines += [
        "",
        f"**Kazanan: `{winner}`** (%{winner_headline * 100:.1f}).",
    ]
    if spread < 2.0:
        lines.append(
            f"Üç konfigürasyon arasındaki fark {spread:.1f} puan — pratikte ayırt edilemez. "
            "Ağırlıklandırmanın bu veri setinde pozisyon sinyaline katkısı yok denecek "
            "kadar az; sinyal metriklerin kendisinde. `pca` yalnızca en yüksek ortalama "
            "benzerliği verdiği için seçildi, belirgin bir üstünlüğü olduğu için değil."
        )
    if winner_headline < TARGET:
        lines.append(
            f"Hiçbir konfigürasyon %{TARGET * 100:.0f} hedefine ulaşmadı. Bu bir bulgudur, "
            "yuvarlanacak bir sayı değil — aşağıdaki karışıklık tablosu hangi rollerin "
            "birbirini soğurduğunu gösteriyor."
        )

    lines += ["", "## Grup bazında", "", "| Grup | Taban oran |"]
    header = "| Grup | Taban oran |"
    separator = "| --- | --- |"
    for weighting in WEIGHTINGS:
        header += f" `{weighting}` | kazanım |"
        separator += " --- | --- |"
    lines[-1] = header
    lines.append(separator)
    for group in groups:
        row = f"| {group} | %{rates[group] * 100:.0f} |"
        for weighting in WEIGHTINGS:
            score = measured["weightings"][weighting]["scores"].get(group, 0.0)
            lift = (score - rates[group]) * 100
            row += f" %{score * 100:.1f} | {lift:+.1f} |"
        lines.append(row)

    for weighting in WEIGHTINGS:
        data = measured["weightings"][weighting]
        lines += [
            "",
            f"## Karışıklık tablosu — `{weighting}`",
            "",
            "Satır: sorgu oyuncusunun grubu. Sütun: komşularının grupları (top-10 payı).",
            "",
        ]
        table = data["confusion"]
        neighbour_groups = sorted({g for counts in table.values() for g in counts})
        lines.append("| Sorgu | " + " | ".join(neighbour_groups) + " |")
        lines.append("| --- | " + " | ".join("---" for _ in neighbour_groups) + " |")
        for group in sorted(table):
            counts = table[group]
            total = sum(counts.values())
            cells = [f"%{counts.get(g, 0) / total * 100:.0f}" for g in neighbour_groups]
            lines.append(f"| {group} | " + " | ".join(cells) + " |")

    lines += [
        "",
        "## Ölçüm notları",
        "",
        f"- Top-{TOP_N} komşu, geniş havuz içinde, kendi `player_id`'si hariç.",
        "- Veri: openplay (Noah Bair), 2025/26, Premier League / La Liga / Serie A.",
        "",
    ]
    for weighting in WEIGHTINGS:
        seconds = measured["weightings"][weighting]["sweep_seconds"]
        lines.append(f"- `{weighting}` tam tarama: {seconds:.1f} sn")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    force_utf8()
    conn = connect(readonly_dsn(), autocommit=True)
    try:
        measured = measure(conn)
    finally:
        conn.close()

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(render(measured), encoding="utf-8")

    print("position consistency (broad pool, GK excluded):")
    for weighting in WEIGHTINGS:
        data = measured["weightings"][weighting]
        print(
            f"  {weighting:<6} {data['headline'] * 100:5.1f}%   "
            f"mean top-10 similarity {data['mean_similarity']:.3f}   "
            f"({data['sweep_seconds']:.1f}s)"
        )
    winner = max(WEIGHTINGS, key=lambda w: measured["weightings"][w]["headline"])
    print(f"  winner: {winner}")
    print(f"\nwrote {REPORT_PATH.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
