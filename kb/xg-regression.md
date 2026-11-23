---
title: xG yorumlama ve ortalamaya dönüş
topic: xg_regression
source: genel xG metodolojisi yazını + proje notu (G − xG tanımı, CLAUDE.md)
---

## G − xG neyi ölçer

Proje `G − xG`'yi `Σ non_penalty_goals − Σ npxg` olarak tanımlar. Pozitif
bir değer, oyuncunun beklenen gol modelinin öngördüğünden daha fazla gol
attığı anlamına gelir. Bu, bitiricilik kalitesinin bir göstergesi
*olabilir* ama tek başına kanıt değildir.

## Ortalamaya dönüş (regression to the mean)

İstatistiksel olarak, bir sezonluk G − xG farkının büyük bir kısmı şans
payından gelir ve bir sonraki sezon bu fark küçülme eğilimindedir — oyuncu
xG'sine daha yakın gol üretir. Bu, küçük örneklemlerde (900 dakika civarı,
bir sezon) özellikle güçlüdür: az sayıda yüksek-xG şutun içeri/dışarı
gitmesi toplam farkı büyük ölçüde değiştirebilir. Bir scouting raporu G −
xG'yi tek sezonluk bir "yetenek skoru" gibi sunmamalı; npxG/şut ve isabetli
şut % gibi daha kararlı metriklerle birlikte, örneklem uyarısı eklenerek
sunulmalıdır.
