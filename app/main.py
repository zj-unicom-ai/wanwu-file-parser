"""FastAPI application entry point."""
from __future__ import annotations

from fastapi import FastAPI

from app.api import router, trace_id_middleware
from app.config import settings


def create_app() -> FastAPI:
    """Build the FastAPI app (used by uvicorn and tests)."""
    app = FastAPI(
        title="wanwu-file-parser",
        description="CPU-only document parsing dispatch service (FastAPI, MIT).",
        version="0.1.0",
    )
    app.middleware("http")(trace_id_middleware)
    app.include_router(router)
    return app


app = create_app()


def main() -> None:
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.app_host,
        port=settings.app_port,
        workers=settings.app_workers,
        reload=False,
    )


if __name__ == "__main__":
    main()
