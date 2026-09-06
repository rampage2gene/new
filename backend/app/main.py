"""FastAPI application factory."""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
from .api import calculators, convert, diagnostics, documents, entities, exports, search
from .config import get_settings
from .db import init_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logging.getLogger("httpx2").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)


def create_app() -> FastAPI:
    settings = get_settings()
    init_db()
    app = FastAPI(title="Marine Electrical Document Intelligence", version=__version__)
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
    for r in (documents.router, entities.router, search.router, calculators.router, exports.router, convert.router, diagnostics.router):
        app.include_router(r)

    dist = Path(settings.frontend_dist)
    if dist.exists() and (dist / "index.html").exists():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        def spa(full_path: str):
            candidate = dist / full_path
            if full_path and candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(dist / "index.html")

    else:

        @app.get("/", include_in_schema=False)
        def root():
            return JSONResponse({"message": "Marine Electrical Document Intelligence API. Build the frontend (cd frontend && npm run build) to serve the UI here.", "docs": "/docs"})

    return app


app = create_app()
