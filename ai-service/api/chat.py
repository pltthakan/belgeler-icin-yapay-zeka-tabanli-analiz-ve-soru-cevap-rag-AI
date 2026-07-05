from __future__ import annotations

from fastapi import APIRouter, Request
from starlette.concurrency import run_in_threadpool

from app.dependencies import error_response, get_rag_engine

router = APIRouter()


@router.post("/api/ask")
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

    rag_engine = get_rag_engine(request)
    try:
        return await run_in_threadpool(
            rag_engine.answer_question,
            document_id=document_id,
            question=question,
            top_k=top_k,
        )
    except FileNotFoundError:
        return error_response("Bu belge için vektör indeksi bulunamadı.", 404)
    except Exception as exc:
        return error_response(str(exc), 500)
