---
title: Pozisyon grupları
topic: position_groups
source: proje notu — CLAUDE.md "Pozisyon ve view'lar" (Gün 3, D-014…D-017)
---

## Sekiz ince grup, dört geniş grup

Proje iki seviyede pozisyon grubu kullanır: ince grup (`GK, CB, FB, DM, CM,
AM, W, FW`) scouting raporlarının ve karşılaştırmaların temel birimidir;
geniş grup (`GK, DEF, MID, ATT`) yalnızca benzerlik vektör uzayı gibi daha
büyük popülasyon gerektiren hesaplamalarda kullanılır. Oylama her zaman
grup düzeyinde yapılır, ham pozisyon kodu düzeyinde değil — ve bu oylama
dakika ağırlıklıdır (ör. bir sezonun çoğunu CB oynayan bir oyuncu, birkaç
maç FB oynasa da CB sayılır).

## Dikkat çeken eşlemeler

`DML`/`DMR` (3-5-2 kanat beki) `FB`'ye eşlenir, `DM`'ye değil — çünkü
oynadıkları rol savunma orta sahasından çok kanat bekine benzer. `ML`/`MR`
ise `W`'ye eşlenir. Her satırda `position_source` (`starts`, `main_position`
veya `unknown`) ve `position_share` tutulur; 900+ dakikalı her oyuncunun
kaynağı `starts`'tır, yani bu grup için pozisyon ataması en güvenilir
bilgiye dayanır.
