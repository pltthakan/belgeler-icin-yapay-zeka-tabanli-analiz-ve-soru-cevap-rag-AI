# Private Document RAG AI Platform

Özel belgeler için açık kaynak model kullanan, React + Spring Boot + Python Flask tabanlı RAG soru-cevap platformu.

Bu proje şu akışı gerçekleştirir:

1. Kullanıcı sisteme kayıt olur / giriş yapar.
2. PDF, DOCX veya TXT belge yükler.
3. Spring Boot backend belgeyi kaydeder ve Flask AI servisine gönderir.
4. Flask servisi PDF/DOCX/TXT metnini (DOCX tabloları dahil) çıkarır, belge profilini oluşturur, chunk'lara böler, açık kaynak embedding modeliyle vektörleştirir ve PostgreSQL içindeki pgvector indeksine kaydeder.
5. Kullanıcı belge hakkında soru sorar.
6. Flask servisi soru türüne göre belge profilini veya en alakalı kaynak parçalarını seçer; yapılandırılmışsa yerel LLM ile, değilse QA/extractive fallback ile belgeye dayalı cevap üretir.
7. Spring Boot cevabı ve kaynakları chat geçmişine; seçilen chunk’ları, prompt’u, model cevabını, süreyi ve hatayı LLM çalışma izine kaydeder.
8. React arayüz cevapları ve kaynak parçaları gösterir.

## Mimari

```text
React Frontend
      ↓
Spring Boot Backend
      ↓
Python Flask AI Service
      ↓
Open-source Embedding + QA Models
      ↓
PostgreSQL + pgvector
```

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
- PostgreSQL
- pgvector (HNSW cosine-similarity araması)
- Maven

### AI Service
- Python Flask
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

### Roller, departman erişimi ve audit log

Roller `EMPLOYEE`, `MANAGER` ve `ADMIN` olarak tanımlıdır. Her yeni belge varsayılan olarak **özel** oluşturulur. Belge sahibi veya admin belgeyi **departmanla paylaşabilir**; aynı departmandaki kullanıcılar belgeyi görüntüleyip soru sorabilir. Departman yöneticisi (`MANAGER`) yalnızca kendi departmanıyla paylaşılmış belgeyi yeniden indeksleyebilir; silme ve paylaşım ayarı belge sahibi veya `ADMIN` ile sınırlıdır.

Yönetici hesabını başlatmak için proje kökündeki yerel `.env` dosyasına mevcut kayıtlı e-posta adresini bir kez yazıp backend’i yeniden başlatın:

```text
APP_BOOTSTRAP_ADMIN_EMAIL=you@example.com
```

Ardından giriş yapıp üst menüdeki **Yönetim** sayfasından departman oluşturabilir, kullanıcıların rol/departmanını atayabilir, son 100 audit kaydını ve LLM/RAG izini inceleyebilirsiniz. Prompt ve seçilen kaynak parçaları belge verisi içerebileceğinden bu ekran yalnızca `ADMIN` rolüne açıktır.

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
- AI Service health: http://localhost:5000/api/health
- PostgreSQL: localhost:5432

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
python app.py
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
├── ai-service/    # Flask RAG servisi
├── frontend/      # React arayüz
├── docker-compose.yml
└── README.md
```

## CV'ye yazılabilecek proje açıklaması

**Kurumsal Belge Analizi ve Soru-Cevap Platformu — RAG AI**

- React, Spring Boot ve Python Flask kullanarak özel PDF/DOCX/TXT belgeleri üzerinde çalışan RAG tabanlı soru-cevap platformu geliştirdim.
- Belge yükleme, metin çıkarma, chunking, embedding üretimi, vektör benzerlik araması ve kaynaklı cevap üretimi süreçlerini uçtan uca tasarladım.
- Spring Security JWT ile rol/departman bazlı belge erişim kontrolü sağladım; PostgreSQL üzerinde kullanıcı, belge, chat geçmişi, audit log ve LLM trace kayıtlarını yönettim.
- JSON yerine pgvector üzerinde HNSW vektör araması, yeniden indeksleme ve kaynak bazlı RAG gözlemlenebilirliği kurdum.
- Açık kaynak sentence-transformers ve transformers modelleriyle OpenAI API kullanmadan belgeye dayalı cevap üretim akışı oluşturdum.

## Önemli notlar

- Bu proje çalışır bir RAG temelidir; production geçişinde migration aracı (Flyway/Liquibase), object storage, şifreleme, merkezi loglama ve retention politikası eklenmelidir.
- Büyük dosyalar ve yüksek trafik için indeksleme kuyruğa alınmalı; object storage ve asenkron worker yapısı kullanılmalıdır.
