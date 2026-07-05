from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse


def get_rag_engine(request: Request):
    return request.app.state.rag_engine


def error_response(message: str, status_code: int) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"message": message})
