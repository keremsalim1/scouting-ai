# Text-to-SQL değerlendirmesi

Üretildi: 2026-11-17 20:00 UTC

Hakem sonuç kümesi eşitliğidir: model referanstan farklı SQL yazdıysa ve satırlar aynıysa cevap doğrudur. Yüzdelik ve grup büyüklüğü gibi zorunlu kolonlar ile yasak yapılar ayrı boyutlarda puanlanır.

## gemini/gemini-3.8-flash

- Koşu: `20261117T200025Z-gemini-3.8-flash` (21 sn)
- **Doğruluk: %83.3** (5/6 puanlanabilir soru, toplam 6)
- Eşik %70.0: geçti
- Paydadan düşenler: 0 (cevaplanamaz 0, altyapı hatası 0, bozuk referans 0)
- Token: girdi 43,691, çıktı 275 (sağlayıcının kendi sayımı) · **$0.0338** (2026-11-17 fiyatlarıyla)

> Sağlayıcı şu parametreleri reddetti: temperature. Koşular bu yüzden tam deterministik değil; başka bir koşuyla karşılaştırırken bunu hesaba kat.

### Kategoriler

| Kategori | n | doğru | çalıştı | zorunlu kolon | yasak yapı |
| --- | --- | --- | --- | --- | --- |
| filters | 4 | %100.0 | 4/4 | 4/4 | 4/4 |
| match_detail | 2 | %50.0 | 2/2 | 2/2 | 2/2 |

### Onarım döngüsü

- İlk denemede geçen: 6
- Onarımla düzelen: 0
- Onarımdan sonra da reddedilen: 0

### Soru soru inceleme

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
