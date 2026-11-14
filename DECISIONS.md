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
