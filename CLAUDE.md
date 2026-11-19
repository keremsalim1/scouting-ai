# CLAUDE.md — Football Intelligence AI

Bu dosya her oturumda geçerlidir. Ayrıntılı 24 günlük plan: `docs/PLAN.md`. Kararlar: `DECISIONS.md`.

## Proje
AI destekli futbol scouting ve oyuncu performans analizi platformu. Bir AI/ML mühendisliği portföy projesi; geliştirici (ben) konuları öğrenerek ilerliyor.

- **Sezon:** 2025–26 (tamamlanmış, sabit veri)
- **Ligler:** Premier League (`eng`), La Liga (`esp`), Serie A (`ita`)
- **Süre:** 4 hafta × 6 gün = 24 gün. Hafta sonu sürümleri: `v0.1`, `v0.2`, `v0.3`, `v1.0`
- **Kapsam dışı:** 2026–27 sezonu, canlı veri, kullanıcı bazlı JWT/RLS, PII maskeleme, sentetik sağlık verisi, fine-tuning, video/tracking

## Öncelik sırası (asla değişmez)
1. Temel scouting motoru (metrikler, profil, benzerlik)
2. Güvenilir text-to-SQL
3. RAG (scouting metodolojisi bilgi tabanı)
4. Çalışan LangGraph ajanı
5. Diğer her şey (kendi xG modeli, PitchAPI, ek görseller) — yalnızca tampon günlerde

Geride kalırsak önce 5. maddeden kes.

## Mimari ve teknolojiler
- Python 3.12, `uv`, `ruff`, `pytest`, `pre-commit`
- Veri: `openplay` paketi, pandas, DuckDB (keşif), PostgreSQL + pgvector (tek veritabanı)
- SQL güvenliği: sqlglot allowlist (yalnız SELECT, izinli tablolar), salt-okunur DB rolü, `LIMIT`, statement timeout
- LLM: LiteLLM · Ajan: LangGraph + Pydantic · RAG: bge-m3 / multilingual-e5-large, pgvector + tam metin + RRF, bge-reranker-v2-m3
- API/UI: FastAPI, Streamlit, mplsoccer · Eval: Ragas, MLflow · İzleme: Langfuse · Deploy: Docker Compose, GitHub Actions
- Repo: `src/football_ai/{data,metrics,sql_agent,scouting,rag,agents,api,ui}`, `kb/`, `evals/`, `tests/`, `reports/`, `config/`, `scripts/`, `infra/`

## Veri gerçekleri (OpenPlay data-v0.1.0, doğrulandı)
- Lisans CC-BY 4.0; her çıktıda atıf: **"openplay (Noah Bair)"**. Ham parquet/csv dosyaları asla git'e girmez.
- Sezon `"2025/26"` yazılır, veride `"2526"` saklanır.
- Koordinatlar 0–100, her takım x=100'e hücum eder. Metre: x×1,05, y×0,68.
- `minutes_played` uzatma dahil "expanded minutes" (tam maç ~98 dk).
- `player_match_stats.position` başlangıç pozisyonu; sonradan girenlerde `Sub`.
- `player_season_stats` oyuncu + takım bazında toplar (takım değiştiren = iki satır).
- `score_matches_events` null olabilen boolean → `fillna(True)`.
- Pres (pressure) olayı ve ilerletici taşıma verisi yok.
- Paket indirme 403 verirse: dosyaları `https://github.com/nlbair/openplay/releases/download/data-v0.1.0/<dosya>` adresinden `data/openplay/`'e indir, `OPENPLAY_DATA_DIR=data/openplay` kullan.
- Gün 1 sonucu: 3 ligde 380/380 maç, xG ve pas bitiş koordinatı %100 dolu, known_gaps/data_issues boş.

## Metrik kuralları
- Per-90: `Σ sayım / Σ minutes_played × 90`
- (npxG + xA)/90: `(Σ npxg + Σ xa) / Σ minutes_played × 90`
- Oranlar toplamların oranıdır, maç değerlerinin ortalaması değil (ör. pas isabeti `Σ passes_completed / Σ passes × 100`; xG/şut `Σ npxg / Σ (shots − penalties_taken)`).
- G − xG: `Σ non_penalty_goals − Σ npxg`.
- Payda 0 ise sonuç null (0 değil). Per-90 değerleri yalnızca OpenPlay içinde karşılaştırılır.
- Yüzdelikler: aynı lig + aynı pozisyon grubu + minimum dakika (varsayılan 900) içinde.
- Tüm metrikler `config/metrics.yaml`'da tanım, formül, birim ve "yüksek iyi mi" alanlarıyla tanımlı ve testli olmalı.

## Veri kalitesi politikası
Eşikler hedeftir, durdurucu değildir. Her kontrol `pass` / `degraded` / `disabled` döner. Başarısızlıkta durma: kapsamı, eksik kayıtları ve etkilenen analizleri raporla. Kritik eşik altında (xG veya pas koordinatı doluluğu < %90, maç kapsamı < %95) ilgili özellik `config/feature_flags.json` ile kapatılır ve ajan o aracı çağırmaz.

## Scouting kuralları
- **LLM sayı üretmez.** Raporlardaki tüm sayılar araç/veritabanı çıktısından gelir; LLM yalnızca yorum yazar. Raporlardaki sayılar veritabanıyla doğrulanır.
- Her scouting raporunda zorunlu: oyuncu/takım/lig/sezon, pozisyon grubu, dakika ve maç, kullanılan minimum dakika, örneklem uyarısı, veri kapsamı, metriklerin per-90 + yüzdelik + karşılaştırma grubu büyüklüğü, istatistik tanımları, benzer profiller, xG değerlendirmesi (uygunsa), sınırlamalar, veri atfı.
- Benzerlik: aynı pozisyon grubu, minimum dakika, lig içi z-skor, takım bağlamı (topa sahip olma düzeltmesi). Her sonuçta şu not: **"Benzerlik oyun profilinin benzerliğidir, oyuncu kalitesi değildir."**

## Çalışma şekli
- Ben öğreniyorum: her adımdan önce ne yapacağını ve nedenini kısaca Türkçe açıkla, sonra ne öğrendiğimizi özetle. Kod, yorumlar ve commit mesajları İngilizce.
- Çalışmayan veya test edilmemiş kod bırakma; script'leri çalıştırıp çıktıyı göster.
- Önemli her kararı `DECISIONS.md`'ye ekle: `## D-XXX: Başlık` → Bağlam, Karar, Alternatifler, Sonuç/ölçüm, Tarih.
- Yeni teknikleri ölçerek ekle: benchmark'ta önce/sonra sayıları.
- Her gün sonunda: testler yeşil, README metrik tablosu güncel, anlamlı commit. Her hafta sonunda: Git tag.
- Bir aşamadan sonrakine (ör. Gün 1 doğrulamadan ETL'e) benim onayım olmadan geçme.
- `docs/PLAN.md`'deki kabul kriterleri karşılanmadan günü bitmiş sayma; karşılanmayanı açıkça söyle.

## Komutlar (oluşturuldukça güncelle)
Tam liste: `make help`. Windows'ta `uv` PATH'te değilse `make UV="$APPDATA/Python/Python311/Scripts/uv.exe" <hedef>`.
- `make setup` — sıfırdan her şey: db-up + migrate + validate + etl (~65 sn)
- `make test` / `make test-data` / `make test-db` — birim / gerçek veri / veritabanı testleri
- `make validate` — veri doğrulama raporu + Gün 2–4 bulguları
- `make migrate` / `make etl` / `make counts` / `make etl-bench`
- `make db-up` / `make db-down` / `make db-reset` / `make db-shell`
- `make ask Q="..."` — doğal dil sorusu (LLM anahtarı gerekir) · `make schema-prompt` · `make llm-models`
- `make lint` / `make fmt` / `make check`
- `make eval-sql`, `make eval-rag`, `make eval-agent`, `make eval-reports` — ileride

## Veritabanı (Gün 2)
PostgreSQL 17 + pgvector, tek konteyner, şema `football`. Ayrıntılı gerekçeler D-008…D-013.
- Tablolar: `teams`, `players`, `matches`, `lineups`, `player_match_stats`, `shots`, `passes`, `data_quality`, `data_quality_features`
- `comp` ve `season` her fact tablosunda tekrarlanır; oyuncu/takım adları da denormalize (sezon donmuş + tam yeniden yükleme olduğu için güvenli)
- Doğal anahtarlar; `passes` PK'si `(match_id, event_id, event_id_sub)`. **Ham `events` bu anahtarda tekil değil** — `OffsideGiven` olayları başka olaylarla id paylaşıyor (82 çakışma).
- `q_Cross` → `is_cross` gibi yeniden adlandırmalar ve `is_completed` türetmesi text-to-SQL içindir.
- Idempotency: fact'ler tek transaction'da `TRUNCATE`+`COPY`; `data_quality` append-only, anahtar raporun `generated_at`'i.
- Roller: `football_etl` (yazar), `football_ro` (yalnız SELECT + sunucu tarafı `statement_timeout`). Gün 5 ajanı yalnızca ikinciyi görür.
- Çıktı basan her script `football_ai.console.force_utf8()` çağırmalı — Windows cp1254 varsayılanı Türkçe karakterlerde `print()`'i patlatıyor.

## Pozisyon ve view'lar (Gün 3)
Ayrıntılı gerekçeler D-014…D-017.
- View'lar: `position_map`, `player_season_club` (1771), `player_season` (1723), `player_per90`
- **`player_season` ve `player_season_club` ayrı** — tek view'da karıştırmak 48 takım değiştireni sessizce iki kez saydırır.
- Pozisyon grupları (8): `GK, CB, FB, DM, CM, AM, W, FW`; geniş havuz (4): `GK, DEF, MID, ATT`.
- **`DML`/`DMR` → `FB`** (3-5-2 kanat beki), `DM` değil. `ML`/`MR` → `W`.
- Oylama **grup düzeyinde**, ham pozisyon kodu düzeyinde değil.
- Her satırda `position_source` (`starts` / `main_position` / `unknown`) ve `position_share` var. 900+ dakikanın tamamı `starts`.
- Metrik kolonları toplanırken **`float32` → `double precision` genişletmesi toplamadan önce** yapılır; yoksa per-90'da 1e-8 hata birikir (D-017).
- Oranlarda payda 0 ise `nullif` ile NULL döner, 0 değil.

## Metrikler ve yüzdelikler (Gün 4)
`config/metrics.yaml` çalışma zamanı otoritesidir, dokümantasyon değil. Gerekçeler D-018…D-020.
- Akış: yaml → doğrulama (`football_ai.metrics`) → `metric_definitions` + `metric_config` tabloları → `player_metrics` view'ı. Eşik değiştirmek migration gerektirmez.
- 38 metrik, 8 kategori; her birinde tanım, formül, birim, yön (`higher_is_better`) ve okuduğu kolon var.
- Yüzdelik: berabere duyarlı **orta-sıra** `(altındakiler + 0,5 × berabereler) / n`. `percent_rank` en kötüye 0, `cume_dist` en iyiye 100 verdiği için ikisi de reddedildi.
- **100 her zaman "grubun en iyisi"** — `higher_is_better: false` metriklerde yüzdelik veri katmanında çevrilir, tüketici `if` yazmaz.
- Karşılaştırma grubu: lig + ince rol → (n < 20 ise) **rolü koru, ligleri havuzla** → (yine n < 20 ise) yüzdelik verme, `comparison_scope = 'insufficient'`, değer yine de döner.
- Her satırda `comparison_scope`, `comparison_comp`, `comparison_group_size` var; scouting raporu grup büyüklüğünü yazmak zorunda.
- Yeni metrik eklerken **üç yeri** güncelle: `metrics.yaml`, view'daki `lateral values` listesi — üçüncüsü testtir, sapmayı o yakalar.
- **`count(*) over w` tuzağı:** `w` penceresinde `ORDER BY` varsa çerçeve `RANGE UNBOUNDED PRECEDING … CURRENT ROW` olur ve koşan sayı döner. Sayım için ayrı, **sırasız** pencere kullan.
- **psycopg tuzağı:** sorgu metnindeki çıplak `%` (yorumlar dahil) parametre yer tutucusu sayılır; `mod()` kullan.

## Text-to-SQL (Gün 5)
Gerekçeler D-022…D-025.
- İki katman: **asıl savunma `football_ro` rolü**, sqlglot doğrulayıcı hızlı başarısızlık için. Parser'la tartışılabilir, yetkisi olmayan rolle tartışılamaz.
- Doğrulayıcı: tek ifade; **ağacın tamamı taranır** (veri değiştiren CTE kökte `Select` görünür); ilişki allowlist'i; **tanınmayan fonksiyon reddedilir** (yapısal allowlist, denylist değil); `LIMIT` zorunlu.
- Şema prompt'u **katalogdan üretilir** (`make schema-prompt`), elle yazılmaz. Düşük kardinaliteli kolonların gerçek değerleri listelenir — `comp = 'Premier League'` sessiz boş sonuç verir, hatadan beterdir.
- **Model adı sorulur, hatırlanmaz:** `make llm-models`. `models.list` varlığı, `generateContent` kullanılabilirliği söyler; ikisi aynı değil.
- Reddedilen parametre (`temperature`) düşürülür **ama bayrağa kaydedilir** — sessiz düşürme eval'i karşılaştırılamaz yapar.
- Geçici (503/429/timeout) yeniden denenir, kalıcı (404/401) hemen fırlatılır. Teşhis **son hataya değil tüm çağrı dizisine** bakar.
- **Dakika filtresi soruya bağlı:** oran sorularında `>= 900`, **toplam sorularında yok** (toplam zaten süreyi içerir; filtre az dakikada çok üreteni gizler).
- **Zayıf model prompt geliştirmenin aletidir.** Güçlü model açığı muhakemeyle kapatır ve prompt'un eksik olduğunu söylemez. İki modeli aynı soruya koş: **uyuşmadıkları yer prompt'un belirsiz olduğu yerdir.**

## Text-to-SQL değerlendirmesi (Gün 6)
Gerekçeler D-026…D-029. Gold set: `evals/sql/questions.yaml` (40 soru, 8 kategori).
- **Hakem sonuç kümesidir, SQL metni değil.** Kolonlar isme göre değil, **sıraya göre ama konuma bağlı olmadan** eşleştirilir: referansın kolonları adayın içinde sırayı koruyan bir **alt dizi** olarak bulunur. Model `player_id`'yi başa eklediğinde cevap yanlış sayılmaz (D-029). Eşleme ilk satır çiftinden bir kez türetilip tüm satırlara uygulanır — satır satır kolon seçmek kazara eşleşme üretir.
- **Referans tam olarak cevabı içerir:** satırın kimliği + sorulan ölçü. Prompt'un istediği bağlam (`minutes_played`, `matches`, kulüp) `required_columns`'ın işi. İkisini karıştırmak "doğru cevap" ile "doğru çıktı biçimi"ni tek sayıya çökertir ve %66,7 ile %80,6 arasındaki farkı yaratır.
- **Dört boyut ayrı puanlanır:** `executes`, `correct` (eşik buna), `required_columns`, `no_forbidden`. Dördüncüsü "doğru sayı, yanlış sebep"i yakalar.
- **Üç şey paydadan düşer ve `correct = None` olur:** `unanswerable` kategorisi, `infra_error`, `reference_failed`. Rapor üçünü **ayrı ayrı sayar** — her birinin çözümü farklı.
- **`infra_error` boş `SqlResult.attempts`'ten anlaşılır**, hata metninden değil: gelen her cevap bir `Attempt` ekler, guard'ın reddettiği cevap bile. Attempt yoksa cevap hiç gelmedi.
- **Bozuk referans asla modele yazılmaz.** Migration bir kolonu yeniden adlandırdığında gold set çürür; bu "model yanlış" diye raporlanırsa olmayan bir prompt hatası aranır.
- **Gold set kendi kendisini doğrular** (`make eval-sql-gold`): guard, `EXPLAIN`, few-shot çakışması, kategori sayıları, zorunlu kolonlar gerçek kolon mu (katalogdan), referans kendi `forbidden`'ını ihlal ediyor mu, eşitlik sınırı. **İlk koşuda kendi gold set'imde 5 hata buldu.** Ayrıca kapsam basar: ilişki 8/12, metrik 5/38 — raporlanır, zorlanmaz.
- **Eşitlik iki ayrı yerde tuzak.** (1) Sıralamanın **içinde**: eşit satırların kendi aralarındaki sıra cevabın parçası değil. Karşılaştırıcı **ilk `ORDER BY` anahtarını** paylaşan satırları blok sayar, blok içi sıra serbest; kuyruktaki `, date` yazarın alışkanlığıdır ve karar vermemeli. (2) **Kesme noktasında**: eşitlik varsa soru matematiksel olarak belirsizdir — "en çok gol atılan 5 maç" 7 gollü beş maç varken cevaplanamaz, limit 7ye taşındı. Her iki kontrol aynı anahtarı kullanır; kullanmazsa biri olmayan eşitlik bildirir, diğeri gerçek olanı kaçırır.
- **`desc` sıralamada Postgres NULL'ları BAŞA koyar.** "En yüksek" sorusunda `is not null` filtresi şart; yoksa ilk satırlar değersiz gelir. Payda 0 olan oranlarda (ör. `npxg_per_shot`) bu sık.
- **CI'da LLM yok, ETL yok.** pgvector servisi + yalnız migration + `EXPLAIN`. Veri olmadan şema doğrulaması tamdır; sağlayıcı 503'ü PR'ı kırmızı yapmaz.
- **En yeni flash modeli en çekişenidir.** `gemini-3.8-flash` 5 sorudan 2'sinde 503 verdi (kullanılamaz ölçüm). Model `Makefile`'da değişken: `make eval-sql-both MODEL_STRONG=...`.
- **Ücretsiz katman günlük kotası 40 soruluk bir koşuyu kaldırmıyor.** `3.6-flash` ~15 soruda tükendi. Tam koşu planlarken kotayı hesaba kat; `--category` ve `--only` tam bu yüzden var.
- **`required_columns` sorulan ölçüyü içermez**, yalnız kimlik ve örneklem bağlamını (`player`/`team`, `minutes_played`, `percentile`, `comparison_group_size`). Ölçünün varlığını kolon sayısı kontrolü garanti ediyor; adını şart koşmak hakemin "kolon adları önemsizdir" ilkesiyle çelişir ve takma ad polisliğine dönüşür.
- **Top-N istemeyen soruya keyfi `LIMIT` koymayın.** "80'in üstünde olanlar" bir kümedir; referansı kırpmak tam cevabı yanlış işaretler ve `order_sensitive` küme sorusunda eşitlik sırasını hakem yapar.

## Profil ve radar (Gün 7)
Gerekçe D-031.
- `player_profile(conn, player_id, comp, season)` → `PlayerProfile` (Pydantic, API'ye hazır JSON). `src/football_ai/scouting/profile.py`.
- **Possession verisi yok, touches payından türetildi.** `player_match_stats`'ta `possession` kolonu yok; proxy iki takımın maçtaki `touches` toplamının payı (`infra/migrations/004_possession.sql`: `team_match_touches` → `match_possession` → `player_possession`). FBref/Wyscout'un tracking verisi olmadığında kullandığı aynı proxy.
- **PAdj yalnızca `defending` kategorisinde:** `PAdj = raw_per90 × 50 / avg_opponent_possession_pct`, oyuncunun oynadığı maçlardaki rakip possession'ının dakika-ağırlıklı ortalaması. `duels` ve diğer kategoriler düzeltilmez — kullanıcı talebi savunma eylemleriyle sınırlı.
- **900 dakika altı oyuncu da tam profil alır.** `player_metrics` (Gün 4) bu oyuncuları hiç içermiyor; `player_per90`'dan ham değerlere düşülür, her metrikte `comparison_scope = 'below_minutes_threshold'`, `percentile = null`, ve açık bir `sample_warning` metni — sessizce boş/eksik profil dönmez.
- Radar eksenleri pozisyona özel: `src/football_ai/scouting/categories.py`'deki `POSITION_CATEGORIES`, `discipline` hariç. **mplsoccer'ın `Radar`'ı 3'ten az eksen kabul etmiyor** — GK için tasarımdaki iki kategori (goalkeeping, passing) üçe çıkarıldı (+ duels, hava topu mücadeleleri kalecide de anlamlı).
- Kategori skoru = o kategorideki metriklerin percentile'larının **basit ortalaması**; hepsi null ise skor null, 0 değil (`src/football_ai/scouting/calc.py`).
- Ölçüm: `player_profile` çağrısı ~328 ms (James Milner, DM, Premier League 2025/26) — kabul kriteri <1 sn.

## Benzerlik (Gün 8)
Gerekçe D-032. `similar_players(conn, player_id, comp, season, n, weighting)` → `SimilarityResult` (Pydantic). `src/football_ai/scouting/similarity.py`.
- **Vektör uzayı geniş pozisyon havuzunda, ince grupta değil.** İnce grup kabul metriğini matematiksel olarak tanımsız yapıyordu (CB 21 boyut vs FB 28 boyut, PCA'da ayrı tabanlar) ve ince grup içinde z-skor almak CB'yi FB'den ayıran sinyali tam olarak siliyordu. Boyutlar: GK 11, DEF 28, MID 35, ATT 24.
- Metrik kümesi `POSITION_CATEGORIES`'ten türetiliyor (geniş grup içindeki ince grupların **birleşimi**), ikinci bir liste yok. `discipline` zaten orada hariç.
- **Vektör kategori skorundan değil, tek tek metriklerden kuruluyor.** Kategori ortalaması "çok şut atan az yaratan" ile tersini aynı noktaya çökertir.
- **Kosinüs, Öklid değil:** z-skorlanmış vektörde kosinüs *örüntüyü* karşılaştırır, büyüklüğü değil. "Benzerlik kalite değildir" kuralını gerçek kılan şey bu; Öklid seviyeyi baskın hale getirip özelliği sessizce kalite sıralamasına çevirirdi.
- **`role` ağırlığı karekökle uygulanır.** Kosinüs iç çarpımında boyutu `w` ile ölçeklemek efektif ağırlığı `w²` yapar; spec'teki `1/(C·k_c)` ağırlığı için çarpan `sqrt(1/(C·k_c))` olmalı. Doğrudan uygulamak ağırlığı karesine alır.
- **PCA deterministik olmak zorunda:** bileşen işaretleri fit'ten fit'e dönebilir ve değişmemiş veride tüm vektörleri çalkalar. `random_state` sabit + en büyük mutlak yüklemeyi pozitife zorlayan işaret normalizasyonu. Bu yüzden bileşenler saklanmıyor, yeniden hesaplanıyor. Ölçüm: ikinci build bit-bit aynı (md5 `78fc5d33…`).
- **Imputed girdiler z-skorun ortalama/sapmasından dışlanır.** "Bilmiyoruz" ile "sıfır yaptı" aynı şey değil; dahil etmek dağılımı dolgu değerine doğru çeker ve herkesin skorunu kaydırır. Sayısı her satırda `imputed_dims`.
- **Possession bilinmiyorsa ham değere düşülmez**, boyut imputed sayılır — düzeltilmiş ve ham değerler tek dağılımda karışırsa sessizce yanlış z-skor çıkar.
- `vector(35)` sabit genişlik + sıfır dolgu (MID en geniş). Karşılaştırma hep tek geniş havuz içinde olduğu için dolgu her çifte aynı katkıyı yapar, sıralamayı değiştirmez.
- **`metric_keys` `pca` satırlarında da *girdi* metriklerini tutar** (`pc1…pcN` değil) — scouting raporunun yazmak zorunda olduğu provenance bu. `pca`'da `cardinality(metric_keys) > dims`.
- **Sorgu oyuncusu `player_id` ile dışlanır, satırla değil** — sezon içinde lig değiştirenin iki vektörü var, yoksa "en benzer oyuncu: kendisi" çıkar. Sonuçta bir `player_id` en fazla bir kez görünür.
- **`StaleVectorsError`:** `metrics.yaml` çalışma zamanı otoritesi ama vektörler batch; eşik/metrik değişince depolanmış z-skorlar sessizce çürür. `similar_players()` saklanan `metric_keys` ile canlı konfigürasyonu karşılaştırıp reddeder → `make build-vectors`.
- 900 dk altı oyuncu vektör almaz ve sorgulanamaz → `PlayerNotQualifiedError`. 200 dakikalık per-90 gürültüdür; üstüne benzerlik listesi kurmak tam olarak yasak olan sessiz yanlışlıktır.
- Her sonuçta zorunlu: **"Benzerlik oyun profilinin benzerliğidir, oyuncu kalitesi değildir."**
- Komutlar: `make build-vectors`, `make eval-similarity`.

## Durum
- [x] Gün 0: plan onaylandı
- [x] Gün 1: OpenPlay doğrulama — 3 ligde tüm kontroller `pass`
- [x] Gün 2: PostgreSQL + pgvector, idempotent ETL — satır sayıları kaynakla birebir
- [x] Gün 3: position_map + season/per-90 view'ları — per-90 OpenPlay ile farkı 0
- [x] Gün 4: `config/metrics.yaml` (38 metrik) + yüzdelikler — 10 elle kontrol doğru, 182 test yeşil
- [x] Gün 5: güvenli text-to-SQL — 36 saldırgan vakada zararlı sorgu 0, uçtan uca çalışıyor
- [x] Gün 6: 40 soruluk benchmark + `make eval-sql` + CI — **%91,7 (33/36), eşik %70**; `gemini-3.8-flash`, 112 sn, 0 altyapı hatası, $0,23. 394 birim + 124 db testi yeşil, gold set 36/36. Yol: %66,7 → %80,6 (hakemde 3 kusur) → %86,1 (model 3.6→3.8, fiyat aynı) → %91,7 (prompt'ta 3 açık). **En büyük kazanç benchmark'ı düzeltmekten geldi, modelden değil.** Onarım döngüsü: 40/40 ilk denemede, onarım hiç çalışmadı.
- [x] Gün 7: `player_profile()` + pozisyona özel radar — profil ~328 ms (<1 sn), 900dk altı oyuncu dahil her satırda dakika/pozisyon/kapsam dolu. 406 birim + 130 db testi yeşil.
- [x] Gün 8: `similar_players()` + pgvector + 3 ağırlıklandırma — sorgu <200 ms, 1072 oyuncu × 3 = 3216 vektör. **Pozisyon tutarlılığı %68.9 (`pca`), hedef %90'ın altında** ve bu raporlandı, iterasyona girilmedi (karar: ölç ve açıkla). Üç konfigürasyon 0.3 puan içinde — ağırlıklandırma bu veri setinde neredeyse etkisiz, sinyal metriklerin kendisinde. Savunma keskin (CB %94.6, FB %92.6), orta saha süreklilik (CM %54.0, taban %54 — sıfır kazanım). 419 birim + 154 db testi yeşil. 10 sorgu elle incelendi (`reports/similarity_hand_review.md`), kaleci dahil.
