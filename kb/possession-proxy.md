---
title: Possession proxy'si ve sınırlamaları
topic: possession_proxy
source: proje notu — CLAUDE.md "Profil ve radar" (Gün 7, D-031, migration 004)
---

## Touches payından türetme

Veri kaynağında doğrudan bir possession % kolonu olmadığı için, projenin
possession proxy'si iki takımın maçtaki toplam `touches` sayısının payından
hesaplanır: önce `team_match_touches`, sonra bunun oranı olarak
`match_possession`, sonra oyuncu bazında `player_possession`. Bu, tracking
verisi olmayan projelerde (FBref, Wyscout gibi kaynaklarda da) yaygın
kullanılan bir yaklaşımdır.

## Neden bir proxy ve neyi kaçırır

Touches payı, gerçek top-sahipliği süresiyle birebir aynı değildir — bir
takım az dokunuşla uzun süre topu tutabilir (örn. az ama uzun paslarla).
Proxy bu tür nüansları kaçırır. Possession hesaplanamadığında (veri
eksikse) bu bir imputed boyut olarak işaretlenir, ham değere sessizce
düşülmez — düzeltilmiş (PAdj) ve ham değerlerin tek dağılımda karışması
yanlış z-skor/yüzdelik üretir.
