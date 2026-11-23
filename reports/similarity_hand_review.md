# Benzerlik — 10 sorgunun elle incelenmesi

Gün 8 kabul kriteri: *"10 sorgu elle incelenmiş"*. Ağırlıklandırma `role`
(`reports/similarity_eval.md` kazananı), her sorguda ilk 5 sonuç. Vektörler
38 performans metriği + 2 rol betimleyicisi (ortalama pas derinliği ve merkez
hattından uzaklık) içeriyor — bkz. `src/football_ai/scouting/descriptors.py`.

Oyuncular her pozisyon grubundan en çok dakika oynayanlar arasından; hücumda
FW/W örtüşmesi ölçümde işaretlendiği için oradan ikişer örnek.

Veri: openplay (Noah Bair), 2025/26, Premier League / La Liga / Serie A.

**Benzerlik oyun profilinin benzerliğidir, oyuncu kalitesi değildir.**

---

## 1. Djordje Petrovic (GK, eng, 3837 dk) — havuz 72

| # | Oyuncu | Lig | Benzerlik | Dk |
| --- | --- | --- | --- | --- |
| 1 | Julen Agirrezabala | esp | 0.882 | 1790 |
| 2 | Gianluigi Donnarumma | eng | 0.646 | 3398 |
| 3 | Luiz Júnior | esp | 0.632 | 2768 |
| 4 | David de Gea | ita | 0.574 | 3653 |
| 5 | Pau López | esp | 0.570 | 904 |

**Makul.** Yüksek hacimli kurtarış yapan kaleciler. İlk isimden sonra belirgin
düşüş — `role` ağırlığında `goalkeeping` kategorisi tek metrikli
(`saves_per90`) olduğu için benzerliğin üçte birini o sürüyor; tasarımda
işaretlenen etki burada görünür hale geliyor ama sıralamayı bozmuyor.

## 2. Virgil van Dijk (CB, eng, 3858 dk) — havuz 220

| # | Oyuncu | Lig | Benzerlik | Dk |
| --- | --- | --- | --- | --- |
| 1 | Dean Huijsen | esp | 0.825 | 2224 |
| 2 | Leo Østigård | ita | 0.803 | 2849 |
| 3 | Alessio Romagnoli | ita | 0.802 | 2908 |
| 4 | Joachim Andersen | eng | 0.783 | 3205 |
| 5 | David López | esp | 0.753 | 933 |

**İyi.** Huijsen zaten "yeni Van Dijk" profilinde tarif edilen topla oynayan
stoper; Andersen de uzun pas hacmi yüksek bir merkez defans.

## 3. Adrien Truffert (FB, eng, 3785 dk) — havuz 200

| # | Oyuncu | Lig | Benzerlik | Dk |
| --- | --- | --- | --- | --- |
| 1 | Hugo Bueno | eng | 0.791 | 2647 |
| 2 | Neco Williams | eng | 0.751 | 3547 |
| 3 | Nahuel Molina | esp | 0.731 | 1511 |
| 4 | Raoul Bellanova | ita | 0.724 | 1504 |
| 5 | Tyrick Mitchell | eng | 0.714 | 3624 |

**İyi.** Tamamı hücuma çıkan kanat bek. Betimleyiciler eklendikten sonra FB
tutarlılığı %92.6 → %96.2 çıktı; genişlik ekseni bu grubu CB'den net ayırıyor.

## 4. James Garner (DM, eng, 3785 dk) — havuz 77

| # | Oyuncu | Lig | Benzerlik | Dk |
| --- | --- | --- | --- | --- |
| 1 | Vitaly Janelt | eng | 0.672 | 1655 |
| 2 | Jon Moncayola | esp | 0.636 | 3281 |
| 3 | Pascal Groß | eng | 0.562 | 1824 |
| 4 | Unai López | esp | 0.554 | 1750 |
| 5 | Lewis Cook | eng | 0.528 | 1018 |

**Makul.** Pascal Groß, Garner için güçlü bir eşleşme — ikisi de duran top +
dağıtım ağırlıklı derin orta saha. Skorlar düşük (0.53–0.67): DM havuzu 77
kişi ve ölçümde en zayıf grup (%42.3). Bu dürüst bir düşüklük.

## 5. Luis Milla (CM, esp, 3630 dk) — havuz 163

| # | Oyuncu | Lig | Benzerlik | Dk |
| --- | --- | --- | --- | --- |
| 1 | Jon Ander Olasagasti | esp | 0.760 | 1951 |
| 2 | Edu Expósito | esp | 0.731 | 2727 |
| 3 | Pablo Martínez | esp | 0.727 | 2028 |
| 4 | Anton Stach | eng | 0.696 | 2605 |
| 5 | Jari Vandeputte | ita | 0.693 | 2097 |

**Makul ama ayırt ediciliği en düşük.** CM ölçümde taban oranının **altında**
(%50.9 / taban %54) ve betimleyiciler eklendikten sonra biraz daha düştü.
Sebebi yapısal: CM, derinlik ekseninde DM ile AM'nin *arasında* duruyor, yani
her iki taraftan komşu topluyor (karışıklık tablosu: %21 AM, %28 DM).

## 6. Dominik Szoboszlai (AM, eng, 3640 dk) — havuz 60

| # | Oyuncu | Lig | Benzerlik | Dk |
| --- | --- | --- | --- | --- |
| 1 | Pablo Fornals | esp | 0.696 | 3076 |
| 2 | Mathias Jensen | eng | 0.665 | 2499 |
| 3 | Bruno Fernandes | eng | 0.627 | 3410 |
| 4 | Santi Cazorla | esp | 0.625 | 1066 |
| 5 | Lazar Samardzic | ita | 0.596 | 1144 |

**İyi.** Bruno Fernandes güçlü bir eşleşme. AM, betimleyicilerden en çok
kazanan grup: %58.5 → %65.1 (+6.6), çünkü derinlik onu CM'den ~1.9 sd ayırıyor.

## 7. Jarrod Bowen (W, eng, 3768 dk) — havuz 101

| # | Oyuncu | Lig | Benzerlik | Dk |
| --- | --- | --- | --- | --- |
| 1 | Jesús Rodríguez | ita | 0.771 | 1874 |
| 2 | Lameck Banda | ita | 0.709 | 1872 |
| 3 | Mohammed Kudus | eng | 0.692 | 1666 |
| 4 | Jan Virgili | esp | 0.685 | 1951 |
| 5 | Yankuba Minteh | eng | 0.647 | 2642 |

**İyi.** İçeri kat eden kanat oyuncuları. W tutarlılığı %61.0 → %64.6; genişlik
ekseni FW'den ayırmaya yardım ediyor ama FW/W örtüşmesi hâlâ %35.

## 8. Antoine Semenyo (W, eng, 3546 dk) — havuz 101

| # | Oyuncu | Lig | Benzerlik | Dk |
| --- | --- | --- | --- | --- |
| 1 | Gonçalo Guedes | esp | 0.513 | 1997 |
| 2 | Riccardo Orsolini | ita | 0.429 | 2294 |
| 3 | Lameck Banda | ita | 0.420 | 1872 |
| 4 | Raphinha | esp | 0.395 | 1486 |
| 5 | Rayan | eng | 0.394 | 1192 |

**Makul — ve dürüst.** En yakın komşu 0.513. Sistem "bu oyuncunun eşi yok"
demeyi beceriyor, uydurma bir yüksek skor üretmiyor. Bir scout bu listeden
"benzer profil bulunamadı" sonucunu çıkarabilir.

## 9. Igor Thiago (FW, eng, 3658 dk) — havuz 171

| # | Oyuncu | Lig | Benzerlik | Dk |
| --- | --- | --- | --- | --- |
| 1 | Jean-Philippe Mateta | eng | 0.856 | 2439 |
| 2 | Vedat Muriqi | esp | 0.826 | 3434 |
| 3 | Raúl García | esp | 0.802 | 1268 |
| 4 | Zian Flemming | eng | 0.752 | 1951 |
| 5 | Orri Óskarsson | esp | 0.734 | 948 |

**İyi.** Tamamı hedef adam / ceza sahası santraforu — en güçlü eşleşme grubu.

**Uyarı:** Óskarsson 948 dk, eşiğin (900) hemen üstünde; per-90 değerleri ~10
maça dayanıyor. Çıktıdaki `minutes_played` bunu görünür kılıyor ve rapora
taşınırken birlikte yazılmalı.

## 10. Vedat Muriqi (FW, esp, 3434 dk) — havuz 171

| # | Oyuncu | Lig | Benzerlik | Dk |
| --- | --- | --- | --- | --- |
| 1 | Raúl García | esp | 0.874 | 1268 |
| 2 | Igor Thiago | eng | 0.826 | 3658 |
| 3 | Toni Martínez | esp | 0.808 | 2931 |
| 4 | Zian Flemming | eng | 0.806 | 1951 |
| 5 | Carlos Espí | esp | 0.802 | 1509 |

**İyi, ve bir tutarlılık kontrolü.** Thiago → Muriqi 0.826 ile Muriqi →
Thiago 0.826 birebir aynı: kosinüs simetrik, beklendiği gibi.

---

## Genel değerlendirme

10 sorgunun 10'u da futbol olarak savunulabilir. Üç gözlem:

1. **Ayrık roller keskin, süreklilikler bulanık — ve bu doğru davranış.**
   CB %96.2 ve FB %96.2 (aralarında genişlikte ~4 sd fark var) karşısında
   CM %50.9 ve DM %42.3. DM/CM/AM tek bir derinlik ekseni üzerinde sıralanıyor;
   bir DM'nin en benzerinin derin bir CM olması hata değil, doğru cevap.
2. **Düşük benzerlik skoru bilgi taşıyor.** Semenyo'da 0.513, Garner'da 0.672 —
   sistem zorlama eşleşme üretmiyor.
3. **Rol betimleyicileri uçlara yardım etti, ortaya zarar verdi.** AM +6.6,
   FB +3.6, W +3.6; CM −3.1. Net manşet etkisi +1.8 puan (%68.9 → %70.7).
   Beklentim %75–80'di, yanlış çıktı; sebebi 1. maddedeki geometri.
