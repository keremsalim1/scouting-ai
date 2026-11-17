# Gün 6 — Text-to-SQL değerlendirmesi: tasarım

Tarih: 2026-11-16 · Durum: **onaylandı** (2026-11-16) · Plan satırı: `docs/PLAN.md` Gün 6

Onayda teyit edilen: `unanswerable` kategorisi `correct` oranının paydasına girmez; eşik fiilen
36 soru üzerinden hesaplanır ve rapor paydayı açıkça yazar.

## Niyet ve neden

Gün 5'te güvenli bir text-to-SQL hattı kuruldu: şema prompt'u katalogdan üretiliyor, sqlglot
doğrulayıcı zararlı sorguyu reddediyor, `football_ro` rolü son durak. Güvenliği ölçtük (36
saldırgan vakada zararlı sorgu 0). **Doğruluğu ölçmedik.** Şu an "çalışıyor" demek, elle
denediğimiz birkaç sorunun makul görünmesinden ibaret.

Gün 5'in asıl bulgusu şu oldu: zayıf model, prompt'un belirsiz olduğu yeri gösteriyor. Güçlü model
açığı muhakemeyle kapatıyor ve prompt'un eksik olduğunu söylemiyor. Bu gözlem ancak tekrarlanabilir
bir ölçüm varsa işe yarar — yoksa her prompt değişikliği bir tahmin olur.

Bu yüzden Gün 6'nın birincil çıktısı bir puan değil, bir **teşhis**: modelin hangi tür soruyu
yanlış anladığı. İkincil çıktısı regresyon koruması: prompt'a dokunduğumuzda dünü bozup bozmadığımız.

## Hedefler

1. **Kategori bazlı teşhis.** 40 soru, 8 kategori. Doğruluk kategori başına raporlanır. Toplam oran
   tek başına hiçbir şey söylemez; "oran sorularında %40, toplam sorularında %95" cümlesi prompt'un
   neresinin eksik olduğunu söyler.
2. **Tekrarlanabilir koşu.** `make eval-sql` tek komutla çalışır, çıktısı diske yazılır, iki koşu
   karşılaştırılabilir.
3. **Diferansiyel koşu.** Aynı 40 soru güçlü ve zayıf modelde koşulur. Uyuşmadıkları yer prompt'un
   belirsiz olduğu yerdir; rapor bu listeyi ayrıca basar.
4. **LLM'siz CI.** Her PR'da referans SQL'lerin hâlâ geçerli olduğu doğrulanır — API anahtarı,
   para ve 503 riski olmadan.
5. **README'de hata analizi.** Hangi kategoride ne kadar, en sık üç hata tipi, her biri için
   örnek.

## Hedef olmayanlar

- Model kıyaslaması. Gemini'nin GPT'den iyi olup olmadığı bu benchmark'ın sorusu değil; prompt'un
  neyi anlatmadığı sorusu.
- Prompt optimizasyonu. Gün 6 ölçüm kurar ve ilk okumayı alır. Prompt düzeltmeleri ölçüm yerinde
  durduğu sürece sonraki günlerin işi.
- Otomatik düzeltme döngüsünü büyütmek. Şu anki "bir onarım denemesi" davranışı ölçülür, kabul
  edilir ya da reddedilir; değiştirilmez.

## Anti-hedefler (teknik olarak çalışsa bile başarısızlık sayılır)

- **Referans SQL'i dize olarak karşılaştırmak.** Model farklı ama doğru yazdığında yanlış demek,
  benchmark'ı prompt'u değil kendi yazım tarzımı ölçen bir şeye çevirir.
- **Benchmark sorularını few-shot'a koymak.** `FEW_SHOT` içindeki örnekler ile gold set soruları
  ayrı kalmak zorunda. Aksi halde puan prompt'un ezberini ölçer.
- **Sayıları prompt'a sızdırmak.** Beklenen sonuçlar modele hiçbir biçimde gösterilmez.
- **Eşiği geçmek için soruyu kolaylaştırmak.** Zor soru silinmez; `expected_difficulty` ile
  işaretlenir ve raporda kalır.
- **CI'ı LLM'e bağımlı kılmak.** Sağlayıcı 503 verdiğinde PR'ın kırmızı olması, ölçümün kendisini
  güvenilmez yapar.

## Kısıtlar

- Veri sabit: 2025/26, 3 lig, tamamlanmış sezon. Beklenen sonuçlar bu yüzden sabit kalır.
- Ham OpenPlay dosyaları git'e girmez, yani CI'da dolu bir veritabanı yok.
- Sağlayıcı yüzeyi dengesiz: 503, parametre reddi, model kaldırma. Eval bunları hata olarak değil
  **altyapı sorunu** olarak raporlamak zorunda; yoksa doğruluk oranı sağlayıcının o günkü haline
  göre oynar.
- Gemini 3.x `temperature`'ı reddediyor, yani koşular tam deterministik değil. Tasarım bunu
  gizlemek yerine görünür kılar.

## Karar verilenler

### Hakem: sonuç kümesi eşitliği (kullanıcı kararı)

Her soruda elle yazılmış bir referans SQL var. Hakem, referans SQL'in sonuç kümesi ile modelin
SQL'inin sonuç kümesini karşılaştırır. Satırlar ve sayılar eşleşiyorsa **doğru** — model farklı
yazmış olsa bile. SQL yapısı farklıysa rapora "farklı yapı" notu düşülür, puana etki etmez.

Karşılaştırma kuralları:
- Kolonlar **sıraya göre**, isme göre değil. Model `as goals` yerine `as total_goals` yazabilir.
- Modelin fazladan kolon döndürmesi hata değil; referansın kolonlarının hepsi, aynı sırada, bir
  önek olarak bulunmak zorunda. (Prompt zaten "kulübü de döndür" diyor; fazlası cezalandırılamaz.)
- Ondalık sayılar `abs(a - b) <= 1e-6 * max(1, abs(b))` toleransıyla.
- `order_sensitive: true` olan sorularda satır sırası önemli (sıralama soruları). Diğerlerinde
  satırlar sıralanıp karşılaştırılır.
- NULL yalnızca NULL'a eşittir. 0 değil — metrik kurallarımız payda 0'da NULL döndürüyor.

### Dört boyutlu puanlama

Sadece sonuç eşitliği, doğru sayıyı yanlış mantıkla üreten sorguyu kaçırır. Her soru dört boyutta
ayrı puanlanır ve rapor dördünü ayrı basar:

| Boyut | Ne sorar | Neden |
| --- | --- | --- |
| `executes` | Sorgu guard'dan geçti ve veritabanında hata vermeden koştu mu? | Taban çizgisi. Uydurulmuş kolon burada yakalanır. |
| `correct` | Sonuç kümesi referansla eşleşiyor mu? | Plandaki "execution accuracy" bu. Eşik buna uygulanır. |
| `required_columns` | Soru tipinin zorunlu kolonları var mı? | `player_metrics`'ten `percentile` ama `comparison_group_size` olmadan dönen cevap, scouting raporunda kullanılamaz. Sayı doğru, çıktı sakat. |
| `no_forbidden` | Yasak yapı var mı? | Toplam sorusunda `minutes_played >= 900`; birleşik toplamda `player_season_club`. İkisi de "doğru görünen yanlış". |

`required_columns` ve `no_forbidden`, modelin ürettiği SQL'in sqlglot ağacı üzerinden kontrol
edilir — dize araması değil. Soru dosyasında her soru kendi listesini taşır.

Başlıkta tek bir sayı duruyorsa o `correct` oranıdır; diğer üçü teşhis kolonlarıdır.

### Onarım döngüsü ölçülür (benim kararım)

`generate.py`'nin kendi docstring'i şöyle diyor: "A second repair rarely helps... Day 6 measures
whether that holds." Yani bu tasarımın cevaplaması gereken bir soru var.

Her soru için rapor `repaired` alanını taşır: guard ilk SQL'i reddetti mi, onarım denemesi
sonucu düzeldi mi. Rapor üç sayı basar: ilk denemede geçen, onarımla geçen, onarımdan sonra da
reddedilen. "Bir onarım denemesi yeterli" iddiası ancak ikinci sayı anlamlı ve üçüncü küçükse
doğrudur.

### İki taraf da aynı guard'dan geçer (benim kararım)

Referans SQL ve modelin SQL'i **aynı** `guard.validate` yolundan geçip guard'ın döndürdüğü SQL
koşulur. Sebep: guard eksik `LIMIT`'i kendisi ekliyor. Yalnızca bir tarafa uygulanırsa referans
200 satır, model 10 satır döndürür ve eşleşme sahte biçimde başarısız olur. Bir referans SQL
guard'dan geçmiyorsa bu gold set hatasıdır, `make eval-sql-gold` onu yakalar.

Koşum rolü `football_ro` — ajanın gördüğü rolün aynısı. Eval, ajandan daha fazla yetkiyle
koşarsa ajanın gerçekte yapamadığı şeyi ölçer.

### Çıkış kodu

`make eval-sql` eşik altında **1 ile çıkar**. Gün 20'nin eval gate'i bu çıkış koduna bağlanacak;
şimdi doğru kurmak sonra sarmalayıcı yazmaktan kolay. `make eval-sql-both` yalnızca güçlü modelin
eşiğine bakar.

### Kategoriler ve dağılım

8 kategori, 40 soru. İkisi kullanıcının işaret ettiği tuzaklar:

| Kategori | Soru | Neyi ölçer |
| --- | --- | --- |
| `totals` | 5 | Sezon toplamları. **Dakika filtresi olmamalı.** |
| `rates` | 6 | Per-90 ve yüzdeler. **Dakika filtresi olmalı**, oranlar toplamların oranı. |
| `percentiles` | 5 | `player_metrics`, karşılaştırma grubu, 100 = en iyi. |
| `transfers` | 5 | Takım değiştirenler. `player_season` mı `player_season_club` mı — 48 oyuncu burada sessizce iki kez sayılıyor. |
| `teams` | 5 | Takım düzeyinde toplama. |
| `match_detail` | 5 | `matches`, `shots`, `passes`, `lineups`. |
| `filters` | 5 | Literal değerler (`comp = 'eng'`, `'Premier League'` değil), pozisyon grupları, sezon. |
| `unanswerable` | 4 | Veride olmayan şeyler: pres, ilerletici taşıma, 2026/27. Uydurulmuş kolon yakalanır. |

`unanswerable` kategorisinde referans sonuç kümesi yoktur; yalnızca `executes` ve `no_forbidden`
puanlanır (uydurulmuş kolon ya da şema dışı tablo yok). Bu kategori `correct` oranının paydasına
girmez ve raporda ayrı satır olarak durur.

### Gold set biçimi

`evals/sql/questions.yaml`, soru başına:

```yaml
- id: rates-01
  question: "La Liga'da 90 dakikada en çok kilit pas atan orta sahalar"
  category: rates
  reference_sql: |
    select player, teams, key_passes_per90, minutes_played
    from football.player_per90
    where comp = 'esp' and position_group = 'CM' and minutes_played >= 900
    order by key_passes_per90 desc
    limit 10
  order_sensitive: true
  required_columns: [player, teams, minutes_played]
  forbidden: []          # ör. totals'ta: [minutes_filter]
  notes: "Oran sorusu: eşik olmadan 40 dakikalık bir cameo listeyi domine eder."
```

Sorular Türkçe yazılır — kullanıcı Türkçe soruyor, `ask.py` Türkçe'yi zaten işliyor, ve Gün 5'teki
503 hatası Türkçe bir soruda çıktı. Birkaç soru İngilizce yazılır ki dil duyarlılığı görülsün.

### Modeller ve eşik (kullanıcı kararı)

- Güçlü model (`gemini/gemini-3.8-flash`, varsayılan): **`correct` ≥ %70** — planın kabul kriteri
  buna uygulanır.
- Zayıf model (`gemini/gemini-3.1-flash-lite`): bilgi amaçlı. Puanı raporlanır, eşiğe tabi değil.
- Rapor bir **uyuşmazlık tablosu** basar: hangi sorularda ikisi farklı sonuç verdi. Gün 5'in
  bulgusu şu: o liste prompt'un belirsiz olduğu yerin listesidir.

### CI deterministik, LLM yerelde (kullanıcı kararı)

GitHub Actions'ta LLM çağrısı yok. CI'ın koştuğu üç iş:

1. `lint` — `ruff check` + `ruff format --check`
2. `test` — birim testler (mevcut `addopts` `data` ve `db` işaretlilerini zaten dışlıyor)
3. `gold` — Postgres (pgvector) servisi başlat, **migration'ları uygula, ETL çalıştırma**, sonra
   40 referans SQL'in her birini guard'dan geçir ve `EXPLAIN` ile koştur.

Üçüncüsünün can alıcı noktası: `EXPLAIN` veri olmadan çalışır ama şemaya karşı tam doğrulama yapar.
Olmayan kolon, kaldırılmış view, yeniden adlandırılmış tablo — hepsi yakalanır. Yani gold set,
şema sürüklenmesine karşı CI'da korunur, OpenPlay indirmesine gerek kalmadan. Bu benim kararım;
alternatifi (CI'da release'ten veri indirip ETL koşmak) birkaç dakika ve bir ağ bağımlılığı
ekliyordu, karşılığında da sadece "sayılar hâlâ aynı mı" sorusunu cevaplıyordu — onu yerel koşu
zaten cevaplıyor.

### Komutlar

| Komut | Ne yapar | LLM | DB |
| --- | --- | --- | --- |
| `make eval-sql` | 40 soru, varsayılan model, rapor yaz | var | dolu |
| `make eval-sql-both` | iki model + uyuşmazlık tablosu | var | dolu |
| `make eval-sql-gold` | referans SQL'ler guard + `EXPLAIN` | yok | boş yeter |

`eval-sql` şu bayrakları alır: `--model`, `--category`, `--only <id,...>`, `--out`. Alt küme
koşmak 40 çağrının parasını ödemeden tek kategoriyi düzeltmeyi mümkün kılar.

### Çıktılar

- `reports/eval_sql/<run_id>.json` — makine okunur: her soru için üretilen SQL, dört boyut, hata
  metni, gecikme, `call_log` (Gün 5'te eklenen per-çağrı enstrümantasyonu), düşülen parametreler.
- `reports/eval_sql/<run_id>.md` — insan okunur: kategori tablosu, dört boyut, uyuşmazlık tablosu,
  en sık hata tipleri, altyapı hataları ayrı sayılmış.
- `reports/eval_sql_latest.md` — son koşunun kopyası; README buna bağlanır.

Ham üretilen SQL'in saklanması şart: bir uyuşmazlığı sonradan inceleyebilmenin tek yolu.

### Altyapı hatası ≠ yanlış cevap

Sağlayıcı 503/429/timeout verdiğinde ve yeniden denemeler de tükendiğinde, soru `infra_error`
olarak işaretlenir ve `correct` oranının **paydasından düşer**. Rapor kaç soruda bunun olduğunu
başlıkta yazar. Payda değiştiği için bu sayı gizlenemez; `infra_error` oranı %10'u geçerse rapor
"bu koşu karşılaştırılabilir değil" uyarısı basar.

## Builder'a bırakılanlar

- 40 sorunun kendisi ve referans SQL'leri. Kural: her referans SQL elle `make db-shell`'de
  koşulup çıktısı göz ile doğrulanacak, LLM'e yazdırılmayacak.
- Sıralama sorularında eşitlik sınırı: "en çok asist yapan 5" sorusunda 5. sırada eşitlik varsa iki
  farklı ama eşit geçerli cevap doğar. Soru yazarken `limit` değeri eşitlik sınırına denk
  gelmeyecek biçimde seçilir; bunu doğrulayan bir kontrol gold set'in parçası olur.
- `required_columns` / `forbidden` kontrollerinin sqlglot ağacı üzerinde nasıl ifade edileceği.
  `minutes_filter` gibi sembolik adlar bir eşleyici tablosunda tutulur.
- Modül yerleşimi: `src/football_ai/evals/sql/` (grader, runner, rapor) + `scripts/eval_sql.py`.
- Gold set'in kendi doğrulaması: `questions.yaml` alanları tipli bir yükleyiciden geçer (id tekil,
  kategori bilinen bir değer, `unanswerable` dışında `reference_sql` zorunlu). `metrics.yaml`'da
  işe yarayan desen bu; eval dosyası da çalışma zamanı otoritesi olacak.
- `run_id` biçimi (öneri: `<UTC zaman damgası>-<model kısaltması>`).
- CI workflow'un uv önbelleği ve Postgres servisi ayrıntıları.
- DECISIONS kayıtları: D-026 sonuç kümesi hakemi + dört boyut, D-027 CI deterministik / LLM yerel,
  D-028 eşik güçlü modele.

## Kabul kriterleri

Plandan: `correct` ≥ %70 (güçlü model), CI yeşil, hata analizi README'de. Buna ek olarak:

- 40 referans SQL'in hepsi `make eval-sql-gold`'dan geçer.
- `make eval-sql` tek komutla çalışır ve iki dosya yazar.
- Rapor kategori başına dört boyutu ayrı basar.
- Uyuşmazlık tablosu en az bir satır üretir (üretmezse zayıf model gerçekten koşulmamıştır).
- Gold set soruları `FEW_SHOT` içindekilerle çakışmaz; bunu bir test doğrular.
- `infra_error` sayısı raporun başlığında görünür.
