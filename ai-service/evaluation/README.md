# RAG değerlendirme seti

Bu klasör, kişisel veya müşteri verisi içermeyen sentetik regresyon vakalarını barındırır.
Her vaka şunları kontrol eder:

- Beklenen kaynak parçasının retrieval sonucunda bulunması
- Cevapta gerekli terimlerin yer alması
- Kod değişikliğinin temel RAG davranışını bozup bozmadığı

Çalıştırma:

```bash
docker compose exec ai-service python evaluation/run_evaluation.py
```

Yerel LLM ile cevap üretimini de değerlendirmek için:

```bash
docker compose exec ai-service python evaluation/run_evaluation.py --with-ollama
```

Yeni vaka eklerken `cases.json` içine kişisel belge metni, CV, sözleşme veya gizli şirket verisi koymayın. Her vaka sentetik olmalı ve `expectedSourceChunks` ile `requiredAnswerTerms` içermelidir.
