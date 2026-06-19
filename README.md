# Private Document RAG AI Platform

Özel belgeler için açık kaynak model kullanan, React + Spring Boot + Python Flask tabanlı RAG soru-cevap platformu.

Bu proje şu akışı gerçekleştirir:

1. Kullanıcı sisteme kayıt olur / giriş yapar.
2. PDF, DOCX veya TXT belge yükler.
3. Spring Boot backend belgeyi kaydeder ve Flask AI servisine gönderir.
4. Flask servisi metni çıkarır, chunk'lara böler, açık kaynak embedding modeliyle vektörleştirir ve lokal vektör indeksine kaydeder.
5. Kullanıcı belge hakkında soru sorar.
6. Flask servisi en alakalı belge parçalarını bulur, açık kaynak QA modeliyle belgeye dayalı cevap üretir.
7. Spring Boot cevabı ve kaynakları chat geçmişine kaydeder.
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
Local Persistent Vector Index
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
ollama pull qwen2.5:7b
```

Docker Desktop üzerinde proje kökünde `.env` dosyasına aşağıdakileri ekleyip servisleri yeniden oluşturun:

```text
OLLAMA_BASE_URL=http://host.docker.internal:11434
OLLAMA_MODEL=qwen2.5:7b
OLLAMA_TIMEOUT_SECONDS=30
```

```bash
docker compose up --build -d
```

Ollama kapalıysa veya erişilemezse uygulama hata vermez; QA ve kısa, belgeye bağlı extractive fallback ile devam eder.

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
DELETE /api/documents/{id}
```

### Chat

```text
POST /api/chat/documents/{documentId}/ask
GET  /api/chat/documents/{documentId}/history
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
- Spring Security JWT ile kullanıcı bazlı belge erişim kontrolü sağladım; PostgreSQL üzerinde kullanıcı, belge ve chat geçmişi kayıtlarını yönettim.
- Açık kaynak sentence-transformers ve transformers modelleriyle OpenAI API kullanmadan belgeye dayalı cevap üretim akışı oluşturdum.

## Önemli notlar

- Bu proje MVP seviyesinde tamamlanmış çalışır bir temel sistemdir.
- Büyük dosyalar ve çok yüksek trafik için production ortamında queue sistemi, object storage, pgvector/ChromaDB/Qdrant ve async processing eklenmesi önerilir.
- Hassas belgeler için production ortamında dosya şifreleme, audit log ve daha detaylı yetki modeli eklenmelidir.
