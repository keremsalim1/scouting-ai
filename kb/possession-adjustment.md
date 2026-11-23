---
title: Possession-adjustment (PAdj)
topic: possession_adjustment
source: proje notu — CLAUDE.md "Profil ve radar" (Gün 7, D-031)
---

## Formül ve kapsamı

PAdj, ham per-90 değerini oyuncunun oynadığı maçlardaki rakip
possession'ının dakika-ağırlıklı ortalamasına göre yeniden ölçekler:
`PAdj = raw_per90 × 50 / rakip_possession%`. Sadece `defending`
kategorisindeki metriklere uygulanır — kullanıcı talebi savunma
eylemleriyle sınırlı olduğu için diğer kategoriler (ikili mücadele, pas vb.)
düzeltilmez.

## Possession verisi kendisi de bir proxy

Projenin veri kaynağında doğrudan bir "possession %" kolonu yoktur;
possession, iki takımın maçtaki toplam `touches` sayısının payından
türetilir (`team_match_touches` → `match_possession` → `player_possession`,
Gün 7, migration 004). Bu, FBref/Wyscout'un tracking verisi olmadığında
kullandığı aynı yaklaşımdır. Possession bilinmiyorsa (örn. veri eksikse)
PAdj hesaplanamaz ve bu boyut imputed sayılır — ham değere sessizce
düşülmez, çünkü düzeltilmiş ve ham değerler tek dağılımda karışırsa
yanlış z-skor üretir (bkz. benzerlik notları).
