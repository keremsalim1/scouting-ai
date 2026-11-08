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

## Durum
- [x] Gün 0: plan onaylandı
- [x] Gün 1: OpenPlay doğrulama — 3 ligde tüm kontroller `pass`, 98 test yeşil
- [x] Gün 2: PostgreSQL + pgvector, idempotent ETL — satır sayıları kaynakla birebir
- [ ] Gün 3: position_map + player_season / player_per90 view'ları
