from __future__ import annotations

from fastapi import APIRouter, Request

from app.dependencies import get_rag_engine

router = APIRouter()


@router.get("/api/health")
def health(request: Request):
    rag_engine = get_rag_engine(request)
    return {
        "status": "UP",
        "service": "private-document-rag-ai-service",
        "embeddingModel": rag_engine.embedding_model_name,
        "qaModel": rag_engine.qa_model_name,
        "localLlmEnabled": bool(rag_engine.ollama_base_url and rag_engine.ollama_model),
        "vectorStore": "pgvector" if rag_engine._vector_store is not None else "json-fallback",
        "cache": rag_engine.cache_status(),
        "reranker": rag_engine.reranker_status(),
    }
