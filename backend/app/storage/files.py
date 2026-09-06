"""Filesystem storage for originals and rendered page images."""
from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

from ..config import get_settings


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def store_original(document_id: str, source: Path, filename: str) -> Path:
    s = get_settings()
    suffix = Path(filename).suffix.lower() or ".bin"
    dest_dir = s.originals_dir / document_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"original{suffix}"
    shutil.copyfile(source, dest)
    return dest


def page_image_path(document_id: str, page_number: int) -> Path:
    s = get_settings()
    d = s.pages_dir / document_id
    d.mkdir(parents=True, exist_ok=True)
    return d / f"page-{page_number:04d}.png"


def delete_document_files(document_id: str) -> None:
    s = get_settings()
    for d in (s.originals_dir / document_id, s.pages_dir / document_id):
        if d.exists():
            shutil.rmtree(d, ignore_errors=True)
