"""FastAPI application factory."""
from __future__ import annotations

import logging
import mimetypes
import secrets
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
from .api import calculators, convert, diagnostics, documents, entities, entities_edit, exports, lan, search, system
from .config import get_settings
from .db import init_db
from .ingest import inbox

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logging.getLogger("httpx2").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)

# Not in Python's table on every OS; a phone will not offer "Add to Home Screen"
# for a manifest served as octet-stream.
mimetypes.add_type("application/manifest+json", ".webmanifest")


def add_access_control(app: FastAPI) -> None:
    """Ask anything that is not this computer for the pairing key.

    Only in force when a key is configured, which the desktop launcher does
    when it serves the app on the local network for a phone. The dev server
    and the Docker image have no key and stay open, as before. Everything
    outside `/api/` - the page itself, its assets, the icons - is served
    without a key, because the phone has to load the page in order to pair.
    """

    @app.middleware("http")
    async def access_control(request, call_next):
        key = get_settings().access_key
        path = request.url.path
        if key and path.startswith("/api/") and path != "/api/pair" and not lan.is_loopback(request):
            offered = request.headers.get(lan.KEY_HEADER) or request.cookies.get(lan.PAIR_COOKIE) or ""
            if not secrets.compare_digest(offered, key):
                return JSONResponse({"detail": lan.PAIR_MESSAGE}, status_code=401)
        return await call_next(request)


def create_app() -> FastAPI:
    settings = get_settings()
    init_db()
    app = FastAPI(title="Marine Electrical Document Intelligence", version=__version__)
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
    add_access_control(app)
    for r in (documents.router, entities.router, entities_edit.router, search.router, calculators.router, exports.router, convert.router, diagnostics.router, lan.router, system.router):
        app.include_router(r)
    if settings.inbox_watcher:
        inbox.start_watcher()

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
