---
title: OpenPlay veri modeli
topic: openplay_data_model
source: proje notu — CLAUDE.md "Veri gerçekleri" (OpenPlay data-v0.1.0)
---

## Koordinatlar ve dakika

OpenPlay verisinde koordinatlar 0–100 ölçeğindedir ve her takım x=100'e
hücum eder; metreye çevirmek için x×1,05, y×0,68 kullanılır. `minutes_played`
uzatma dahil "expanded minutes"tir — tam bir maç ~98 dakikaya karşılık
gelir, nominal 90 değil. Sezon verisi `"2025/26"` olarak yazılır ama ham
veride `"2526"` saklanır.

## Lisans ve sınırlamalar

Veri CC-BY 4.0 lisanslıdır; her çıktıda "openplay (Noah Bair)" atıfı
zorunludur. Ham parquet/csv dosyaları git'e girmez. Veride pres (pressure)
olayı ve ilerletici taşıma için ayrı bir olay tipi yoktur — bu, ilerletme ve
baskı analizinde bir sınırlama olarak projenin her yerinde not edilir.
`player_match_stats.position` oyuncunun başlangıç pozisyonudur; sonradan
girenlerde `Sub` değerini taşır.
