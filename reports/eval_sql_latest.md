# Text-to-SQL değerlendirmesi

Üretildi: 2026-11-17 19:37 UTC

Hakem sonuç kümesi eşitliğidir: model referanstan farklı SQL yazdıysa ve satırlar aynıysa cevap doğrudur. Yüzdelik ve grup büyüklüğü gibi zorunlu kolonlar ile yasak yapılar ayrı boyutlarda puanlanır.

## gemini/gemini-3.8-flash

- Koşu: `20261117T192146Z-gemini-3.8-flash` (137 sn)
- **Doğruluk: %86.1** (31/36 puanlanabilir soru, toplam 40)
- Eşik %70.0: geçti
- Paydadan düşenler: 4 (cevaplanamaz 4, altyapı hatası 0, bozuk referans 0)
- Token: girdi 354,127, çıktı 2,493 (sağlayıcının kendi sayımı) · **$0.2749** (2026-11-17 fiyatlarıyla)

> Sağlayıcı şu parametreleri reddetti: temperature. Koşular bu yüzden tam deterministik değil; başka bir koşuyla karşılaştırırken bunu hesaba kat.

### Kategoriler

| Kategori | n | doğru | çalıştı | zorunlu kolon | yasak yapı |
| --- | --- | --- | --- | --- | --- |
| totals | 5 | %100.0 | 5/5 | 5/5 | 5/5 |
| rates | 6 | %100.0 | 6/6 | 4/6 | 6/6 |
| percentiles | 5 | %80.0 | 5/5 | 5/5 | 5/5 |
| transfers | 5 | %80.0 | 5/5 | 3/5 | 4/5 |
| teams | 5 | %80.0 | 5/5 | 5/5 | 5/5 |
| match_detail | 5 | %60.0 | 5/5 | 5/5 | 5/5 |
| filters | 5 | %100.0 | 5/5 | 5/5 | 5/5 |
| unanswerable | 4 | n/a | 4/4 | 4/4 | 4/4 |

### Onarım döngüsü

- İlk denemede geçen: 40
- Onarımla düzelen: 0
- Onarımdan sonra da reddedilen: 0

### Soru soru inceleme

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

#### `rates-06` (rates)

Soru: Serie A'da dribling başarı yüzdesi en yüksek 8 kanat oyuncusu

Neden: missing required column(s): minutes_played

```sql
SELECT player, teams, value AS dribble_pct, percentile, comparison_group_size FROM football.player_metrics WHERE comp = 'ita' AND position_group = 'W' AND metric = 'dribble_pct' ORDER BY value DESC LIMIT 8
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

#### `transfers-02` (transfers)

Soru: Kulüp değiştiren oyuncuların her kulüpteki dakikaları nedir?

Neden: forbidden structure(s): player_season; row count: expected 144, got 96

```sql
SELECT psc.player, psc.team, psc.minutes_played, psc.matches FROM football.player_season_club AS psc JOIN football.player_season AS ps ON psc.player_id = ps.player_id AND psc.comp = ps.comp AND psc.season = ps.season WHERE ps.clubs > 1 ORDER BY psc.player, psc.minutes_played DESC LIMIT 200
```

Beklenen (referans):
  - Adama Traoré | Fulham | 376
  - Adama Traoré | West Ham | 180
  - Ademola Lookman | Atalanta | 852
  - Ademola Lookman | Atletico | 672
  - Adrià Pedrosa | Elche | 1245

Gelen (model):
  - Adama Traoré | Fulham | 376 | 15
  - Adama Traoré | West Ham | 180 | 9
  - Adrià Pedrosa | Elche | 1245 | 26
  - Adrià Pedrosa | Sevilla | 13 | 1
  - Alfon González | Villarreal | 385 | 10

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

#### `match_detail-02` (match_detail)

Soru: Which 5 La Liga matches had the highest attendance?

Neden: row 1, column 2: 'Real Madrid' is not in the candidate row

```sql
SELECT home_team, away_team, date, attendance, venue FROM football.matches WHERE comp = 'esp' AND attendance IS NOT NULL ORDER BY attendance DESC LIMIT 5
```

Beklenen (referans):
  - 2025-10-26 | Real Madrid | Barcelona | 78107
  - 2026-03-22 | Real Madrid | Atletico | 77964
  - 2025-10-04 | Real Madrid | Villarreal | 75216
  - 2026-01-04 | Real Madrid | Real Betis | 75190
  - 2025-11-01 | Real Madrid | Valencia | 74796

Gelen (model):
  - Real Madrid | Barcelona | 2025-10-26 | 78107 | Santiago Bernabéu
  - Real Madrid | Atletico | 2026-03-22 | 77964 | Estadio Bernabéu
  - Real Madrid | Villarreal | 2025-10-04 | 75216 | Santiago Bernabéu
  - Real Madrid | Real Betis | 2026-01-04 | 75190 | Estadio Bernabéu
  - Real Madrid | Valencia | 2025-11-01 | 74796 | Santiago Bernabéu

#### `match_detail-04` (match_detail)

Soru: Premier League'de xG'si en yüksek 10 şut kime ait?

Neden: row 1, column 1: 'David Brooks' is not in the candidate row

```sql
SELECT p.player, t.team, s.xg, s.minute, s.result, s.is_goal FROM football.shots AS s LEFT JOIN football.players AS p ON s.player_id = p.player_id LEFT JOIN football.teams AS t ON s.team_id = t.team_id WHERE s.comp = 'eng' ORDER BY s.xg DESC LIMIT 10
```

Beklenen (referans):
  - David Brooks | 0.951172
  - Casemiro | 0.935379
  - Tomás Soucek | 0.934048
  - Callum Wilson | 0.91099
  - Kyle Walker-Peters | 0.909612

Gelen (model):
  - Brajan Gruda | Brighton | None | 24 | MissedShots | False
  - Bart Verbruggen | Brighton | None | 20 | Goal | True
  - Gabriel Gudmundsson | Leeds | None | 93 | Goal | True
  - Jan Paul van Hecke | Brighton | None | 81 | Goal | True
  - Ethan Pinnock | Brentford | None | 49 | Goal | True
