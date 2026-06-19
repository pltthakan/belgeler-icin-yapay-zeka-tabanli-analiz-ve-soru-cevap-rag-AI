import io
import json
import math
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np
from docx import Document as DocxDocument
from pypdf import PdfReader
from sklearn.feature_extraction.text import HashingVectorizer


class RagEngine:
    def __init__(self, data_dir: str):
        self.data_dir = Path(data_dir)
        self.index_dir = self.data_dir / "indexes"
        self.index_dir.mkdir(parents=True, exist_ok=True)

        self.embedding_model_name = os.getenv(
            "EMBEDDING_MODEL_NAME",
            "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        )
        self.qa_model_name = os.getenv(
            "QA_MODEL_NAME",
            "deepset/xlm-roberta-base-squad2",
        )
        self.disable_qa_model = os.getenv("DISABLE_QA_MODEL", "false").lower() == "true"

        # Ollama isteğe bağlıdır. Değişkenler ayarlanmadığında her soru için
        # yerel modele bağlanmayı denemeden QA fallback ile devam edilir.
        self.ollama_base_url = os.getenv("OLLAMA_BASE_URL", "").rstrip("/")
        self.ollama_model = os.getenv("OLLAMA_MODEL", "").strip()
        self.ollama_timeout_seconds = float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "30"))

        self._embedding_model = None
        self._qa_pipeline = None
        self._hashing_vectorizer = HashingVectorizer(
            n_features=384,
            alternate_sign=False,
            norm="l2",
            lowercase=True,
        )

    def ingest_document(self, document_id: str, file_storage) -> Dict[str, Any]:
        filename = file_storage.filename or "document"
        raw_bytes = file_storage.read()

        pages = self._extract_pages(filename=filename, raw_bytes=raw_bytes)
        chunks = self._chunk_pages(pages)
        if not chunks:
            raise ValueError("Belgeden okunabilir metin çıkarılamadı.")

        texts = [chunk["text"] for chunk in chunks]
        embeddings = self._embed_texts(texts)

        index_payload = {
            "documentId": document_id,
            "filename": filename,
            "chunkCount": len(chunks),
            "chunks": chunks,
            "embeddings": embeddings.tolist(),
        }

        index_path = self._index_path(document_id)
        index_path.write_text(json.dumps(index_payload, ensure_ascii=False), encoding="utf-8")

        return {
            "documentId": document_id,
            "chunkCount": len(chunks),
            "message": "Belge başarıyla işlendi.",
        }

    def answer_question(self, document_id: str, question: str, top_k: int = 4) -> Dict[str, Any]:
        index = self._load_index(document_id)
        chunks = index["chunks"]
        embeddings = np.array(index["embeddings"], dtype=np.float32)

        question_embedding = self._embed_texts([question])[0]
        scores = embeddings @ question_embedding
        top_indices = np.argsort(scores)[::-1][:max(top_k, 1)]

        selected_sources = []
        for idx in top_indices:
            chunk = chunks[int(idx)]
            selected_sources.append({
                "pageNumber": chunk.get("pageNumber"),
                "chunkIndex": chunk.get("chunkIndex"),
                "score": float(scores[int(idx)]),
                "text": chunk.get("text", ""),
            })

        answer = self._build_answer(question, selected_sources, chunks)
        return {
            "answer": answer,
            "sources": selected_sources,
        }

    def _extract_pages(self, filename: str, raw_bytes: bytes) -> List[Dict[str, Any]]:
        lower = filename.lower()
        if lower.endswith(".pdf"):
            return self._extract_pdf_pages(raw_bytes)
        if lower.endswith(".docx"):
            return self._extract_docx_pages(raw_bytes)
        if lower.endswith(".txt"):
            text = raw_bytes.decode("utf-8", errors="ignore")
            return [{"pageNumber": 1, "text": self._clean_text(text)}]
        raise ValueError("Desteklenmeyen dosya tipi. PDF, DOCX veya TXT yükleyin.")

    def _extract_pdf_pages(self, raw_bytes: bytes) -> List[Dict[str, Any]]:
        reader = PdfReader(io.BytesIO(raw_bytes))
        pages = []
        for i, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            cleaned = self._clean_text(text)
            if cleaned:
                pages.append({"pageNumber": i, "text": cleaned})
        return pages

    def _extract_docx_pages(self, raw_bytes: bytes) -> List[Dict[str, Any]]:
        document = DocxDocument(io.BytesIO(raw_bytes))
        paragraphs = [p.text for p in document.paragraphs if p.text and p.text.strip()]
        text = self._clean_text("\n".join(paragraphs))
        return [{"pageNumber": 1, "text": text}] if text else []

    def _chunk_pages(self, pages: List[Dict[str, Any]], chunk_size: int = 1200, overlap: int = 200) -> List[Dict[str, Any]]:
        chunks = []
        chunk_index = 0
        for page in pages:
            text = page["text"]
            start = 0
            while start < len(text):
                end = min(start + chunk_size, len(text))
                piece = text[start:end]
                if len(piece.strip()) >= 80:
                    chunks.append({
                        "chunkIndex": chunk_index,
                        "pageNumber": page["pageNumber"],
                        "text": piece.strip(),
                    })
                    chunk_index += 1
                if end >= len(text):
                    break
                start = max(0, end - overlap)
        return chunks

    def _embed_texts(self, texts: List[str]) -> np.ndarray:
        model = self._get_embedding_model()
        if model is not None:
            vectors = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
            return np.array(vectors, dtype=np.float32)

        # Fallback: açık kaynak model indirilemezse hashing tabanlı vektörleme.
        vectors = self._hashing_vectorizer.transform(texts).toarray()
        return np.array(vectors, dtype=np.float32)

    def _get_embedding_model(self):
        if self._embedding_model is not None:
            return self._embedding_model
        try:
            from sentence_transformers import SentenceTransformer
            self._embedding_model = SentenceTransformer(self.embedding_model_name)
            return self._embedding_model
        except Exception as exc:
            print(f"Embedding modeli yüklenemedi, HashingVectorizer fallback kullanılacak: {exc}")
            self._embedding_model = None
            return None

    def _get_qa_pipeline(self):
        if self.disable_qa_model:
            return None
        if self._qa_pipeline is not None:
            return self._qa_pipeline
        try:
            from transformers import pipeline
            self._qa_pipeline = pipeline("question-answering", model=self.qa_model_name, tokenizer=self.qa_model_name)
            return self._qa_pipeline
        except Exception as exc:
            print(f"QA modeli yüklenemedi, kaynak özet fallback kullanılacak: {exc}")
            self._qa_pipeline = None
            return None

    def _build_answer(
        self,
        question: str,
        sources: List[Dict[str, Any]],
        all_chunks: List[Dict[str, Any]],
    ) -> str:
        if not sources:
            return "Bu belge içinde soruyla ilişkili bir bölüm bulunamadı."

        # "Ana konusu nedir?" bir span-extraction sorusu değildir. Retrieval ile
        # gelen son sayfadaki bir anket sorusunu döndürmek yerine belge başlığını
        # kullanmak, modelin yüklenemediği ortamlarda da kararlı sonuç verir.
        if self._is_topic_question(question):
            topic = self._extract_document_topic(all_chunks)
            if topic:
                return f"Bu belgenin ana konusu: {topic}."

        generated_answer = self._answer_with_ollama(question, sources)
        if generated_answer:
            return generated_answer

        qa_pipeline = self._get_qa_pipeline()
        if qa_pipeline is not None:
            best_answer = None
            best_score = -1.0
            for source in sources:
                try:
                    result = qa_pipeline(question=question, context=source["text"])
                    score = float(result.get("score", 0.0))
                    answer = str(result.get("answer", "")).strip()
                    if answer and score > best_score:
                        best_score = score
                        best_answer = answer
                except Exception:
                    continue

            if best_answer and best_score >= 0.02:
                return f"Belgeye göre: {best_answer}"

        # Model kullanılamadığında ham 900 karakterlik chunk döndürmek yerine,
        # soruyla en fazla kesişen kısa cümleleri seç.
        short_text = self._extract_relevant_passage(question, sources[0]["text"])
        return f"Belgeye göre: {short_text}"

    def _is_topic_question(self, question: str) -> bool:
        normalized = self._normalize_for_matching(question)
        markers = (
            "ana konusu",
            "ana konu",
            "belgenin konusu",
            "dokumanin konusu",
            "ne hakkında",
            "konusu nedir",
            "genel konusu",
        )
        return any(marker in normalized for marker in markers)

    def _extract_document_topic(self, chunks: List[Dict[str, Any]]) -> str | None:
        """Belge başındaki en anlamlı başlığı, ana konu soruları için döndürür."""
        if not chunks:
            return None

        opening_text = chunks[0].get("text", "")
        lines = [self._normalize_whitespace(line) for line in opening_text.splitlines()]
        candidates = [
            line for line in lines
            if 12 <= len(line) <= 280 and self._contains_letters(line)
        ]
        if not candidates and opening_text:
            first_sentence = re.split(r"(?<=[.!?])\s+", opening_text, maxsplit=1)[0]
            candidates = [self._normalize_whitespace(first_sentence)]

        # Birçok kurumsal belgede üst bilgi, ders/alan adı ve gerçek belge başlığı
        # ayrı satırlarda yazılır. Örneğin "... EĞİTİM DERSİ" + "... ANKETİ".
        # Başlık türünü içeren satırı ve gerekiyorsa hemen önceki üst başlığı birlikte
        # döndürmek, kurum adını tek başına konu diye göstermeyi engeller.
        heading_lines = []
        for candidate in candidates[:6]:
            if self._looks_like_heading(candidate):
                heading_lines.append(candidate)
            elif heading_lines:
                break

        title_markers = (
            "anket", "form", "rapor", "sozlesme", "şartname", "sartname",
            "kilavuz", "kılavuz", "yonerge", "yönerge", "prosedur", "prosedür",
            "politika", "talimat",
        )
        for index, candidate in enumerate(heading_lines):
            normalized = self._normalize_for_matching(candidate)
            if any(marker in normalized for marker in title_markers):
                title_parts = heading_lines[max(0, index - 1):index + 1]
                return " — ".join(part.rstrip(".:") for part in title_parts)

        for candidate in candidates:
            # Formlarda başlığın hemen altındaki "öğrenci bilgileri" gibi bölüm
            # adlarını değil, belgenin gerçek üst başlığını tercih et.
            if self._normalize_for_matching(candidate) not in {"ogrenci bilgileri", "icerindekiler"}:
                return candidate.rstrip(".:")
        return None

    def _answer_with_ollama(self, question: str, sources: List[Dict[str, Any]]) -> str | None:
        """Yapılandırılmışsa kaynaklarla sınırlı bir Ollama cevabı üretir."""
        if not self.ollama_base_url or not self.ollama_model:
            return None

        context_parts = []
        for position, source in enumerate(sources, start=1):
            context_parts.append(f"KAYNAK {position}:\n{source.get('text', '')}")
        context = "\n\n---\n\n".join(context_parts)
        prompt = f"""Sen, yalnızca verilen belge parçalarına göre cevap veren Türkçe bir belge asistanısın.
Kurallar:
- Sadece BELGE BAĞLAMI'ndaki bilgiye dayan; bağlamda yoksa bunu açıkça belirt.
- Soruyu doğrudan, en fazla 3 kısa cümleyle cevapla.
- Ham kaynak metnini veya 'Kaynak 1' ifadelerini tekrar etme.
- Varsayım, uydurma bilgi ve genel tavsiye ekleme.

SORU:
{question}

BELGE BAĞLAMI:
{context}

CEVAP:"""
        payload = json.dumps({
            "model": self.ollama_model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.1},
        }).encode("utf-8")
        request = urllib.request.Request(
            f"{self.ollama_base_url}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.ollama_timeout_seconds) as response:
                result = json.loads(response.read().decode("utf-8"))
            answer = str(result.get("response", "")).strip()
            return answer or None
        except (urllib.error.URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
            print(f"Ollama cevabı alınamadı, QA fallback kullanılacak: {exc}")
            return None

    def _extract_relevant_passage(self, question: str, text: str) -> str:
        sentences = [
            self._normalize_whitespace(sentence)
            for sentence in re.split(r"(?<=[.!?])\s+|\n+", text)
            if self._normalize_whitespace(sentence)
        ]
        if not sentences:
            return self._shorten(text, max_chars=450)

        question_terms = self._meaningful_terms(question)
        scored = []
        for index, sentence in enumerate(sentences):
            sentence_terms = set(self._meaningful_terms(sentence))
            overlap = len(question_terms & sentence_terms)
            scored.append((overlap, -index, sentence))

        matching = [item for item in scored if item[0] > 0]
        if not matching:
            return self._shorten(sentences[0], max_chars=450)

        best = sorted(matching, reverse=True)[:2]
        selected = sorted(best, key=lambda item: -item[1])
        return self._shorten(" ".join(item[2] for item in selected), max_chars=550)

    def _meaningful_terms(self, text: str) -> set[str]:
        stop_words = {
            "acaba", "ama", "bir", "bu", "bunu", "da", "de", "gibi", "icin", "ile",
            "mi", "mı", "mu", "mü", "nasıl", "ne", "nedir", "olan", "olarak", "soru",
            "su", "şu", "ve", "veya", "ya", "belge", "belgede", "belgenin", "dokuman", "dokumanda",
        }
        return {
            term for term in re.findall(r"[a-zçğıöşü0-9]+", self._normalize_for_matching(text))
            if len(term) > 2 and term not in stop_words
        }

    def _normalize_for_matching(self, text: str) -> str:
        # Türkçe I/İ dönüşümünü lower() tek başına düzgün normalize etmez.
        return text.replace("I", "ı").replace("İ", "i").lower()

    def _normalize_whitespace(self, text: str) -> str:
        return re.sub(r"\s+", " ", text).strip()

    def _contains_letters(self, text: str) -> bool:
        return bool(re.search(r"[A-Za-zÇĞİÖŞÜçğıöşü]", text))

    def _looks_like_heading(self, text: str) -> bool:
        letters = re.findall(r"[A-Za-zÇĞİÖŞÜçğıöşü]", text)
        if not letters or "?" in text:
            return False
        uppercase_letters = [letter for letter in letters if letter.isupper()]
        return len(uppercase_letters) / len(letters) >= 0.7

    def _load_index(self, document_id: str) -> Dict[str, Any]:
        index_path = self._index_path(document_id)
        if not index_path.exists():
            raise FileNotFoundError(index_path)
        return json.loads(index_path.read_text(encoding="utf-8"))

    def _index_path(self, document_id: str) -> Path:
        safe_id = re.sub(r"[^a-zA-Z0-9_-]", "_", str(document_id))
        return self.index_dir / f"{safe_id}.json"

    def _clean_text(self, text: str) -> str:
        text = text.replace("\x00", " ")
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def _trim_to_sentence(self, text: str) -> str:
        text = text.strip()
        if len(text) < 300:
            return text
        candidates = [text.rfind(". "), text.rfind("? "), text.rfind("! "), text.rfind("\n")]
        cut = max(candidates)
        if cut > int(len(text) * 0.55):
            return text[:cut + 1]
        return text

    def _shorten(self, text: str, max_chars: int) -> str:
        text = text.strip()
        if len(text) <= max_chars:
            return text
        shortened = text[:max_chars]
        cut = max(shortened.rfind(". "), shortened.rfind("\n"))
        if cut > 300:
            shortened = shortened[:cut + 1]
        return shortened.strip() + "..."
