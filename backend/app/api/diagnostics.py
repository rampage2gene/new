"""Diagnostics: what the app is, where its files are, and what the log says.

The desktop app has no console, so when something goes wrong the only evidence
is the rotating log the launcher writes. These two endpoints put that evidence
behind the UI's Diagnostics page, which is a great deal easier to explain than
"open %LOCALAPPDATA% and find app.log". The app is single-user; a phone on the
same Wi-Fi reaches these the same way it reaches everything else, by having
been paired (`api/lan.py`).
"""
from __future__ import annotations

import platform
import shutil
import subprocess
import sys
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import __version__
from ..config import get_settings
from ..db import get_db
from ..models import Document

router = APIRouter(prefix="/api", tags=["diagnostics"])


def log_path() -> Path:
    """Where the launcher's rotating log lives (`setup_logging` in desktop/launcher.py)."""
    return get_settings().data_dir / "logs" / "app.log"


def _inbox_state() -> dict:
    """What the inbox folder is holding, so the app can say it out loud.

    A file the app cannot read is moved to `inbox/failed/` beside a
    `.error.txt` giving the reason. Nothing used to read that folder, so from
    the user's side the file simply vanished - on the very route the library
    recommends when drag-and-drop has already let them down.
    """
    from ..ingest.inbox import inbox_dir

    root = inbox_dir()
    failed: list[dict] = []
    try:
        for note in sorted((root / "failed").glob("*.error.txt")):
            reason = note.read_text(encoding="utf-8", errors="replace").strip().splitlines()
            failed.append({"name": note.name[: -len(".error.txt")], "reason": reason[0] if reason else "no reason recorded"})
    except OSError:  # the folder is only created on first use
        pass
    try:
        waiting = sum(1 for p in root.glob("*") if p.is_file())
    except OSError:
        waiting = 0
    return {"folder": str(root), "waiting": waiting, "failed": failed}


def _tesseract() -> tuple[str | None, str | None]:
    exe = shutil.which("tesseract")
    if not exe:
        return None, None
    try:
        out = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=10)
        first = (out.stdout or out.stderr or "").splitlines()
        return exe, first[0].strip() if first else None
    except (OSError, subprocess.SubprocessError):
        return exe, None


@router.get("/diagnostics")
def diagnostics(db: Session = Depends(get_db)) -> dict:
    from ..ai.client import ai_available
    from ..ocr.engine import engine_status, get_ocr_engine
    from ..search.semantic import get_embedding_provider

    s = get_settings()
    path = log_path()
    exe, version = _tesseract()
    counts = dict(db.execute(select(Document.status, func.count()).group_by(Document.status)).all())
    return {
        "version": __version__,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "python": sys.version.split()[0],
        "frozen": bool(getattr(sys, "frozen", False)),
        "data_dir": str(s.data_dir),
        "log_path": str(path),
        "log_exists": path.exists(),
        "log_size": path.stat().st_size if path.exists() else 0,
        "ocr_engine": get_ocr_engine().name,
        "ocr_engines": engine_status(),
        "exports_dir": str(s.exports_dir),
        "inbox": _inbox_state(),
        "tesseract_path": exe,
        "tesseract_version": version,
        "ai_available": ai_available(),
        "ai_model": s.ai_model if ai_available() else None,
        "embedding_provider": get_embedding_provider().name,
        "max_upload_mb": s.max_upload_mb,
        "phone_access": bool(s.lan),
        "phone_key_required": bool(s.access_key),
        "documents": {
            "total": sum(counts.values()),
            "ready": counts.get("ready", 0),
            "failed": counts.get("failed", 0),
        },
    }


@router.get("/logs", response_class=PlainTextResponse)
def logs(tail: int = Query(500, ge=1, le=5000)) -> str:
    """The last `tail` lines of the app log, as plain text to paste into a bug report."""
    path = log_path()
    if not path.exists():
        raise HTTPException(404, f"No log file at {path}. It is written by the desktop app; a development server logs to the console instead.")
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        lines = fh.readlines()
    return "".join(lines[-tail:])
