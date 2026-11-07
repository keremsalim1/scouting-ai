# Football Intelligence AI — 24 günlük plan

Kaynak: onaylanmış plan dokümanı. Her günün kabul kriteri karşılanmadan gün bitmiş sayılmaz. Tampon günler: 6, 12, 18, 24.

## Hafta 1 — Veri doğrulama, metrik katmanı, güvenli text-to-SQL → `v0.1`

| Gün | Öğrenme | Görev | Kabul kriteri |
| --- | --- | --- | --- |
| 1 | Event data, OpenPlay veri modeli, koordinatlar, expanded minutes, veri kalitesi dosyaları | Repo iskeleti; openplay kurulumu; `scripts/validate_openplay.py`; `reports/data_validation_2526.md`; DECISIONS D-001…D-006 | Script tek komutla çalışır; 3 lig için kapsam, xG ve pas koordinatı doluluğu, eksik/sorunlu maçlar raporda; testler yeşil |
| 2 | İlişkisel modelleme, Docker Compose, idempotent ETL | PostgreSQL + pgvector; ETL: `matches`, `teams`, `players`, `lineups`, `player_match_stats`, `shots`, `passes`, `data_quality`; `make etl` | Satır sayıları parquet ile birebir; ikinci çalıştırmada kopya yok; veri testleri yeşil |
| 3 | Per-90, minimum dakika, küçük örneklem, pozisyon grupları | `position_map` (dakika ağırlıklı, `Sub` ele alınmış); `player_season` ve `player_per90` view'ları; takım değiştirenler için takım bazlı + birleşik satır | 20 oyuncuda per-90 `op.player_season_stats(per90=True)` ile ±0,01; pozisyon eşlemesi %100 kapsar |
| 4 | xG, npxG, xA, kilit/ilerletici pas, yüzdelikler | `config/metrics.yaml`; türetilmiş metrikler; pozisyon + lig içi yüzdelikler | Her metriğin formülü, birimi ve testi var; yüzdelikler 0–100; 10 elle kontrol doğru |
| 5 | Text-to-SQL, structured output, SQL güvenliği | metrics.yaml'dan şema açıklaması, few-shot, sqlglot doğrulayıcı, salt-okunur rol, timeout, 1 düzeltme denemesi | 20 saldırgan prompt'ta zararlı sorgu çalışmaz |
| 6 | Text-to-SQL değerlendirmesi | 40 soruluk benchmark; `make eval-sql`; GitHub Actions; README | Execution accuracy ≥ %70; CI yeşil; hata analizi README'de |

## Hafta 2 — Profiller, benzerlik, bilgi tabanı, API/UI → `v0.2`

| Gün | Öğrenme | Görev | Kabul kriteri |
| --- | --- | --- | --- |
| 7 | Scouting metodolojisi, rol profilleri, radar, topa sahip olma düzeltmesi | `player_profile(player_id)` + radar | Profil < 1 sn; dakika, pozisyon, kapsam her zaman var |
| 8 | Benzerlik: özellik seçimi, lig içi z-skor, kosinüs, PCA | Pozisyona özel vektörler pgvector'da; `similar_players(...)`; 3 ağırlık konfigürasyonu (eşit / rol / PCA) | Pozisyon tutarlılığı ≥ %90; 10 sorgu elle incelenmiş; kazanan DECISIONS'ta; sorgu < 200 ms |
| 9 | RAG korpus tasarımı, chunking, metadata | `kb/` ~20 metodoloji notu + veri sözlüğü + metrik sözlüğü; `make ingest-kb` | ≥ 25 doküman; her chunk'ta kaynak ve konu; kopya yok |
| 10 | Hybrid search, RRF, reranker, cevapsızlık | `methodology_search` | Her cevapta atıf; korpus dışı soruda uydurma yok |
| 11 | RAG değerlendirmesi | 50 soruluk altın set; ablation (dense / hybrid / +reranker); MLflow | Recall@5 ≥ %85; faithfulness ≥ 0,85; tuzak reddetme ≥ %80 |
| 12 | FastAPI, Streamlit, uçtan uca test | `/sql`, `/players/{id}/profile`, `/players/{id}/similar`, `/kb/ask`; Streamlit oyuncu sayfası | Uçtan uca testler yeşil; README güncel |

## Hafta 3 — Ajan, scouting raporları, xG analizi → `v0.3`

| Gün | Öğrenme | Görev | Kabul kriteri |
| --- | --- | --- | --- |
| 13 | LangGraph: state, node, edge, tool calling | Araçlar: sql_query, player_profile, similar_players, methodology_search, xg_analysis, make_chart; graf (≤ 6 adım); `/agent` | 10 duman testi geçer; adım sınırında kontrollü hata |
| 14 | Rapor standardı, structured output, "LLM sayı üretmez" | `ScoutingReport` Pydantic şeması; Streamlit rapor görünümü | Şema doğrulama %100; düşük dakikada uyarılı rapor |
| 15 | G−xG, xG/şut, ortalamaya dönüş, şut simülasyonu | `xg_analysis(player)` + şut haritası | Simülasyon ortalaması xG toplamıyla ±%1; hücum yönü doğru |
| 16 | Ajan değerlendirmesi | 30 görevlik benchmark; Langfuse; `make eval-agent` | Araç seçimi ≥ %85; görev başarısı ≥ %70; adım/süre/maliyet raporlu |
| 17 | Rapor kalitesi ölçümü | Sayısal doğrulayıcı, zorunlu alan kontrolü, rubrik judge; `make eval-reports` | 20 raporda sayısal doğruluk ≥ %98; zorunlu alanlar %100 |
| 18 | Hata analizi | En sık 3 hata kategorisini düzelt; README | En az bir metrikte ölçülmüş iyileşme; CI yeşil |

## Hafta 4 — Güvenlik temelleri, CI, izleme, yayın → `v1.0`

| Gün | Öğrenme | Görev | Kabul kriteri |
| --- | --- | --- | --- |
| 19 | SQL güvenliği derinlemesine, temel API korumaları | 30 saldırgan prompt; API anahtarı; rate limit; istek boyutu sınırı | Zararlı SQL 0; anahtarsız 401, limit aşımı 429 |
| 20 | CI/CD ve eval gate | Actions: lint → test → hızlı eval (SQL 15, RAG 15, ajan 10) → eşik → image | Bozuk prompt'lu PR başarısız; CI < 10 dk |
| 21 | Gözlemlenebilirlik | Langfuse panoları; eval'ler MLflow'da; p95 gecikme ve maliyet raporu | İsteklerin %100'ü izlenebilir |
| 22 | Deployment | VM veya Cloud Run; `/health`; arayüzde OpenPlay atfı | Demo 30 sn içinde ilk cevabı verir |
| 23 | Teknik anlatım | README, DECISIONS tamamlama, 2–3 dk demo videosu | Bir başkası README ile 15 dk'da yerelde çalıştırabilir |
| 24 | Tampon ve kapanış | Eksikler; opsiyonel PitchAPI çapraz kontrolü; CV maddeleri | Tüm çıkış kriterleri yeşil; `v1.0` tag'i |

## Opsiyonel (MVP'ye bağımlı değil; yalnızca tampon günlerde)
- Kendi xG modeli (`ml/xg/`): 2014/15–2024/25 şutlarla eğit, 2025–26 ile test; lojistik regresyon + LightGBM; log loss, Brier, kalibrasyon; OpenPlay xG ile karşılaştırma.
- PitchAPI çapraz kontrolü (20 maç), StatsBomb tarihsel analiz, rol bazlı skor şablonları.
