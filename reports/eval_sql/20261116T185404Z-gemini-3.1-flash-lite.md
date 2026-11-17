# Text-to-SQL değerlendirmesi

Üretildi: 2026-11-16 18:58 UTC

Hakem sonuç kümesi eşitliğidir: model referanstan farklı SQL yazdıysa ve satırlar aynıysa cevap doğrudur. Yüzdelik ve grup büyüklüğü gibi zorunlu kolonlar ile yasak yapılar ayrı boyutlarda puanlanır.

## gemini/gemini-3.1-flash-lite

- Koşu: `20261116T185404Z-gemini-3.1-flash-lite` (279 sn)
- **Doğruluk: %52.8** (19/36 puanlanabilir soru, toplam 40)
- Eşik %70.0: **geçemedi**
- Paydadan düşenler: 4 (cevaplanamaz 4, altyapı hatası 0, bozuk referans 0)
- Sağlayıcı yeniden denemesi: 1

### Kategoriler

| Kategori | n | doğru | çalıştı | zorunlu kolon | yasak yapı |
| --- | --- | --- | --- | --- | --- |
| totals | 5 | %40.0 | 5/5 | 5/5 | 5/5 |
| rates | 6 | %16.7 | 6/6 | 2/6 | 6/6 |
| percentiles | 5 | %80.0 | 5/5 | 5/5 | 5/5 |
| transfers | 5 | %40.0 | 5/5 | 3/5 | 5/5 |
| teams | 5 | %100.0 | 5/5 | 5/5 | 5/5 |
| match_detail | 5 | %0.0 | 3/5 | 5/5 | 5/5 |
| filters | 5 | %100.0 | 5/5 | 5/5 | 5/5 |
| unanswerable | 4 | n/a | 4/4 | 4/4 | 4/4 |

### Onarım döngüsü

- İlk denemede geçen: 38
- Onarımla düzelen: 0
- Onarımdan sonra da reddedilen: 2

### Soru soru inceleme

#### `totals-02` (totals)

Soru: La Liga'da en çok sarı kart gören 7 oyuncu

Neden: column count: expected at least 5, got 3

```sql
SELECT player, teams, yellow_cards FROM football.player_season WHERE comp = 'esp' ORDER BY yellow_cards DESC LIMIT 7
```

Beklenen (referans):
  - José Ángel Carmona | Sevilla | 13 | 2852 | 35
  - Domingos Duarte | Getafe | 12 | 3244 | 34
  - Lucien Agoumé | Sevilla | 12 | 2976 | 34
  - Jon Aramburu | Real Sociedad | 11 | 3064 | 35
  - Alejandro Catena | Osasuna | 11 | 3402 | 35

Gelen (model):
  - José Ángel Carmona | Sevilla | 13
  - Domingos Duarte | Getafe | 12
  - Lucien Agoumé | Sevilla | 12
  - Jon Aramburu | Real Sociedad | 11
  - Alejandro Catena | Osasuna | 11

#### `totals-04` (totals)

Soru: Serie A'da en fazla top kazanımı yapan 5 oyuncu

Neden: row 1, column 1: expected 'Ylber Ramadani', got 'Ebenezer Akinsanmiro'

```sql
SELECT player, teams, value AS ball_recoveries_per90, percentile, comparison_group_size FROM football.player_metrics WHERE metric = 'ball_recoveries_per90' AND comp = 'ita' ORDER BY value DESC LIMIT 5
```

Beklenen (referans):
  - Ylber Ramadani | Lecce | 211 | 3446 | 37
  - Luka Modric | AC Milan | 188 | 3051 | 34
  - Bryan Cristante | Roma | 186 | 3336 | 37
  - Nikola Vlasic | Torino | 181 | 3256 | 37
  - Manuel Locatelli | Juventus | 180 | 3218 | 36

Gelen (model):
  - Ebenezer Akinsanmiro | Pisa | 6.188946015424165 | 99.39024390243902 | 82
  - Ibrahim Sulemana | Cagliari / Bologna | 5.795121951219512 | 98.17073170731707 | 82
  - Nicolò Barella | Inter | 5.622882950696274 | 96.95121951219512 | 82
  - Luka Modric | AC Milan | 5.545722713864307 | 95.73170731707317 | 82
  - Ylber Ramadani | Lecce | 5.510737086477075 | 87.82051282051282 | 78

#### `totals-05` (totals)

Soru: Premier League'de en çok dakika oynayan 10 oyuncu

Neden: column count: expected at least 4, got 3

```sql
SELECT player, teams, minutes_played FROM football.player_season WHERE comp = 'eng' ORDER BY minutes_played DESC LIMIT 10
```

Beklenen (referans):
  - Virgil van Dijk | Liverpool | 3858 | 38
  - Djordje Petrovic | Bournemouth | 3837 | 38
  - Bernd Leno | Fulham | 3827 | 38
  - Bart Verbruggen | Brighton | 3824 | 38
  - Jordan Pickford | Everton | 3796 | 38

Gelen (model):
  - Virgil van Dijk | Liverpool | 3858
  - Djordje Petrovic | Bournemouth | 3837
  - Bernd Leno | Fulham | 3827
  - Bart Verbruggen | Brighton | 3824
  - Jordan Pickford | Everton | 3796

#### `rates-02` (rates)

Soru: Premier League'de pas isabeti en yüksek 10 stoper

Neden: missing required column(s): minutes_played; row 1, column 4: expected Decimal('3382'), got 99.28571428571429

```sql
SELECT player, teams, value AS pass_pct, percentile, comparison_group_size FROM football.player_metrics WHERE metric = 'pass_pct' AND comp = 'eng' AND position_group = 'CB' ORDER BY value DESC LIMIT 10
```

Beklenen (referans):
  - Ezri Konsa | Aston Villa | 95.24940617577197 | 3382
  - Victor Lindelöf | Aston Villa | 94.20970266040689 | 1070
  - Trevoh Chalobah | Chelsea | 92.88194444444444 | 3160
  - Rúben Dias | Man City | 92.69535673839184 | 2402
  - William Saliba | Arsenal | 92.6852288815479 | 2942

Gelen (model):
  - Ezri Konsa | Aston Villa | 95.24940617577197 | 99.28571428571429 | 70
  - Victor Lindelöf | Aston Villa | 94.20970266040689 | 97.85714285714286 | 70
  - Trevoh Chalobah | Chelsea | 92.88194444444444 | 96.42857142857143 | 70
  - Rúben Dias | Man City | 92.69535673839184 | 95.0 | 70
  - William Saliba | Arsenal | 92.6852288815479 | 93.57142857142857 | 70

#### `rates-03` (rates)

Soru: Serie A'da 90 dakikada en çok hava topu kazanan 8 orta saha

Neden: missing required column(s): minutes_played; row 1, column 1: expected 'Morten Thorsby', got 'Omri Gandelman'

```sql
SELECT player, teams, value AS aerials_per90, percentile, comparison_group_size FROM football.player_metrics WHERE comp = 'ita' AND metric = 'aerials_per90' AND position_group IN ('AM', 'CM', 'DM') ORDER BY value DESC LIMIT 8
```

Beklenen (referans):
  - Morten Thorsby | Genoa / Cremonese | 5.773126266036462 | 1481
  - Cesare Casadei | Torino | 4.315068493150685 | 2190
  - Bryan Cristante | Roma | 3.0215827338129495 | 3336
  - Nahuel Estévez | Parma Calcio 1913 | 2.36259228876128 | 1219
  - Ruben Loftus-Cheek | AC Milan | 2.1796875 | 1280

Gelen (model):
  - Omri Gandelman | Lecce | 10.738636363636363 | 99.18032786885246 | 61
  - Morten Thorsby | Genoa / Cremonese | 10.573936529372046 | 99.39024390243902 | 82
  - Cesare Casadei | Torino | 6.205479452054794 | 98.17073170731707 | 82
  - Bryan Cristante | Roma | 5.66546762589928 | 96.95121951219512 | 82
  - Giovanni Fabbian | Bologna / Fiorentina | 4.520865533230294 | 94.26229508196721 | 61

#### `rates-04` (rates)

Soru: Which 10 Premier League players have the highest npxG per shot?

Neden: missing required column(s): minutes_played; row 1, column 4: expected Decimal('1232'), got 99.2063492063492

```sql
SELECT player, teams, value AS npxg_per_shot, percentile, comparison_group_size FROM football.player_metrics WHERE metric = 'npxg_per_shot' AND comp = 'eng' ORDER BY value DESC LIMIT 10
```

Beklenen (referans):
  - Joël Veltman | Brighton | 0.360592745244503 | 1232
  - Tomás Soucek | West Ham | 0.2796384235844016 | 2479
  - Axel Disasi | West Ham | 0.25859166868031025 | 1382
  - Morato | Nottingham Forest | 0.2542281962931156 | 1532
  - Santiago Bueno | Wolves | 0.24678540416061878 | 2850

Gelen (model):
  - Joël Veltman | Brighton | 0.360592745244503 | 99.2063492063492 | 63
  - Tomás Soucek | West Ham | 0.2796384235844016 | 98.52941176470588 | 34
  - Axel Disasi | West Ham | 0.25859166868031025 | 99.28571428571429 | 70
  - Morato | Nottingham Forest | 0.2542281962931156 | 97.85714285714286 | 70
  - Santiago Bueno | Wolves | 0.24678540416061878 | 96.42857142857143 | 70

#### `rates-05` (rates)

Soru: La Liga'da 90 dakikada en çok ilerletici pas atan 10 oyuncu

Neden: row 1, column 4: expected Decimal('2500'), got 98.9795918367347

```sql
SELECT player, teams, value AS progressive_passes_per90, percentile, comparison_group_size, minutes_played, matches FROM football.player_metrics WHERE metric = 'progressive_passes_per90' AND comp = 'esp' ORDER BY value DESC LIMIT 10
```

Beklenen (referans):
  - Lamine Yamal | Barcelona | 5.904000000000001 | 2500
  - Iago Aspas | Celta Vigo | 5.7975460122699385 | 1304
  - Óscar Mingueza | Celta Vigo | 5.420689655172414 | 2175
  - Álex Baena | Atletico | 5.156526875369167 | 1693
  - Pedri | Barcelona | 4.791756118505797 | 2329

Gelen (model):
  - Lamine Yamal | Barcelona | 5.904000000000001 | 98.9795918367347 | 49 | 2500 | 28
  - Iago Aspas | Celta Vigo | 5.7975460122699385 | 99.10714285714286 | 56 | 1304 | 32
  - Óscar Mingueza | Celta Vigo | 5.420689655172414 | 99.27536231884058 | 69 | 2175 | 34
  - Álex Baena | Atletico | 5.156526875369167 | 98.95833333333333 | 48 | 1693 | 27
  - Pedri | Barcelona | 4.791756118505797 | 98.14814814814815 | 27 | 2329 | 29

#### `rates-06` (rates)

Soru: Serie A'da dribling başarı yüzdesi en yüksek 8 kanat oyuncusu

Neden: missing required column(s): minutes_played; row 1, column 4: expected Decimal('1712'), got 94.6078431372549

```sql
SELECT player, teams, value AS dribble_pct, percentile, comparison_group_size FROM football.player_metrics WHERE metric = 'dribble_pct' AND comp = 'ita' AND position_group = 'W' ORDER BY value DESC LIMIT 8
```

Beklenen (referans):
  - Mërgim Vojvoda | Como | 48.148148148148145 | 1712
  - Jonathan Rowe | Bologna | 45.370370370370374 | 1711
  - Martin Baturina | Como | 41.07142857142857 | 1719
  - Riccardo Orsolini | Bologna | 38.55421686746988 | 2294
  - Santiago Pierotti | Lecce | 35.13513513513514 | 2756

Gelen (model):
  - Mërgim Vojvoda | Como | 48.148148148148145 | 94.6078431372549 | 102
  - Jonathan Rowe | Bologna | 45.370370370370374 | 86.76470588235294 | 102
  - Martin Baturina | Como | 41.07142857142857 | 77.94117647058823 | 102
  - Riccardo Orsolini | Bologna | 38.55421686746988 | 59.31372549019608 | 102
  - Santiago Pierotti | Lecce | 35.13513513513514 | 39.21568627450981 | 102

#### `percentiles-04` (percentiles)

Soru: La Liga stoperleri arasında top kaybı metriğinde en iyi 10 oyuncu

Neden: row 1, column 1: expected 'Duje Caleta-Car', got 'Marcão'

```sql
SELECT player, teams, value AS dispossessed_per90, percentile, comparison_group_size FROM football.player_metrics WHERE metric = 'dispossessed_per90' AND comp = 'esp' AND position_group = 'CB' ORDER BY value ASC LIMIT 10
```

Beklenen (referans):
  - Duje Caleta-Car | Real Sociedad | 0.07531380753138076 | 99.30555555555556 | 72
  - Yoel Lago | Celta Vigo | 0.0862895493767977 | 97.91666666666667 | 72
  - Domingos Duarte | Getafe | 0.11097410604192355 | 96.52777777777777 | 72
  - Dani Calvo | Real Oviedo | 0.20122973728339855 | 95.13888888888889 | 72
  - Antonio Rüdiger | Real Madrid | 0.2212661339889367 | 93.75 | 72

Gelen (model):
  - Marcão | Sevilla | 0.0 | 96.52777777777777 | 72
  - David López | Mallorca | 0.0 | 96.52777777777777 | 72
  - Facundo Garcés | Deportivo Alaves | 0.0 | 96.52777777777777 | 72
  - Unai Elgezabal | Levante | 0.0 | 96.52777777777777 | 72
  - Rafa Marín | Villarreal | 0.0 | 96.52777777777777 | 72

#### `transfers-01` (transfers)

Soru: Sezon içinde kulüp değiştiren oyuncular arasında toplam golü en yüksek 10 oyuncu

Neden: missing required column(s): clubs; column count: expected at least 5, got 3

```sql
SELECT player, teams, goals FROM football.player_season WHERE clubs > 1 ORDER BY goals DESC LIMIT 10
```

Beklenen (referans):
  - Antoine Semenyo | Bournemouth / Man City | 2 | 17 | 3546
  - Karl Etta Eyong | Levante / Villarreal | 2 | 7 | 1888
  - Eberechi Eze | Arsenal / Crystal Palace | 2 | 7 | 2110
  - M'Bala Nzola | Pisa / Sassuolo | 2 | 4 | 1673
  - Walid Cheddira | Lecce / Sassuolo | 2 | 4 | 1379

Gelen (model):
  - Antoine Semenyo | Bournemouth / Man City | 17
  - Karl Etta Eyong | Levante / Villarreal | 7
  - Eberechi Eze | Arsenal / Crystal Palace | 7
  - M'Bala Nzola | Pisa / Sassuolo | 4
  - Walid Cheddira | Lecce / Sassuolo | 4

#### `transfers-02` (transfers)

Soru: Kulüp değiştiren oyuncuların her kulüpteki dakikaları nedir?

Neden: column count: expected at least 4, got 3

```sql
SELECT player, team, minutes_played FROM football.player_season_club WHERE player_id IN (SELECT player_id FROM football.player_season_club GROUP BY player_id HAVING COUNT(DISTINCT team_id) > 1) ORDER BY player, minutes_played DESC LIMIT 200
```

Beklenen (referans):
  - Adama Traoré | Fulham | 376 | 15
  - Adama Traoré | West Ham | 180 | 9
  - Ademola Lookman | Atalanta | 852 | 12
  - Ademola Lookman | Atletico | 672 | 12
  - Adrià Pedrosa | Elche | 1245 | 26

Gelen (model):
  - Adama Traoré | Fulham | 376
  - Adama Traoré | West Ham | 180
  - Ademola Lookman | Atalanta | 852
  - Ademola Lookman | Atletico | 672
  - Adrià Pedrosa | Elche | 1245

#### `transfers-04` (transfers)

Soru: Kulüp değiştirenler arasında toplam asisti en yüksek 5 oyuncu

Neden: missing required column(s): clubs; column count: expected at least 5, got 3

```sql
SELECT player, teams, assists FROM football.player_season WHERE clubs > 1 ORDER BY assists DESC LIMIT 5
```

Beklenen (referans):
  - Giovane | Verona / Napoli | 2 | 5 | 2011
  - Hans Nicolussi Caviglia | Parma Calcio 1913 / Fiorentina | 2 | 4 | 1583
  - Antoine Semenyo | Bournemouth / Man City | 2 | 4 | 3546
  - Karl Etta Eyong | Levante / Villarreal | 2 | 4 | 1888
  - Emil Holm | Bologna / Juventus | 2 | 4 | 974

Gelen (model):
  - Giovane | Verona / Napoli | 5
  - Hans Nicolussi Caviglia | Parma Calcio 1913 / Fiorentina | 4
  - Antoine Semenyo | Bournemouth / Man City | 4
  - Karl Etta Eyong | Levante / Villarreal | 4
  - Emil Holm | Bologna / Juventus | 4

#### `match_detail-01` (match_detail)

Soru: Premier League'de en çok gol atılan 5 maç hangileri?

Neden: column count: expected at least 6, got 4

```sql
SELECT home_team, away_team, date, (home_score + away_score) AS total_goals FROM football.matches WHERE comp = 'eng' ORDER BY total_goals DESC LIMIT 5
```

Beklenen (referans):
  - 2025-12-02 | Fulham | Man City | 4 | 5 | 9
  - 2025-12-15 | Man Utd | Bournemouth | 4 | 4 | 8
  - 2025-12-03 | Brighton | Aston Villa | 3 | 4 | 7
  - 2026-01-07 | Newcastle | Leeds | 4 | 3 | 7
  - 2026-02-28 | Burnley | Brentford | 3 | 4 | 7

Gelen (model):
  - Fulham | Man City | 2025-12-02 | 9
  - Man Utd | Bournemouth | 2025-12-15 | 8
  - Newcastle | Leeds | 2026-01-07 | 7
  - Brighton | Aston Villa | 2025-12-03 | 7
  - Burnley | Brentford | 2026-02-28 | 7

#### `match_detail-02` (match_detail)

Soru: Which 5 La Liga matches had the highest attendance?

Neden: row 1, column 1: expected datetime.date(2025, 10, 26), got 'Real Madrid'

```sql
SELECT home_team, away_team, attendance, date FROM football.matches WHERE comp = 'esp' ORDER BY attendance DESC LIMIT 5
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

Soru: Serie A'da en çok şut çekilen 5 maç

Neden: column "home_team" does not exist
LINE 1: SELECT match_id, home_team, away_team, SUM(shots) AS total_s...
                         ^

```sql
SELECT match_id, home_team, away_team, SUM(shots) AS total_shots FROM football.player_match_stats WHERE comp = 'ita' GROUP BY match_id, home_team, away_team ORDER BY total_shots DESC LIMIT 5
```

Beklenen (referans):
  - 2026-02-08 | Juventus | Lazio | 43
  - 2026-01-23 | Inter | Pisa | 42
  - 2026-02-09 | Atalanta | Cremonese | 41
  - 2026-05-24 | AC Milan | Cagliari | 41
  - 2025-12-01 | Bologna | Cremonese | 39

Gelen (model):
_(satır yok)_

#### `match_detail-04` (match_detail)

Soru: Premier League'de xG'si en yüksek 10 şut kime ait?

Neden: column "player" does not exist
LINE 1: SELECT player, team_id, xg, match_id, minute FROM football.s...
               ^
HINT:  Perhaps you meant to reference the column "shots.player_id".

```sql
SELECT player, team_id, xg, match_id, minute FROM football.shots WHERE comp = 'eng' ORDER BY xg DESC LIMIT 10
```

Beklenen (referans):
  - David Brooks | 0.951172 | True | Left Foot
  - Casemiro | 0.935379 | False | Left Foot
  - Tomás Soucek | 0.934048 | True | Right Foot
  - Callum Wilson | 0.91099 | True | Left Foot
  - Kyle Walker-Peters | 0.909612 | True | Right Foot

Gelen (model):
_(satır yok)_

#### `match_detail-05` (match_detail)

Soru: En uzun 10 tamamlanmış pas kime ait?

Neden: row 1, column 3: expected 'esp', got 1914166

```sql
SELECT p.player, ps.pass_length, ps.match_id, ps.minute FROM football.passes AS ps JOIN football.players AS p ON ps.player_id = p.player_id WHERE ps.is_completed = TRUE ORDER BY ps.pass_length DESC LIMIT 10
```

Beklenen (referans):
  - Marko Dmitrovic | 104.3 | esp
  - Augusto Batalla | 100.0 | esp
  - Adrian Semper | 98.2 | ita
  - Augusto Batalla | 94.9 | esp
  - Augusto Batalla | 94.2 | esp

Gelen (model):
  - Marko Dmitrovic | 104.3 | 1914166 | 30
  - Augusto Batalla | 100.0 | 1914059 | 70
  - Adrian Semper | 98.2 | 1901099 | 94
  - Augusto Batalla | 94.9 | 1913987 | 17
  - Augusto Batalla | 94.2 | 1914231 | 46
