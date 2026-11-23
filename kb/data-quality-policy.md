---
title: Veri kalitesi politikası
topic: data_quality_policy
source: proje notu — CLAUDE.md "Veri kalitesi politikası"
---

## Eşikler hedeftir, durdurucu değildir

Proje, veri kalitesi kontrollerinde "başarısızlıkta durma" ilkesini
benimser: her kontrol `pass`, `degraded` veya `disabled` durumu döner ve
kapsamı, eksik kayıtları, etkilenen analizleri raporlar — sessizce
çalışmaya devam etmez ama sert bir şekilde de durmaz.

## Kritik eşik altında özellik kapatılır

xG veya pas koordinatı doluluğu %90'ın, maç kapsamı %95'in altına
düşerse, ilgili özellik `config/feature_flags.json` ile kapatılır ve ajan
o aracı hiç çağırmaz. Bu, düşük kaliteli veriyle hesaplanmış ama normal
görünen bir sayı üretmek yerine, o özelliğin tamamen devre dışı olduğunu
açıkça göstermeyi tercih eder — "sessiz yanlışlık" yerine "açık eksiklik."
