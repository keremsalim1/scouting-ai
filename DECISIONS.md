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

---

## D-008: İlişkisel model — hafif normalize, lig/sezon her fact tablosunda

**Bağlam.** Şema Gün 5'te text-to-SQL'in, Gün 3–4'te view ve metriklerin, Gün 8'de pgvector benzerliğinin üzerine kurulacağı temel. Normalizasyon düzeyi bir depolama tercihi değil, **LLM'in doğru SQL yazma olasılığını belirleyen bir parametre**: her ek join, modelin hata yapabileceği bir yer.

**Karar.**
- Her şey `public` değil **`football` şemasında**. Gün 5 allowlist'i böylece "şema football, şu tablolar" olur; `public` toptan kilitlenir.
- Boyut tabloları (`teams`, `players`) + fact tabloları (`matches`, `lineups`, `player_match_stats`, `shots`, `passes`) + `data_quality`.
- **`comp` ve `season` her fact tablosunda tekrarlanır.** Scouting sorgusunun en sık filtresi lig + sezon; bunu join yerine iki küçük kolonla ödemek doğrudan doğruluk kazancı.
- Etiket kolonları (`player`, `team`, `opponent` adları) da fact tablolarında denormalize. **Bunu güvenli kılan şey sezonun donmuş ve ETL'in tam yeniden yükleme olması** — kopyaların boyut satırından sapması imkânsız.
- Doğal anahtarlar, surrogate yok. Kaynak id'leri kararlı integer; ek bir katman LLM'in öğrenmesi gereken bir şey olurdu, karşılığı yok.
- **Yabancı anahtarlar bilinçli olarak tanımlı.** Bütünlüğün yanında asıl gerekçe: Gün 5'te şema açıklaması Postgres kataloğundan üretilecek ve FK'lar modele tabloların nasıl join edileceğini söyleyen şey.
- `passes` kolonları yeniden adlandırıldı: `q_Cross` → `is_cross`, `q_Longball` → `is_long_ball`, `q_Length` → `pass_length`. **Kolon adlandırması bir text-to-SQL özelliğidir.** `outcome = 'Successful'` yerine `is_completed` boolean'ı türetildi; modelin string literal'i hatırlaması gerekmiyor.
- Ham `events` tablosu **yüklenmedi.** 152 kolonun çoğu kaynak-özgü nitelik bayrağı; `passes` ve `shots` küratörlü özetler. Başka olay tipi gerektiğinde o gün kendi tablosunu alır.

**Anahtarlar kodlanmadan önce doğrulandı.** Probe sonucu:

| Anahtar | Sonuç |
| --- | --- |
| `matches(match_id)` | tekil ✓ |
| `player_match_stats(match_id, player_id)` | tekil ✓ |
| `lineups(match_id, player_id)` | tekil ✓ |
| `shots(match_id, event_id, event_id_sub)` | tekil ✓ |
| `passes(match_id, event_id, event_id_sub)` | tekil ✓ |
| `events(match_id, event_id, event_id_sub)` | **tekil DEĞİL — 82 kopya** |

Kopyaların kök nedeni bulundu: 82 grubun **hepsinde** `OffsideGiven` var. Kaynak (WhoScored), offside olayına aynı maçtaki başka bir olayın `event_id`'sini veriyor — örnek: 69. dakikadaki offside ile 80. dakikadaki pas aynı id, farklı takım, farklı oyuncu. Anahtara `type` eklenince üç ligde de 0 kopya. `Pass` alt kümesi zaten temiz olduğu için `passes` 3 kolonlu PK kullanabiliyor. **Probe yapılmasaydı bu, raw events tablosunda yükleme hatası olarak ortaya çıkardı.**

**Değerlendirilen alternatifler.**
- *Saf 3NF* — "PL'de xA/90'ı en yüksek sol kanatlar" sorusu 4 join gerektirirdi.
- *Tek büyük denormalize tablo* — toplama (aggregation) belirsizleşir; hangi satır düzeyinde olduğu kaybolur.
- *Surrogate anahtar + doğal anahtar üzerinde unique index* — ekstra katman, sıfır fayda; kaynak id'leri zaten kararlı.

**Sonuç/ölçüm.** 9 tablo, PostgreSQL 17.11 + pgvector 0.8.7. Yüklenen satırlar kaynakla birebir: teams 60 (3×20), matches 1140, lineups 49 901, player_match_stats 35 373, shots 28 434, passes 1 083 374.

**Tarih.** 2026-11-08

---

## D-009: Boyut tabloları yalnızca referans edilen satırlarla yüklenir

**Bağlam.** `op.teams()` 422 takım, `op.players()` 20 782 oyuncu döndürüyor — tüm turnuvalar, tüm sezonlar. Bizim kapsamımız 3 lig / 1 sezon.

**Karar.** Fact tablolarının referans ettiği id'ler toplanıp boyut tabloları ona göre filtrelenir. Toplama `player_id` **ve** `assist_player_id`'yi, takımlarda `team_id`/`opponent_id`/`home_team_id`/`away_team_id`'yi kapsar. Referans edilen bir id kaynakta yoksa ETL Python tarafında **okunabilir bir hatayla durur**, 1 milyon satırlık COPY'nin ortasında FK ihlaliyle değil.

**Değerlendirilen alternatifler.**
- *Hepsini yükle* — `select count(*) from players` sorusuna 20 782 cevabı yanıltıcı olurdu; LLM'in "veritabanında kaç oyuncu var" sorusuna verdiği cevap yanlış olur. Takımlarda daha beter: milli takımlar listeye girer.
- *Yalnızca `player_match_stats`'tan topla* — `shots.assist_player_id` FK'sı kırılırdı; asist yapan ama o ligde maç istatistiği olmayan oyuncular var.

**Sonuç/ölçüm.** teams 422 → **60**, players 20 782 → **2166**. 2166 sayısı `player_season_stats`'taki 1723'ten yüksek, çünkü `lineups` kullanılmayan yedekleri de içeriyor (sahaya çıkmayan oyuncunun maç istatistiği yok ama kadro satırı var).

**Tarih.** 2026-11-08

---

## D-010: Idempotency — donmuş fact'lerde TRUNCATE, tarihçede append

**Bağlam.** Gün 2 kabul kriteri: "ikinci çalıştırmada kopya yok". Üç strateji mümkün: truncate-and-reload, UPSERT (`on conflict`), staging tablo + atomik swap.

**Karar.** **Veri tipine göre iki farklı strateji:**

*Fact tabloları (donmuş sezon):* tek transaction içinde `TRUNCATE` + `COPY`. Bunu güvenli kılan şey **PostgreSQL'de TRUNCATE'in transactional olması** (MySQL'de değildir): yükleme yarıda patlarsa rollback eski satırları geri getirir. Tek `TRUNCATE` ifadesinde tüm tablolar birlikte adlandırılıyor; böylece aralarındaki FK'lar aynı anda sağlanır, bağımlılık sıralaması gerekmez ve `CASCADE` (sonraki günlerin tablolarını da silerdi) hiç kullanılmaz.

*`data_quality` (biriken tarihçe):* append + `on conflict do nothing`. Anahtar **raporun kendi `generated_at` değeri**, ETL'in çalıştığı an değil.

**Bu ikinci kısım bir hata düzeltmesidir.** İlk uygulamada `run_at = datetime.now()` idi ve tablo da TRUNCATE ediliyordu: yani tarihçe için tasarlanmış bir tabloyu her koşuda siliyordum, üstelik idempotency anahtarı **duvar saatinden** geliyordu. Doğru kural: **idempotency anahtarı veriden türer, yükleyicinin saatinden değil.** `validate_openplay.py` artık rapora `generated_at` yazıyor; aynı raporu iki kez yüklemek no-op, yeni bir doğrulama koşusu ise yeni bir tarihçe noktası.

**Değerlendirilen alternatifler.**
- *UPSERT (fact'ler için)* — değişen veri için doğru araç; bizde veri değişmiyor. Dahası kaynaktan bir satır silinse DB'de yetim kalırdı.
- *Staging tablo + atomik swap* — kesintisiz production yeniden yüklemesi için; geliştirme ortamında uptime gereksinimi yok, karşılığında karmaşıklık getirir.
- *`DELETE FROM`* — TRUNCATE'ten yavaş, tablo şişmesi (bloat) bırakır.

**Sonuç/ölçüm.** İkinci ETL koşusu aynı satır sayılarını üretti; 7 tabloda doğal anahtar üzerinde 0 kopya (test edildi). Migration da idempotent: ikinci koşu 0 migration uyguluyor; uygulanmış bir migration dosyası değiştirilirse SHA-256 kontrolü hata verip duruyor.

**Tarih.** 2026-11-08

---

## D-011: Yükleme yöntemi COPY — ve darboğazın gerçekte nerede olduğu

**Bağlam.** 1,08 M pas satırı yüklenecek. `pandas.to_sql` kolay yol.

**Karar.** `COPY ... FROM STDIN` (psycopg3). Kolonlar COPY ifadesinde açıkça adlandırılıyor, böylece tabloya sonradan kolon eklenmesi değerleri sessizce kaydırmıyor. ETL sonunda `ANALYZE`: COPY planner istatistiklerini güncellemez, onsuz planner tabloları boş sanıp Gün 3 view'larında nested loop seçer.

**Sonuç/ölçüm — ve bir iddia düzeltmesi.** İlk yazdığım yorumda COPY'nin avantajını "dakikalar vs saniyeler" diye tarif etmiştim. **Ölçüm bunu çürüttü.** 50 000 pas satırında:

| Yöntem | Süre | Hız |
| --- | --- | --- |
| `COPY` | 1,01 s | 49 316 satır/s |
| `pandas.to_sql` | 2,51 s | 19 932 satır/s |
| fark | | **2,5×** |

Gerçek, ama bu tercihin genelde satıldığı büyüklük sırası değil. "Neden sadece 2,5×" sorusunu ayrıca ölçtük:

| Aşama (50 000 satır × 31 kolon) | Süre |
| --- | --- |
| `itertuples` tek başına | 0,143 s |
| + hücre başına `to_copy_value` | 0,721 s |
| `to_csv` ile aynı serileştirme | 0,381 s |

Yani 1,01 saniyenin **~%71'i socket'in bizim tarafında**, pandas skalerlerini Python'da dönüştürmekte geçiyor — sunucuda değil. `to_csv` yoluna geçmek bu kısmı 1,9× hızlandırır, toplam yüklemeyi ~1,5× (passes 36 s → ~24 s).

**Alınmayan karar:** bu optimizasyon şimdi yapılmadı. 1,5× kazanç için metin kolonlarında NULL / boş string kodlamasını kırılgan hale getirmeye değmez. Yükleme süresi sorun olmaya başlarsa bilinen ilk adım bu.

Tam yükleme: okuma 4,0 s + COPY/commit 41,2 s.

**Tarih.** 2026-11-08

---

## D-012: Migration yönetimi — numaralı SQL dosyaları, Alembic değil

**Bağlam.** 22 gün daha şema değişecek (Gün 3 view'ları, Gün 8 vektör tablosu). Şema değişikliklerinin hem tekrar edilebilir hem de makineler arası tutarlı olması gerekiyor.

**Karar.** `infra/migrations/NNN_*.sql` + `scripts/migrate.py` (~130 satır). Uygulananlar `football.schema_migrations` tablosunda **SHA-256'sıyla** kayıtlı. Her migration kendi transaction'ında. Uygulanmış bir dosya sonradan değiştirilirse runner durup hata veriyor — aksi halde aynı repodan iki makine farklı şema elde ederdi.

Salt-okunur rolün **oluşturulması** Python'da, migration'da değil: şifre ortamdan geliyor ve commit edilen bir dosyaya girmemeli. Migration yalnızca `GRANT` yapıyor.

**Değerlendirilen alternatifler.**
- *Alembic* — değeri SQLAlchemy modellerinden diff üretmesi. Bu projede ORM yok (Gün 5 sqlglot ile doğrulayacak, SQLAlchemy ile değil). Modelsiz Alembic = Python iskeleti içine sarılmış elle yazılmış SQL: tüm tören, sıfır fayda.
- *`docker-entrypoint-initdb.d/init.sql`* — yalnızca volume boşken çalışır. Her şema değişikliğinde veritabanını silmek gerekirdi; 22 gün için tuzak.
- *Migration'ı hiç kullanmamak, şemayı elle yönetmek* — tekrar üretilemez.

**Öğrenilen Postgres ayrıntısı.** `CREATE ROLE` / `ALTER ROLE` **utility** ifadeleridir ve bind parametresi kabul etmez: `password %s` → `syntax error at or near "$1"`. Çözüm string birleştirme değil, `psycopg.sql.Literal` (kaçışlamayı doğru yapar) ve rol adı için `psycopg.sql.Identifier`.

**Tarih.** 2026-11-08

---

## D-013: Gün 5 güvenliği şemayı bugünden şekillendirir

**Bağlam.** Gün 5'te LLM üretimi SQL çalıştırılacak, Gün 19'da 30 saldırgan prompt denenecek. Güvenliği o gün eklemek, şemayı o gün yeniden yazmak demek.

**Karar — bugün uygulandı:**
- İki rol: `football_etl` (sahip, yazar) ve `football_ro` (yalnız `SELECT`).
- `ALTER DEFAULT PRIVILEGES` ile Gün 3 view'ları ve sonradan eklenen tablolar `SELECT` iznini otomatik devralır; her yeni nesnede grant unutma riski yok.
- `REVOKE ALL ON SCHEMA public FROM PUBLIC` ve `REVOKE CREATE ON SCHEMA football FROM football_ro`.
- **`ALTER ROLE football_ro SET statement_timeout = 5000`** — zaman aşımı rolün üzerinde, yani **sunucu tarafında** zorunlu. Python tarafı bir timeout istemci iyi niyetine bağlıdır; prompt injection ile üretilmiş bir sorgu rolün ayarını kaldıramaz.
- `NOCREATEDB NOCREATEROLE NOSUPERUSER` açıkça set edilmiş.
- `db.py` iki ayrı fonksiyon sunuyor: `etl_dsn()` ve `readonly_dsn()`. Yalnızca `readonly_dsn` import eden bir modül yazma erişimi **elde edemez**.
- `ALLOWED_TABLES` listesi `db.py`'de; şema, ETL ve Gün 5 allowlist'inin birbirinden sapması engellenir (testle doğrulanıyor).

**Sonuç/ölçüm.** 12 güvenlik testi geçiyor (`uv run pytest -m db`): `football_ro` 7 farklı yazma ifadesinde (`insert`, `update`, `delete`, `truncate`, `create table`, `drop table`, `alter table`) ve `public` şemasında tablo oluşturmada `InsufficientPrivilege` alıyor; `select pg_sleep(30)` gerçekten `QueryCanceled` ile iptal ediliyor; `is_superuser` = `off`.

**Tarih.** 2026-11-08

---

## D-014: Pozisyon grupları — 8 ince + 4 geniş, ölçülerek seçildi

**Bağlam.** Gün 4'te yüzdelikler "aynı lig + aynı pozisyon grubu" içinde hesaplanacak. Grup seçimi bir zevk meselesi değil: grup çok küçükse yüzdelik anlamsız olur, çok büyükse farklı roller aynı potada karşılaştırılır. 17 ham pozisyon kodunu kaç gruba indireceğimiz **ölçülerek** karar verilmeli.

**Karar.** İki seviye, `position_map` view'ında iki kolon:
- **İnce (8):** `GK, CB, FB, DM, CM, AM, W, FW`
- **Geniş (4):** `GK, DEF, MID, ATT` — ince grup yüzdelik için fazla küçükse Gün 4'ün düşeceği havuz

Eşleme:

| Grup | Ham kodlar |
| --- | --- |
| GK | GK |
| CB | DC |
| **FB** | DL, DR, **DML, DMR** |
| DM | DMC |
| CM | MC |
| AM | AMC |
| W | AML, AMR, ML, MR |
| FW | FW, FWL, FWR |

**İki eşleme kararı ölçümden çıktı:**

1. **`DML`/`DMR` orta saha değil, kanat bek.** Serie A'da `DML+DMR` dakikaların %9,1'i, `DL+DR` %6,2; İngiltere'de tam tersi (%2,8 vs %13,7). Bu 3-5-2 dizilişinin imzası. Onları `DM`'e koyunca Serie A'da **22 bek** çıkıyordu (eng 65, esp 69 iken) — futbolen imkânsız, her takım iki geniş savunmacı oynatır. `FB`'ye taşıyınca üç lig **65 / 69 / 67** oldu. Yan doğrulama: pas konumu merkezleri tablosunda `FB` merkezden sapması 39,6 ile **en geniş** grup.
2. **`ML`/`MR` kendi grubunu kuramaz.** Ayrı `WM` grubu denendiğinde 900+ dakikada eng 5, esp 22, **ita 0** kişi veriyordu. Kanatlara katıldı.

**Değerlendirilen alternatifler.**
- *9 grup (`WM` ayrı)* — ita'da 0 kişi; reddedildi.
- *`DML/DMR` → `DM`* — ita'da 22 bek; reddedildi.
- *Tek seviye grup* — ince grup küçük kaldığında yedek havuz kalmıyor.
- *Ham 17 kodu grup olarak kullanmak* — `FWL` gibi kodlarda lig başına 10'un altında oyuncu.

**Sonuç/ölçüm.** 900+ dakikada grup büyüklükleri:

| Grup | eng | esp | ita |
| --- | --- | --- | --- |
| CB | 71 | 72 | 80 |
| FB | 61 | 69 | 64 |
| CM | 34 | 49 | 83 |
| FW | 49 | 56 | 70 |
| DM | 42 | 27 | **10** |
| W | 39 | 48 | **9** |
| AM | 36 | 16 | **14** |
| GK | 25 | 24 | 24 |

Geniş gruplar sağlıklı: GK 24–25, DEF 135–146, MID 91–106, ATT 78–105. Kalın yazılan dört hücre Gün 4'te geniş gruba düşecek.

**Ek karar — oylama grup düzeyinde yapılır, ham kod düzeyinde değil.** DL 400 dk + DR 300 dk + AMC 500 dk oynayan bir oyuncu: grup düzeyinde FB (700) kazanır, ham kod düzeyinde AMC (500) kazanırdı. Grup, sonucun kullanılacağı birim olduğu için oylama orada yapılmalı. İlk uygulama ham kod düzeyindeydi ve eng'de AM'i 31 yerine 36 gösteriyordu; düzeltildi ve bir testle çivilendi.

**Tarih.** 2026-11-08

---

## D-015: Pozisyon kaynağı üç katmanlı ve her satırda yazılı

**Bağlam.** `position` başlangıç pozisyonudur; sonradan girenlerde `Sub` yazar, yani yedek dakikaları pozisyon bilgisi taşımaz. Hiç ilk 11'de başlamamış **204 oyuncu** var ve kabul kriteri %100 kapsama istiyor.

**Karar.** Üç katman, ve `position_source` kolonu hangisinin kullanıldığını söyler:

| Kaynak | Kural | Oyuncu |
| --- | --- | --- |
| `starts` | Dakika ağırlıklı baskın başlangıç grubu | 1519 |
| `main_position` | `players` boyut tablosundaki ana pozisyon | 74 |
| `unknown` | İkisi de yok → grup `UNK` | 130 |

Ayrıca `position_share` kolonu: baskın grubun başlangıç dakikalarındaki payı.

**Reddedilen üçüncü kaynak — ve nedeni ölçüldü.** Pas konumundan (medyan x, medyan merkez-sapması) en yakın-merkez sınıflandırması denendi ve **bildiğimiz oyuncular üzerinde doğrulandı**:

| Grup | n | Doğruluk |
| --- | --- | --- |
| GK | 109 | %100 |
| CB | 297 | %93 |
| FB | 258 | %87 |
| W | 150 | %80 |
| FW | 233 | %59 |
| DM | 88 | %57 |
| CM | 214 | %37 |
| AM | 100 | %32 |
| **Toplam** | **1449** | **%70,9** |

Orta saha rollerinde yazı-tura seviyesinde; merkez bölgeler sahada fiziksel olarak üst üste biniyor. Dahası bu ölçüm **≥50 paslı** oyuncularda yapıldı, oysa sınıflandırılacak 130 oyuncunun **ortalaması 13 pas** (altısında hiç pas yok). Gerçek doğruluk daha da düşük olurdu. **Tahmin etmektense bilmediğini söylemek.**

**"%100 kapsama" ne demek.** Her oyuncu-sezonun bir satırı ve beyan edilmiş bir kaynağı var (1723/1723, hiç NULL yok). 130 oyuncu dürüstçe `UNK` etiketli, uydurulmuş değil. Kritik nokta: **900+ dakika oynayan 931 oyuncunun tamamı `starts` kaynaklı** — yani hiçbir yüzdelik popülasyonu bu boşluktan etkilenmiyor. Bu bir testle çivili.

**Pozisyon belirsizliği gizlenmiyor.** `position_share` dağılımı: 996 oyuncu ≥0,80; 245 oyuncu 0,60–0,80; 225 oyuncu 0,40–0,60; 53 oyuncu <0,40. Yani her altı oyuncudan biri gerçekten çok pozisyonlu ve grup etiketi onlar için bir basitleştirme. Scouting raporu bunu saklamak yerine göstermeli.

**Tarih.** 2026-11-08

---

## D-016: `player_season` ve `player_season_club` ayrı view'lar

**Bağlam.** Plan "takım değiştirenler için takım bazlı + birleşik satır" istiyor. 48 oyuncu sezon içinde kulüp değiştirmiş.

**Karar.** Tek view içinde iki granülerlik karıştırmak yerine **iki ayrı view**:
- `player_season_club` — oyuncu + kulüp bazında (1771 satır). `op.player_season_stats` bu granülerlikte, çapraz kontrol buna karşı yapılıyor.
- `player_season` — oyuncu + lig-sezon bazında, kulüpler birleşik (1723 satır). Scouting sorularının sorulduğu birim. `clubs` ve `teams` kolonları transferi görünür kılıyor.

**Değerlendirilen alternatifler.**
- *Tek view, `team_id IS NULL` birleşik satır* — `SELECT ... FROM player_season WHERE comp='eng'` sorgusu 48 oyuncuyu **sessizce iki kez sayar**. Gün 5'te LLM'in yazacağı en doğal sorgu bu. İki view bu şekilde yanlış okunamaz.
- *Sadece birleşik view* — kulüp bazlı analiz ve OpenPlay ile çapraz kontrol imkânsızlaşırdı.

**Sonuç/ölçüm.** 1771 − 1723 = **48** = takım değiştiren sayısı (Gün 1'de ölçülen 14+11+23 ile birebir). Dakikalar üç seviyede de aynı: 2 489 523. `matches`, `goals`, `assists`, `shots`, `passes`, `tackles` toplamları fact tablosuyla birebir (testli).

**Tarih.** 2026-11-08

---

## D-017: `float32` toplamadan önce `double precision`'a genişletilir

**Bağlam.** Gün 1'de kendi per-90 hesabımız `op.player_season_stats(per90=True)` ile karşılaştırılmış ve en büyük fark **2,86e-08** çıkmıştı. "Kayan nokta yuvarlaması, önemsiz" diye geçilmişti. Gün 3'te aynı karşılaştırma **tam 0,000e+00** verdi — ve kendi iyi sonucuma şüphelenmek gerekti: ya gerçek bir iyileşme ya da karşılaştırma bozuk.

**Karar.** View'larda `xa`, `xg`, `npxg` kolonları `sum(col::double precision)` ile toplanıyor, `sum(col)` ile değil. Sayım kolonları `bigint` olarak toplanıyor (tam sayı, hatasız).

**Sonuç/ölçüm — hipotez test edildi.** Aynı veriyle üç yol karşılaştırıldı (1064 oyuncu-kulüp satırı, 900+ dakika):

| Yöntem | OpenPlay'den max fark |
| --- | --- |
| `float32`'de topla, sonra `float64`'e çevir (Gün 1'in yolu) | **2,863e-08** |
| `float64`'e çevir, sonra topla | **0,000e+00** |
| Veritabanı view'ı | **0,000e+00** |

Gün 1'in `2,86e-08`'i birebir yeniden üretildi. Yani hata ne OpenPlay'de ne formüldeydi: kaynak `npxg` kolonu `float32` ve 20–38 maç değeri genişletilmeden toplanıyordu. `op.player_season_stats` ise `float64` döndürüyor. Genişletme toplamadan önce yapılınca sonuç **bit düzeyinde aynı**.

**Neden önemli.** Tek başına 1e-8 önemsiz. Ama Gün 4'te bu toplamların üzerine yüzdelikler, Gün 8'de z-skorlar ve kosinüs benzerliği kurulacak; Gün 17'de rapor sayıları veritabanıyla doğrulanacak. Hesabın tabanını bit düzeyinde tekrar üretilebilir tutmak, sonraki farkların **gerçek** fark olduğunu bilmeyi sağlıyor. Ayrıca D-004'teki "tolerans ±0,01" artık gereksiz cömert: ölçülen fark 0.

**Tarih.** 2026-11-08

---

## D-018: Yüzdelik yöntemi — orta-sıra (midrank), yöne göre çevrilmiş

**Bağlam.** Yüzdelikler Gün 7 radarlarında, Gün 8 benzerliğinde ve Gün 14 scouting raporlarında kullanılacak. En küçük gerçek karşılaştırma grubu 23 kişi, metrik bazında bazı gruplar daha da küçülüyor. Fonksiyon seçimi küçük gruplarda belirleyici.

**Karar.** `(sıradaki konum − 0,5) / n`, berabere duyarlı biçimde:
`(altındaki oyuncular + 0,5 × berabere oyuncular) / n × 100`.
SQL'de `percent_rank()` ve `cume_dist()` ikilisiyle ifade ediliyor: `percent_rank × (n−1)` kesin olarak altındakileri, `cume_dist × n` altındaki ve berabereleri sayar; ikisinin ortalaması berabere duyarlı orta-sıradır.

Ayrıca **yüzdelik yöne göre çevrilir**: `higher_is_better = false` olan metriklerde (kötü kontrol, top kaptırma, yapılan faul, hata) `100 − p` uygulanır. Böylece **100 her metrikte "grubun en iyisi"** demektir.

**Değerlendirilen alternatifler.** 10 kişilik gerçek bir grupta (Serie A kanatları) ölçüldü:

| | en düşük oyuncu | en yüksek oyuncu |
| --- | --- | --- |
| `percent_rank()` | **0,0** | 100,0 |
| `cume_dist()` | 10,0 | **100,0** |
| orta-sıra | 5,0 | 95,0 |

- *`percent_rank()`* — en kötüye tam 0 verir. "0. yüzdelik" oyuncunun kendisi dahil herkesten kötü olduğunu ima eder; sonlu bir örneklemde yanlış bir mutlaklık.
- *`cume_dist()`* — simetrik olarak en iyiye tam 100 verir, aynı sorun.
- *`ntile(100)`* — n < 100 olduğunda kovalar boş kalır, sıçramalı sonuç verir.
- *Ham yüzdeliği verip çevirmeyi tüketiciye bırakmak* — radar çizen her yerde aynı `if` tekrarlanır ve bir yerde unutulursa sessizce ters okunur. Yön bir kez, veri katmanında uygulanır.

**Sonuç/ölçüm.** 40 409 satırda yüzdelik aralığı **0,49 – 99,51**; hiçbir satır 0 veya 100 değil, aralık dışı 0. Beraberlik kontrolü: aynı değere sahip **0** oyuncu çifti farklı yüzdelik almış. Yön kontrolü: `miscontrols_per90`'da en az kötü kontrol yapan (0,084/90) yüzdelik 99,3; en çok yapan (1,222/90) yüzdelik 0,7.

**Tarih.** 2026-11-14

---

## D-019: Karşılaştırma grubu — lig içi rol, yetmezse rolü koruyup ligleri havuzla

**Bağlam.** `CLAUDE.md` yüzdelikleri "aynı lig + aynı pozisyon grubu + minimum dakika" içinde tanımlıyor. Ama Gün 3 ölçümü bazı hücrelerin bunu taşıyamayacak kadar küçük olduğunu gösterdi: Serie A'da DM 10, W 10, AM 14; La Liga'da AM 16 oyuncu. 10 kişilik grupta yüzdelik 10 puanlık adımlarla hareket eder.

**Karar.** Üç kademeli:
1. **Lig + ince pozisyon grubu** — tercih edilen karşılaştırma.
2. Hücre `min_group_size`'ın (20) altındaysa → **rolü koru, ligleri havuzla**.
3. Havuzda bile 20'nin altındaysa → **yüzdelik verilme**, `comparison_scope = 'insufficient'`, `percentile = NULL`. Değer yine de raporlanır.

Her satır `comparison_scope`, `comparison_comp` ve `comparison_group_size` taşır; `CLAUDE.md`'nin scouting kuralı zaten her raporda karşılaştırma grubu büyüklüğünü zorunlu kılıyor.

**Bu, `CLAUDE.md`'deki "aynı lig" kuralından bilinçli bir sapmadır** ve ölçüme dayanır. Varyasyon katsayısı (düşük = havuz rol açısından daha homojen):

| Metrik | aynı lig + ince (ideal) | **tüm ligler + ince** | aynı lig + geniş |
| --- | --- | --- | --- |
| `npxg_per90` | 0,932 | **1,264** | 1,399 |
| `crosses_per90` | 0,918 | **0,938** | 1,012 |
| `tackles_per90` | 0,525 | **0,518** | 0,687 |
| `passes_per90` | 0,260 | **0,257** | 0,260 |

Rolü koruyup ligleri havuzlamak **dört metrikte de** ideale daha yakın; `tackles_per90` ve `passes_per90`'da ideali bile geçiyor. Ligi koruyup rolü genişletmek en kötü seçenek. Sezgisel gerekçe: bir Serie A kanadını Serie A forvetleriyle karşılaştırmak, orta yapan bir oyuncuyu bitirici bir oyuncuyla karşılaştırmaktır; Avrupa kanatlarıyla karşılaştırmak benzeri benzerle karşılaştırmaktır.

**Değerlendirilen alternatifler.**
- *Eşiği düşürüp her hücreyi sıralamak* — 10 kişilik grupta yüzdelik yanlış bir hassasiyet iddiası taşır.
- *Geniş gruba (GK/DEF/MID/ATT) düşmek* — ölçümde en kötü; Gün 3'te üretilen `position_group_broad` kolonu yine de duruyor, Gün 8 benzerlik havuzu için adayı.
- *Üç ligi her zaman havuzlamak* — lig stili farkını (Serie A dakikalarının %17,8'i `MC`, PL'de %9,1) tamamen siler.

**Sonuç/ölçüm.** 40 409 satırın dağılımı: `league_position` 38 430 (grup 23–82), `position_pooled` 1 963 (grup 25–102), `insufficient` **16**. Havuza düşen hücreler tam olarak Gün 3'ün işaret ettiği dörtlü (esp AM, ita AM, ita DM, ita W). Yüzdelik verilmeyen 16 satır, penaltı dışı şut çekmiş 8 kalecinin `npxg_per_shot` ve `shot_accuracy_pct` değerleri — 8 kişilik havuz sıralanamaz.

**Tarih.** 2026-11-14

---

## D-020: `config/metrics.yaml` çalışma zamanı sözleşmesidir, dokümantasyon değil

**Bağlam.** `CLAUDE.md`: "Tüm metrikler `config/metrics.yaml`'da tanım, formül, birim ve 'yüksek iyi mi' alanlarıyla tanımlı ve testli olmalı." Böyle bir dosya kolayca **yorum satırına** dönüşür: kod ayrı yerde yaşar, yaml güncellenmez, ikisi sessizce ayrışır.

**Karar.** Yaml çalışma zamanında otoritedir:
1. `football_ai.metrics` yaml'ı **doğrular** — eksik alan, tanımsız kategori, geçersiz birim, string olarak yazılmış `"false"` (ki truthy'dir ve metriği sessizce ters çevirirdi), tekrar eden anahtar.
2. ETL doğrulanmış içeriği `football.metric_definitions` ve `football.metric_config` tablolarına yükler.
3. `football.player_metrics` view'ı eşikleri `metric_config`'ten, yönü ve etiketi `metric_definitions`'tan okur.

Sonuç: yaml'da `min_group_size`'ı değiştirmek migration gerektirmeden davranışı değiştirir. Formül ve tanım metni de veritabanında, yani rapor "bu sayı nasıl hesaplandı" sorusunu SQL ile cevaplayabilir — Gün 14'ün "LLM sayı üretmez" kuralının altyapısı.

**Sapma riski testle kapatıldı.** View'daki `lateral values` listesi elle tutuluyor; üç kaynağın da aynı metrikleri adlandırdığı test ediliyor: yaml ↔ `metric_definitions` ↔ `player_metrics`. Ayrıca her `source_column`'un `player_per90` üzerinde gerçekten var olduğu doğrulanıyor.

**Değerlendirilen alternatifler.**
- *Metrikleri Python sabiti olarak tutmak* — yaml'ın okunabilirliğini kaybeder; metrik eklemek kod değişikliği olur.
- *Yaml'dan SQL üretip migration'a gömmek* — yaml dokümantasyona döner, her eşik değişikliği migration gerektirir.
- *Yüzdelikleri tabloya yazıp ETL'de yenilemek* — bayatlama riski; 1 072 oyuncu × 38 metrik view olarak zaten milisaniyeler içinde hesaplanıyor.

**Sonuç/ölçüm.** 38 metrik, 8 kategori; hepsinde formül, birim, yön ve Türkçe tanım var. `make etl` yaml'ı doğrulayıp yüklüyor. 29 birim testi doğrulayıcıyı, 24 veritabanı testi view'ı sınıyor. Toplam **182 test** yeşil (70 birim + 7 gerçek veri + 105 veritabanı).

**Öğrenilen iki tuzak.**
1. **Pencere çerçevesi.** `count(*) over w` ifadesinde `w` penceresinde `ORDER BY` varsa varsayılan çerçeve `RANGE UNBOUNDED PRECEDING … CURRENT ROW` olur ve `count(*)` bölümün tamamını değil, **o satıra kadarki koşan sayıyı** döndürür — her grubun en düşük değerli oyuncusu için 1. `percent_rank()`/`cume_dist()` sıralama fonksiyonu oldukları için çerçeveyi yok sayar, bu yüzden yalnızca sayımlar bozuldu ve hata sessiz kaldı. Çözüm: sayım için ayrı, **sırasız** pencere tanımlamak. Regresyon testi eklendi.
2. **psycopg ve yüzde işareti.** psycopg sorgu metnini **yorumlar dahil** tarar ve çıplak `%` işaretini parametre yer tutucusu sayar. `n % 2` yerine `mod(n, 2)`; `%` karakteri yorumda bile bırakılmamalı.

**Tarih.** 2026-11-14

---

## D-021: Kendi xG modeli opsiyonelden çıkıp Gün 18'e sabitlendi

**Bağlam.** Plan gözden geçirildiğinde ortaya çıktı: 24 günün AI içeriği ağırlıklı olarak LLM mühendisliği (text-to-SQL, RAG, ajan). Gözetimli öğrenme — veri hazırlama, eğitim/test ayrımı, kalibrasyon, metrik seçimi — yalnızca opsiyonel xG modelinde vardı ve o da tampon günlere bırakılmıştı, yani "zaman kalırsa" demekti.

**Karar.** xG modeli Gün 18'e sabit iş olarak alındı: `ml/xg/`, 2014/15–2024/25 şutlarıyla eğitim, 2025–26 ile test, lojistik regresyon (temel) + LightGBM, log loss / Brier / kalibrasyon eğrisi, OpenPlay xG ile karşılaştırma. Yerini aldığı "hata analizi" işi Gün 17 (rapor kalitesi ölçümü) ve Gün 20'ye (CI eval gate) dağıtıldı; ikisi de zaten hata kategorisi üretip eşiğe bağlıyor.

**Değerlendirilen alternatifler.**
- *Opsiyonel bırakmak* — tampon günler dolma eğilimindedir; pratikte hiç yapılmaz.
- *Gün 15'e eklemek* — Gün 15 zaten xG analizi yapıyor ama tek güne iki iş sığmaz.
- *Benzerliği (Gün 8) ML çalışması saymak* — z-skor ve PCA gözetimsiz; eğitim, kalibrasyon ve genelleme ölçümü yok.

**Sonuç/ölçüm.** Gün 18 kabul kriteri: her iki modelde log loss ve Brier raporlu, kalibrasyon eğrisi çizili, OpenPlay xG ile karşılaştırma tablosu var. Model OpenPlay'den kötüyse gerekçesi yazılı olacak — "kötü çıktı, atladık" kabul edilmiyor.

**Tarih.** 2026-11-15

---

## D-022: SQL koruması — sqlglot allowlist, ama asıl savunma rol

**Bağlam.** Gün 5'ten itibaren LLM üretimi SQL çalıştırılacak. Gün 19'da 30 saldırgan prompt denenecek.

**Karar.** İki bağımsız katman, ve hangisinin asıl olduğu açıkça yazılı:

1. **`football_ro` rolü (asıl savunma).** `INSERT`/`UPDATE`/`DELETE`/`CREATE`/`DROP` yetkisi yok, sunucu tarafında `statement_timeout` var (D-013). **Bir parser'la tartışılabilir; yetkisi olmayan bir rolle tartışılamaz.**
2. **sqlglot doğrulayıcı (hızlı başarısızlık).** Ayrıştır veya reddet; tek ifade; **ağacın tamamını tara**, sadece kökü değil; ilişkiler allowlist'te; tanınmayan fonksiyon reddedilir; `LIMIT` zorunlu.

**Tasarımı belirleyen üç probe bulgusu.** Kurallar varsayımla değil, sqlglot'un gerçek çıktısına bakarak yazıldı:
- **Veri değiştiren CTE'ler kökte `Select` görünüyor.** `with d as (delete ... returning *) select * from d` → root `Select`. Sadece kök tipi kontrol edilseydi geçerdi.
- **CTE adları `Table` düğümü olarak sayılıyor** — ayıklanmazsa meşru `WITH` sorguları reddedilir.
- **sqlglot tanımadığı fonksiyonu `Anonymous` yapıyor.** Test edilen 35 meşru analitik fonksiyonun 34'ü tipli düğüm; yalnızca kendi `position_group()` fonksiyonumuz `Anonymous`. Bu, kuralı tersine çevirmeyi mümkün kıldı: **"tanınmayanı reddet"** — denylist değil, yapısal allowlist. `pg_sleep`, `pg_read_file`, `lo_import`, `dblink` ve akla gelmeyen her şey kapsanır. Denylist yalnızca yazarın hatırladığını engeller.

**Değerlendirilen alternatifler.**
- *Yalnızca rol* — yanlış SQL veritabanına kadar gider, hata mesajı modele yararsız döner, pahalı ama meşru sorgular (LIMIT'siz 1 M satır) engellenmez.
- *Yalnızca parser* — bir ayrıştırıcı atlatılabilir; tek savunma olamaz.
- *Regex tabanlı filtre* — yorum, string ve alt sorgu içinde kaçırır; klasik olarak yanlış araç.
- *Tehlikeli fonksiyon denylist'i* — yalnızca bilinenleri engeller.

**Sonuç/ölçüm.** 36 saldırgan vaka (kriter 20 istiyordu) + 10 meşru sorgu test ediliyor. Saldırılar: düz yazmalar (9), CTE içinde gizli yazmalar (3), ifade yığma (2), kendi korumamızı kapatma (4), futbol dışı veri okuma (8), yan etkili fonksiyonlar (8), bozuk girdi (2). Ayrıca `test_sql_guard_db.py` her saldırının **rol tarafından da** reddedildiğini kanıtlıyor.

**Veritabanının öğrettiği bir ayrıntı.** `GRANT` hata vermiyor: yetkisi olmayan bir rol `GRANT` çalıştırınca PostgreSQL `WARNING: no privileges were granted` deyip **başarı** döndürüyor. Test "hata verdi mi" yerine "yetki kazandı mı" sormalı — ölçüm: `insert/update/delete/truncate` hepsi `false` kaldı. **Hata vermeyen bir ifade, bir şey yaptı demek değil.**

**Tarih.** 2026-11-15

---

## D-023: Şema açıklaması katalogdan üretilir, elle yazılmaz

**Bağlam.** Text-to-SQL'in doğruluğu, modele şemayı nasıl anlattığına bağlı. Elle yazılan şema prompt'ları çürür: migration'da kolon adı değişir, prompt eski adı anlatmaya devam eder, model çalışmayan SQL yazar ve kimse neden olduğunu anlamaz.

**Karar.** `football_ai.sql_agent.schema` her şeyi veritabanından okur: tablo/view listesi (korumanın allowlist'iyle **aynı** liste), kolonlar ve tipleri, view yorumları, **yabancı anahtarlar join ipucu olarak**, ve `metric_definitions`'tan 38 metriğin formülü.

**En çok fark yaratan kısım: düşük kardinaliteli kolonların gerçek değerleri listeleniyor.** `comp` kolonunun `'eng'`, `'esp'`, `'ita'` tuttuğunu bilmeyen model `where comp = 'Premier League'` yazar ve **boş sonuç** alır — bu hatadan beterdir, çünkü hiçbir şey yanlış görünmez. Aynı sebeple 38 metrik anahtarı ve 8 pozisyon grubu da listeleniyor.

Gün 2'de FK'ları bilerek tanımlamıştık (D-008); karşılığı burada alınıyor — join ipuçları katalogdan geliyor, elle yazılmıyor.

**Sonuç/ölçüm.** 18 684 karakter ≈ 4 671 token. Ölçüldü, **kırpılmadı**: şema azaltmak genelde doğruluğu düşürür ve Gün 6 ölçümü olmadan kırpmak yanlış optimizasyon olurdu. Üretim yerel olarak 1,2 saniye sürüyor, süreç başına bir kez.

**Tarih.** 2026-11-15

---

## D-024: Sağlayıcı yüzeyi kararsızdır — uyumsuzlukları sessizce yutma, kaydet

**Bağlam.** Gün 5'te LLM'i bağlarken dört hata arka arkaya geldi ve **hiçbiri testle yakalanamazdı**; kod doğruydu, 180 test yeşildi. Hepsi sağlayıcının gerçek davranışıyla ilgiliydi:

| Hata | Gerçek sebep | Benim ilk tavsiyem |
| --- | --- | --- |
| 404 | Model adı emekli olmuş (`gemini-2.5-flash` yeni anahtarlara kapalı) | "Auth hatası olabilir" ❌ |
| `TimeoutError` çökmesi | `TimeoutError`, `URLError`'ın değil `OSError`'ın alt sınıfı | — |
| `UnsupportedParamsError` | Gemini 3.x `temperature` kabul etmiyor | — |
| 503 ×3 + timeout | Model doymuş | "Timeout'u artır" ❌ |

**Karar.**
- **Model adı sorulur, hatırlanmaz.** `make llm-models` anahtarın eriştiği modelleri listeler **ve gerçekten dener** — `models.list` varlığı söyler, `generateContent` kullanılabilirliği; ikisi aynı şey değil (`gemini-2.5-flash` listede görünüp 404 veriyordu).
- **Reddedilen parametre düşürülür ama kaydedilir.** LiteLLM'in `drop_params=True` kısayolu kullanılmadı: Gün 6 execution accuracy ölçecek ve `temperature`'ı sessizce düşürülmüş bir koşu, uygulanmış bir koşuyla **karşılaştırılamaz**. `temperature_supported` bayrağı rapora giriyor.
- **Geçici ile kalıcı ayrılır.** 503/429/502/timeout → 1s, 2s, 4s bekleyip yeniden dene. 404/401/desteklenmeyen parametre → **hemen fırlat**; denemek yalnızca gerçek mesajı geciktirir.
- **Her çağrı ayrı kaydedilir** (`call_log`). Tek bir toplam süre, "bir yavaş cevap" ile "üç başarısızlık + yeniden deneme"yi ayırt edemez; ikisinin çözümü zıttır.
- **Teşhis son hataya değil tüm diziye bakar.** Üç 503 sonrası bir timeout, "timeout'u artır" değil "model doymuş" demektir.

**Sonuç/ölçüm.** `gemini-3.8-flash` sürekli 503 veriyordu (40,7 sn → 136 sn → başarısız). `gemini-3.1-flash-lite`: tek çağrı, **4,0 sn**. 40 soruluk Gün 6 benchmark'ı: ~3 dakika vs ~30 dakika. Bu fark, prompt değişikliklerini ölçerek geliştirmeyi mümkün kılan şey.

**Tarih.** 2026-11-15

---

## D-025: Zayıf model, prompt geliştirmek için ölçüm aletidir

**Bağlam.** `gemini-3.8-flash` ile `gemini-3.1-flash-lite` aynı soruya farklı SQL üretti:

```sql
-- 3.8-flash
SELECT player, teams, assists FROM football.player_season
WHERE comp = 'eng' ORDER BY assists DESC LIMIT 5
-- 3.1-flash-lite
SELECT player, assists FROM football.player_season
WHERE comp = 'eng' AND minutes_played >= 900 ORDER BY assists DESC LIMIT 5
```

İki fark: lite `teams` döndürmedi ve **gereksiz bir dakika filtresi ekledi.**

**Kök neden modelde değil, prompt'ta.** System prompt'ta şu satır vardı: *"When comparing players outside player_metrics, filter `minutes_played >= 900`."* Kural fazla genişti. "En çok asist" bir **toplam** sorusudur; toplam zaten oynama süresini içinde barındırır ve filtre, az dakikada çok üreten oyuncuyu gizler — **tam da bir scout'un görmek istediği oyuncuyu.** Büyük model muhakeme edip kuralı esnetti, lite model harfiyen uyguladı.

**Karar.**
- **Zayıf model prompt geliştirmenin birincil aletidir.** Güçlü model açıkları muhakemeyle kapatır ve prompt'un eksik olduğunu **söylemez**; sen "prompt iyi" sanırsın, oysa iş gören şey modelin iyi niyetidir. Model değiştiğinde, maliyet düşürüldüğünde veya sağlayıcı modeli emekliye ayırdığında o iyi niyet kaybolur.
- **Zayıf modelin kötü talimatı harfiyen uygulamasının çözümü güçlü model değil, talimatı düzeltmektir.** Güçlü model yalnızca hatayı örter.
- **Diferansiyel test:** aynı soruyu iki modele sor; **uyuşmadıkları her yer prompt'un belirsiz olduğu yerdir.** Doğru cevabı bilmeye bile gerek yok.
- Prompt'ta kural + **örnek** birlikte verilir; örnek daha güçlüdür. Toplam ve oran için ayrı birer few-shot eklendi.

**Sonuç/ölçüm.** Dakika kuralı toplam/oran ayrımıyla yeniden yazıldı, dönülecek kolonlar açıkça belirtildi (oyuncu + kulüp + sorulan sayı + örneklem; `player_metrics` için ayrıca `comparison_group_size`), iki yeni few-shot eklendi. Aynı lite model düzeltmeden sonra **iki soruyu da doğru** yanıtladı: toplam sorusunda filtre yok, oran sorusunda `minutes_played >= 900` var, ikisinde de `teams` dönüyor.

**Gün 6'ya etkisi.** "Execution accuracy" tek başına yetersiz — iki sorgu da çalışıyordu. Benchmark dört boyut ölçecek: çalışıyor mu, sonuç kümesi referansla aynı mı, zorunlu kolonlar var mı, yasaklı yapı yok mu. Dördüncüsü kritik: bazı hatalar **doğru sonuç verir ama yanlış sebeple** — bu soruda dakika filtresi cevabı değiştirmedi (ilk beş zaten 900+ oynamıştı), başka bir soruda değiştirirdi.

**Tarih.** 2026-11-15

---

## D-026: Hakem sonuç kümesidir; doğruluk dört boyutta ölçülür

**Bağlam.** Gün 5 güvenliği ölçtü, doğruluğu ölçmedi. "Çalışıyor" demek birkaç soruyu elle deneyip makul görmekten ibaretti. Benchmark kurmak için önce "doğru" kelimesinin tanımı gerekiyordu.

**Karar.**
- **Hakem sonuç kümesi eşitliğidir, SQL metni değil.** Model referanstan tamamen farklı yazıp aynı satırları döndürdüyse cevap doğrudur. SQL metnini karşılaştırmak prompt'u değil benim yazım tarzımı ölçer.
- Kolonlar **sıraya göre**, isme göre değil (model `value`'yu `npxg_per90` diye adlandırabilir). Referansın kolonları bir **önek** olarak bulunmak zorunda; **fazlası hata değil** — prompt zaten "kulübü ve örneklemi de döndür" diyor, fazlalığı cezalandırmak talimatı cezalandırmak olur.
- Sayılar **bağıl toleransla** (`1e-6`, 1'de tabanlanmış): psycopg `numeric`'i `Decimal`, `double precision`'ı `float` veriyor, aynı per-90 değeri hangi view'dan geldiğine göre iki farklı tip olarak dönüyor. Aralarında `==` son bite oynanan bir kumardır.
- `bool` sayısal yoldan **ayrı tutulur**: Python'da `True == 1`, yani boolean bir kolon bir sayımla sessizce eşleşirdi.
- Satırlar yalnız **soru sıraya duyarlı değilse** sıralanır, ve çoklu küme olarak (kopyalar korunur). Sıralama anahtarı NULL'ları ve karışık tipleri ayrı sıralara koyar — oran metriklerimiz payda 0'da NULL döndürüyor ve NULL'u bir dizeyle karşılaştırmak `TypeError` fırlatır, yani koşu 23. soruda ölürdü.

**Dört boyut.** Sonuç eşitliği tek başına "doğru sayıyı yanlış mantıkla üretmeyi" kaçırıyor (D-025'teki dakika filtresi tam olarak böyleydi). Her soru ayrı ayrı puanlanır:

| Boyut | Sorduğu | Yakaladığı |
| --- | --- | --- |
| `executes` | guard'dan ve veritabanından geçti mi | uydurulmuş kolon |
| `correct` | sonuç kümesi referansla aynı mı | asıl doğruluk (eşik buna) |
| `required_columns` | çıktı kullanılabilir mi | grup büyüklüğü olmayan yüzdelik |
| `no_forbidden` | doğru yoldan mı geldi | toplam sorusunda 900 dakika filtresi |

**Alternatifler.** (a) Yalnız execution accuracy — Gün 5'te iki sorgu da çalışıyordu, biri yanlıştı; ölçüm kör. (b) SQL dizesi karşılaştırma — reddedildi, yukarıda. (c) LLM-as-judge — ölçmek istediğimiz şeyi ölçen aracı aynı aileden bir modele bırakmak; ayrıca deterministik değil.

**Sonuç/ölçüm.** 40 soru, 8 kategori, 36 referans sorgu (4 `unanswerable` kategorisinde referans yok). Gold set'in kendi doğrulaması (`make eval-sql-gold`) ilk koşusunda **kendi yazdığım gold set'te 5 hata buldu:** bir referans yasakladığı view'ı alt sorguda kullanıyordu, ikisi eşitlik sınırında kesiyordu (iki farklı cevap da doğru, karşılaştırıcı ayırt edemez), ikisi `desc` sıralamada NULL'ları "en yüksek" sanıyordu — Postgres `desc`'te NULL'ları başa koyuyor.

**Tarih.** 2026-11-16

---

## D-027: CI deterministik kalır; LLM eval yerelde koşar

**Bağlam.** Gün 6'nın iki müşterisi var: teşhis (hangi soru tipini yanlış anlıyor) ve regresyon koruması (prompt değişikliği dünü bozdu mu). İkincisi CI'a bakar, ama 40 soruluk bir LLM koşusunu her PR'da koşturmak API anahtarı, para ve 503 riski demek.

**Karar.** GitHub Actions'ta **LLM çağrısı yok**. Üç iş: `lint`, `test` (birim testler; `addopts` zaten `data` ve `db` işaretlilerini dışlıyor), `gold`.

`gold` işi pgvector servisi başlatır, **migration'ları uygular, ETL çalıştırmaz**, sonra 40 referans SQL'i guard'dan geçirip `EXPLAIN` ile doğrular.

**Can alıcı nokta:** `EXPLAIN` veri olmadan çalışır ama şemaya karşı **tam** doğrulama yapar. Olmayan kolon, silinmiş view, parse edilemez hale gelmiş referans — hepsi yakalanır. Bu tam olarak sessizce "daha düşük doğruluk oranı"na dönüşen hata sınıfıdır.

**Alternatifler.** (a) CI'da release'ten OpenPlay indirip ETL koşmak: birkaç dakika ve bir ağ bağımlılığı ekliyor, karşılığında yalnız "sayılar hâlâ aynı mı" sorusunu cevaplıyor — onu yerel koşu zaten cevaplıyor. (b) Katalog anlık görüntüsünü commit'leyip ona karşı doğrulamak: anlık görüntünün kendisi sürüklenir. (c) CI'da LLM: sağlayıcı 503'ü PR'ı kırmızı yapar, sinyal kullanılamaz hale gelir.

**Sonuç/ölçüm.** Yerelde atılabilir boş bir veritabanıyla doğrulandı (yalnız migration, ETL yok): şema kontrolleri **36/36** geçti. Sonra bir referanstaki kolon adı bozuldu ve iş **`totals-01`'i adıyla söyleyerek başarısız oldu** — yani sürüklenme gerçekten yakalanıyor. Probe veritabanı silindi.

**Tarih.** 2026-11-16

---

## D-028: Eşik güçlü modele uygulanır; zayıf model teşhis aletidir

**Bağlam.** Plandaki kabul kriteri "execution accuracy ≥ %70". İki model koşuyorsa eşik hangisine uygulanır?

**Karar.** Eşik **yalnız güçlü modele** uygulanır (`--models` listesinin ilki; `make eval-sql`'in çıkış kodu buna bakar). Zayıf modelin puanı raporlanır ama kapı değildir.

**Gerekçe.** D-025'te kurulan ayrım: zayıf model prompt'un belirsiz olduğu yeri gösteren alet, ürünün kalite çıtası değil. Zayıf modeli eşiğe tabi tutmak iki şeyi birbirine karıştırır ve prompt'u zayıf modele göre aşırı uydurmaya (overfit) iter. Tersi — eşiği zayıf modelden kaldırmak — teşhisi kaybeder.

**Sonuç/ölçüm.** **Kriter karşılandı: %80,6 (29/36), eşik %70.**

`gemini/gemini-3.6-flash`, 40 soru, 121 sn, **0 altyapı hatası**, ölçülen maliyet **$0,23** (283.304 girdi + 4.975 çıktı token, sağlayıcının kendi sayımı). Payda 36: 4 `unanswerable` sorusunun referans sonuç kümesi yok.

**Kategori kırılımı:** `totals` %100, `filters` %100, `rates` %83, `percentiles` %80, `transfers` %80, `teams` %80, `match_detail` %40.

Teşhisin değeri iki kolonun ayrılmasında: `rates` doğruluk %83 ama **zorunlu kolon 2/6** — model doğru per-90 değerini hesaplıyor ve dayandığı `minutes_played`'i döndürmüyor. Örneklemi olmayan bir oran, scouting raporunun basmasına izin verilmeyen bir sayıdır. Bu gerçek bir açık, ama doğruluk açığı değil; tek skorda birleştirmek onu gizliyordu.

`match_detail` %40 ile en zayıf kategori ve kimse öngörmedi — şema prompt'unun en az şey söylediği kategori o.

**Kalan 7 hatanın dağılımı:** 4'ü yanlış SQL (`rates-03` yanlış kolon, `percentiles-04` ters metrik tuzağı, `match_detail-03/-04`), 1'i yanlış ilişki (`transfers-02` kulüp bazlı soruyu birleşik view'dan cevapladı; `forbidden` boyutu yakaladı), 1'i yuvarlama tercihi (`teams-02` → `round(sum(xg), 2)`), 1'i farklı sonuç kümesi.

**Yan ölçüm — onarım döngüsü: 0.** 40 soru ilk denemede guard'dan geçti, onarım yolu hiç çalışmadı. İki modelde, iki koşuda aynı sonuç. `generate.py`'nin docstring'indeki tahmin doğruydu.

**Yan ölçüm — D-025 kalıcı mı?** 40 sorudan 39'unda yasak yapı ihlali yok. Tek ihlal `transfers-02` ve o zaten yanlış cevap.

**Zayıf model artık zayıf değil.** `gemini-3.1-flash-lite` de 29/36 aldı, yalnız 4 uyuşmazlık kaldı. D-025'in dayandığı diferansiyel sinyal bu gold set'te inceldi; gerçekten daha zayıf bir model ya da daha zor sorular gerekiyor. Bu, D-028'in kararını geçersiz kılmıyor (eşik yine güçlü modele uygulanır) ama zayıf modelin teşhis değerini bu gold set için azaltıyor.

**Tarih.** 2026-11-17

---

## D-029: Hakem cevabı yargılar, çıktı biçimini değil

**Bağlam.** İlk gerçek koşu %66,7 verdi ve eşiği kaçırdı. 12 hatayı tek tek okuyunca **yalnız 3'ünün yanlış SQL olduğu** çıktı. Dördü şuydu:

```sql
-- referans:  select player, count(distinct comp) ...
-- model:     SELECT player_id, player, COUNT(DISTINCT comp) AS n_comps, ...
```

Bilgi eksiksiz, üstüne fazlası var — ama konumsal önek karşılaştırması 1. kolonda `104058` görüp `'Ademola Lookman'` bekliyordu. Zayıf model aynı soruyu daha az kolonla yazıp doğru aldı: **benchmark daha bilgilendirici cevabı cezalandırıyordu.** Beş hata daha atlanan bağlam kolonuydu (`minutes_played`, `clubs`) — o bir çıktı sözleşmesi ihlali ve yeri `required_columns`.

**Karar.** İki değişiklik, ve hiçbiri tek başına çalışmıyor:

1. **Referans tam olarak cevabı içerir:** satırın kimliği + sorulan ölçü. Prompt'un istediği bağlam (`minutes_played`, `matches`, kulüp) `required_columns`'a taşındı. 24 referans düzenlendi.
2. **Karşılaştırıcı referansın kolonlarını adayın içinde arar** — sırayı koruyarak, ama 0. konumdan başlamak zorunda olmadan. Eşleme **ilk satır çiftinden bir kez** türetilip tüm satırlara uygulanır; satır satır kolon seçmek, adayın her satırda başka bir kolonu seçerek eşleşmesine izin verirdi (test bunu sabitliyor).

Neden birlikte: referansı tek başına küçültmek durumu kötüleştirir. Referans `(player, goals)` olup model `(player, teams, goals)` döndürdüğünde önek `(player, teams)` olur ve yine yanlış çıkar.

**Gold set'in self-check'i de değişti.** Referans artık kendi `required_columns`'unu içermek zorunda değil — tasarım gereği içermiyor. Yerine katalog kontrolü geldi: her zorunlu kolon, referansın okuduğu ilişkilerden birinin **gerçek bir kolonu** olmak zorunda. Bu, `teams` yerine `team` yazmak gibi bir yazım hatasını yakalar; o hata düzeltilmezse her modeli sonsuza kadar başarısız yapar.

**Alternatifler.** (a) Kuralı olduğu gibi bırakıp %66,7'yi kaydetmek: benchmark "doğru cevap" ile "doğru çıktı biçimi"ni tek sayıda karıştırmaya devam ederdi. (b) Yalnız alt-dizi eşleşmesi (referansları küçültmeden): baştaki kimlik kolonu sorununu çözerdi (4 soru) ama atlanan bağlam kolonlarını `correct`'te cezalandırmaya devam ederdi.

**Sonuç/ölçüm.** Doğruluk **%66,7 → %80,6**, model değişmeden. O fark ölçüm hatasıydı. Açıkça söylemek gerekir: ilk sayı model hakkında yanlış, benchmark hakkında doğruydu.

**Bilinen sınırlama.** Tolerans (bağıl 1e-6) sunum tercihini reddediyor: `teams-02` xG'yi iki ondalığa yuvarlayıp yanlış sayılıyor. Toleransı genel olarak gevşetmek gerçek hataları gizlerdi (per-90'da 5,77 ile 5,8 farkı önemlidir), o yüzden tolerans duruyor ve bu soru bilinen bir yanlış-negatif olarak kayıtlı.

**Tarih.** 2026-11-17

---

## D-030: Benchmark güvenilir olduktan sonra bulduğu ilk üç şey prompt'un açıklarıydı

**Bağlam.** Hakem düzeltildikten sonra (D-029) doğruluk %86,1 oldu ve kalan hatalar artık ölçüm hatası değil, gerçek bulgu olarak okunabilir hale geldi. Üçü prompt/şema açığı çıktı. Üçü de **satırları okumakla** bulundu, skora bakmakla değil — bu, Gün 6 boyunca tekrarlayan tek yöntemdi.

**Bulgular ve düzeltmeler.**

1. **Örnek kuraldan güçlüdür — ve benim örneğim kendi kuralımı ihlal ediyordu.** Her iki `player_metrics` few-shot'u `percentile, comparison_group_size` döndürüp `minutes_played`'i atlıyordu. Prompt'ta "örneklemi döndür" kuralı yazılı olmasına rağmen **iki model de örneği kopyaladı**: `rates` kategorisinde 6/6 doğru ama **2/6 zorunlu kolon**. D-025 bunu zaten yazmıştı ("kural + örnek birlikte verilir; örnek daha güçlüdür"); ben kuralı yazıp örneği düzeltmeyi atlamıştım. Örnekler düzeltildikten sonra `rates` kolon skoru **6/6**.

2. **Kural fazla dar kapsamlıydı.** NULL uyarısı "**oran** sıralarken `is not null` ekle" diyordu. `shots.xg` bir oran değil; model kuralı haklı olarak uygulamadı ve "xG'si en yüksek şut" sorusuna değersiz satırlarla cevap verdi. Postgres `desc` sıralamada NULL'ları başa koyuyor. Kural her kolona genişletildi.

3. **Listelenmemiş kolon değeri.** `status_code` 1140 maçın hepsinde tek bir değer taşıyor (`6`), ama `ENUM_LIKE_COLUMNS` haritasında yoktu, yani prompt bunu hiç söylemiyordu. Model `status_code = 3` uydurdu ve "La Liga'da kaç maç oynandı" sorusuna **0** cevabını verdi — sessiz boş sonuç, hatadan beteri. **Asıl kusur haritanın elle tutulması:** bu, D-023'ün kendi ilkesiyle ("şema açıklaması katalogdan üretilir, elle yazılmaz") doğrudan çelişiyor. `status_code` ve `max_period` eklendi; doğru çözüm `pg_stats.n_distinct` ile katalogdan keşif (böylece `passes`'ın 1,08M satırı hiç taranmaz) ve bu koda yorum olarak takip işi diye yazıldı.

**Bir bulgu da gold set'in kendi hatasıydı.** `percentiles-04` "top kaybı metriğinde en iyi" diye soruyordu; `config/metrics.yaml`'da iki metriğin Türkçe etiketi de bu anlama geliyor — `miscontrols_per90` ("Kötü kontrol") ve `dispossessed_per90` ("Top kaptırma"). Model ikincisini seçti ve haklıydı. Soru metriğin kendi etiketini kullanacak şekilde yazıldı; böylece **sözde sınadığı ters-metrik tuzağı ilk kez gerçekten sınandı** ve geçti. Ders: soru metni, projenin kendi sözlüğünden (`metrics.yaml` etiketleri) seçilmeli, serbest Türkçeden değil.

**Sonuç/ölçüm.** %86,1 → **%91,7 (33/36)**. Kategori bazında: `percentiles` 4/5 → 5/5, `rates` zorunlu kolon 4/6 → 6/6, `filters-03` ve `match_detail-04` kurtarıldı. Kalan üç hata: bir gerçek SQL hatası (`rates-03`), bir yuvarlama (`teams-02`, bilinen yanlış-negatif), bir farklı sıralama (`match_detail-02`).

**Yan gözlem — diferansiyel sinyal geri döndü.** Aynı değişiklikler zayıf modelde 29/36 → 26/36 yaptı. Tek koşu olduğu için gürültü olabilir, ama iki model arasındaki fark 2 sorudan 7 soruya çıktı; D-025'in dayandığı sinyal zayıflamak yerine güçlendi. Prompt'u sıkılaştırmanın güçlü modele daha çok yardım ettiği, zayıf modeli ise bir miktar zorladığı okuması makul.

**Gün 6'nın tamamının dekompozisyonu**, çünkü yalnız bir aşaması modelle ilgili:

| Aşama | Doğruluk | Ne değişti |
| --- | --- | --- |
| İlk gerçek koşu | %66,7 | — |
| Hakem düzeltildi (3 kusur) | %80,6 | **+13,9 puan, model aynı** |
| `3.6-flash` → `3.8-flash` | %86,1 | +5,5 puan, fiyat birebir aynı |
| Prompt düzeltildi (3 açık) | **%91,7** | +5,6 puan |

En büyük tek kazanç **benchmark'ı düzeltmekten** geldi, test edilen sistemden değil. Toplam sağlayıcı harcaması, tüm tekrar koşular dahil ~$1,85.

**Tarih.** 2026-11-17

---

## D-031: Touches-share possession proxy ve savunma metriklerinde PAdj formülü

**Bağlam.** Gün 7, `player_profile()` için savunma eylemlerini (tackle, interception vb.) oyuncunun takımının topa sahip olma oranına göre normalize etmek istedi — az topa sahip olan takımın oyuncusu doğal olarak daha fazla savunma eylemi biriktirir. Şemada (`player_match_stats`, `matches`, `passes`, `shots`) hiçbir possession yüzdesi kolonu yok.

**Karar.** Possession proxy'si olarak maçtaki touches payı kullanıldı (`infra/migrations/004_possession.sql`): `team_match_touches` (takım × maç toplam touches) → `match_possession` (iki takımın birbirine göre payı, toplamı her zaman 100) → `player_possession` (oyuncunun oynadığı maçlardaki rakip possession'ının dakika-ağırlıklı ortalaması). Düzeltme formülü, FBref'in possession-adjusted istatistiklerindeki yaklaşımla aynı: `PAdj = raw_per90 × 50 / avg_opponent_possession_pct`. Yalnızca `category = 'defending'` metriklerine uygulanıyor — kullanıcı talebi özellikle savunma eylemleriyle sınırlıydı, `duels` kategorisi (hava topu vb.) dahil edilmedi.

**Değerlendirilen alternatifler.**
- *Possession verisi için ayrı bir kaynak/ETL eklemek* — OpenPlay paketinde possession/tracking verisi yok (CLAUDE.md'de zaten not edilmiş bir sınır); kapsam dışı.
- *PAdj'yi tüm kategorilere uygulamak* — kullanıcı özellikle savunma eylemlerini kastetti; hücum/pas metriklerinde possession düzeltmesi farklı bir varsayım gerektirir ve istenmedi.

**Sonuç/ölçüm.** `match_possession`'da takım+rakip yüzdesi her satırda 100'e toplanıyor (db testiyle doğrulandı). `player_profile()` çağrısı ~328 ms (James Milner, DM, Premier League 2025/26) — Gün 7 kabul kriteri <1 sn.

**Yan not — mplsoccer 3 eksen altını kabul etmiyor.** Tasarımda kalecilere (GK) iki radar kategorisi (goalkeeping, passing) verilmişti; `mplsoccer.Radar` çalışma zamanında "3'ten az eksen" hatası verdi. GK'ye üçüncü kategori olarak `duels` (hava topu mücadeleleri, kalecide de anlamlı) eklendi.

**Tarih.** 2026-11-18

---

## D-032: Benzerlik vektörleri geniş pozisyon havuzunda kurulur; ağırlıklandırma neredeyse etkisiz çıktı

**Bağlam.** Gün 8 `similar_players()` istiyordu: aynı ince pozisyon grubundan "bu oyuncu gibi oynayan" oyuncular. İlk tasarım vektör uzayını **ince** pozisyon grubunda kuruyordu (FW'ye FW metrikleri, CB'ye CB metrikleri). Builder check bunun iki yönden çalışmadığını gösterdi: (1) kabul metriği geniş havuzda CB ile FB'yi karşılaştırmayı gerektiriyor ama CB vektörü 21, FB vektörü 28 boyut ve farklı metrikler farklı slotlarda — aralarında kosinüs **tanımsız**; `pca` konfigürasyonunda tabanlar da tamamen ayrı. (2) z-skor ince grup içinde alınınca her grup ortalaması 0 olur ve CB'yi FB'den ayıran seviye farkı **tam olarak normalize edilip atılır** — yani ölçülmek istenen sinyal, ölçüm kurulmadan önce siliniyordu.

**Karar.** Vektör uzayı **geniş** gruba (GK/DEF/MID/ATT) taşındı. Metrik kümesi o geniş gruptaki ince grupların `POSITION_CATEGORIES` kategorilerinin birleşimi (GK 11, DEF 28, MID 35, ATT 24 boyut); z-skor `(comp, position_group_broad)` hücresinde. Üretimdeki arama yine **ince** gruba filtreleniyor — kullanıcı talebi buydu — ama kabul metriği o filtreyi kaldırarak ölçüyor, böylece başarısız olabiliyor. Üç ağırlıklandırma: `equal`, `role` (`sqrt(1/(C·k_c))` çarpanı; kosinüs iç çarpımı çarpanı karelediği için ağırlığın karekökü uygulanır), `pca` (geniş grup başına, %90 varyans, işaret-normalize ve deterministik).

**Değerlendirilen alternatifler.**
- *Ölçüm için ayrı bir ikinci vektör uzayı kurmak* — üretimde ince ayrımı korurdu ama ~2 kat iş ve 4 ek PCA fit; kazancı ölçülmemiş bir incelik.
- *Kabul metriğini değiştirmek* — hesaplanabilir ama plandaki kriterden sapma; ve "pozisyon tutarlılığı" zaten vektörün işe yarayıp yaramadığını soran doğru soru.
- *İnce grup z-skoru + geniş havuz metriği* — matematiksel olarak imkansız (yukarıdaki (1)).

**Sonuç/ölçüm.** `make eval-similarity`, geniş havuzda top-10 komşunun kaçının aynı ince pozisyonda olduğu, GK hariç (geniş havuzu = ince havuzu, yapı gereği %100), yedi grubun **ağırlıksız** ortalaması (oyuncu başına ortalama CB 221 ve FW 172'yi baskın yapardı):

| Ağırlıklandırma | Pozisyon tutarlılığı | Ortalama top-10 benzerlik |
| --- | --- | --- |
| `equal` | %68,5 | 0,649 |
| `role` | %68,6 | 0,648 |
| `pca` | **%68,9** | 0,704 |

**Hedef %90 tutmadı ve iterasyona girilmedi** — karar önceden alınmıştı: ölç, karışıklık tablosuyla açıkla, sayıyı yuvarlama. Grup bazında (taban oran → sonuç):

| Grup | Taban | `pca` | Kazanım |
| --- | --- | --- | --- |
| CB | %52 | %94,6 | +42,2 |
| FB | %48 | %92,6 | +45,0 |
| FW | %63 | %79,8 | +17,0 |
| W | %37 | %61,0 | +23,8 |
| AM | %20 | %58,5 | +38,4 |
| CM | %54 | %54,0 | **+0,0** |
| DM | %26 | %41,5 | +15,8 |

**Üç bulgu, hiçbiri modelle ilgili değil:**
1. **Ağırlıklandırma bu veri setinde neredeyse etkisiz.** Üç konfigürasyon 0,3 puan içinde. Sıralama ölçütü pozisyon tutarlılığı; `pca` yalnızca o tek ölçütte kıl payı önde olduğu için seçildi. Ortalama top-10 benzerliğinin en yükseğini de o veriyor (0,704 / 0,649) ama bu **lehine değil aleyhine** bir işaret: herkesi birbirine benzer bulan bir konfigürasyon ayırt etmiş olmaz. Gün 6'daki dersin tekrarı: ölçüm kurulunca "hangi varyant kazanır" sorusunun cevabı çoğu zaman "hiçbiri" oluyor.
2. **Savunma keskin, orta saha bir süreklilik.** CB %94,6 ve FB %92,6'ya karşı CM %54,0 (taban oranın tam üstünde, yani **sıfır kazanım**) ve DM %41,5 — DM'nin en yakın komşularının %54'ü aslında CM. AM/CM/DM üç ayrı rol değil, tek bir spektrum; OpenPlay'in taşıdığı top-olayı metrikleriyle ayrıştırılamıyorlar. Bu futbolla ilgili bir bulgu, bir prompt/parametre hatası değil.
3. **Düşük benzerlik skoru bilgi taşıyor.** Elle incelemede Semenyo'nun en yakın komşusu 0,51; sistem zorlama bir eşleşme üretmek yerine düşük skor veriyor.

Staleness: `metric_keys` karşılaştırması metrik kümesindeki değişikliği yakalıyordu ama **eşik değişikliğini yakalamıyordu** — `min_minutes` popülasyonu değiştirir, yani her z-skoru ve PCA tabanını, anahtar listesi birebir aynı kalırken. Migration 006 eşiği satıra yazdı; `similar_players()` artık ikisini de karşılaştırıyor.

Ayrıca: `role`'de tek metrikli `goalkeeping` kategorisinin (`saves_per90`) kaleci benzerliğinin üçte birini sürmesi riski işaretlenmişti; elle incelemede **gerçekleşmedi** — ilk iki isim üç konfigürasyonda da aynı.

Performans: sorgu <200 ms (testle sabit), 1072 oyuncu × 3 ağırlıklandırma = 3216 vektör, tam build saniyeler. Yeniden build bit-bit aynı (md5 `78fc5d33c08d207937530c47d15ec0c9`) — PCA bileşenleri bu yüzden saklanmıyor.

**Tarih.** 2026-11-19

---

## D-033: Rol betimleyicileri vektöre girdi, %90 tutmadı — ve nedeni ölçüldü

**Bağlam.** D-032 pozisyon tutarlılığını %68,9 ile kapatmıştı ve açıklaması "AM/CM/DM gerçekten örtüşüyor" idi. Bu açıklama **ölçülmemişti** — bir gözlemi gerekçe gibi sunmuştu. Kullanıcı itiraz etti, haklıydı.

**Ölçülen üç şey, sırayla.**

*(1) Etiket gürültüsü hipotezi reddedildi.* "Gün 3'ün pozisyon oylaması belirsiz orta sahacılara gürültülü etiket veriyor" hipotezi makuldü: `position_share` ortalaması AM'de 0,665, DM'de 0,740 (CB'de 0,950). Değerlendirmeyi `position_share >= 0.8` oyuncularla sınırladım: manşet yalnızca **%68,9 → %70,5** oldu ve **DM düştü** (%42 → %34). Etiketler tavan değildi.

*(2) Asıl eksik mekânsal boyuttu.* `metrics.yaml`'daki 38 metriğin tamamı hacim veya oran; hiçbiri konum taşımıyor. Oysa DM/CM/AM ayrımı tanımı gereği mekânsal. Pas başlangıç noktasından ölçüldü:

| | ort. x | sapma | merkez hattından uzaklık | sapma |
| --- | --- | --- | --- | --- |
| DM | 50,6 | 3,2 | 21,7 | 3,2 |
| CM | 53,2 | 4,1 | 23,1 | 3,0 |
| AM | 60,5 | 3,5 | 26,5 | 2,8 |
| FW | 62,6 | 3,0 | 24,6 | 4,5 |
| W | 64,1 | 4,1 | 32,1 | 3,2 |
| CB | 38,5 | 3,6 | 22,4 | 4,5 |
| FB | 52,7 | 4,1 | 36,8 | 2,6 |

AM–CM derinlikte ve FW–W genişlikte ~1,9 sd ayrı; CB–FB genişlikte ~4 sd. Vektördeki hiçbir metrik bu ayırt ediciliğe yaklaşmıyordu.

**Karar.** İki betimleyici eklendi (`action_x`, `action_lateral_dev`; migration 007, `player_action_position` view). **`config/metrics.yaml`'a girmediler** — o dosya her metriğe `higher_is_better` dayatıyor ve yüzdelik katmanı "100 her zaman en iyi" garantisi veriyor; saha konumunun iyi/kötü yönü yoktur. Zorlamak her oyuncu profiline anlamsız bir "konumlanma yüzdeliği" ve her Gün 7 radarına saçma bir eksen eklerdi. Vektör bu yüzden bilinçli olarak **metrikler + betimleyiciler**; `vector_feature_keys()` ikisini birleştirir ve staleness kontrolü artık onu karşılaştırır. Ham `y` değil merkez hattından uzaklık: sol ve sağ bek aynı rolün aynasıdır.

**Sonuç/ölçüm.** Manşet **%68,9 → %70,7** (kazanan `pca` → `role` oldu). **Tahminim %75–80'di ve yanlıştı; sayıyı düzeltiyorum.**

| Grup | Taban | önce (`pca`) | sonra (`role`) | fark |
| --- | --- | --- | --- | --- |
| AM | %20 | %58,5 | **%65,1** | +6,6 |
| FB | %48 | %92,6 | **%96,2** | +3,6 |
| W | %37 | %61,0 | **%64,6** | +3,6 |
| CB | %52 | %94,6 | %96,2 | +1,6 |
| DM | %26 | %41,5 | %42,3 | +0,8 |
| FW | %63 | %79,8 | %79,4 | −0,4 |
| CM | %54 | %54,0 | **%50,9** | −3,1 |

*(3) Kalan açık yapısal, ve bu sefer ölçülmüş.* Betimleyiciler **uçlara yardım etti, ortaya zarar verdi.** CM, derinlik ekseninde DM ile AM'nin arasında duruyor, yani her iki taraftan komşu topluyor — karışıklık tablosunda CM'nin komşularının %21'i AM, %28'i DM. Bir eksende sıralı üç sınıfta ortadaki sınıf tanım gereği ayrıştırılamaz.

**Asıl bulgu:** roller gerçekten ayrıksa vektör **%96** yapıyor (CB/FB, genişlikte 4 sd); süreklilikse yapamıyor **ve yapmamalı** — bir DM'nin en benzerinin derin bir CM olması doğru scouting cevabıdır, hata değil. %90 hedefi, verinin tek sürekli eksen taşıdığı yerde ayrık sınıf ayırt etmesini istiyor. Hedef bu haliyle yalnızca ayrık-rol grupları için anlamlı.

**Değerlendirilen alternatifler.**
- *Betimleyicileri `metrics.yaml`'a koymak* — `higher_is_better` sözleşmesini bozar, profil ve radarı kirletir.
- *Kabul metriğini geniş gruba çevirmek* — %100'e yakın çıkar, hiçbir şey ölçmez.
- *CM etiketini kaldırmak / DM+CM birleştirmek* — Gün 3'ün pozisyon şemasını benzerlik uğruna değiştirmek; etki alanı çok geniş, ayrı bir karar.

**Tarih.** 2026-11-19

---

## D-034: RAG kb/ korpusu — bge-m3 (yalnızca dense), başlık bazlı chunking, sabit topic constraint'i

**Bağlam.** Gün 9, Gün 10'un `methodology_search` aracının ve Hafta 3'ün scouting-raporu ajanının okuyacağı metodoloji içeriğini üretiyor. "LLM sayı üretmez" kuralının metin karşılığı: metodoloji bilgisi de modelin eğitim verisinden hatırlanmamalı, projenin kendi yazdığı, kaynağı gösterilebilir metinden gelmeli.

**Karar.**
- **Embedding modeli:** `bge-m3`, `sentence-transformers` üzerinden lokalde çalıştırılıyor (`BAAI/bge-m3`, dense çıktı 1024 boyut). API maliyeti yok (öğrenci bütçesi kısıtı). bge-m3 aynı zamanda sparse çıktı da üretiyor ama bu gün yalnızca dense vektör saklanıyor — sparse/multi-vector Gün 10'un hibrit arama işi. `FlagEmbedding` yerine `sentence-transformers` seçildi: daha hafif bağımlılık zinciri, bu gün için tek ihtiyaç olan dense encode'u doğrudan destekliyor.
- **Chunking:** sabit karakter/token penceresi değil, markdown `## ` başlıklarına göre bölme; 500 kelimeyi aşan bölümler paragraf sınırında ikiye ayrılıyor. Gerekçe: sabit kesim cümle ortasından kesebilir, başlık zaten yazarın kurduğu mantıksal birim.
- **`topic` sabit bir migration-level check constraint** (`infra/migrations/008_kb.sql`, `player_vectors_weighting_check`'i mirror ediyor): 22 sabit değer, kb/ korpusunun A (8 metrik kategorisi) / B (9 proje metodolojisi) / C (5 veri sözlüğü) gruplarına karşılık geliyor. Yeni bir *konu* eklemek migration gerektiriyor — bu sürtünme bilinçli, korpusun şekli şemada görünür kalsın diye.
- **`doc_id` = dosya adı** (frontmatter alanı değil); **`content_hash`** yalnızca boşluk normalizasyonu yapıyor (kelime/noktalama değişikliği farklı hash üretir — fuzzy eşleştirme değil, kazara kopya tespiti).
- `make ingest-kb` CI'da çalışmıyor (Gün 6 kuralı: "CI'da LLM yok, ETL yok" aynı burada da geçerli) — testler sahte/mock `embed_fn` ile çalışıyor, gerçek model yalnızca bu komutla elle indiriliyor.

**Değerlendirilen alternatifler.**
- *Sabit boyutlu sliding-window chunking* — uygulaması basit ama cümle ortasından kesme riski taşıyor; başlık bazlı bölme reddedildi gerekçesiyle elendi.
- *`multilingual-e5-large`* — de çok dilli ve çalışabilirdi, ama sparse çıktı üretmiyor; Gün 10'un hibrit aramasında ikinci bir modele ihtiyaç doğururdu.
- *`topic`'i yalnızca uygulama seviyesinde doğrulamak* — migration'da iz bırakmaz, şemadan korpusun kapsamı okunamaz hale gelir.

**Sonuç/ölçüm.** 22 dosya → **50 chunk** (hedef ≥25'in oldukça üzerinde; `metric-glossary.md` tek başına 8 chunk, kalan 21 dosya 2'şer chunk üretti — hiçbiri boş bölüm içermedi). İkinci `make ingest-kb` çalıştırması aynı sayıyı veriyor, `duplicates_skipped=0` (idempotent, kopya yok). `count(*) = count(distinct content_hash) = 50`; her satırda `source`/`title`/`topic` dolu. 446 birim + 163 db testi yeşil.

**Tarih.** 2026-11-24
