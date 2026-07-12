# Geniş RAG evaluation paketi

Bu klasör retrieval, cevap üretimi ve guard davranışını kişisel veri içermeyen sentetik vakalarla çevrimdışı ve tekrarlanabilir olarak değerlendirir. Varsayılan koşu ağ erişimi, Ollama, Hugging Face model indirmesi, pgvector veya Redis gerektirmez; hashing embedding ve geçici JSON indeks kullanır.

## Veri setleri

- `cases.json`: 12 uçtan uca pipeline vakası
- `guard_cases.json`: modele hatalı cevap enjekte eden 4 output guard vakası
- `quality_gates.json`: başarısız koşuda non-zero exit code üreten minimum kalite eşikleri

Vakalar doğrudan bilgi, çoklu gerçek, yüzde, para, tarih, süre, olumsuz ifade, benzer varlık ayrımı, OCR bozulması, no-answer ve anlamsız soru sınıflarını kapsar.

## Ölçülen metrikler

- **Recall@K:** İlgili chunk'ların getirilen ilk K kaynak içindeki oranı
- **Precision@K:** Getirilen kaynakların ne kadarının ilgili olduğu
- **MRR:** İlk ilgili chunk'ın sırasına göre reciprocal rank
- **Answer correctness:** Gerekli ve yasaklı cevap gerçeklerine göre deterministik doğruluk
- **Groundedness:** Cevabın claim verification kararının kaynak desteği
- **Citation accuracy:** En az bir doğru kaynak chunk'ının cevapla birlikte dönmesi
- **No-answer accuracy:** Kaynakta olmayan soruların güvenli biçimde reddedilmesi
- **Guard accuracy:** Enjekte edilen yanlış model cevaplarının engellenmesi veya düzeltilmesi
- **Latency:** Ortalama, p50, p95 ve maksimum uçtan uca süre

Bu groundedness ölçümü harici bir LLM hakemi değil, uygulamanın deterministik claim verification çıktısıdır. Üretim kalitesini tek başına kanıtlamaz; regresyonları hızlı ve tekrarlanabilir biçimde yakalamak için kullanılır.

## Çalıştırma

Önce güncel AI service imajını oluşturun:

```bash
docker compose up -d --build ai-service
```

Ardından evaluation paketini çalıştırın:

```bash
docker compose exec ai-service python evaluation/run_evaluation.py
```

Rapor konsola yazılır. Docker Compose koşusunda kalıcı `ai_data` volume'u içindeki `/app/data/evaluation/latest.json` dosyasına, yerel koşuda `ai-service/evaluation/reports/latest.json` dosyasına yazılır. Runtime raporları Git'e eklenmez.

Docker raporunu host çalışma dizinine almak için:

```bash
docker compose cp ai-service:/app/data/evaluation/latest.json \
  ai-service/evaluation/reports/latest.json
```

Aktif Ollama modelini de değerlendirmek için:

```bash
docker compose exec ai-service python evaluation/run_evaluation.py --with-ollama
```

Farklı rapor yolu veya retrieval kaynak sayısı kullanılabilir:

```bash
docker compose exec ai-service python evaluation/run_evaluation.py \
  --top-k 4 \
  --output evaluation/reports/top-k-4.json
```

Kalite kapılarından biri sağlanmazsa komut `1` koduyla çıkar. Yalnızca keşif amaçlı koşuda kapıları exit code açısından devre dışı bırakmak için `--no-gates` kullanılabilir; başarısız metrikler raporda görünmeye devam eder.

## Yeni vaka ekleme

Her vaka benzersiz bir `id`, sentetik `chunks`, `question` ve ilgili kaynaklar için `expectedSourceChunks` içermelidir. Cevap beklentisi aşağıdaki alanlarla tanımlanabilir:

- `requiredAnswerTerms`: cevapta bulunması gereken tüm terimler
- `requiredAnswerTermGroups`: her grup içindeki alternatiflerden en az biri
- `forbiddenAnswerTerms`: cevapta bulunmaması gereken gerçekler
- `shouldAnswer: false`: standart no-answer beklenen vaka
- `evaluationMode: guard` ve `candidateAnswer`: yanlış model cevabını output guard'a doğrudan enjekte eden vaka

Gerçek kullanıcı belgesi, CV, sözleşme, kişisel veri veya gizli şirket içeriği evaluation dosyalarına eklenmemelidir.
