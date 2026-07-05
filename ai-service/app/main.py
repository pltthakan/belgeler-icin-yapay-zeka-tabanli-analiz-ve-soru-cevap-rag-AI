from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.chat import router as chat_router
from api.documents import router as documents_router
from api.health import router as health_router
from app.config import DATA_DIR
from app.engine import RagEngine


def create_app(rag_engine: RagEngine | None = None, data_dir: str | None = None) -> FastAPI:
    engine = rag_engine or RagEngine(data_dir=data_dir or DATA_DIR)
    application = FastAPI(title="Private Document RAG AI Service")
    application.state.rag_engine = engine
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.include_router(health_router)
    application.include_router(documents_router)
    application.include_router(chat_router)
    return application


rag_engine = RagEngine(data_dir=DATA_DIR)
app = create_app(rag_engine=rag_engine)

__all__ = ["DATA_DIR", "app", "create_app", "rag_engine"]
