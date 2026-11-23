# Benzerlik değerlendirmesi — pozisyon tutarlılığı

Üretildi: 2026-11-23T19:05:14+00:00

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
| `equal` | **%69.8** | altında | 0.653 |
| `role` | **%70.7** | altında | 0.669 |
| `pca` | **%69.8** | altında | 0.713 |

**Kazanan: `role`** (%70.7).
Sıralama ölçütü **pozisyon tutarlılığı**, ortalama benzerlik değil: herkesi birbirine benzer bulan bir konfigürasyon ayırt etmiş olmaz, yani yüksek ortalama benzerlik bir üstünlük değil bir çekincedir.
Üç konfigürasyon arasındaki fark 0.9 puan — pratikte ayırt edilemez. Ağırlıklandırmanın bu veri setinde pozisyon sinyaline katkısı yok denecek kadar az; sinyal metriklerin kendisinde. `role` yalnızca sıralanan tek ölçütte kıl payı önde olduğu için seçildi, belirgin bir üstünlüğü olduğu için değil.
Hiçbir konfigürasyon %90 hedefine ulaşmadı. Bu bir bulgudur, yuvarlanacak bir sayı değil — aşağıdaki karışıklık tablosu hangi rollerin birbirini soğurduğunu gösteriyor.

## Grup bazında

| Grup | Taban oran | `equal` | kazanım | `role` | kazanım | `pca` | kazanım |
| --- | --- | --- | --- | --- | --- | --- | --- |
| AM | %20 | %62.6 | +42.5 | %65.1 | +44.9 | %60.2 | +40.0 |
| CB | %52 | %95.4 | +43.1 | %96.2 | +43.8 | %95.3 | +43.0 |
| CM | %54 | %52.5 | -1.6 | %50.9 | -3.2 | %52.1 | -2.1 |
| DM | %26 | %41.5 | +15.8 | %42.3 | +16.6 | %42.9 | +17.2 |
| FB | %48 | %94.6 | +46.9 | %96.2 | +48.6 | %95.0 | +47.3 |
| FW | %63 | %80.1 | +17.3 | %79.4 | +16.6 | %79.9 | +17.2 |
| W | %37 | %61.7 | +24.4 | %64.6 | +27.4 | %63.3 | +26.1 |

## Karışıklık tablosu — `equal`

Satır: sorgu oyuncusunun grubu. Sütun: komşularının grupları (top-10 payı).

| Sorgu | AM | CB | CM | DM | FB | FW | W |
| --- | --- | --- | --- | --- | --- | --- | --- |
| AM | %63 | %0 | %36 | %2 | %0 | %0 | %0 |
| CB | %0 | %95 | %0 | %0 | %5 | %0 | %0 |
| CM | %20 | %0 | %52 | %27 | %0 | %0 | %0 |
| DM | %6 | %0 | %53 | %42 | %0 | %0 | %0 |
| FB | %0 | %5 | %0 | %0 | %95 | %0 | %0 |
| FW | %0 | %0 | %0 | %0 | %0 | %80 | %20 |
| W | %0 | %0 | %0 | %0 | %0 | %38 | %62 |

## Karışıklık tablosu — `role`

Satır: sorgu oyuncusunun grubu. Sütun: komşularının grupları (top-10 payı).

| Sorgu | AM | CB | CM | DM | FB | FW | W |
| --- | --- | --- | --- | --- | --- | --- | --- |
| AM | %65 | %0 | %33 | %2 | %0 | %0 | %0 |
| CB | %0 | %96 | %0 | %0 | %4 | %0 | %0 |
| CM | %21 | %0 | %51 | %28 | %0 | %0 | %0 |
| DM | %5 | %0 | %53 | %42 | %0 | %0 | %0 |
| FB | %0 | %4 | %0 | %0 | %96 | %0 | %0 |
| FW | %0 | %0 | %0 | %0 | %0 | %79 | %21 |
| W | %0 | %0 | %0 | %0 | %0 | %35 | %65 |

## Karışıklık tablosu — `pca`

Satır: sorgu oyuncusunun grubu. Sütun: komşularının grupları (top-10 payı).

| Sorgu | AM | CB | CM | DM | FB | FW | W |
| --- | --- | --- | --- | --- | --- | --- | --- |
| AM | %60 | %0 | %38 | %2 | %0 | %0 | %0 |
| CB | %0 | %95 | %0 | %0 | %5 | %0 | %0 |
| CM | %20 | %0 | %52 | %28 | %0 | %0 | %0 |
| DM | %5 | %0 | %52 | %43 | %0 | %0 | %0 |
| FB | %0 | %5 | %0 | %0 | %95 | %0 | %0 |
| FW | %0 | %0 | %0 | %0 | %0 | %80 | %20 |
| W | %0 | %0 | %0 | %0 | %0 | %37 | %63 |

## Ölçüm notları

- Top-10 komşu, geniş havuz içinde, kendi `player_id`'si hariç.
- Veri: openplay (Noah Bair), 2025/26, Premier League / La Liga / Serie A.

- `equal` tam tarama: 0.1 sn
- `role` tam tarama: 0.1 sn
- `pca` tam tarama: 0.1 sn
