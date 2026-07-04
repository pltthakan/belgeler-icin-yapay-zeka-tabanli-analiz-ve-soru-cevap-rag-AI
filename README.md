# Private Document RAG AI Platform

Özel belgeler için açık kaynak model kullanan, React + Spring Boot + Python FastAPI tabanlı RAG soru-cevap platformu.

Bu proje şu akışı gerçekleştirir:

1. Kullanıcı sisteme kayıt olur / giriş yapar.
2. PDF, DOCX veya TXT belge yükler.
3. Spring Boot backend belgeyi kaydeder, durumunu `PROCESSING` yapar ve RabbitMQ'ya belge işleme işi gönderir.
4. Ayrı Spring Boot worker servisi RabbitMQ kuyruğundan işi tüketir, belge dosyasını ortak upload volume'undan okur ve FastAPI AI servisine gönderir.
5. FastAPI servisi PDF/DOCX/TXT metnini (DOCX tabloları dahil) çıkarır, belge profilini oluşturur, chunk'lara böler, açık kaynak embedding modeliyle vektörleştirir ve PostgreSQL içindeki pgvector indeksine kaydeder.
6. Worker işlem sonucuna göre belge durumunu `READY` veya `FAILED` olarak günceller.
7. Kullanıcı belge hakkında soru sorar.
8. FastAPI servisi soru türüne göre belge profilini veya en alakalı kaynak parçalarını seçer; yapılandırılmışsa yerel LLM ile, değilse QA/extractive fallback ile belgeye dayalı cevap üretir.
9. Spring Boot cevabı ve kaynakları chat geçmişine; seçilen chunk’ları, prompt’u, model cevabını, süreyi ve hatayı LLM çalışma izine kaydeder.
10. React arayüz cevapları ve kaynak parçaları gösterir.

## Mimari

<img width="504" height="675" alt="Ekran Resmi 2026-06-30 21 12 07" src="https://github.com/user-attachments/assets/4c229c2e-40ec-44e9-9a59-f36b6b5f6417" />

## Kullanıcı Arayüzü Önizlemesi

<img width="1470" height="768" alt="Ekran Resmi 2026-07-02 22 03 23" src="https://github.com/user-attachments/assets/549dcfd5-9a42-4586-b636-9f73e11bb68c" />

<img width="1417" height="772" alt="Ekran Resmi 2026-07-02 22 07 01" src="https://github.com/user-attachments/assets/94c10384-9566-433b-99a8-641bc8096847" />

<img width="1437" height="770" alt="Ekran Resmi 2026-07-02 22 07 52" src="https://github.com/user-attachments/assets/60cadac8-f887-4c3a-a009-72fea8de20fa" />

<img width="1425" height="762" alt="Ekran Resmi 2026-07-02 22 08 14" src="https://github.com/user-attachments/assets/f05b9ef1-cb34-44f2-ba74-f1db1d5c39f7" />






## Kullanılan teknolojiler

### Frontend
- React
- Vite
- Axios
- React Router

### Backend
- Java 17
- Spring Boot 3
- Spring Security JWT
- Spring Data JPA
- RabbitMQ producer
- PostgreSQL
- pgvector (HNSW cosine-similarity araması)
- Maven

### Worker
- Java 17
- Spring Boot 3
- Spring AMQP RabbitMQ consumer
- Spring JDBC

### AI Service
- Python FastAPI
- pypdf
- python-docx
- sentence-transformers
- transformers
- scikit-learn fallback

### Model tarafı
Varsayılan açık kaynak modeller:

- Embedding: `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`
- Question Answering: `deepset/xlm-roberta-base-squad2`

> Not: İlk çalıştırmada modeller Hugging Face üzerinden indirileceği için internet gerekir. İndirme bittikten sonra cache üzerinden çalışır.

### Doğal dilde cevap üretimi (isteğe bağlı Ollama)

Varsayılan akış, soru-cevap modelini kullanır; bu model metinden cevap parçası çıkarır. `Ana konusu nedir?` gibi belgeyi bütün olarak yorumlamayı gerektiren sorularda sistem doğrudan belge başlığını kullanır. Daha doğal, kısa cevaplar için yerel bir Ollama modeli eklenebilir:

```bash
ollama pull qwen3:8b
```

Docker Desktop üzerinde proje kökünde `.env` dosyasına aşağıdakileri ekleyip servisleri yeniden oluşturun:

```text
OLLAMA_BASE_URL=http://host.docker.internal:11434
OLLAMA_MODEL=qwen3:8b
OLLAMA_TIMEOUT_SECONDS=60
```

```bash
docker compose up --build -d
```

Ollama kapalıysa veya erişilemezse uygulama hata vermez. Belge-genel sorular, yükleme sırasında çıkarılan belge profiliyle; ayrıntılı sorular ise QA ve kısa, belgeye bağlı extractive fallback ile cevaplanır.

Mevcut bir belgenin DOCX tablo çıkarımı ve yeni indeksleme kurallarından yararlanması için ana ekrandaki **Yeniden indeksle** düğmesini kullanın. Başarısız bir yeniden indeksleme, önceki başarılı indeksi silmez.

### pgvector indeksi

Docker Compose, PostgreSQL 16 ile uyumlu `pgvector/pgvector:0.8.2-pg16` imajını kullanır. AI servisinin `PGVECTOR_DSN` bağlantısı varsayılan olarak Compose içindeki PostgreSQL’e bağlıdır. Yüklenen veya **Yeniden indeksle** ile tekrar işlenen her belge için belge profili `rag_document_profiles` tablosuna; chunk metni ve embedding ise `rag_document_chunks` tablosuna yazılır. HNSW indeks, cosine similarity ile en yakın kaynak parçalarını seçer.

Eski JSON indeksleri, daha önce indekslenmiş belgeleri bozmamak için yalnızca geçici uyumluluk fallback’i olarak okunabilir; kalıcı indeksleme hedefi pgvector’dır.

### Heading-aware chunking

AI service, belge metnini indekslemeden önce başlık yapısını tespit etmeye çalışır. 
Yönetmelik, yönerge, sözleşme, rapor ve eğitim dokümanı gibi başlıklı belgelerde 
`Amaç`, `Kapsam`, `Gizlilik`, `Rekabet Etmeme`, `Eğitmenler`, `Program İçeriği` gibi 
bölümler başlıklarıyla birlikte chunk'lanır.

Bu sayede başlık ile başlığın altındaki açıklama farklı kaynak parçalarına dağılmadan 
aynı bağlam içinde tutulur. Örneğin `Eğitmenler kimdir?` veya `İşten ayrıldıktan sonra 
aynı projeyi yapabilir miyim?` gibi sorularda ilgili bölümün bulunma olasılığı artar.

Eğer belgede yeterli başlık yapısı tespit edilemezse sistem otomatik olarak mevcut 
overlap'li semantik chunking yöntemine geri döner.

### Reranker

AI service, pgvector/hybrid search ile daha geniş bir aday kaynak kümesi getirir ve opsiyonel reranker modeliyle en alakalı kaynakları yeniden sıralar.

Varsayılan:

```text
RERANKER_ENABLED=true
RERANKER_MODEL_NAME=cross-encoder/mmarco-mMiniLMv2-L12-H384-v1
RERANKER_CANDIDATE_COUNT=20



### Asenkron belge işleme

Belge yükleme ve yeniden indeksleme işlemleri HTTP isteği içinde tamamlanmaz. Backend dosyayı `/app/uploads` altına kaydeder, belgeyi `PROCESSING` durumuna alır ve RabbitMQ'daki `document-processing.queue` kuyruğuna bir iş mesajı gönderir. `document-worker` servisi bu işi tüketir, aynı Docker volume'u üzerinden dosyaya erişir, AI servisini çağırır ve işlem tamamlandığında belge durumunu `READY` veya `FAILED` olarak günceller.

Bu yapı büyük PDF yüklemelerinde HTTP timeout riskini azaltır. Worker eşzamanlılığı Compose ortamında varsayılan olarak `DOCUMENT_WORKER_CONCURRENCY=1` ve `DOCUMENT_WORKER_MAX_CONCURRENCY=2` ile sınırlıdır; böylece embedding işlemleri AI servisini aşırı yüklemez.

### RAG guardrail katmanı

AI servisi, belge dışı sorularda LLM'i doğrudan çalıştırmaz. Önce retrieval guard ile sorunun seçilen kaynak parçalarıyla ilişkisi kontrol edilir; genel bilgi veya alakasız sorular standart güvenli cevapla döner. Ollama etkinse cevap üretimi sıkı bir belge-bağlam prompt'u ile yapılır ve üretilen cevap tekrar kaynak terimleriyle doğrulanır. Kaynak dışı bilgi eklendiği tespit edilirse cevap iptal edilip "Bu bilgi belgede yer almıyor" fallback'i döndürülür.

### Roller, departman erişimi ve audit log

Roller `EMPLOYEE`, `MANAGER` ve `ADMIN` olarak tanımlıdır. Her yeni belge varsayılan olarak **özel** oluşturulur. Belge sahibi veya admin belgeyi **departmanla paylaşabilir**; aynı departmandaki kullanıcılar belgeyi görüntüleyip soru sorabilir. Departman yöneticisi (`MANAGER`) yalnızca kendi departmanıyla paylaşılmış belgeyi yeniden indeksleyebilir; silme ve paylaşım ayarı belge sahibi veya `ADMIN` ile sınırlıdır.

Yönetici hesabını başlatmak için proje kökündeki yerel `.env` dosyasına mevcut kayıtlı e-posta adresini bir kez yazıp backend’i yeniden başlatın:

```text
APP_BOOTSTRAP_ADMIN_EMAIL=you@example.com
```

Ardından giriş yapıp üst menüdeki **Yönetim** sayfasından departman oluşturabilir, kullanıcıların rol/departmanını atayabilir, son 100 audit kaydını ve LLM/RAG izini inceleyebilirsiniz. Prompt ve seçilen kaynak parçaları belge verisi içerebileceğinden bu ekran yalnızca `ADMIN` rolüne açıktır.

### Kalite paneli

Yönetim ekranındaki **RAG kalite özeti**, tüm kayıtlı LLM çalışma izlerinden aşağıdaki metrikleri hesaplar:

- Toplam AI isteği ve başarılı istek sayısı
- Başarı oranı ve hata sayısı
- Ortalama yanıt süresi
- Ollama ile üretilen yanıtlar
- QA, extractive ve retrieval fallback yanıtları

Metrikler yalnızca `ADMIN` rolüne açıktır. Başarı oranı, hata kaydı olmayan LLM çağrılarının tüm çağrılara oranıdır; bu nedenle model cevabının içerik doğruluğunu değil, isteğin teknik olarak tamamlanmasını ölçer.

### Cevap türleri ve kalite değerlendirmesi

Soru türü otomatik olarak sınıflandırılır:

- **Bilgi sorusu:** Belgedeki doğrudan bilgiyi verir.
- **Özet sorusu:** Belgenin türünü, amacını ve ana konusunu özetler.
- **Değerlendirme sorusu:** “Sence”, “eksikleri neler?”, “nasıl iyileşir?” gibi sorularda belgeye dayalı çıkarım yapar; çıkarımı kesin belge bilgisi gibi sunmaz.

`ai-service/evaluation/cases.json`, kişisel veri içermeyen sentetik regresyon vakalarını içerir. Retrieval ve cevap davranışını kontrol etmek için:

```bash
docker compose exec ai-service python evaluation/run_evaluation.py
```

Aktif Ollama modeliyle cevap üretimini de test etmek için:

```bash
docker compose exec ai-service python evaluation/run_evaluation.py --with-ollama
```

## IDE önerisi

En rahat kullanım:

- Tüm projeyi açmak için: **VS Code**
- Backend için: **IntelliJ IDEA Community / Ultimate**
- AI service için: **PyCharm** veya VS Code
- Frontend için: VS Code

Başlangıç için en pratik yol: root klasörü VS Code ile açıp Docker Compose ile çalıştırmak.

## Docker ile çalıştırma

Bilgisayarında Docker Desktop açık olmalı.

```bash
docker compose up --build
```

Servisler:

- Frontend: http://localhost:3000
- Backend: http://localhost:8080
- AI Service health: http://localhost:5001/api/health
- PostgreSQL: localhost:5433

## Manuel çalıştırma

### 1. PostgreSQL

Lokal PostgreSQL oluştur:

```sql
CREATE DATABASE ragdb;
```

Varsayılan bilgiler:

```text
DB: ragdb
User: postgres
Password: postgres
```

### 2. AI Service

```bash
cd ai-service
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app:app --host 0.0.0.0 --port 5000
```

### 3. Backend

```bash
cd backend
mvn spring-boot:run
```

### 4. Frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend lokal geliştirme adresi:

```text
http://localhost:5173
```

## API uçları

### Auth

```text
POST /api/auth/register
POST /api/auth/login
```

### Documents

```text
POST /api/documents/upload
GET  /api/documents
GET  /api/documents/{id}
POST /api/documents/{id}/reindex
PUT  /api/documents/{id}/sharing
DELETE /api/documents/{id}
```

### Chat

```text
POST /api/chat/documents/{documentId}/ask
GET  /api/chat/documents/{documentId}/history
```

### Admin

```text
POST /api/admin/departments
GET  /api/admin/departments
GET  /api/admin/users
PUT  /api/admin/users/{userId}/access
GET  /api/admin/audit-logs?documentId={optional}
GET  /api/admin/llm-traces?documentId={optional}
GET  /api/admin/quality-summary
```

## Demo kullanım

1. http://localhost:3000 adresine git.
2. Hesap oluştur.
3. PDF/DOCX/TXT belge yükle.
4. Belge durumu `READY` olduktan sonra `Sohbet` butonuna bas.
5. Belgeyle ilgili soru sor.

Örnek sorular:

```text
Bu belgenin ana konusu nedir?
Sözleşmede fesih şartları nelerdir?
Belgede ödeme süresi kaç gün olarak belirtilmiş?
Bu dokümanda hangi yükümlülüklerden bahsediliyor?
```

## Proje yapısı

```text
private-document-rag-ai/
├── backend/       # Spring Boot ana backend
├── ai-service/    # FastAPI RAG servisi
├── frontend/      # React arayüz
├── docker-compose.yml
└── README.md
```

## CV'ye yazılabilecek proje açıklaması

**Kurumsal Belge Analizi ve Soru-Cevap Platformu — RAG AI**

- React, Spring Boot ve Python FastAPI kullanarak özel PDF/DOCX/TXT belgeleri üzerinde çalışan RAG tabanlı soru-cevap platformu geliştirdim.
- Belge yükleme, metin çıkarma, chunking, embedding üretimi, vektör benzerlik araması ve kaynaklı cevap üretimi süreçlerini uçtan uca tasarladım.
- Spring Security JWT ile rol/departman bazlı belge erişim kontrolü sağladım; PostgreSQL üzerinde kullanıcı, belge, chat geçmişi, audit log ve LLM trace kayıtlarını yönettim.
- JSON yerine pgvector üzerinde HNSW vektör araması, yeniden indeksleme ve kaynak bazlı RAG gözlemlenebilirliği kurdum.
- Açık kaynak sentence-transformers ve transformers modelleriyle OpenAI API kullanmadan belgeye dayalı cevap üretim akışı oluşturdum.

## Önemli notlar

- Bu proje çalışır bir RAG temelidir; production geçişinde migration aracı (Flyway/Liquibase), object storage, şifreleme, merkezi loglama ve retention politikası eklenmelidir.
- Büyük dosyalar ve yüksek trafik için indeksleme kuyruğa alınmalı; object storage ve asenkron worker yapısı kullanılmalıdır.
