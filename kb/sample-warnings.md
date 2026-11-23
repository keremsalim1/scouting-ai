---
title: Örneklem uyarıları neden zorunlu
topic: sample_warnings
source: proje notu — CLAUDE.md "Scouting kuralları"
---

## Her raporda dakika ve maç sayısı zorunlu

Projenin scouting raporu şeması, her raporda dakika, maç sayısı, kullanılan
minimum dakika eşiği ve örneklem uyarısını zorunlu tutar. Bunun nedeni basit:
aynı per-90 değeri 950 dakikadan türediğinde ile 9.000 dakikadan
türediğinde çok farklı güvenilirlik taşır, ama per-90 sayısının kendisi bu
farkı göstermez. Okuyucu bu bağlamı görmeden "0,8 gol/90" sayısını
değerlendiremez.

## Küçük grup, küçük sayı — ikisi de uyarı gerektirir

İki ayrı küçüklük kaynağı var: oyuncunun kendi dakikası (900 eşiğinin
altındaysa `below_minutes_threshold`) ve karşılaştırma grubunun büyüklüğü
(20'nin altındaysa `comparison_scope = 'insufficient'`). İkisi farklı
şeyleri ölçer — biri "bu oyuncunun sayısı ne kadar gürültülü", diğeri "bu
oyuncuyu kime göre sıraladık" — ve rapor ikisini de ayrı ayrı belirtmek
zorundadır; biri diğerini gizleyemez.
