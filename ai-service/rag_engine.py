import io
import json
import math
import os
import re
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

        answer = self._build_answer(question, selected_sources)
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

    def _build_answer(self, question: str, sources: List[Dict[str, Any]]) -> str:
        if not sources:
            return "Bu belge içinde soruyla ilişkili bir bölüm bulunamadı."

        context = "\n\n".join(source["text"] for source in sources)
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
                return (
                    "Belgedeki ilgili bölümlere göre cevap: "
                    f"{best_answer}\n\n"
                    "Not: Cevap, aşağıdaki kaynak parçalar kullanılarak üretildi."
                )

        # Fallback cevap: en alakalı kaynak parçasından kısa belgeye dayalı özet.
        best_text = sources[0]["text"]
        short_text = self._shorten(best_text, max_chars=900)
        return (
            "Belgedeki en alakalı bölüm şu bilgiyi veriyor:\n\n"
            f"{short_text}\n\n"
            "Bu cevap doğrudan belge parçalarına dayalıdır. Daha net sonuç için soruyu daha spesifik sorabilirsin."
        )

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
