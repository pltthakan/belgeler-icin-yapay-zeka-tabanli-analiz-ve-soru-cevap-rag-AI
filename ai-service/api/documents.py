from __future__ import annotations

from fastapi import APIRouter, File, Form, Request, UploadFile
from starlette.concurrency import run_in_threadpool

from app.dependencies import error_response, get_rag_engine
from app.schemas import InMemoryUpload

router = APIRouter()


@router.post("/api/ingest")
async def ingest(
    request: Request,
    document_id: str | None = Form(default=None, alias="documentId"),
    owner_id: str | None = Form(default=None, alias="ownerId"),
    department_id: str | None = Form(default=None, alias="departmentId"),
    file: UploadFile | None = File(default=None),
):
    if not document_id:
        return error_response("documentId zorunludur.", 400)
    if file is None:
        return error_response("file zorunludur.", 400)

    rag_engine = get_rag_engine(request)
    try:
        upload = InMemoryUpload(
            filename=file.filename or "document",
            content=await file.read(),
        )
        return await run_in_threadpool(
            rag_engine.ingest_document,
            document_id=document_id,
            file_storage=upload,
            owner_id=owner_id,
            department_id=department_id,
        )
    except Exception as exc:
        return error_response(str(exc), 500)
    finally:
        await file.close()


@router.delete("/api/index/{document_id}")
async def delete_index(request: Request, document_id: str):
    rag_engine = get_rag_engine(request)
    try:
        await run_in_threadpool(rag_engine.delete_document, document_id)
        return {"documentId": document_id, "deleted": True}
    except Exception as exc:
        return error_response(str(exc), 500)
