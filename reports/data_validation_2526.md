# OpenPlay 2025/26 veri doğrulama raporu

Veri sürümü: data-v0.1.0 · Ligler: Premier League, La Liga, Serie A

## Hedef eşikler

| Kontrol | Hedef | Premier League | La Liga | Serie A |
| --- | --- | --- | --- | --- |
| match_coverage_pct | ≥ 99.0 | 100.0 (pass) | 100.0 (pass) | 100.0 (pass) |
| shot_xg_filled_pct | ≥ 99.0 | 100.0 (pass) | 100.0 (pass) | 100.0 (pass) |
| pass_end_xy_filled_pct | ≥ 99.0 | 100.0 (pass) | 100.0 (pass) | 100.0 (pass) |
| coords_out_of_range | ≤ 0 | 0 (pass) | 0 (pass) | 0 (pass) |
| score_mismatch_pct | ≤ 1.0 | 0.0 (pass) | 0.0 (pass) | 0.0 (pass) |
| unknown_minutes_pct | ≤ 1.0 | 0.0 (pass) | 0.0 (pass) | 0.0 (pass) |

## Bilgi amaçlı ölçümler

| Ölçüm | Premier League | La Liga | Serie A |
| --- | --- | --- | --- |
| matches | 380 | 380 | 380 |
| events | 577884 | 577205 | 562672 |
| passes | 362739 | 362956 | 357679 |
| shots | 9543 | 9510 | 9381 |
| players | 537 | 600 | 586 |
| player_match_rows | 11492 | 11953 | 11928 |
| known_gaps | 0 | 0 | 0 |
| data_issues | 0 | 0 | 0 |
| median_match_length_min | 100.0 | 99.0 | 98.0 |
| team_minutes_ratio_median | 1.0 | 1.0 | 1.0 |
| team_minutes_ratio_min | 0.912 | 0.881 | 0.898 |
| sub_position_rows_pct | 27.25 | 30.06 | 29.91 |
| season_goals | 1045 | 1024 | 922 |
| season_xg | 1099.2 | 1023.4 | 982.4 |

## Özellik durumu

| Özellik | Durum |
| --- | --- |
| gol / G−xG analizleri | pass |
| koordinat tabanlı pas metrikleri | pass |
| minimum dakika filtresi | pass |
| pas haritaları | pass |
| per-90 | pass |
| per-90 metrikleri | pass |
| tüm koordinat tabanlı görseller | pass |
| tüm sezon toplamları | pass |
| xG analizi | pass |
| xG tabanlı scouting metrikleri | pass |

## Premier League: eksik ve sorunlu maçlar

Eksik veya sorunlu maç yok.

## La Liga: eksik ve sorunlu maçlar

Eksik veya sorunlu maç yok.

## Serie A: eksik ve sorunlu maçlar

Eksik veya sorunlu maç yok.

## Gün 2-4 için bulgular

### 1. Pozisyon kodları ve dakika payları

`position` başlangıç pozisyonudur; sonradan girenlerde `Sub` yazar. Dakikaların dörtte birinden fazlası `Sub` satırlarında olduğu için pozisyon grubu ataması bu satırları ayrıca ele almak zorunda (Gün 3, D-005).

| position | eng_minute_share_pct | esp_minute_share_pct | ita_minute_share_pct |
| --- | --- | --- | --- |
| DC | 19.42 | 18.92 | 22.52 |
| Sub | 9.54 | 11.75 | 11.61 |
| DMC | 9.27 | 6.44 | 2.53 |
| MC | 9.07 | 11.23 | 17.82 |
| GK | 9.07 | 9.11 | 9.05 |
| FW | 8.45 | 10.42 | 10.39 |
| DR | 6.85 | 7.23 | 3.11 |
| DL | 6.82 | 7.35 | 3.1 |
| AMC | 6.55 | 3.29 | 4.61 |
| AML | 4.14 | 2.71 | 0.92 |
| AMR | 4.11 | 2.72 | 0.98 |
| DML | 1.46 | 0.94 | 4.53 |
| DMR | 1.35 | 0.83 | 4.59 |
| FWR | 1.18 | 0.92 | 1.33 |
| FWL | 1.11 | 0.89 | 1.32 |
| ML | 0.81 | 2.62 | 0.8 |
| MR | 0.8 | 2.64 | 0.8 |

`Sub` satırlarının payı (satır sayısı / dakika / medyan dakika):

| comp | row_share_pct | minute_share_pct | median_minutes |
| --- | --- | --- | --- |
| eng | 27.25 | 9.54 | 23.0 |
| esp | 30.06 | 11.75 | 26.0 |
| ita | 29.91 | 11.61 | 25.0 |

Toplam **17** farklı pozisyon kodu var.

### 2. Sezon içinde takım değiştirenler

`player_season_stats` oyuncu + takım bazında toplar; takım değiştiren oyuncu iki satırdır. Analiz için iki ayrı eşik anlamlı: toplam dakikası 900+ olanlar, ve tek bir kulüpte 900+ oynayanlar. İkincisi, kulüp bazlı satırın tek başına güvenilir olduğu durumdur.

| comp | league | players | season_rows | switchers | switchers_combined_900plus | switchers_single_club_900plus |
| --- | --- | --- | --- | --- | --- | --- |
| eng | Premier League | 537 | 551 | 14 | 9 | 5 |
| esp | La Liga | 600 | 611 | 11 | 9 | 7 |
| ita | Serie A | 586 | 609 | 23 | 16 | 10 |

### 3. Per-90 çapraz kontrolü

Kendi formülümüz (`Σ sayım / Σ minutes_played × 90`, oyuncu + takım bazında, 900+ dakika) ile `op.player_season_stats(per90=True)` karşılaştırması. Tablo **en büyük farkı veren 5 oyuncuyu** gösterir; tolerans ±0.01.

**Premier League**

| player | team | minutes | npxg_own | npxg_op | xa_own | xa_op | progressive_passes_own | progressive_passes_op | max_diff |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Beto | Everton | 1757 | 0.489 | 0.489 | 0.0526 | 0.0526 | 0.2049 | 0.2049 | 2.25e-08 |
| Callum Wilson | West Ham | 1457 | 0.4984 | 0.4984 | 0.0603 | 0.0603 | 0.3706 | 0.3706 | 1.91e-08 |
| Raúl Jiménez | Fulham | 2416 | 0.3031 | 0.3031 | 0.0695 | 0.0695 | 0.894 | 0.894 | 1.75e-08 |
| David Brooks | Bournemouth | 1381 | 0.341 | 0.341 | 0.2617 | 0.2617 | 3.3888 | 3.3888 | 1.66e-08 |
| Liam Delap | Chelsea | 1298 | 0.3414 | 0.3414 | 0.0142 | 0.0142 | 0.3467 | 0.3467 | 1.60e-08 |

**La Liga**

| player | team | minutes | npxg_own | npxg_op | xa_own | xa_op | progressive_passes_own | progressive_passes_op | max_diff |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Robert Lewandowski | Barcelona | 1860 | 0.4664 | 0.4664 | 0.0905 | 0.0905 | 0.5323 | 0.5323 | 1.98e-08 |
| Roberto Fernández | Espanyol | 2620 | 0.2922 | 0.2922 | 0.1018 | 0.1018 | 0.6183 | 0.6183 | 1.95e-08 |
| Lamine Yamal | Barcelona | 2500 | 0.3346 | 0.3346 | 0.338 | 0.338 | 5.904 | 5.904 | 1.76e-08 |
| Mikel Oyarzabal | Real Sociedad | 2993 | 0.2608 | 0.2608 | 0.1449 | 0.1449 | 1.7441 | 1.7441 | 1.50e-08 |
| Kylian Mbappé | Real Madrid | 2832 | 0.4284 | 0.4284 | 0.2124 | 0.2124 | 2.0021 | 2.0021 | 1.28e-08 |

**Serie A**

| player | team | minutes | npxg_own | npxg_op | xa_own | xa_op | progressive_passes_own | progressive_passes_op | max_diff |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Dusan Vlahovic | Juventus | 1054 | 0.5953 | 0.5953 | 0.1241 | 0.1241 | 0.6831 | 0.6831 | 2.86e-08 |
| Gift Orban | Verona | 2176 | 0.3656 | 0.3656 | 0.097 | 0.097 | 0.9513 | 0.9513 | 1.78e-08 |
| Gianluca Scamacca | Atalanta | 1422 | 0.393 | 0.393 | 0.0845 | 0.0845 | 1.3291 | 1.3291 | 1.47e-08 |
| Nikola Krstovic | Atalanta | 1960 | 0.6592 | 0.6592 | 0.1235 | 0.1235 | 0.9184 | 0.9184 | 1.37e-08 |
| Thijs Dallinga | Bologna | 922 | 0.2985 | 0.2985 | 0.0661 | 0.0661 | 1.1714 | 1.1714 | 1.31e-08 |

Üç ligdeki **en büyük** mutlak fark: `2.86e-08` (tolerans `0.01`) → **GEÇTİ**. Bu, kayan nokta yuvarlama düzeyinde bir fark; formülümüz OpenPlay ile aynı.

### 4. Pas isabeti neden toplamların oranı olmalı

Doğru: `Σ passes_completed / Σ passes`. Yanlış: maç başına yüzdelerin ortalaması — bu, 3 pas attığı maçı 60 pas attığı maçla eşit ağırlıklar. Aşağıda iki hesabın en çok ayrıştığı oyuncular (fark = yanlış − doğru, yüzde puanı):

**Premier League**

| player | team | matches | passes | completed | correct_pct | naive_pct | gap_pp |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Bafodé Diakité | Bournemouth | 17 | 751 | 659 | 87.75 | 79.56 | -8.19 |
| Maximilian Kilman | West Ham | 19 | 690 | 605 | 87.68 | 79.8 | -7.88 |
| Joël Veltman | Brighton | 22 | 570 | 445 | 78.07 | 70.54 | -7.53 |
| Ao Tanaka | Leeds | 28 | 730 | 605 | 82.88 | 75.48 | -7.4 |
| Hjalmar Ekdal | Burnley | 19 | 684 | 581 | 84.94 | 77.55 | -7.39 |

**La Liga**

| player | team | matches | passes | completed | correct_pct | naive_pct | gap_pp |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Gerard Gumbau | Rayo Vallecano | 28 | 541 | 424 | 78.37 | 68.63 | -9.74 |
| Jofre Carreras | Espanyol | 26 | 253 | 172 | 67.98 | 59.57 | -8.41 |
| Beñat Turrientes | Real Sociedad | 27 | 706 | 604 | 85.55 | 77.29 | -8.26 |
| Fran García | Real Madrid | 13 | 541 | 464 | 85.77 | 77.72 | -8.04 |
| Nemanja Gudelj | Sevilla | 34 | 1116 | 981 | 87.9 | 80.54 | -7.37 |

**Serie A**

| player | team | matches | passes | completed | correct_pct | naive_pct | gap_pp |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Koni De Winter | AC Milan | 26 | 1289 | 1169 | 90.69 | 81.38 | -9.31 |
| Ruben Loftus-Cheek | AC Milan | 27 | 419 | 348 | 83.05 | 74.81 | -8.24 |
| Neil El Aynaoui | Roma | 25 | 603 | 529 | 87.73 | 79.82 | -7.91 |
| Alessio Zerbin | Cremonese | 32 | 555 | 377 | 67.93 | 60.89 | -7.04 |
| Patrizio Masini | Genoa | 28 | 583 | 427 | 73.24 | 66.31 | -6.93 |

Somut örnek — **Bafodé Diakité** (Bournemouth, 17 maç). En az ve en çok pas attığı ikişer maç:

| date | opponent | minutes_played | passes | passes_completed | match_pct |
| --- | --- | --- | --- | --- | --- |
| 2026-01-07 | Tottenham | 14 | 2 | 1 | 50.0 |
| 2026-01-19 | Brighton | 22 | 4 | 1 | 25.0 |
| 2025-12-02 | Everton | 98 | 67 | 60 | 89.6 |
| 2025-12-20 | Burnley | 98 | 71 | 67 | 94.4 |

Toplamların oranı: **87.75%** (659/751). Maç yüzdelerinin ortalaması: **79.56%**. Fark **-8.19** yüzde puanı. Düşük hacimli maçlar ortalamayı çekiyor; bu yüzden tüm oranlar toplamların oranı olarak hesaplanır (D-004).

### 5. Expanded minutes per-90'ı ne kadar düşürüyor

`minutes_played` uzatma dahil gerçek dakikadır. Per-90 değerleri bu yüzden nominal 90 dakika varsayan kaynaklardan sistematik olarak düşüktür:

| comp | league | mean_match_length_min | median_match_length_min | per90_lower_than_nominal_pct |
| --- | --- | --- | --- | --- |
| eng | Premier League | 100.89 | 100.0 | 10.8 |
| esp | La Liga | 99.69 | 99.0 | 9.7 |
| ita | Serie A | 98.02 | 98.0 | 8.2 |

Pratik sonuç: OpenPlay per-90 değerleri FBref/Opta gibi kaynaklarla **doğrudan karşılaştırılamaz**; karşılaştırmalar yalnızca OpenPlay içinde yapılır (D-004).

### 6. Uyarı: `unknown_minutes_pct` yapısal olarak her zaman 0

Üç ligde `in_lineup` sütununun tamamı `True`: `False` olan satır sayısı **0**. Satır sayısı da bunu doğruluyor: 25080 ilk 11 + 10293 `Sub` = 35373 = toplam satır (35373). Yani `player_match_stats` **yalnızca sahaya çıkan** oyuncuları içeriyor; kullanılmayan yedekler tabloda yok.

Bu nedenle doğrulama raporundaki `unknown_minutes_pct` metriği hiçbir zaman başarısız olamaz ve yanlış bir güven veriyor. Gün 2'de dakika bütünlüğü kontrolü `team_minutes_ratio` (takım dakikası / 11 × maç uzunluğu) üzerinden yapılmalı — kırmızı kart alan maçlarda bu oran 1'in altına düşüyor ve gerçek bir sinyal taşıyor.
