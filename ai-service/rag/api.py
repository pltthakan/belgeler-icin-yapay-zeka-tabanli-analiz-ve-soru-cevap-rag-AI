"""Backward-compatible imports for the FastAPI application."""

from app.main import DATA_DIR, app, create_app, rag_engine
from app.schemas import InMemoryUpload
from app.dependencies import error_response

__all__ = ["DATA_DIR", "InMemoryUpload", "app", "create_app", "error_response", "rag_engine"]
