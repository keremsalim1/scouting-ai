---
title: Z-skor ve kosinüs benzerliği — sezgisel açıklama
topic: zscore_cosine
source: proje notu — CLAUDE.md "Benzerlik" (Gün 8, D-032)
---

## Z-skor: "ortalamadan kaç standart sapma"

Z-skor, bir metriği kendi grubunun ortalaması ve sapmasıyla ölçeklendirir:
`(değer − ortalama) / sapma`. Bu, farklı birimlerdeki metrikleri (örn.
şut/90 ile pas isabeti %) karşılaştırılabilir bir ölçeğe taşır — ikisi de
artık "ortalamanın kaç sapma üstünde/altında" diye okunur. Z-skorlama
olmadan, büyük sayılarla ölçülen bir metrik (pas/90) küçük sayılarla
ölçülen bir metriği (gol/90) benzerlik hesabında ezip geçerdi.

## Kosinüs neden Öklid değil

İki vektör arasındaki Öklid uzaklığı, hem *yönü* hem *büyüklüğü* hesaba
katar — iyi bir oyuncu ile vasat bir oyuncu, aynı oyun tarzını paylaşsalar
bile Öklid'de "uzak" çıkabilir, çünkü biri her boyutta daha yüksek değer
taşır. Kosinüs benzerliği ise iki vektörün açısını ölçer, büyüklüğü
görmezden gelir — bu da "aynı yönde işaret eden" profilleri yakın sayar,
seviyeyi değil. Projenin kosinüsü seçmesinin nedeni tam olarak bu: Öklid
seçilseydi, benzerlik sessizce bir kalite sıralamasına dönüşürdü.
