---
title: Season vs season_club — takım değiştirenler
topic: season_vs_club
source: proje notu — CLAUDE.md "Pozisyon ve view'lar" (Gün 3, D-014…D-017)
---

## İki ayrı view, iki ayrı amaç

`player_season_club`, bir oyuncunun sezon içinde her takımdaki satırını ayrı
tutar (1.771 satır); `player_season` ise takım değiştiren oyuncuları
birleştirip sezonun bütününü tek satırda toplar (1.723 satır). Bu ikisini
tek bir view'da karıştırmak, sezon içinde takım değiştiren ~48 oyuncuyu
sessizce iki kez saydırır — toplam sayılar, yüzdelikler ve karşılaştırma
grubu büyüklükleri bu hatadan etkilenirdi.

## Hangi soruda hangisi kullanılır

"Bu oyuncu X takımındayken nasıl oynadı" sorusu `season_club`'ı gerektirir;
"bu oyuncu bu sezon genel olarak nasıl oynadı" sorusu `season`'ı gerektirir.
Text-to-SQL ve scouting raporu araçları bu ayrımı açıkça yapmalı — hangi
view'ın kullanıldığı raporda (veya SQL sorgusunda) belirtilmelidir, çünkü
ikisi aynı oyuncu için farklı dakika ve farklı per-90 sayıları üretebilir.
