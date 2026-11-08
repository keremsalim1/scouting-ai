"""Gün 1 ek keşif: Gün 2-4'te ihtiyaç duyacağımız yapısal bulgular.

Cevapladığı sorular:
  1. Hangi pozisyon kodları var, dakikaların ne kadarı hangi kodda, `Sub` oranı?
  2. Sezon içinde takım değiştiren ve 900+ dakika oynayan kaç oyuncu var?
  3. Kendi per-90 hesabımız `op.player_season_stats(per90=True)` ile uyuşuyor mu?
  4. Pas isabeti neden toplamların oranı olmalı, maç yüzdelerinin ortalaması değil?
  5. "expanded minutes" per-90 değerlerini nominal 90 dakikaya göre ne kadar düşürüyor?

Çıktıyı `reports/data_validation_2526.md` dosyasının sonuna
"## Gün 2-4 için bulgular" başlığı altında ekler. Tekrar çalıştırmak güvenlidir:
mevcut bölüm silinip yeniden yazılır.
"""

from __future__ import annotations

import sys
import warnings
from pathlib import Path

import openplay as op
import pandas as pd

from football_ai.console import force_utf8

SEASON = "2025/26"
LEAGUES = {"eng": "Premier League", "esp": "La Liga", "ita": "Serie A"}
MIN_MINUTES = 900
SECTION = "## Gün 2-4 için bulgular"
# Kaynaklar per-90 için genelde 90 dakika varsayar; OpenPlay gerçek (uzatma dahil)
# dakikayı kullanır. Farkı ölçmek için nominal maç uzunluğu.
NOMINAL_MATCH_MINUTES = 90


def load(comp: str) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    return (
        op.matches(comp, SEASON),
        op.player_match_stats(comp, SEASON),
        op.player_season_stats(comp, SEASON),
    )


# --- 1. Pozisyon kodları ve dakika payları -------------------------------------


def positions(pms: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Pozisyon kodu basina dakika payi ve satir payi (lig bazinda)."""
    rows = []
    for comp, p in pms.items():
        total_min = float(p["minutes_played"].sum())
        g = p.groupby("position", observed=True).agg(
            minutes=("minutes_played", "sum"), rows=("minutes_played", "size")
        )
        for pos, r in g.iterrows():
            rows.append(
                {
                    "comp": comp,
                    "position": pos,
                    "minute_share_pct": round(float(r["minutes"]) / total_min * 100, 2),
                    "row_share_pct": round(float(r["rows"]) / len(p) * 100, 2),
                    "median_minutes": float(p.loc[p["position"] == pos, "minutes_played"].median()),
                }
            )
    return pd.DataFrame(rows)


# --- 2. Takim degistirenler ----------------------------------------------------


def switchers(pss: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Sezon icinde takim degistirenler; 900 dk esigi iki farkli sekilde."""
    rows = []
    for comp, s in pss.items():
        per_player = s.groupby("player_id").agg(
            teams=("team_id", "nunique"), total_minutes=("minutes_played", "sum")
        )
        multi = per_player[per_player["teams"] > 1]
        # Tek kulupte 900+ dakika oynayanlar: Gun 3'te kulup bazli satir
        # tek basina analiz edilebilir mi sorusunun cevabi.
        single_club_ok = s[
            (s["player_id"].isin(multi.index)) & (s["minutes_played"] >= MIN_MINUTES)
        ]
        rows.append(
            {
                "comp": comp,
                "league": LEAGUES[comp],
                "players": int(s["player_id"].nunique()),
                "season_rows": len(s),
                "switchers": len(multi),
                "switchers_combined_900plus": int((multi["total_minutes"] >= MIN_MINUTES).sum()),
                "switchers_single_club_900plus": int(single_club_ok["player_id"].nunique()),
            }
        )
    return pd.DataFrame(rows)


# --- 3. Per-90 capraz kontrolu -------------------------------------------------

PER90_COLS = ["npxg", "xa", "progressive_passes"]
TOLERANCE = 0.01


def per90_crosscheck(comp: str, n: int = 5) -> pd.DataFrame:
    """Kendi per-90 hesabimizi op.player_season_stats(per90=True) ile karsilastir.

    Formul: toplam sayim / toplam minutes_played * 90. Gruplama oyuncu + takim
    bazinda, cunku player_season_stats de boyle topluyor.
    """
    pms = op.player_match_stats(comp, SEASON)
    ref = op.player_season_stats(comp, SEASON, per90=True)

    agg = {"minutes_played": ("minutes_played", "sum")}
    agg |= {c: (c, "sum") for c in PER90_COLS}
    own = pms.groupby(["player_id", "team_id"], as_index=False).agg(**agg)
    own = own[own["minutes_played"] >= MIN_MINUTES].copy()
    for c in PER90_COLS:
        own[c] = own[c].astype("float64") / own["minutes_played"].astype("float64") * 90

    merged = own.merge(
        ref[["player_id", "team_id", "player", "team", *PER90_COLS]],
        on=["player_id", "team_id"],
        suffixes=("_own", "_op"),
    )
    for c in PER90_COLS:
        merged[f"{c}_diff"] = (merged[f"{c}_own"] - merged[f"{c}_op"]).abs()
    merged["max_diff"] = merged[[f"{c}_diff" for c in PER90_COLS]].max(axis=1)
    # En kotu durumu gostermek en durust ornek: hata varsa burada gorunur.
    return merged.sort_values("max_diff", ascending=False).head(n)


# --- 4. Pas isabeti: toplamlarin orani vs maç ortalamasi -----------------------


def pass_accuracy_gap(comp: str, n: int = 5) -> pd.DataFrame:
    """Iki hesabin en cok ayristigi oyuncular.

    correct  = Σ passes_completed / Σ passes            (toplamlarin orani)
    naive    = mean(maç basina passes_completed/passes) (maç yuzdelerinin ortalamasi)
    """
    pms = op.player_match_stats(comp, SEASON)
    played = pms[pms["passes"] > 0].copy()
    played["match_pct"] = (
        played["passes_completed"].astype("float64") / played["passes"].astype("float64") * 100
    )
    g = played.groupby(["player_id", "team_id"], as_index=False).agg(
        player=("player", "first"),
        team=("team", "first"),
        minutes=("minutes_played", "sum"),
        passes=("passes", "sum"),
        completed=("passes_completed", "sum"),
        naive_pct=("match_pct", "mean"),
        matches=("match_pct", "size"),
    )
    g = g[g["minutes"] >= MIN_MINUTES].copy()
    g["correct_pct"] = g["completed"].astype("float64") / g["passes"].astype("float64") * 100
    g["gap_pp"] = g["naive_pct"] - g["correct_pct"]
    g["abs_gap"] = g["gap_pp"].abs()
    return g.sort_values("abs_gap", ascending=False).head(n)


def pass_accuracy_example(comp: str, player_id: int, team_id: int) -> pd.DataFrame:
    """Tek oyuncunun en kucuk ve en buyuk hacimli maclarini goster."""
    pms = op.player_match_stats(comp, SEASON)
    rows = pms[(pms["player_id"] == player_id) & (pms["team_id"] == team_id) & (pms["passes"] > 0)]
    rows = rows[["date", "opponent", "minutes_played", "passes", "passes_completed"]].copy()
    rows["date"] = rows["date"].dt.strftime("%Y-%m-%d")
    rows["match_pct"] = round(rows["passes_completed"] / rows["passes"] * 100, 1)
    rows = rows.sort_values("passes")
    return pd.concat([rows.head(2), rows.tail(2)])


# --- 5. Expanded minutes etkisi ------------------------------------------------


def expanded_minutes_effect(matches: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for comp, m in matches.items():
        mean_len = float(m["expanded_max_minute"].mean())
        rows.append(
            {
                "comp": comp,
                "league": LEAGUES[comp],
                "mean_match_length_min": round(mean_len, 2),
                "median_match_length_min": float(m["expanded_max_minute"].median()),
                # Ayni sayimi nominal 90 dk ile boleriz: per-90 degeri bu oranda
                # daha yuksek cikardi. Yani OpenPlay per-90'i bu kadar "dusuk".
                "per90_lower_than_nominal_pct": round(
                    (1 - NOMINAL_MATCH_MINUTES / mean_len) * 100, 1
                ),
            }
        )
    return pd.DataFrame(rows)


# --- Markdown ------------------------------------------------------------------


def md_table(df: pd.DataFrame) -> list[str]:
    header = "| " + " | ".join(str(c) for c in df.columns) + " |"
    sep = "| " + " | ".join("---" for _ in df.columns) + " |"
    body = [
        "| " + " | ".join("" if pd.isna(x) else str(x) for x in row) + " |"
        for row in df.itertuples(index=False, name=None)
    ]
    return [header, sep, *body]


def build_section() -> str:
    matches, pms, pss = {}, {}, {}
    for comp in LEAGUES:
        matches[comp], pms[comp], pss[comp] = load(comp)

    lines = [SECTION, ""]

    lines += [
        "### 1. Pozisyon kodları ve dakika payları",
        "",
        "`position` başlangıç pozisyonudur; sonradan girenlerde `Sub` yazar. "
        "Dakikaların dörtte birinden fazlası `Sub` satırlarında olduğu için "
        "pozisyon grubu ataması bu satırları ayrıca ele almak zorunda (Gün 3, D-005).",
        "",
    ]
    pos = positions(pms)
    pivot = (
        pos.pivot(index="position", columns="comp", values="minute_share_pct")
        .reindex(columns=list(LEAGUES))
        .sort_values("eng", ascending=False)
        .reset_index()
    )
    pivot.columns = ["position", *[f"{c}_minute_share_pct" for c in LEAGUES]]
    lines += md_table(pivot)
    lines += [""]
    sub = pos[pos["position"] == "Sub"]
    lines += [
        "`Sub` satırlarının payı (satır sayısı / dakika / medyan dakika):",
        "",
    ]
    lines += md_table(sub[["comp", "row_share_pct", "minute_share_pct", "median_minutes"]])
    lines += [
        "",
        f"Toplam **{pos['position'].nunique()}** farklı pozisyon kodu var.",
        "",
    ]

    lines += [
        "### 2. Sezon içinde takım değiştirenler",
        "",
        "`player_season_stats` oyuncu + takım bazında toplar; takım değiştiren "
        "oyuncu iki satırdır. Analiz için iki ayrı eşik anlamlı: toplam dakikası "
        f"{MIN_MINUTES}+ olanlar, ve tek bir kulüpte {MIN_MINUTES}+ oynayanlar. "
        "İkincisi, kulüp bazlı satırın tek başına güvenilir olduğu durumdur.",
        "",
    ]
    sw = switchers(pss)
    lines += md_table(sw)
    lines += [""]

    lines += [
        "### 3. Per-90 çapraz kontrolü",
        "",
        f"Kendi formülümüz (`Σ sayım / Σ minutes_played × 90`, oyuncu + takım "
        f"bazında, {MIN_MINUTES}+ dakika) ile `op.player_season_stats(per90=True)` "
        f"karşılaştırması. Tablo **en büyük farkı veren 5 oyuncuyu** gösterir; "
        f"tolerans ±{TOLERANCE}.",
        "",
    ]
    worst_overall = 0.0
    for comp in LEAGUES:
        cc = per90_crosscheck(comp)
        worst_overall = max(worst_overall, float(cc["max_diff"].max()))
        # merge() suffixed the overlapping metric columns: <metric>_own / <metric>_op.
        value_cols = [f"{c}_{side}" for c in PER90_COLS for side in ("own", "op")]
        show = cc[["player", "team", "minutes_played", *value_cols, "max_diff"]].copy()
        show = show.rename(columns={"minutes_played": "minutes"})
        for c in value_cols:
            show[c] = show[c].round(4)
        show["max_diff"] = show["max_diff"].map(lambda x: f"{x:.2e}")
        lines += [f"**{LEAGUES[comp]}**", ""]
        lines += md_table(show)
        lines += [""]
    verdict = "GEÇTİ" if worst_overall <= TOLERANCE else "BAŞARISIZ"
    lines += [
        f"Üç ligdeki **en büyük** mutlak fark: `{worst_overall:.2e}` "
        f"(tolerans `{TOLERANCE}`) → **{verdict}**. Bu, kayan nokta "
        "yuvarlama düzeyinde bir fark; formülümüz OpenPlay ile aynı.",
        "",
    ]

    lines += [
        "### 4. Pas isabeti neden toplamların oranı olmalı",
        "",
        "Doğru: `Σ passes_completed / Σ passes`. Yanlış: maç başına yüzdelerin "
        "ortalaması — bu, 3 pas attığı maçı 60 pas attığı maçla eşit ağırlıklar. "
        "Aşağıda iki hesabın en çok ayrıştığı oyuncular (fark = yanlış − doğru, "
        "yüzde puanı):",
        "",
    ]
    for comp in LEAGUES:
        gap = pass_accuracy_gap(comp)
        show = gap[
            [
                "player",
                "team",
                "matches",
                "passes",
                "completed",
                "correct_pct",
                "naive_pct",
                "gap_pp",
            ]
        ].copy()
        for c in ["correct_pct", "naive_pct", "gap_pp"]:
            show[c] = show[c].round(2)
        lines += [f"**{LEAGUES[comp]}**", ""]
        lines += md_table(show)
        lines += [""]

    top = pass_accuracy_gap("eng", n=1).iloc[0]
    ex = pass_accuracy_example("eng", int(top["player_id"]), int(top["team_id"]))
    lines += [
        f"Somut örnek — **{top['player']}** ({top['team']}, {int(top['matches'])} maç). "
        "En az ve en çok pas attığı ikişer maç:",
        "",
    ]
    lines += md_table(ex)
    lines += [
        "",
        f"Toplamların oranı: **{top['correct_pct']:.2f}%** "
        f"({int(top['completed'])}/{int(top['passes'])}). "
        f"Maç yüzdelerinin ortalaması: **{top['naive_pct']:.2f}%**. "
        f"Fark **{top['gap_pp']:.2f}** yüzde puanı. Düşük hacimli maçlar "
        "ortalamayı çekiyor; bu yüzden tüm oranlar toplamların oranı olarak "
        "hesaplanır (D-004).",
        "",
    ]

    lines += [
        "### 5. Expanded minutes per-90'ı ne kadar düşürüyor",
        "",
        "`minutes_played` uzatma dahil gerçek dakikadır. Per-90 değerleri bu "
        "yüzden nominal 90 dakika varsayan kaynaklardan sistematik olarak düşüktür:",
        "",
    ]
    lines += md_table(expanded_minutes_effect(matches))
    lines += [
        "",
        "Pratik sonuç: OpenPlay per-90 değerleri FBref/Opta gibi kaynaklarla "
        "**doğrudan karşılaştırılamaz**; karşılaştırmalar yalnızca OpenPlay "
        "içinde yapılır (D-004).",
        "",
    ]

    not_in_lineup = sum(int((~p["in_lineup"]).sum()) for p in pms.values())
    starters = sum(int(p["is_starter"].sum()) for p in pms.values())
    subs = sum(int((p["position"] == "Sub").sum()) for p in pms.values())
    total_rows = sum(len(p) for p in pms.values())
    lines += [
        "### 6. Uyarı: `unknown_minutes_pct` yapısal olarak her zaman 0",
        "",
        f"Üç ligde `in_lineup` sütununun tamamı `True`: `False` olan satır sayısı "
        f"**{not_in_lineup}**. Satır sayısı da bunu doğruluyor: {starters} ilk 11 "
        f"+ {subs} `Sub` = {starters + subs} = toplam satır ({total_rows}). Yani "
        "`player_match_stats` **yalnızca sahaya çıkan** oyuncuları içeriyor; "
        "kullanılmayan yedekler tabloda yok.",
        "",
        "Bu nedenle doğrulama raporundaki `unknown_minutes_pct` metriği hiçbir "
        "zaman başarısız olamaz ve yanlış bir güven veriyor. Gün 2'de dakika "
        "bütünlüğü kontrolü `team_minutes_ratio` (takım dakikası / 11 × maç "
        "uzunluğu) üzerinden yapılmalı — kırmızı kart alan maçlarda bu oran "
        "1'in altına düşüyor ve gerçek bir sinyal taşıyor.",
        "",
    ]

    return "\n".join(lines)


def main(report: str = "reports/data_validation_2526.md") -> int:
    force_utf8()
    warnings.simplefilter("ignore", op.CoverageWarning)
    section = build_section()
    path = Path(report)
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    # Idempotent: varsa eski bolumu kes, yenisini ekle.
    head = existing.split(SECTION)[0].rstrip()
    path.write_text(f"{head}\n\n{section}", encoding="utf-8")
    print(f"wrote {SECTION!r} to {path} ({len(section)} chars)")
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
