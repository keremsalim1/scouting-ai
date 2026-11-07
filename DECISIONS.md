# Teknik kararlar

Her karar: Bağlam → Karar → Değerlendirilen alternatifler → Sonuç/ölçüm → Tarih.
Kararlar değişmez; değişiklik gerekirse yeni bir D-XXX kaydı açılır ve eskisi
"D-YYY ile güncellendi" notuyla işaretlenir.

---

## D-001: Ana veri kaynağı OpenPlay

**Bağlam.** 2025–26 sezonu için üç lige ait oyuncu ve olay seviyesi veri gerekiyor.
Olay verisi (shot/pass koordinatları, xG) ücretsiz ve yeniden dağıtılabilir
lisansla nadir bulunur.

**Karar.** `openplay` paketi (Noah Bair), `data-v0.1.0` sürümü, CC-BY 4.0.
Her çıktıda atıf: **"openplay (Noah Bair)"**.

**Değerlendirilen alternatifler.**
- *StatsBomb Open Data* — kalitesi yüksek ama 2025–26 güncel lig kapsamı yok;
  tarihsel referans olarak kalır.
- *FBref/Understat kazıma* — kullanım şartları ve kırılganlık riski; koordinat
  seviyesi olay verisi yok.
- *Ücretli sağlayıcı (Opta, Wyscout)* — portföy projesi için maliyet dışı.
- *PitchAPI* — opsiyonel çapraz kontrol olarak tampon günlere bırakıldı.

**Riskler ve azaltma.**
| Risk | Azaltma |
| --- | --- |
| v0.1.0 bir önizleme sürümü | Sürüm sabit (`data-v0.1.0`); `op.DATA_TAG` her raporda yazılı |
| Tek kişilik bakım | Veri yerel önbellekte; proje paket güncellemesine bağımlı değil |
| Veri kaynak siteden derlenmiş | Gün 1 doğrulaması her çalıştırmada kapsamı ölçer; StatsBomb referans |
| Ham veriyi yeniden dağıtma | Parquet/CSV asla git'e girmez (`.gitignore`: `/data/`, `*.parquet`, `*.csv`) |

**Sonuç/ölçüm.** Veri yolu olarak **paketin kendi indirme + önbellek mekanizması**
kullanıldı; `OPENPLAY_DATA_DIR` yedek yoluna gerek kalmadı (403 alınmadı).
Önbellek: `%LOCALAPPDATA%\openplay\cache\data-v0.1.0`.

Tek sapma: paketin indiricisi socket zaman aşımı kullanmıyor ve
`events_esp_2526.parquet` indirilirken bağlantı kopunca süreç 3+ dakika asılı
kaldı. Eksik iki olay dosyası `curl --retry 8 --speed-time 20` ile **aynı önbellek
klasörüne** çekildi ve SHA-256 + bayt boyutu `checksums.json` ile doğrulandı
(üçü de eşleşti). Bütünlük garantisi atlanmadı.

**Tarih.** 2026-11-07

---

## D-002: Kapsam — üç lig, tek sezon

**Bağlam.** 24 günlük bir takvimde veri hacmi ve lig çeşitliliği doğrudan
maliyet. Her ek lig ETL, metrik yüzdelikleri ve eval setlerini büyütür.

**Karar.** Yalnızca Premier League (`eng`), La Liga (`esp`), Serie A (`ita`),
sezon 2025–26 (`"2025/26"` yazılır, veride `"2526"` saklanır). Sezon tamamlanmış
ve veri sabit.

**Kapsam dışı.** 2026–27 sezonu, canlı/akış veri, Bundesliga ve Ligue 1
(veride var ama dahil değil), kupa turnuvaları, kullanıcı bazlı JWT/RLS, PII
maskeleme, sentetik sağlık verisi, fine-tuning, video/tracking verisi.

**Değerlendirilen alternatifler.**
- *Beş büyük lig* — yüzdelik karşılaştırma havuzunu büyütürdü; 4 hafta için
  ETL ve eval maliyeti fazla. `ger`/`fra` veride mevcut, sonradan eklenebilir.
- *Tek lig (yalnız PL)* — lig içi z-skor ve "lig etkisi" tartışmasını
  kaybederdik; scouting projesinde bu asıl ilginç kısım.

**Sonuç/ölçüm.** Üç ligde 3 × 380 = 1140 maç, 1 717 761 olay, 28 434 şut,
35 373 oyuncu-maç satırı. Oyuncu sayısı lig bazında 537 + 600 + 586 = 1723
(lig değiştirenler iki kez sayılır); oyuncu-takım sezon satırı 551 + 611 + 609
= 1771. Doğrulama script'i önbellekten **5,4 saniyede** tamamlanıyor — hızlı
yineleme mümkün.

**Tarih.** 2026-11-07

---

## D-003: Veri kalitesi politikası — eşikler hedeftir, durdurucu değil

**Bağlam.** Ücretsiz, tek bakımcılı bir veri kümesinde "mükemmel veri" bekleyip
eşik tutmazsa durmak, projeyi ilk gün kilitler. Ama sessizce bozuk veriyle
analiz üretmek daha kötü.

**Karar.** Her kontrol üç durumdan birini döner:
- `pass` — hedef karşılandı.
- `degraded` — hedef karşılanmadı ama kritik eşiğin üstünde: analiz devam eder,
  rapora uyarı düşer.
- `disabled` — kritik eşiğin altında: etkilenen özellik `config/feature_flags.json`
  ile kapatılır ve ajan o aracı **çağırmaz**.

Script hiçbir durumda sıfır dışı çıkış kodu döndürmez; kapsam, eksik kayıt ve
etkilenen analizler raporlanır.

| Kontrol | Hedef | Kritik eşik (altı → `disabled`) |
| --- | --- | --- |
| `match_coverage_pct` | ≥ 99 | < 95 |
| `shot_xg_filled_pct` | ≥ 99 | < 90 |
| `pass_end_xy_filled_pct` | ≥ 99 | < 90 |
| `coords_out_of_range` | ≤ 0 | — (yalnız `degraded`) |
| `score_mismatch_pct` | ≤ 1 | — |
| `unknown_minutes_pct` | ≤ 1 | — |

Birden fazla lig aynı özelliği etkilerse **en kötü durum** kazanır
(`pass` < `degraded` < `disabled`).

**Değerlendirilen alternatifler.**
- *Sert kapı (eşik tutmazsa çıkış kodu 1)* — CI'da net ama günlük çalışmayı
  bloke eder ve "eşiği düşür" baskısı yaratır.
- *Yalnızca loglama* — bozuk veriyle sessizce rapor üretme riski; LLM'in
  güvenilmez sayılara yorum yazmasını engelleyemez.

**Sonuç/ölçüm.** Gün 1'de üç ligde **tüm kontroller `pass`**: 380/380 maç,
şut xG doluluğu %100, pas bitiş koordinatı %100, aralık dışı koordinat 0,
skor uyumsuzluğu %0, `known_gaps` ve `data_issues` boş. 10 özellik de `pass`.

**Bilinen zayıflık.** `unknown_minutes_pct` yapısal olarak her zaman 0 çıkıyor:
`player_match_stats` yalnızca sahaya çıkanları içeriyor (25 080 ilk 11 +
10 293 `Sub` = 35 373 = toplam satır), yani `in_lineup` hep `True`. Bu metrik
yanlış güven veriyor. Gün 2'de dakika bütünlüğü `team_minutes_ratio`
(takım dakikası / 11 × maç uzunluğu) ile ölçülecek — bu ölçüm kırmızı kartlı
maçlarda 1'in altına düşüyor (ölçülen minimum: eng 0,912 · esp 0,881 · ita 0,898),
yani gerçek sinyal taşıyor.

**Tarih.** 2026-11-07

---

## D-004: Per-90 ve oran hesaplama formülü

**Bağlam.** Per-90 ve yüzde metrikleri iki farklı şekilde hesaplanabilir ve
sonuçlar anlamlı ölçüde ayrışıyor. Ayrıca OpenPlay `minutes_played` değeri
uzatma dahil gerçek dakika ("expanded minutes"), nominal 90 değil.

**Karar.**
- Per-90: `Σ sayım / Σ minutes_played × 90`
- (npxG + xA)/90: `(Σ npxg + Σ xa) / Σ minutes_played × 90`
- **Oranlar toplamların oranıdır**, maç değerlerinin ortalaması değil:
  pas isabeti `Σ passes_completed / Σ passes × 100`;
  xG/şut `Σ npxg / Σ (shots − penalties_taken)`
- G − xG: `Σ non_penalty_goals − Σ npxg`
- Payda 0 ise sonuç **null**, 0 değil.
- Per-90 değerleri **yalnızca OpenPlay içinde** karşılaştırılır.
- Yüzdelikler: aynı lig + aynı pozisyon grubu + minimum dakika (varsayılan 900).

**Değerlendirilen alternatifler.**
- *Maç yüzdelerinin ortalaması* — 3 pas attığı maçı 60 pas attığı maçla eşit
  ağırlıklar; aşağıda ölçülen sapma bu yüzden reddedildi.
- *Nominal 90 dakikaya normalize etmek* (uzatmayı yok sayarak) — dış kaynaklarla
  karşılaştırılabilirlik kazanırdık ama veriyle tutarsız bir kurgu üretirdik;
  oynama süresi gerçekten 98–101 dakika.

**Sonuç/ölçüm.**
1. **Formül doğrulandı.** Kendi hesabımız `op.player_season_stats(per90=True)`
   ile üç ligde, 900+ dakika oynayan tüm oyuncu-takım satırlarında karşılaştırıldı
   (`npxg`, `xa`, `progressive_passes`). **En büyük mutlak fark 2,86e-08** —
   tolerans ±0,01'in çok altında, kayan nokta yuvarlaması düzeyinde.
2. **Oran sapması gerçek.** Pas isabetinde "maç ortalaması" yöntemi doğru
   değerden 6,9–9,7 yüzde puanı **düşük** sonuç veriyor. Örnek: Bafodé Diakité
   (Bournemouth, 17 maç) → toplamların oranı %87,75 (659/751), maç
   ortalaması %79,56, fark **−8,19 pp**. Nedeni: 2 ve 4 paslık kısa süreli
   maçlarda isabet %50 ve %25, bunlar 67–71 paslık maçlarla eşit ağırlık alıyor.
3. **Expanded minutes etkisi ölçüldü.** Ortalama maç uzunluğu
   eng 100,89 · esp 99,69 · ita 98,02 dakika. Per-90 değerlerimiz nominal 90
   dakika varsayan kaynaklardan **%8,2–10,8 düşük** (ligden lige değişir).
   Not: `CLAUDE.md`'deki "~%8" tahmini aralığın alt sınırı (Serie A); gerçek
   aralık 8,2–10,8 ve lig bazında farklı.

**Tarih.** 2026-11-07

---

## D-005: Pozisyon belirleme — dakika ağırlıklı başlangıç pozisyonu

**Bağlam.** `player_match_stats.position` **başlangıç** pozisyonudur; oyun içinde
giren oyuncularda değer `Sub` olur, gerçek pozisyon kaybolur. Yüzdelikler ve
benzerlik pozisyon grubu içinde hesaplandığı için her oyuncuya tek bir güvenilir
pozisyon grubu atamak zorunlu.

**Karar.** Sezon pozisyonu, oyuncunun **dakika ağırlıklı en sık başlangıç
pozisyonu** olacak; `Sub` bir pozisyon değil, "bilinmiyor" olarak ele alınacak ve
ağırlıklı oylamaya girmeyecek. Hiç ilk 11 başlangıcı olmayan oyuncular ayrı
işaretlenecek. Uygulama Gün 3.

**Değerlendirilen alternatifler.**
- *`Sub`'ı ayrı bir pozisyon grubu saymak* — "yedek" bir rol değil; grup içi
  yüzdelikleri anlamsızlaştırır.
- *Satır sayısına göre mod (dakika ağırlığı olmadan)* — 5 dakikalık bir kanat
  görevini 90 dakikalık stoperlikle eşitler.
- *`events` içindeki `q_PlayerPosition` / `q_FormationSlot` niteliklerinden
  türetmek* — daha hassas olabilir; Gün 3'te `Sub` satırlarını kurtarmak için
  ikincil kaynak olarak denenecek.

**Sonuç/ölçüm.** 17 farklı pozisyon kodu var: `GK, DC, DL, DR, DML, DMR, DMC,
MC, ML, MR, AMC, AML, AMR, FW, FWL, FWR` ve `Sub`.

`Sub` satırlarının ağırlığı — bu kararı zorunlu kılan sayı:

| Lig | `Sub` satır payı | `Sub` dakika payı | `Sub` medyan dakika |
| --- | --- | --- | --- |
| Premier League | %27,25 | %9,54 | 23 |
| La Liga | %30,06 | %11,75 | 26 |
| Serie A | %29,91 | %11,61 | 25 |

Yani satırların yaklaşık üçte biri pozisyonsuz, ama bunlar dakikaların yalnızca
~%10'u. Dakika ağırlıklı yaklaşım bu yüzden işe yarıyor: bilgi kaybı dakika
bazında küçük.

Ayrıca lig stilleri pozisyon dağılımında görünüyor: Serie A dakikalarının
%17,82'si `MC`'de (PL %9,07), PL'de `DMC` %9,27 (Serie A %2,53).

**Tarih.** 2026-11-07

---

## D-006: Öncelik sırası

**Bağlam.** 24 gün sabit, kapsam esnek. Geride kalındığında neyin kesileceği
önceden kararlaştırılmazsa, kesim kararı en kötü anda (panikte) verilir.

**Karar.** Öncelik sırası — asla değişmez:
1. Temel scouting motoru (metrikler, oyuncu profili, benzerlik)
2. Güvenilir text-to-SQL
3. RAG (scouting metodolojisi bilgi tabanı)
4. Çalışan LangGraph ajanı
5. Diğer her şey: kendi xG modeli, PitchAPI çapraz kontrolü, ek görseller

Geride kalınırsa **önce 5. maddeden** kesilir. 5. madde yalnızca tampon
günlerde (6, 12, 18, 24) ele alınır.

**Değerlendirilen alternatifler.**
- *Ajanı öne almak* — demosu etkileyici ama altındaki metrikler ve SQL
  güvenilmezse ajan güvenilmez sayılara yorum yazar; bu, projenin "LLM sayı
  üretmez" ilkesini kökten bozar.
- *Kendi xG modelini öne almak* — ML açısından çekici, scouting ürünü açısından
  OpenPlay xG'si zaten yeterli. Portföy değeri var ama MVP'ye bağımlı değil.

**Sonuç/ölçüm.** Gün 1'de 1. maddenin önkoşulu (veri doğrulama) tamamlandı:
tüm özellikler `pass`, hiçbir özellik `degraded`/`disabled` değil.

**Tarih.** 2026-11-07

---

## D-007: Geliştirme ortamı — uv, ruff, pre-commit

**Bağlam.** Proje Python 3.12 gerektiriyor; geliştirme makinesinde sistem
Python'u 3.11.9. Ayrıca kod stilinin CI'da deterministik olması ve bozuk kodun
commit'e girmemesi gerekiyor.

**Karar.**
- `uv` — paket, sanal ortam ve Python sürüm yönetimi. `pyproject.toml` niyeti,
  `uv.lock` tam olarak kurulanı kaydeder.
- `ruff` (line-length 100, target py312) — lint + format tek araçta.
  Seçili kurallar: `E, W, F, I, UP, B, SIM, PD, RUF`.
- `pre-commit` — commit anında 9 kontrol (trailing whitespace, EOF, YAML/TOML
  doğrulama, 512 KB dosya sınırı, merge conflict, private key, ruff check --fix,
  ruff format).
- `pytest` — `data` işaretli gerçek veri testleri varsayılan koşuda atlanır
  (`addopts = "-m 'not data'"`); gerçek veri için `uv run pytest -m data`.

**Değerlendirilen alternatifler.**
- *poetry + black + flake8 + isort* — dört araç, dört yapılandırma, ~10 kat
  daha yavaş; `uv` + `ruff` ikisini de kapsıyor.
- *`requirements.txt` + venv* — kilit dosyası ve Python sürüm yönetimi yok.

**Ortama özgü notlar (Windows).**
- `ruff` kuralları `RUF001/002/003` kapatıldı: bu kurallar İngilizce kodda
  homoglyph saldırısı yakalamak için var, bizim rapor metinleri bilinçli Türkçe
  (`ı`) ve tipografik işaret (`–`, `−`, `≤`, `≥`) kullanıyor.
- Rapor yazarken `write_text(..., encoding="utf-8")` **zorunlu**: Windows
  varsayılanı `cp1254` ve `≤`/`≥` karakterlerinde `UnicodeEncodeError` veriyor.
- `uv`'nin yönetilen Python'u `%APPDATA%\uv\python` altında bozuk bir junction
  oluşturdu (`Missing expected target directory for Python minor version link`).
  Çözüm: `UV_PYTHON_INSTALL_DIR=C:\Users\ASUS\.uv-python` ile kurulum. Proje
  `.venv`'i bir kez oluşturulduktan sonra `uv run` bu değişkene ihtiyaç duymuyor.
- `uv.exe` `%APPDATA%\Python\Python311\Scripts` altında ve PATH'te değil;
  kalıcı PATH eklemesi bu oturumda yapılamadı (bkz. README kurulum notu).

**Sonuç/ölçüm.** Python 3.12.16, 25 paket kilitlendi. `uv run pytest` →
28 birim testi geçti, 4 `data` testi atlandı (0,92 s). `uv run pytest -m data` →
4 test geçti (3,68 s). `ruff check .` → temiz. pre-commit → 9/9 geçti.

**Tarih.** 2026-11-07
