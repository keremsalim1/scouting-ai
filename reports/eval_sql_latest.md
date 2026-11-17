# Text-to-SQL değerlendirmesi

Üretildi: 2026-11-17 20:05 UTC

Hakem sonuç kümesi eşitliğidir: model referanstan farklı SQL yazdıysa ve satırlar aynıysa cevap doğrudur. Yüzdelik ve grup büyüklüğü gibi zorunlu kolonlar ile yasak yapılar ayrı boyutlarda puanlanır.

## gemini/gemini-3.8-flash

- Koşu: `20261117T200114Z-gemini-3.8-flash` (112 sn)
- **Doğruluk: %91.7** (33/36 puanlanabilir soru, toplam 40)
- Eşik %70.0: geçti
- Paydadan düşenler: 4 (cevaplanamaz 4, altyapı hatası 0, bozuk referans 0)
- Token: girdi 291,347, çıktı 2,256 (sağlayıcının kendi sayımı) · **$0.2270** (2026-11-17 fiyatlarıyla)

> Sağlayıcı şu parametreleri reddetti: temperature. Koşular bu yüzden tam deterministik değil; başka bir koşuyla karşılaştırırken bunu hesaba kat.

### Kategoriler

| Kategori | n | doğru | çalıştı | zorunlu kolon | yasak yapı |
| --- | --- | --- | --- | --- | --- |
| totals | 5 | %100.0 | 5/5 | 5/5 | 5/5 |
| rates | 6 | %83.3 | 6/6 | 6/6 | 6/6 |
| percentiles | 5 | %100.0 | 5/5 | 5/5 | 5/5 |
| transfers | 5 | %100.0 | 5/5 | 3/5 | 5/5 |
| teams | 5 | %80.0 | 5/5 | 5/5 | 5/5 |
| match_detail | 5 | %80.0 | 5/5 | 5/5 | 5/5 |
| filters | 5 | %100.0 | 5/5 | 5/5 | 5/5 |
| unanswerable | 4 | n/a | 4/4 | 4/4 | 4/4 |

### Onarım döngüsü

- İlk denemede geçen: 40
- Onarımla düzelen: 0
- Onarımdan sonra da reddedilen: 0

### Soru soru inceleme

#### `rates-03` (rates)

Soru: Serie A'da 90 dakikada en çok hava topu kazanan 8 orta saha

Neden: row 2, column 1: expected 'Cesare Casadei', got 'Omri Gandelman'

```sql
SELECT player, teams, aerials_won_per90, minutes_played, matches FROM football.player_per90 WHERE comp = 'ita' AND position_group IN ('CM', 'DM', 'AM') AND minutes_played >= 900 AND aerials_won_per90 IS NOT NULL ORDER BY aerials_won_per90 DESC LIMIT 8
```

Beklenen (referans):
  - Morten Thorsby | 5.773126266036462
  - Cesare Casadei | 4.315068493150685
  - Bryan Cristante | 3.0215827338129495
  - Nahuel Estévez | 2.36259228876128
  - Ruben Loftus-Cheek | 2.1796875

Gelen (model):
  - Morten Thorsby | Genoa / Cremonese | 5.773126266036462 | 1481 | 24
  - Omri Gandelman | Lecce | 4.6875 | 1056 | 19
  - Cesare Casadei | Torino | 4.315068493150685 | 2190 | 33
  - Bryan Cristante | Roma | 3.0215827338129495 | 3336 | 37
  - Nahuel Estévez | Parma Calcio 1913 | 2.36259228876128 | 1219 | 32

#### `transfers-01` (transfers)

Soru: Sezon içinde kulüp değiştiren oyuncular arasında toplam golü en yüksek 10 oyuncu

Neden: missing required column(s): clubs

```sql
SELECT player, teams, goals, minutes_played, matches FROM football.player_season WHERE clubs > 1 AND goals IS NOT NULL ORDER BY goals DESC LIMIT 10
```

Beklenen (referans):
  - Antoine Semenyo | 17
  - Karl Etta Eyong | 7
  - Eberechi Eze | 7
  - M'Bala Nzola | 4
  - Walid Cheddira | 4

Gelen (model):
  - Antoine Semenyo | Bournemouth / Man City | 17 | 3546 | 37
  - Karl Etta Eyong | Levante / Villarreal | 7 | 1888 | 33
  - Eberechi Eze | Arsenal / Crystal Palace | 7 | 2110 | 33
  - M'Bala Nzola | Pisa / Sassuolo | 4 | 1673 | 30
  - Walid Cheddira | Lecce / Sassuolo | 4 | 1379 | 33

#### `transfers-04` (transfers)

Soru: Kulüp değiştirenler arasında toplam asisti en yüksek 5 oyuncu

Neden: missing required column(s): clubs

```sql
SELECT player, teams, assists, minutes_played, matches FROM football.player_season WHERE clubs > 1 AND assists IS NOT NULL ORDER BY assists DESC LIMIT 5
```

Beklenen (referans):
  - Giovane | 5
  - Hans Nicolussi Caviglia | 4
  - Antoine Semenyo | 4
  - Karl Etta Eyong | 4
  - Emil Holm | 4

Gelen (model):
  - Giovane | Verona / Napoli | 5 | 2011 | 33
  - Hans Nicolussi Caviglia | Parma Calcio 1913 / Fiorentina | 4 | 1583 | 26
  - Antoine Semenyo | Bournemouth / Man City | 4 | 3546 | 37
  - Karl Etta Eyong | Levante / Villarreal | 4 | 1888 | 33
  - Emil Holm | Bologna / Juventus | 4 | 974 | 18

#### `teams-02` (teams)

Soru: What is the total xG of each Serie A team?

Neden: row 1, column 2: expected 59.103394804522395, got Decimal('59.10')

```sql
SELECT team, ROUND(CAST(SUM(xg) AS DECIMAL), 2) AS total_xg FROM football.player_season_club WHERE comp = 'ita' GROUP BY team ORDER BY total_xg DESC LIMIT 200
```

Beklenen (referans):
  - Inter | 74.43994088284671
  - Juventus | 68.83422989421524
  - Atalanta | 62.813358017243445
  - Como | 61.31147583713755
  - AC Milan | 59.103394804522395

Gelen (model):
  - Inter | 74.44
  - Juventus | 68.83
  - Atalanta | 62.81
  - Como | 61.31
  - AC Milan | 59.10

#### `match_detail-02` (match_detail)

Soru: Which 5 La Liga matches had the highest attendance?

Neden: row 1, column 2: 'Real Madrid' is not in the candidate row

```sql
SELECT home_team, away_team, date, attendance FROM football.matches WHERE comp = 'esp' AND attendance IS NOT NULL ORDER BY attendance DESC LIMIT 5
```

Beklenen (referans):
  - 2025-10-26 | Real Madrid | Barcelona | 78107
  - 2026-03-22 | Real Madrid | Atletico | 77964
  - 2025-10-04 | Real Madrid | Villarreal | 75216
  - 2026-01-04 | Real Madrid | Real Betis | 75190
  - 2025-11-01 | Real Madrid | Valencia | 74796

Gelen (model):
  - Real Madrid | Barcelona | 2025-10-26 | 78107
  - Real Madrid | Atletico | 2026-03-22 | 77964
  - Real Madrid | Villarreal | 2025-10-04 | 75216
  - Real Madrid | Real Betis | 2026-01-04 | 75190
  - Real Madrid | Valencia | 2025-11-01 | 74796

## gemini/gemini-3.1-flash-lite

- Koşu: `20261117T200306Z-gemini-3.1-flash-lite` (122 sn)
- **Doğruluk: %72.2** (26/36 puanlanabilir soru, toplam 40)
- Eşik %70.0: geçti
- Paydadan düşenler: 4 (cevaplanamaz 4, altyapı hatası 0, bozuk referans 0)
- Token: girdi 291,347, çıktı 8,449 (sağlayıcının kendi sayımı) · **$0.1085** (2026-11-17 fiyatlarıyla)

### Kategoriler

| Kategori | n | doğru | çalıştı | zorunlu kolon | yasak yapı |
| --- | --- | --- | --- | --- | --- |
| totals | 5 | %80.0 | 5/5 | 5/5 | 5/5 |
| rates | 6 | %83.3 | 6/6 | 6/6 | 6/6 |
| percentiles | 5 | %100.0 | 5/5 | 5/5 | 5/5 |
| transfers | 5 | %40.0 | 5/5 | 3/5 | 3/5 |
| teams | 5 | %80.0 | 5/5 | 4/5 | 5/5 |
| match_detail | 5 | %20.0 | 4/5 | 5/5 | 5/5 |
| filters | 5 | %100.0 | 5/5 | 5/5 | 5/5 |
| unanswerable | 4 | n/a | 3/4 | 4/4 | 4/4 |

### Onarım döngüsü

- İlk denemede geçen: 38
- Onarımla düzelen: 0
- Onarımdan sonra da reddedilen: 2

### Soru soru inceleme

#### `totals-04` (totals)

Soru: Serie A'da en fazla top kazanımı yapan 5 oyuncu

Neden: row 1, column 1: 'Ylber Ramadani' is not in the candidate row

```sql
SELECT player, teams, minutes_played, value AS ball_recoveries_per90, percentile, comparison_group_size FROM football.player_metrics WHERE metric = 'ball_recoveries_per90' AND comp = 'ita' AND value IS NOT NULL ORDER BY value DESC LIMIT 5
```

Beklenen (referans):
  - Ylber Ramadani | 211
  - Luka Modric | 188
  - Bryan Cristante | 186
  - Nikola Vlasic | 181
  - Manuel Locatelli | 180

Gelen (model):
  - Ebenezer Akinsanmiro | Pisa | 1556 | 6.188946015424165 | 99.39024390243902 | 82
  - Ibrahim Sulemana | Cagliari / Bologna | 1025 | 5.795121951219512 | 98.17073170731707 | 82
  - Nicolò Barella | Inter | 2657 | 5.622882950696274 | 96.95121951219512 | 82
  - Luka Modric | AC Milan | 3051 | 5.545722713864307 | 95.73170731707317 | 82
  - Ylber Ramadani | Lecce | 3446 | 5.510737086477075 | 87.82051282051282 | 78

#### `rates-03` (rates)

Soru: Serie A'da 90 dakikada en çok hava topu kazanan 8 orta saha

Neden: row 2, column 1: expected 'Cesare Casadei', got 'Omri Gandelman'

```sql
SELECT player, teams, aerials_won_per90, minutes_played FROM football.player_per90 WHERE comp = 'ita' AND position_group IN ('CM', 'DM', 'AM') AND minutes_played >= 900 AND aerials_won_per90 IS NOT NULL ORDER BY aerials_won_per90 DESC LIMIT 8
```

Beklenen (referans):
  - Morten Thorsby | 5.773126266036462
  - Cesare Casadei | 4.315068493150685
  - Bryan Cristante | 3.0215827338129495
  - Nahuel Estévez | 2.36259228876128
  - Ruben Loftus-Cheek | 2.1796875

Gelen (model):
  - Morten Thorsby | Genoa / Cremonese | 5.773126266036462 | 1481
  - Omri Gandelman | Lecce | 4.6875 | 1056
  - Cesare Casadei | Torino | 4.315068493150685 | 2190
  - Bryan Cristante | Roma | 3.0215827338129495 | 3336
  - Nahuel Estévez | Parma Calcio 1913 | 2.36259228876128 | 1219

#### `transfers-01` (transfers)

Soru: Sezon içinde kulüp değiştiren oyuncular arasında toplam golü en yüksek 10 oyuncu

Neden: missing required column(s): clubs; forbidden structure(s): player_season_club; row 1, column 1: expected 'Antoine Semenyo', got 'Donyell Malen'

```sql
SELECT player, SUM(goals) AS total_goals, COUNT(team) AS clubs_played FROM football.player_season_club GROUP BY player_id, player HAVING COUNT(team) > 1 ORDER BY total_goals DESC LIMIT 10
```

Beklenen (referans):
  - Antoine Semenyo | 17
  - Karl Etta Eyong | 7
  - Eberechi Eze | 7
  - M'Bala Nzola | 4
  - Walid Cheddira | 4

Gelen (model):
  - Donyell Malen | 18 | 2
  - Antoine Semenyo | 17 | 2
  - Valentín Castellanos | 8 | 2
  - Karl Etta Eyong | 7 | 2
  - Eberechi Eze | 7 | 2

#### `transfers-02` (transfers)

Soru: Kulüp değiştiren oyuncuların her kulüpteki dakikaları nedir?

Neden: row count: expected 144, got 151

```sql
SELECT player, team, minutes_played FROM football.player_season_club WHERE player IN (SELECT player FROM football.player_season_club GROUP BY player HAVING COUNT(*) > 1) ORDER BY player, minutes_played DESC LIMIT 200
```

Beklenen (referans):
  - Adama Traoré | Fulham | 376
  - Adama Traoré | West Ham | 180
  - Ademola Lookman | Atalanta | 852
  - Ademola Lookman | Atletico | 672
  - Adrià Pedrosa | Elche | 1245

Gelen (model):
  - Adama Traoré | Fulham | 376
  - Adama Traoré | West Ham | 180
  - Ademola Lookman | Atalanta | 852
  - Ademola Lookman | Atletico | 672
  - Adrià Pedrosa | Elche | 1245

#### `transfers-04` (transfers)

Soru: Kulüp değiştirenler arasında toplam asisti en yüksek 5 oyuncu

Neden: missing required column(s): clubs; forbidden structure(s): player_season_club; row 5, column 1: expected 'Karl Etta Eyong', got 'Samuel Chukwueze'

```sql
SELECT player, SUM(assists) AS total_assists FROM football.player_season_club GROUP BY player_id, player HAVING COUNT(DISTINCT team) > 1 ORDER BY total_assists DESC LIMIT 5
```

Beklenen (referans):
  - Giovane | 5
  - Hans Nicolussi Caviglia | 4
  - Antoine Semenyo | 4
  - Karl Etta Eyong | 4
  - Emil Holm | 4

Gelen (model):
  - Giovane | 5
  - Emil Holm | 4
  - Antoine Semenyo | 4
  - Samuel Chukwueze | 4
  - Hans Nicolussi Caviglia | 4

#### `teams-03` (teams)

Soru: Premier League'de en çok sarı kart gören 5 takım

Neden: missing required column(s): team; row 1, column 2: Decimal('99') is not in the candidate row

```sql
SELECT teams, SUM(yellow_cards) AS total_yellow_cards FROM football.player_season WHERE comp = 'eng' GROUP BY teams ORDER BY total_yellow_cards DESC LIMIT 5
```

Beklenen (referans):
  - Tottenham | 99
  - Chelsea | 90
  - Bournemouth | 88
  - Brighton | 86
  - Sunderland | 82

Gelen (model):
  - Tottenham | 97
  - Chelsea | 87
  - Brighton | 86
  - Bournemouth | 82
  - Sunderland | 82

#### `match_detail-01` (match_detail)

Soru: Premier League'de en çok gol atılan 7 maç hangileri?

Neden: row 1, column 2: 'Fulham' is not in the candidate row

```sql
SELECT home_team, away_team, date, (home_score + away_score) AS total_goals FROM football.matches WHERE comp = 'eng' ORDER BY total_goals DESC LIMIT 7
```

Beklenen (referans):
  - 2025-12-02 | Fulham | Man City | 9
  - 2025-12-15 | Man Utd | Bournemouth | 8
  - 2025-12-03 | Brighton | Aston Villa | 7
  - 2026-01-07 | Newcastle | Leeds | 7
  - 2026-02-28 | Burnley | Brentford | 7

Gelen (model):
  - Fulham | Man City | 2025-12-02 | 9
  - Man Utd | Bournemouth | 2025-12-15 | 8
  - Liverpool | West Ham | 2026-02-28 | 7
  - Brighton | Aston Villa | 2025-12-03 | 7
  - Newcastle | Leeds | 2026-01-07 | 7

#### `match_detail-02` (match_detail)

Soru: Which 5 La Liga matches had the highest attendance?

Neden: row 1, column 2: 'Real Madrid' is not in the candidate row

```sql
SELECT home_team, away_team, attendance, date FROM football.matches WHERE comp = 'esp' AND attendance IS NOT NULL ORDER BY attendance DESC LIMIT 5
```

Beklenen (referans):
  - 2025-10-26 | Real Madrid | Barcelona | 78107
  - 2026-03-22 | Real Madrid | Atletico | 77964
  - 2025-10-04 | Real Madrid | Villarreal | 75216
  - 2026-01-04 | Real Madrid | Real Betis | 75190
  - 2025-11-01 | Real Madrid | Valencia | 74796

Gelen (model):
  - Real Madrid | Barcelona | 78107 | 2025-10-26
  - Real Madrid | Atletico | 77964 | 2026-03-22
  - Real Madrid | Villarreal | 75216 | 2025-10-04
  - Real Madrid | Real Betis | 75190 | 2026-01-04
  - Real Madrid | Valencia | 74796 | 2025-11-01

#### `match_detail-03` (match_detail)

Soru: Serie A'da en çok şut çekilen 6 maç

Neden: row 1, column 2: 'Juventus' is not in the candidate row

```sql
SELECT home_team, away_team, n_shots, date FROM football.matches WHERE comp = 'ita' ORDER BY n_shots DESC LIMIT 6
```

Beklenen (referans):
  - 2026-02-08 | Juventus | Lazio | 43
  - 2026-01-23 | Inter | Pisa | 42
  - 2026-02-09 | Atalanta | Cremonese | 41
  - 2026-05-24 | AC Milan | Cagliari | 41
  - 2025-12-01 | Bologna | Cremonese | 39

Gelen (model):
  - Juventus | Lazio | 43 | 2026-02-08
  - Inter | Pisa | 42 | 2026-01-23
  - Atalanta | Cremonese | 41 | 2026-02-09
  - AC Milan | Cagliari | 41 | 2026-05-24
  - AC Milan | Genoa | 39 | 2026-01-08

#### `match_detail-04` (match_detail)

Soru: Premier League'de xG'si en yüksek 10 şut kime ait?

Neden: column "player" does not exist
LINE 1: SELECT player, team, xg, match_id, minute FROM football.shot...
               ^
HINT:  Perhaps you meant to reference the column "shots.player_id".

```sql
SELECT player, team, xg, match_id, minute FROM football.shots WHERE comp = 'eng' ORDER BY xg DESC LIMIT 10
```

Beklenen (referans):
  - David Brooks | 0.951172
  - Casemiro | 0.935379
  - Tomás Soucek | 0.934048
  - Callum Wilson | 0.91099
  - Kyle Walker-Peters | 0.909612

Gelen (model):
_(satır yok)_

#### `unanswerable-02` (unanswerable)

Soru: En çok ilerletici taşıma yapan 10 oyuncu

Neden: column "progressive_carries" does not exist
LINE 1: SELECT player, teams, progressive_carries, minutes_played FR...
                              ^

```sql
SELECT player, teams, progressive_carries, minutes_played FROM football.player_season ORDER BY progressive_carries DESC LIMIT 10
```


## Modeller arası uyuşmazlık

Gün 5'in bulgusu: iki modelin ayrıldığı yer prompt'un belirsiz olduğu yerdir.

| Soru | Kategori | gemini/gemini-3.8-flash | gemini/gemini-3.1-flash-lite |
| --- | --- | --- | --- |
| `totals-04` | totals | doğru | yanlış |
| `transfers-01` | transfers | doğru | yanlış |
| `transfers-02` | transfers | doğru | yanlış |
| `transfers-04` | transfers | doğru | yanlış |
| `teams-02` | teams | yanlış | doğru |
| `teams-03` | teams | doğru | yanlış |
| `match_detail-01` | match_detail | doğru | yanlış |
| `match_detail-03` | match_detail | doğru | yanlış |
| `match_detail-04` | match_detail | doğru | yanlış |
