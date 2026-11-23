---
title: Yüzdelik (percentile) metodolojisi
topic: percentile_methodology
source: proje notu — CLAUDE.md "Metrikler ve yüzdelikler" (Gün 4, D-018…D-020)
---

## Orta-sıra yöntemi ve 100'ün anlamı

Yüzdelik, berabere duyarlı orta-sıra formülüyle hesaplanır:
`(altındakiler + 0,5 × berabereler) / n`. Bu, en kötü oyuncuya 0, en iyi
oyuncuya 100 vermeyen; ikisini de biraz içeri çeken bir yöntemdir
(`percent_rank` en kötüye 0 verdiği, `cume_dist` en iyiye 100 verdiği için
ikisi de reddedildi). Projede **100 her zaman "grubun en iyisi"** anlamına
gelir — `higher_is_better: false` olan metriklerde (örn. hata/90) bu çeviri
veri katmanında yapılır, tüketici kodun `if higher_is_better` yazmasına
gerek kalmaz.

## Grup küçükse ne olur

Karşılaştırma grubu önce lig + ince pozisyon grubudur. Bu hücre 20
oyuncudan azsa, önce rolü koruyup ligleri birleştirme denenir (ince grubu
genişletmek yerine) — ölçülerek seçilmiş bir sıra: lig birleştirme,
katsayı-varyasyonda role genişletmeye göre daha tutarlı çıkıyor. Bu da
yetmezse yüzdelik hiç verilmez, `comparison_scope = 'insufficient'` olur
ve ham değer yine de döner — sessizce eksik veya yanlış yüzdelik yerine
açık bir "yetersiz" işareti.
