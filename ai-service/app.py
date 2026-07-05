"""Compatibility entrypoint for direct `uvicorn app:app` usage."""

from app.main import DATA_DIR, app, create_app, rag_engine

__all__ = ["DATA_DIR", "app", "create_app", "rag_engine"]


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=5000)
