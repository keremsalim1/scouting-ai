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
- `uv run pytest` — testler (`-m data` gerçek veri testleri)
- `uv run python scripts/validate_openplay.py reports` — veri doğrulama
- `make etl`, `make eval-sql`, `make eval-rag`, `make eval-agent`, `make eval-reports` — ileride

## Durum
- [x] Gün 0: plan onaylandı
- [ ] Gün 1: OpenPlay doğrulama (devam ediyor)
