# Text-to-SQL değerlendirmesi

Üretildi: 2026-11-17 19:03 UTC

Hakem sonuç kümesi eşitliğidir: model referanstan farklı SQL yazdıysa ve satırlar aynıysa cevap doğrudur. Yüzdelik ve grup büyüklüğü gibi zorunlu kolonlar ile yasak yapılar ayrı boyutlarda puanlanır.

## gemini/gemini-3.6-flash

- Koşu: `20261117T185926Z-gemini-3.6-flash` (121 sn)
- **Doğruluk: %80.6** (29/36 puanlanabilir soru, toplam 40)
- Eşik %70.0: geçti
- Paydadan düşenler: 4 (cevaplanamaz 4, altyapı hatası 0, bozuk referans 0)
- Token: girdi 283,304, çıktı 4,975 (sağlayıcının kendi sayımı) · **$0.2311** (2026-11-17 fiyatlarıyla)

> Sağlayıcı şu parametreleri reddetti: temperature. Koşular bu yüzden tam deterministik değil; başka bir koşuyla karşılaştırırken bunu hesaba kat.

### Kategoriler

| Kategori | n | doğru | çalıştı | zorunlu kolon | yasak yapı |
| --- | --- | --- | --- | --- | --- |
| totals | 5 | %100.0 | 5/5 | 5/5 | 5/5 |
| rates | 6 | %83.3 | 6/6 | 2/6 | 6/6 |
| percentiles | 5 | %80.0 | 5/5 | 5/5 | 5/5 |
| transfers | 5 | %80.0 | 5/5 | 3/5 | 4/5 |
| teams | 5 | %80.0 | 5/5 | 5/5 | 5/5 |
| match_detail | 5 | %40.0 | 5/5 | 5/5 | 5/5 |
| filters | 5 | %100.0 | 5/5 | 5/5 | 5/5 |
| unanswerable | 4 | n/a | 4/4 | 4/4 | 4/4 |

### Onarım döngüsü

- İlk denemede geçen: 40
- Onarımla düzelen: 0
- Onarımdan sonra da reddedilen: 0

### Soru soru inceleme

#### `rates-02` (rates)

Soru: Premier League'de pas isabeti en yüksek 10 stoper

Neden: missing required column(s): minutes_played

```sql
SELECT player, teams, value AS pass_pct, percentile, comparison_group_size FROM football.player_metrics WHERE comp = 'eng' AND position_group = 'CB' AND metric = 'pass_pct' ORDER BY value DESC LIMIT 10
```

Beklenen (referans):
  - Ezri Konsa | 95.24940617577197
  - Victor Lindelöf | 94.20970266040689
  - Trevoh Chalobah | 92.88194444444444
  - Rúben Dias | 92.69535673839184
  - William Saliba | 92.6852288815479

Gelen (model):
  - Ezri Konsa | Aston Villa | 95.24940617577197 | 99.28571428571429 | 70
  - Victor Lindelöf | Aston Villa | 94.20970266040689 | 97.85714285714286 | 70
  - Trevoh Chalobah | Chelsea | 92.88194444444444 | 96.42857142857143 | 70
  - Rúben Dias | Man City | 92.69535673839184 | 95.0 | 70
  - William Saliba | Arsenal | 92.6852288815479 | 93.57142857142857 | 70

#### `rates-03` (rates)

Soru: Serie A'da 90 dakikada en çok hava topu kazanan 8 orta saha

Neden: missing required column(s): minutes_played; row 1, column 2: 5.773126266036462 is not in the candidate row

```sql
SELECT player, teams, value AS aerials_won_per90, percentile, comparison_group_size FROM football.player_metrics WHERE metric = 'aerials_per90' AND comp = 'ita' AND position_group = 'CM' ORDER BY value DESC LIMIT 8
```

Beklenen (referans):
  - Morten Thorsby | 5.773126266036462
  - Cesare Casadei | 4.315068493150685
  - Bryan Cristante | 3.0215827338129495
  - Nahuel Estévez | 2.36259228876128
  - Ruben Loftus-Cheek | 2.1796875

Gelen (model):
  - Morten Thorsby | Genoa / Cremonese | 10.573936529372046 | 99.39024390243902 | 82
  - Cesare Casadei | Torino | 6.205479452054794 | 98.17073170731707 | 82
  - Bryan Cristante | Roma | 5.66546762589928 | 96.95121951219512 | 82
  - Cheikh Niasse | Verona | 4.406779661016949 | 95.73170731707317 | 82
  - Nahuel Estévez | Parma Calcio 1913 | 4.20836751435603 | 94.51219512195122 | 82

#### `rates-04` (rates)

Soru: Which 10 Premier League players have the highest npxG per shot?

Neden: missing required column(s): minutes_played

```sql
SELECT player, teams, value AS npxg_per_shot, percentile, comparison_group_size FROM football.player_metrics WHERE metric = 'npxg_per_shot' AND comp = 'eng' ORDER BY value DESC LIMIT 10
```

Beklenen (referans):
  - Joël Veltman | 0.360592745244503
  - Tomás Soucek | 0.2796384235844016
  - Axel Disasi | 0.25859166868031025
  - Morato | 0.2542281962931156
  - Santiago Bueno | 0.24678540416061878

Gelen (model):
  - Joël Veltman | Brighton | 0.360592745244503 | 99.2063492063492 | 63
  - Tomás Soucek | West Ham | 0.2796384235844016 | 98.52941176470588 | 34
  - Axel Disasi | West Ham | 0.25859166868031025 | 99.28571428571429 | 70
  - Morato | Nottingham Forest | 0.2542281962931156 | 97.85714285714286 | 70
  - Santiago Bueno | Wolves | 0.24678540416061878 | 96.42857142857143 | 70

#### `rates-06` (rates)

Soru: Serie A'da dribling başarı yüzdesi en yüksek 8 kanat oyuncusu

Neden: missing required column(s): minutes_played

```sql
SELECT player, teams, value AS dribble_pct, percentile, comparison_group_size FROM football.player_metrics WHERE metric = 'dribble_pct' AND comp = 'ita' AND position_group = 'W' ORDER BY value DESC LIMIT 8
```

Beklenen (referans):
  - Mërgim Vojvoda | 48.148148148148145
  - Jonathan Rowe | 45.370370370370374
  - Martin Baturina | 41.07142857142857
  - Riccardo Orsolini | 38.55421686746988
  - Santiago Pierotti | 35.13513513513514

Gelen (model):
  - Mërgim Vojvoda | Como | 48.148148148148145 | 94.6078431372549 | 102
  - Jonathan Rowe | Bologna | 45.370370370370374 | 86.76470588235294 | 102
  - Martin Baturina | Como | 41.07142857142857 | 77.94117647058823 | 102
  - Riccardo Orsolini | Bologna | 38.55421686746988 | 59.31372549019608 | 102
  - Santiago Pierotti | Lecce | 35.13513513513514 | 39.21568627450981 | 102

#### `percentiles-04` (percentiles)

Soru: La Liga stoperleri arasında top kaybı metriğinde en iyi 10 oyuncu

Neden: row 1, column 1: 'Duje Caleta-Car' is not in the candidate row

```sql
SELECT player, teams, value AS dispossessed_per90, percentile, comparison_group_size FROM football.player_metrics WHERE comp = 'esp' AND position_group = 'CB' AND metric = 'dispossessed_per90' ORDER BY percentile DESC LIMIT 10
```

Beklenen (referans):
  - Duje Caleta-Car | 99.30555555555556
  - Yoel Lago | 97.91666666666667
  - Domingos Duarte | 96.52777777777777
  - Dani Calvo | 95.13888888888889
  - Antonio Rüdiger | 93.75

Gelen (model):
  - Marcão | Sevilla | 0.0 | 96.52777777777777 | 72
  - David López | Mallorca | 0.0 | 96.52777777777777 | 72
  - Facundo Garcés | Deportivo Alaves | 0.0 | 96.52777777777777 | 72
  - Unai Elgezabal | Levante | 0.0 | 96.52777777777777 | 72
  - Rafa Marín | Villarreal | 0.0 | 96.52777777777777 | 72

#### `transfers-01` (transfers)

Soru: Sezon içinde kulüp değiştiren oyuncular arasında toplam golü en yüksek 10 oyuncu

Neden: missing required column(s): clubs

```sql
SELECT player, teams, goals, minutes_played, matches FROM football.player_season WHERE clubs > 1 ORDER BY goals DESC LIMIT 10
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

#### `transfers-02` (transfers)

Soru: Kulüp değiştiren oyuncuların her kulüpteki dakikaları nedir?

Neden: forbidden structure(s): player_season; row count: expected 144, got 96

```sql
SELECT player, team, minutes_played, matches, goals, assists FROM football.player_season_club WHERE player_id IN (SELECT player_id FROM football.player_season WHERE clubs > 1) ORDER BY player, minutes_played DESC LIMIT 200
```

Beklenen (referans):
  - Adama Traoré | Fulham | 376
  - Adama Traoré | West Ham | 180
  - Ademola Lookman | Atalanta | 852
  - Ademola Lookman | Atletico | 672
  - Adrià Pedrosa | Elche | 1245

Gelen (model):
  - Adama Traoré | Fulham | 376 | 15 | 0 | 0
  - Adama Traoré | West Ham | 180 | 9 | 0 | 0
  - Adrià Pedrosa | Elche | 1245 | 26 | 1 | 1
  - Adrià Pedrosa | Sevilla | 13 | 1 | 0 | 0
  - Alfon González | Villarreal | 385 | 10 | 1 | 0

#### `transfers-04` (transfers)

Soru: Kulüp değiştirenler arasında toplam asisti en yüksek 5 oyuncu

Neden: missing required column(s): clubs

```sql
SELECT player, teams, assists, minutes_played, matches FROM football.player_season WHERE clubs > 1 ORDER BY assists DESC LIMIT 5
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

#### `match_detail-01` (match_detail)

Soru: Premier League'de en çok gol atılan 5 maç hangileri?

Neden: row 1, column 2: 'Fulham' is not in the candidate row

```sql
SELECT home_team, away_team, home_score + away_score AS total_goals, date, match_id FROM football.matches WHERE comp = 'eng' ORDER BY total_goals DESC LIMIT 5
```

Beklenen (referans):
  - 2025-12-02 | Fulham | Man City | 9
  - 2025-12-15 | Man Utd | Bournemouth | 8
  - 2025-12-03 | Brighton | Aston Villa | 7
  - 2026-01-07 | Newcastle | Leeds | 7
  - 2026-02-28 | Burnley | Brentford | 7

Gelen (model):
  - Fulham | Man City | 9 | 2025-12-02 | 1903251
  - Man Utd | Bournemouth | 8 | 2025-12-15 | 1903490
  - Newcastle | Leeds | 7 | 2026-01-07 | 1903285
  - Brighton | Aston Villa | 7 | 2025-12-03 | 1903249
  - Burnley | Brentford | 7 | 2026-02-28 | 1903402

#### `match_detail-03` (match_detail)

Soru: Serie A'da en çok şut çekilen 5 maç

Neden: row 1, column 1: datetime.date(2026, 2, 8) is not in the candidate row

```sql
SELECT m.match_id, m.home_team, m.away_team, m.home_score, m.away_score, m.n_shots FROM football.matches AS m WHERE m.comp = 'ita' ORDER BY m.n_shots DESC LIMIT 5
```

Beklenen (referans):
  - 2026-02-08 | Juventus | Lazio | 43
  - 2026-01-23 | Inter | Pisa | 42
  - 2026-02-09 | Atalanta | Cremonese | 41
  - 2026-05-24 | AC Milan | Cagliari | 41
  - 2025-12-01 | Bologna | Cremonese | 39

Gelen (model):
  - 1901164 | Juventus | Lazio | 2 | 2 | 43
  - 1901122 | Inter | Pisa | 6 | 2 | 42
  - 1901436 | AC Milan | Cagliari | 1 | 2 | 41
  - 1901158 | Atalanta | Cremonese | 2 | 1 | 41
  - 1901336 | AC Milan | Genoa | 1 | 1 | 39

#### `match_detail-04` (match_detail)

Soru: Premier League'de xG'si en yüksek 10 şut kime ait?

Neden: row 1, column 1: 'David Brooks' is not in the candidate row

```sql
SELECT s.xg, p.player, t.team, m.date, m.home_team, m.away_team FROM football.shots AS s JOIN football.players AS p ON s.player_id = p.player_id JOIN football.teams AS t ON s.team_id = t.team_id JOIN football.matches AS m ON s.match_id = m.match_id WHERE s.comp = 'eng' ORDER BY s.xg DESC LIMIT 10
```

Beklenen (referans):
  - David Brooks | 0.951172
  - Casemiro | 0.935379
  - Tomás Soucek | 0.934048
  - Callum Wilson | 0.91099
  - Kyle Walker-Peters | 0.909612

Gelen (model):
  - None | Brajan Gruda | Brighton | 2025-10-05 | Wolves | Brighton
  - None | Bart Verbruggen | Brighton | 2025-10-05 | Wolves | Brighton
  - None | Gabriel Gudmundsson | Leeds | 2025-09-13 | Fulham | Leeds
  - None | Jan Paul van Hecke | Brighton | 2025-09-20 | Brighton | Tottenham
  - None | Ethan Pinnock | Brentford | 2025-09-20 | Fulham | Brentford

## gemini/gemini-3.1-flash-lite

- Koşu: `20261117T190127Z-gemini-3.1-flash-lite` (143 sn)
- **Doğruluk: %80.6** (29/36 puanlanabilir soru, toplam 40)
- Eşik %70.0: geçti
- Paydadan düşenler: 4 (cevaplanamaz 4, altyapı hatası 0, bozuk referans 0)
- Token: girdi 283,304, çıktı 14,265 (sağlayıcının kendi sayımı) · **$0.1207** (2026-11-17 fiyatlarıyla)

### Kategoriler

| Kategori | n | doğru | çalıştı | zorunlu kolon | yasak yapı |
| --- | --- | --- | --- | --- | --- |
| totals | 5 | %80.0 | 5/5 | 5/5 | 5/5 |
| rates | 6 | %83.3 | 6/6 | 2/6 | 6/6 |
| percentiles | 5 | %80.0 | 5/5 | 5/5 | 5/5 |
| transfers | 5 | %100.0 | 5/5 | 3/5 | 5/5 |
| teams | 5 | %100.0 | 5/5 | 5/5 | 5/5 |
| match_detail | 5 | %20.0 | 3/5 | 5/5 | 5/5 |
| filters | 5 | %100.0 | 5/5 | 5/5 | 5/5 |
| unanswerable | 4 | n/a | 4/4 | 4/4 | 4/4 |

### Onarım döngüsü

- İlk denemede geçen: 38
- Onarımla düzelen: 0
- Onarımdan sonra da reddedilen: 2

### Soru soru inceleme

#### `totals-04` (totals)

Soru: Serie A'da en fazla top kazanımı yapan 5 oyuncu

Neden: row 1, column 1: 'Ylber Ramadani' is not in the candidate row

```sql
SELECT player, teams, value AS ball_recoveries_per90, percentile, comparison_group_size FROM football.player_metrics WHERE metric = 'ball_recoveries_per90' AND comp = 'ita' ORDER BY value DESC LIMIT 5
```

Beklenen (referans):
  - Ylber Ramadani | 211
  - Luka Modric | 188
  - Bryan Cristante | 186
  - Nikola Vlasic | 181
  - Manuel Locatelli | 180

Gelen (model):
  - Ebenezer Akinsanmiro | Pisa | 6.188946015424165 | 99.39024390243902 | 82
  - Ibrahim Sulemana | Cagliari / Bologna | 5.795121951219512 | 98.17073170731707 | 82
  - Nicolò Barella | Inter | 5.622882950696274 | 96.95121951219512 | 82
  - Luka Modric | AC Milan | 5.545722713864307 | 95.73170731707317 | 82
  - Ylber Ramadani | Lecce | 5.510737086477075 | 87.82051282051282 | 78

#### `rates-02` (rates)

Soru: Premier League'de pas isabeti en yüksek 10 stoper

Neden: missing required column(s): minutes_played

```sql
SELECT player, teams, value AS pass_pct, percentile, comparison_group_size FROM football.player_metrics WHERE metric = 'pass_pct' AND comp = 'eng' AND position_group = 'CB' ORDER BY value DESC LIMIT 10
```

Beklenen (referans):
  - Ezri Konsa | 95.24940617577197
  - Victor Lindelöf | 94.20970266040689
  - Trevoh Chalobah | 92.88194444444444
  - Rúben Dias | 92.69535673839184
  - William Saliba | 92.6852288815479

Gelen (model):
  - Ezri Konsa | Aston Villa | 95.24940617577197 | 99.28571428571429 | 70
  - Victor Lindelöf | Aston Villa | 94.20970266040689 | 97.85714285714286 | 70
  - Trevoh Chalobah | Chelsea | 92.88194444444444 | 96.42857142857143 | 70
  - Rúben Dias | Man City | 92.69535673839184 | 95.0 | 70
  - William Saliba | Arsenal | 92.6852288815479 | 93.57142857142857 | 70

#### `rates-03` (rates)

Soru: Serie A'da 90 dakikada en çok hava topu kazanan 8 orta saha

Neden: missing required column(s): minutes_played; row 1, column 1: 'Morten Thorsby' is not in the candidate row

```sql
SELECT player, teams, value AS aerials_per90, percentile, comparison_group_size FROM football.player_metrics WHERE comp = 'ita' AND metric = 'aerials_per90' AND position_group IN ('AM', 'CM', 'DM') ORDER BY value DESC LIMIT 8
```

Beklenen (referans):
  - Morten Thorsby | 5.773126266036462
  - Cesare Casadei | 4.315068493150685
  - Bryan Cristante | 3.0215827338129495
  - Nahuel Estévez | 2.36259228876128
  - Ruben Loftus-Cheek | 2.1796875

Gelen (model):
  - Omri Gandelman | Lecce | 10.738636363636363 | 99.18032786885246 | 61
  - Morten Thorsby | Genoa / Cremonese | 10.573936529372046 | 99.39024390243902 | 82
  - Cesare Casadei | Torino | 6.205479452054794 | 98.17073170731707 | 82
  - Bryan Cristante | Roma | 5.66546762589928 | 96.95121951219512 | 82
  - Giovanni Fabbian | Bologna / Fiorentina | 4.520865533230294 | 94.26229508196721 | 61

#### `rates-04` (rates)

Soru: Which 10 Premier League players have the highest npxG per shot?

Neden: missing required column(s): minutes_played

```sql
SELECT player, teams, value AS npxg_per_shot, percentile, comparison_group_size FROM football.player_metrics WHERE metric = 'npxg_per_shot' AND comp = 'eng' ORDER BY value DESC LIMIT 10
```

Beklenen (referans):
  - Joël Veltman | 0.360592745244503
  - Tomás Soucek | 0.2796384235844016
  - Axel Disasi | 0.25859166868031025
  - Morato | 0.2542281962931156
  - Santiago Bueno | 0.24678540416061878

Gelen (model):
  - Joël Veltman | Brighton | 0.360592745244503 | 99.2063492063492 | 63
  - Tomás Soucek | West Ham | 0.2796384235844016 | 98.52941176470588 | 34
  - Axel Disasi | West Ham | 0.25859166868031025 | 99.28571428571429 | 70
  - Morato | Nottingham Forest | 0.2542281962931156 | 97.85714285714286 | 70
  - Santiago Bueno | Wolves | 0.24678540416061878 | 96.42857142857143 | 70

#### `rates-06` (rates)

Soru: Serie A'da dribling başarı yüzdesi en yüksek 8 kanat oyuncusu

Neden: missing required column(s): minutes_played

```sql
SELECT player, teams, value AS dribble_pct, percentile, comparison_group_size FROM football.player_metrics WHERE metric = 'dribble_pct' AND comp = 'ita' AND position_group = 'W' ORDER BY value DESC LIMIT 8
```

Beklenen (referans):
  - Mërgim Vojvoda | 48.148148148148145
  - Jonathan Rowe | 45.370370370370374
  - Martin Baturina | 41.07142857142857
  - Riccardo Orsolini | 38.55421686746988
  - Santiago Pierotti | 35.13513513513514

Gelen (model):
  - Mërgim Vojvoda | Como | 48.148148148148145 | 94.6078431372549 | 102
  - Jonathan Rowe | Bologna | 45.370370370370374 | 86.76470588235294 | 102
  - Martin Baturina | Como | 41.07142857142857 | 77.94117647058823 | 102
  - Riccardo Orsolini | Bologna | 38.55421686746988 | 59.31372549019608 | 102
  - Santiago Pierotti | Lecce | 35.13513513513514 | 39.21568627450981 | 102

#### `percentiles-04` (percentiles)

Soru: La Liga stoperleri arasında top kaybı metriğinde en iyi 10 oyuncu

Neden: row 1, column 1: 'Duje Caleta-Car' is not in the candidate row

```sql
SELECT player, teams, value AS dispossessed_per90, percentile, comparison_group_size FROM football.player_metrics WHERE metric = 'dispossessed_per90' AND comp = 'esp' AND position_group = 'CB' ORDER BY value ASC LIMIT 10
```

Beklenen (referans):
  - Duje Caleta-Car | 99.30555555555556
  - Yoel Lago | 97.91666666666667
  - Domingos Duarte | 96.52777777777777
  - Dani Calvo | 95.13888888888889
  - Antonio Rüdiger | 93.75

Gelen (model):
  - Marcão | Sevilla | 0.0 | 96.52777777777777 | 72
  - David López | Mallorca | 0.0 | 96.52777777777777 | 72
  - Facundo Garcés | Deportivo Alaves | 0.0 | 96.52777777777777 | 72
  - Unai Elgezabal | Levante | 0.0 | 96.52777777777777 | 72
  - Rafa Marín | Villarreal | 0.0 | 96.52777777777777 | 72

#### `transfers-01` (transfers)

Soru: Sezon içinde kulüp değiştiren oyuncular arasında toplam golü en yüksek 10 oyuncu

Neden: missing required column(s): clubs

```sql
SELECT player, teams, goals FROM football.player_season WHERE clubs > 1 ORDER BY goals DESC LIMIT 10
```

Beklenen (referans):
  - Antoine Semenyo | 17
  - Karl Etta Eyong | 7
  - Eberechi Eze | 7
  - M'Bala Nzola | 4
  - Walid Cheddira | 4

Gelen (model):
  - Antoine Semenyo | Bournemouth / Man City | 17
  - Karl Etta Eyong | Levante / Villarreal | 7
  - Eberechi Eze | Arsenal / Crystal Palace | 7
  - M'Bala Nzola | Pisa / Sassuolo | 4
  - Walid Cheddira | Lecce / Sassuolo | 4

#### `transfers-04` (transfers)

Soru: Kulüp değiştirenler arasında toplam asisti en yüksek 5 oyuncu

Neden: missing required column(s): clubs

```sql
SELECT player, teams, assists FROM football.player_season WHERE clubs > 1 ORDER BY assists DESC LIMIT 5
```

Beklenen (referans):
  - Giovane | 5
  - Hans Nicolussi Caviglia | 4
  - Antoine Semenyo | 4
  - Karl Etta Eyong | 4
  - Emil Holm | 4

Gelen (model):
  - Giovane | Verona / Napoli | 5
  - Hans Nicolussi Caviglia | Parma Calcio 1913 / Fiorentina | 4
  - Antoine Semenyo | Bournemouth / Man City | 4
  - Karl Etta Eyong | Levante / Villarreal | 4
  - Emil Holm | Bologna / Juventus | 4

#### `match_detail-01` (match_detail)

Soru: Premier League'de en çok gol atılan 5 maç hangileri?

Neden: row 1, column 2: 'Fulham' is not in the candidate row

```sql
SELECT home_team, away_team, date, (home_score + away_score) AS total_goals FROM football.matches WHERE comp = 'eng' ORDER BY total_goals DESC LIMIT 5
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
  - Newcastle | Leeds | 2026-01-07 | 7
  - Brighton | Aston Villa | 2025-12-03 | 7
  - Burnley | Brentford | 2026-02-28 | 7

#### `match_detail-02` (match_detail)

Soru: Which 5 La Liga matches had the highest attendance?

Neden: row 1, column 2: 'Real Madrid' is not in the candidate row

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
  - David Brooks | 0.951172
  - Casemiro | 0.935379
  - Tomás Soucek | 0.934048
  - Callum Wilson | 0.91099
  - Kyle Walker-Peters | 0.909612

Gelen (model):
_(satır yok)_


## Modeller arası uyuşmazlık

Gün 5'in bulgusu: iki modelin ayrıldığı yer prompt'un belirsiz olduğu yerdir.

| Soru | Kategori | gemini/gemini-3.6-flash | gemini/gemini-3.1-flash-lite |
| --- | --- | --- | --- |
| `totals-04` | totals | doğru | yanlış |
| `transfers-02` | transfers | yanlış | doğru |
| `teams-02` | teams | yanlış | doğru |
| `match_detail-02` | match_detail | doğru | yanlış |
