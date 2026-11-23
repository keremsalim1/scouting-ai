---
title: Minimum dakika eşiği
topic: minutes_threshold
source: proje notu — CLAUDE.md ve config/metrics.yaml defaults.min_minutes
---

## Eşik neden 900

Proje, bir oyuncunun karşılaştırma grubuna (yüzdelik hesaplamasına) girmesi
için varsayılan olarak 900 dakika (yaklaşık 9 tam maç) ister. Bu sayı 3
ligdeki 1.723 oyuncudan 1.072'sini bırakacak şekilde seçildi — her
lig-pozisyon grubu hücresinin hâlâ çalışılabilir büyüklükte kalmasını
sağlayan bir eşik. Daha düşük bir eşik daha fazla oyuncu bırakır ama
per-90 gürültüsünü artırır; daha yüksek bir eşik gürültüyü azaltır ama
grupları küçültüp yüzdelik hesaplamasını belirsizleştirir.

## 900 altındaki oyuncular profilsiz bırakılmaz

`player_profile()` 900 dakika altındaki oyuncular için de tam profil
üretir — ham per-90 değerlerine düşer, yüzdelik vermez
(`comparison_scope = 'below_minutes_threshold'`) ve açık bir örneklem
uyarısı ekler. Benzerlik (`similar_players()`) ise bu oyuncuları hiç
sorgulayamaz (`PlayerNotQualifiedError`) — 200 dakikalık bir per-90
üzerine "en benzer oyuncular" listesi kurmak, projenin "sessiz
yanlışlık" yasağına girer.
