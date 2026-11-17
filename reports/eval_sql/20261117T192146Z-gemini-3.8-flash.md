# Text-to-SQL değerlendirmesi

Üretildi: 2026-11-17 19:22 UTC

Hakem sonuç kümesi eşitliğidir: model referanstan farklı SQL yazdıysa ve satırlar aynıysa cevap doğrudur. Yüzdelik ve grup büyüklüğü gibi zorunlu kolonlar ile yasak yapılar ayrı boyutlarda puanlanır.

## gemini/gemini-3.8-flash

- Koşu: `20261117T192146Z-gemini-3.8-flash` (27 sn)
- **Doğruluk: %85.7** (6/7 puanlanabilir soru, toplam 8)
- Eşik %70.0: geçti
- Paydadan düşenler: 1 (cevaplanamaz 1, altyapı hatası 0, bozuk referans 0)
- Token: girdi 56,663, çıktı 383 (sağlayıcının kendi sayımı) · **$0.0439** (2026-11-17 fiyatlarıyla)

> Sağlayıcı şu parametreleri reddetti: temperature. Koşular bu yüzden tam deterministik değil; başka bir koşuyla karşılaştırırken bunu hesaba kat.

### Kategoriler

| Kategori | n | doğru | çalıştı | zorunlu kolon | yasak yapı |
| --- | --- | --- | --- | --- | --- |
| totals | 1 | %100.0 | 1/1 | 1/1 | 1/1 |
| rates | 1 | %100.0 | 1/1 | 1/1 | 1/1 |
| percentiles | 1 | %100.0 | 1/1 | 1/1 | 1/1 |
| transfers | 1 | %100.0 | 1/1 | 0/1 | 1/1 |
| teams | 1 | %100.0 | 1/1 | 1/1 | 1/1 |
| match_detail | 1 | %0.0 | 1/1 | 1/1 | 1/1 |
| filters | 1 | %100.0 | 1/1 | 1/1 | 1/1 |
| unanswerable | 1 | n/a | 1/1 | 1/1 | 1/1 |

### Onarım döngüsü

- İlk denemede geçen: 8
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

#### `match_detail-01` (match_detail)

Soru: Premier League'de en çok gol atılan 5 maç hangileri?

Neden: row 3, column 1: expected datetime.date(2025, 12, 3), got datetime.date(2026, 1, 7)

```sql
SELECT match_id, date, home_team, away_team, home_score, away_score, (home_score + away_score) AS total_goals FROM football.matches WHERE comp = 'eng' ORDER BY total_goals DESC LIMIT 5
```

Beklenen (referans):
  - 2025-12-02 | Fulham | Man City | 9
  - 2025-12-15 | Man Utd | Bournemouth | 8
  - 2025-12-03 | Brighton | Aston Villa | 7
  - 2026-01-07 | Newcastle | Leeds | 7
  - 2026-02-28 | Burnley | Brentford | 7

Gelen (model):
  - 1903251 | 2025-12-02 | Fulham | Man City | 4 | 5 | 9
  - 1903490 | 2025-12-15 | Man Utd | Bournemouth | 4 | 4 | 8
  - 1903285 | 2026-01-07 | Newcastle | Leeds | 4 | 3 | 7
  - 1903249 | 2025-12-03 | Brighton | Aston Villa | 3 | 4 | 7
  - 1903402 | 2026-02-28 | Burnley | Brentford | 3 | 4 | 7
