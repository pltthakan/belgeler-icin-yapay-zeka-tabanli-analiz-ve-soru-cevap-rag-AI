from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict

import numpy as np
from sklearn.feature_extraction.text import HashingVectorizer

from app.cache import RagCache
from app.cache_helpers import CacheMixin
from app.config import SettingsMixin
from app.text_utils import TextUtilitiesMixin
from chunking.heading_chunker import HeadingChunkerMixin
from chunking.semantic_chunker import SemanticChunkerMixin
from embeddings.embedding_model import EmbeddingModelMixin
from embeddings.embedding_service import EmbeddingServiceMixin
from generation.answer_service import AnswerServiceMixin
from generation.extractive_fallback import ExtractiveFallbackMixin
from generation.ollama_client import OllamaClientMixin
from generation.qa_answerer import QaAnswererMixin
from guardrails.claim_validator import ClaimValidatorMixin
from guardrails.output_guard import OutputGuardMixin
from guardrails.retrieval_guard import RetrievalGuardMixin
from ingestion.document_parser import DocumentParserMixin
from ingestion.document_profiler import DocumentProfileMixin
from ingestion.docx_parser import DocxParserMixin
from ingestion.pdf_parser import PdfParserMixin
from ingestion.text_parser import TextParserMixin
from observability.tracing import TracingMixin
from retrieval.hybrid_retriever import HybridRetrieverMixin
from retrieval.pgvector_store import PgVectorStore
from retrieval.reranker import RerankerMixin
from retrieval.source_selector import OrderSensitiveAnswerMixin, QueryAnalysisMixin


class RagEngine(
    CacheMixin,
    QueryAnalysisMixin,
    DocumentParserMixin,
    PdfParserMixin,
    DocxParserMixin,
    TextParserMixin,
    HeadingChunkerMixin,
    SemanticChunkerMixin,
    HybridRetrieverMixin,
    RerankerMixin,
    EmbeddingServiceMixin,
    EmbeddingModelMixin,
    AnswerServiceMixin,
    QaAnswererMixin,
    OllamaClientMixin,
    ExtractiveFallbackMixin,
    OrderSensitiveAnswerMixin,
    RetrievalGuardMixin,
    ClaimValidatorMixin,
    OutputGuardMixin,
    DocumentProfileMixin,
    TracingMixin,
    TextUtilitiesMixin,
    SettingsMixin,
):
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
        self.reranker_enabled = os.getenv("RERANKER_ENABLED", "true").lower() == "true"
        self.reranker_model_name = os.getenv(
            "RERANKER_MODEL_NAME",
            "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1",
        )
        self.reranker_candidate_count = self._read_int_env("RERANKER_CANDIDATE_COUNT", 20, minimum=4, maximum=50)
        # Vektör araması her sorgu için teknik olarak bir sonuç döndürebilir.
        # Düşük skorlu sonuçları LLM'e göndermemek hem halüsinasyonu hem de
        # anlamsız sorulardaki gereksiz beklemeyi engeller.
        self.min_retrieval_score = self._read_retrieval_score_threshold()
        self.pgvector_dsn = os.getenv("PGVECTOR_DSN", "").strip()
        self._vector_store = PgVectorStore(self.pgvector_dsn) if self.pgvector_dsn else None
        self.cache = RagCache()

        self._embedding_model = None
        self._qa_pipeline = None
        self._reranker_model = None
        self._reranker_error_logged = False
        self._hashing_vectorizer = HashingVectorizer(
            n_features=384,
            alternate_sign=False,
            norm="l2",
            lowercase=True,
        )

    def ingest_document(
        self,
        document_id: str,
        file_storage,
        owner_id: str | None = None,
        department_id: str | None = None,
    ) -> Dict[str, Any]:
        filename = file_storage.filename or "document"
        raw_bytes = file_storage.read()

        pages = self._extract_pages(filename=filename, raw_bytes=raw_bytes)
        chunks = self._chunk_pages(pages)
        if not chunks:
            raise ValueError("Belgeden okunabilir metin çıkarılamadı.")

        texts = [chunk["text"] for chunk in chunks]
        embeddings = self._embed_texts(texts)
        document_profile = self._build_document_profile(chunks)

        if self._vector_store is not None:
            self._vector_store.replace_document(
                document_id=document_id,
                filename=filename,
                owner_id=owner_id,
                department_id=department_id,
                chunks=chunks,
                embeddings=embeddings,
                profile=document_profile,
            )
            self._invalidate_document_cache(document_id)
        else:
            # PGVECTOR_DSN ayarlanmamış yerel geliştirme ortamları için eski
            # dosya tabanlı indeks yalnızca uyumluluk fallback'i olarak kalır.
            index_payload = {
                "documentId": document_id,
                "filename": filename,
                "chunkCount": len(chunks),
                "chunks": chunks,
                "embeddings": embeddings.tolist(),
                "documentProfile": document_profile,
            }
            index_path = self._index_path(document_id)
            temporary_index_path = index_path.with_suffix(".tmp")
            temporary_index_path.write_text(json.dumps(index_payload, ensure_ascii=False), encoding="utf-8")
            temporary_index_path.replace(index_path)
            self._invalidate_document_cache(document_id)

        return {
            "documentId": document_id,
            "chunkCount": len(chunks),
            "message": "Belge başarıyla işlendi.",
        }

    def answer_question(self, document_id: str, question: str, top_k: int = 4) -> Dict[str, Any]:
        started_at = time.perf_counter()
        retrieval_question = self._normalize_question_for_retrieval(question)
        if self._vector_store is not None:
            index_version = self._vector_store.get_profile_version(document_id)
            if index_version is not None:
                cached_result = self._get_cached_answer(
                    document_id=document_id,
                    question=question,
                    top_k=top_k,
                    index_version=index_version,
                    started_at=started_at,
                )
                if cached_result is not None:
                    return cached_result

                profile_record = self._get_cached_profile_record(document_id, index_version)
                if profile_record is None:
                    raise FileNotFoundError("Bu belge için vektör indeksi bulunamadı.")

                result = self._answer_question_from_pgvector(
                    document_id=document_id,
                    question=question,
                    retrieval_question=retrieval_question,
                    top_k=top_k,
                    document_profile=profile_record["profile"],
                    started_at=started_at,
                )
                self._cache_answer(
                    document_id=document_id,
                    question=question,
                    top_k=top_k,
                    index_version=index_version,
                    result=result,
                )
                return result

        index = self._load_index(document_id)
        chunks = index["chunks"]
        embeddings = np.array(index["embeddings"], dtype=np.float32)
        document_profile = index.get("documentProfile") or self._build_document_profile(chunks)
        index_version = self._json_index_version(document_id)

        cached_result = self._get_cached_answer(
            document_id=document_id,
            question=question,
            top_k=top_k,
            index_version=index_version,
            started_at=started_at,
        )
        if cached_result is not None:
            return cached_result

        ordered_result = self._answer_order_sensitive_question(
            question=question,
            chunks=[self._source_from_chunk(chunk, 1.0) for chunk in chunks],
            document_profile=document_profile,
            top_k=top_k,
            started_at=started_at,
        )
        if ordered_result is not None:
            self._cache_answer(document_id, question, top_k, index_version, ordered_result)
            return ordered_result

        question_embedding = self._embed_question(retrieval_question)
        scores = embeddings @ question_embedding

        if self._is_document_overview_question(question):
            # Belge-genel sorularda en benzer rastgele paragrafı değil, belgenin
            # başlangıcını ve yükleme sırasında çıkarılan profil bilgisini kullan.
            overview_indices = list(range(min(max(top_k, 1), len(chunks))))
            selected_sources = [self._source_from_chunk(chunks[index], 1.0) for index in overview_indices]
        else:
            selected_sources = self._hybrid_sources_from_memory(
                chunks=chunks,
                dense_scores=scores,
                question=retrieval_question,
                top_k=self._retrieval_candidate_count(top_k),
            )
            selected_sources = self._rerank_sources(retrieval_question, selected_sources, top_k)

        guard_result = self._relevance_guard_result(retrieval_question, selected_sources)
        if guard_result is not None:
            result = self._answer_result_from_guard(guard_result, started_at)
            self._cache_answer(document_id, question, top_k, index_version, result)
            return result

        answer, generation = self._build_answer_result(question, selected_sources, document_profile)
        result = {
            "answer": answer,
            "sources": selected_sources,
            "trace": self._build_trace(
                generation=generation,
                selected_sources=selected_sources,
                duration_ms=(time.perf_counter() - started_at) * 1000,
            ),
        }
        self._cache_answer(document_id, question, top_k, index_version, result)
        return result

    def delete_document(self, document_id: str) -> None:
        """Vektör verisini, ana belge silinmeden önce güvenli biçimde kaldırır."""
        if self._vector_store is not None:
            self._vector_store.delete_document(document_id)
            self._invalidate_document_cache(document_id)
            return
        self._index_path(document_id).unlink(missing_ok=True)
        self._invalidate_document_cache(document_id)

    def cache_status(self) -> Dict[str, Any]:
        return self.cache.status()

    def reranker_status(self) -> Dict[str, Any]:
        return {
            "enabled": self.reranker_enabled,
            "model": self.reranker_model_name if self.reranker_enabled else None,
            "candidateCount": self.reranker_candidate_count,
            "loaded": self._reranker_model is not None,
        }
