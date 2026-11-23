---
title: Per-90 normalizasyonu
topic: per90_normalization
source: proje notu — CLAUDE.md "Metrik kuralları" ve config/metrics.yaml
---

## Toplamların oranı, maç ortalamasının ortalaması değil

Projede per-90 her zaman `Σ sayım / Σ minutes_played × 90` şeklinde
hesaplanır — her maçın per-90'ını alıp ortalamasını almak değil. Bu fark
önemlidir: 10 dakika oynayıp 1 gol atan bir maç, per-90'da devasa bir sayı
(9,0 gol/90) üretir; bu maçın diğer maçlarla eşit ağırlıkta ortalamaya
girmesi toplam istatistiği bozar. Toplamların oranını almak, az dakika
oynanan maçların ağırlığını otomatik olarak düşürür.

## 90 değil, "expanded minutes"

`minutes_played`, uzatma dahil gerçek oynanan dakikayı tutar (tam maç
~98–101 dakika). Bu yüzden per-90 değerleri, nominal 90 dakika varsayan
kaynaklara göre %8–11 daha düşük çıkar. Bu proje-içi bir tutarlılık
meselesidir — per-90 değerleri yalnızca bu projenin kendi verisi içinde
karşılaştırılmalı, dışarıdan bir kaynağın per-90 sayısıyla doğrudan
kıyaslanmamalıdır.
