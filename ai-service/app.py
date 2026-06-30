import os
from dataclasses import dataclass

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from rag_engine import RagEngine


app = FastAPI(title="Private Document RAG AI Service")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DATA_DIR = os.getenv("DATA_DIR", "./data")
rag_engine = RagEngine(data_dir=DATA_DIR)


@dataclass
class InMemoryUpload:
    filename: str
    content: bytes

    def read(self) -> bytes:
        return self.content


def error_response(message: str, status_code: int) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"message": message})


@app.get("/api/health")
def health():
    return {
        "status": "UP",
        "service": "private-document-rag-ai-service",
        "embeddingModel": rag_engine.embedding_model_name,
        "qaModel": rag_engine.qa_model_name,
        "localLlmEnabled": bool(rag_engine.ollama_base_url and rag_engine.ollama_model),
        "vectorStore": "pgvector" if rag_engine._vector_store is not None else "json-fallback",
        "cache": rag_engine.cache_status(),
    }


@app.post("/api/ingest")
async def ingest(
    document_id: str | None = Form(default=None, alias="documentId"),
    owner_id: str | None = Form(default=None, alias="ownerId"),
    department_id: str | None = Form(default=None, alias="departmentId"),
    file: UploadFile | None = File(default=None),
):
    if not document_id:
        return error_response("documentId zorunludur.", 400)
    if file is None:
        return error_response("file zorunludur.", 400)

    try:
        upload = InMemoryUpload(
            filename=file.filename or "document",
            content=await file.read(),
        )
        result = await run_in_threadpool(
            rag_engine.ingest_document,
            document_id=document_id,
            file_storage=upload,
            owner_id=owner_id,
            department_id=department_id,
        )
        return result
    except Exception as exc:
        return error_response(str(exc), 500)
    finally:
        await file.close()


@app.post("/api/ask")
async def ask(request: Request):
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}

    document_id = payload.get("documentId")
    question = payload.get("question")
    try:
        top_k = int(payload.get("topK") or 4)
    except (TypeError, ValueError):
        return error_response("topK geçerli bir sayı olmalıdır.", 400)

    if not document_id:
        return error_response("documentId zorunludur.", 400)
    if not question:
        return error_response("question zorunludur.", 400)

    try:
        result = await run_in_threadpool(
            rag_engine.answer_question,
            document_id=document_id,
            question=question,
            top_k=top_k,
        )
        return result
    except FileNotFoundError:
        return error_response("Bu belge için vektör indeksi bulunamadı.", 404)
    except Exception as exc:
        return error_response(str(exc), 500)


@app.delete("/api/index/{document_id}")
async def delete_index(document_id: str):
    try:
        await run_in_threadpool(rag_engine.delete_document, document_id)
        return {"documentId": document_id, "deleted": True}
    except Exception as exc:
        return error_response(str(exc), 500)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=5000)
