---
title: Savunma müdahaleleri ve top kazanma
topic: defending
source: genel scouting/taktik analiz yazını, possession-adjustment kavramı
---

## Pozisyon bağımlılığı çok yüksek

Müdahale/90, pas arası/90, top kazanma/90 gibi metrikler pozisyona göre çok
farklı okunur: bir CB için az müdahale genelde iyi işarettir (rakip onun
bölgesine az giriyor demektir), bir DM için aynı sayı düşük iş yükü veya
zayıf alan kontrolü anlamına gelebilir. Bu metrikleri pozisyon grubu
belirtmeden karşılaştırmak anlamsızdır — proje bu yüzden yüzdelikleri her
zaman aynı pozisyon grubu içinde hesaplar.

## Possession-adjustment (PAdj) neden sadece burada

Az topa sahip olan bir takımın savunmacısı, çok topa sahip olan bir takımın
aynı rol oyuncusundan doğal olarak daha fazla savunma eylemi yapar — çünkü
rakip topu daha çok onda tutuyor. PAdj bu farkı düzeltir: ham değeri rakibin
ortalama possession'ına göre yeniden ölçekler (`raw × 50 / rakip
possession%`). Bu düzeltme yalnızca savunma kategorisinde uygulanır, çünkü
possession farkının davranışı en çok çarptığı yer budur; ikili mücadele gibi
diğer kategoriler düzeltilmez.
