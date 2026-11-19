# Benzerlik değerlendirmesi — pozisyon tutarlılığı

Üretildi: 2026-11-19T13:16:55+00:00

Üretimdeki `similar_players()` adayları **ince** pozisyon grubuna filtreler,
bu da tutarlılığı tanım gereği %100 yapardı. Bu ölçüm o filtreyi kaldırır:
her oyuncunun **geniş** havuzdaki en yakın 10 komşusunun kaçı aynı ince
pozisyonda? Taban oranın üstündeki fark, vektörün taşıdığı pozisyon sinyalidir.

**GK dışlandı:** geniş havuzu ince havuzuyla aynı, yani yapı gereği %100 alır
ve ortalamayı şişirirdi.

**Manşet sayı, yedi GK-dışı grubun ağırlıksız ortalaması** — oyuncu başına
ortalama olsaydı CB (221) ve FW (172) sonucu taşır, AM (61, taban %20) ise
neredeyse hiç etkilemezdi.

Hedef: ≥ %90

## Özet

| Ağırlıklandırma | Pozisyon tutarlılığı | Hedef | Ortalama top-10 benzerlik |
| --- | --- | --- | --- |
| `equal` | **%68.5** | altında | 0.649 |
| `role` | **%68.6** | altında | 0.648 |
| `pca` | **%68.9** | altında | 0.704 |

**Kazanan: `pca`** (%68.9).
Üç konfigürasyon arasındaki fark 0.3 puan — pratikte ayırt edilemez. Ağırlıklandırmanın bu veri setinde pozisyon sinyaline katkısı yok denecek kadar az; sinyal metriklerin kendisinde. `pca` yalnızca en yüksek ortalama benzerliği verdiği için seçildi, belirgin bir üstünlüğü olduğu için değil.
Hiçbir konfigürasyon %90 hedefine ulaşmadı. Bu bir bulgudur, yuvarlanacak bir sayı değil — aşağıdaki karışıklık tablosu hangi rollerin birbirini soğurduğunu gösteriyor.

## Grup bazında

| Grup | Taban oran | `equal` | kazanım | `role` | kazanım | `pca` | kazanım |
| --- | --- | --- | --- | --- | --- | --- | --- |
| AM | %20 | %59.0 | +38.9 | %59.3 | +39.2 | %58.5 | +38.4 |
| CB | %52 | %94.6 | +42.2 | %94.7 | +42.3 | %94.6 | +42.2 |
| CM | %54 | %53.2 | -0.9 | %53.0 | -1.1 | %54.0 | -0.1 |
| DM | %26 | %40.1 | +14.4 | %41.2 | +15.4 | %41.5 | +15.8 |
| FB | %48 | %92.5 | +44.9 | %92.4 | +44.8 | %92.6 | +45.0 |
| FW | %63 | %80.1 | +17.3 | %80.1 | +17.3 | %79.8 | +17.0 |
| W | %37 | %60.0 | +22.8 | %59.3 | +22.1 | %61.0 | +23.8 |

## Karışıklık tablosu — `equal`

Satır: sorgu oyuncusunun grubu. Sütun: komşularının grupları (top-10 payı).

| Sorgu | AM | CB | CM | DM | FB | FW | W |
| --- | --- | --- | --- | --- | --- | --- | --- |
| AM | %59 | %0 | %38 | %3 | %0 | %0 | %0 |
| CB | %0 | %95 | %0 | %0 | %5 | %0 | %0 |
| CM | %20 | %0 | %53 | %27 | %0 | %0 | %0 |
| DM | %6 | %0 | %54 | %40 | %0 | %0 | %0 |
| FB | %0 | %8 | %0 | %0 | %92 | %0 | %0 |
| FW | %0 | %0 | %0 | %0 | %0 | %80 | %20 |
| W | %0 | %0 | %0 | %0 | %0 | %40 | %60 |

## Karışıklık tablosu — `role`

Satır: sorgu oyuncusunun grubu. Sütun: komşularının grupları (top-10 payı).

| Sorgu | AM | CB | CM | DM | FB | FW | W |
| --- | --- | --- | --- | --- | --- | --- | --- |
| AM | %59 | %0 | %38 | %3 | %0 | %0 | %0 |
| CB | %0 | %95 | %0 | %0 | %5 | %0 | %0 |
| CM | %20 | %0 | %53 | %27 | %0 | %0 | %0 |
| DM | %6 | %0 | %53 | %41 | %0 | %0 | %0 |
| FB | %0 | %8 | %0 | %0 | %92 | %0 | %0 |
| FW | %0 | %0 | %0 | %0 | %0 | %80 | %20 |
| W | %0 | %0 | %0 | %0 | %0 | %41 | %59 |

## Karışıklık tablosu — `pca`

Satır: sorgu oyuncusunun grubu. Sütun: komşularının grupları (top-10 payı).

| Sorgu | AM | CB | CM | DM | FB | FW | W |
| --- | --- | --- | --- | --- | --- | --- | --- |
| AM | %59 | %0 | %39 | %3 | %0 | %0 | %0 |
| CB | %0 | %95 | %0 | %0 | %5 | %0 | %0 |
| CM | %19 | %0 | %54 | %27 | %0 | %0 | %0 |
| DM | %5 | %0 | %53 | %42 | %0 | %0 | %0 |
| FB | %0 | %7 | %0 | %0 | %93 | %0 | %0 |
| FW | %0 | %0 | %0 | %0 | %0 | %80 | %20 |
| W | %0 | %0 | %0 | %0 | %0 | %39 | %61 |

## Ölçüm notları

- Top-10 komşu, geniş havuz içinde, kendi `player_id`'si hariç.
- Veri: openplay (Noah Bair), 2025/26, Premier League / La Liga / Serie A.

- `equal` tam tarama: 0.1 sn
- `role` tam tarama: 0.1 sn
- `pca` tam tarama: 0.1 sn
